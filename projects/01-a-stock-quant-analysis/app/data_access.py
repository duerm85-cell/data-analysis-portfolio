"""Cached, parameterized SQLite reads for the public Streamlit application."""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd
import streamlit as st

from portfolio_config import DEMO_SERVING_DB_PATH


CATALOG_COLUMNS = (
    "code",
    "name",
    "market",
    "board",
    "industry_l1",
    "list_date",
    "is_demo",
    "has_detail",
    "source",
    "updated_at",
)
STOCK_HISTORY_COLUMNS = (
    "code",
    "date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "volume",
    "amount",
    "ret",
    "ret_5d",
    "ret_10d",
    "ma5",
    "ma10",
    "ma20",
    "ma60",
    "ma5_ma10_diff",
    "ma5_ma20_diff",
    "volatility_20d",
    "volatility_60d",
    "rsi",
    "macd",
    "macd_signal",
    "macd_hist",
    "volume_ma5",
    "volume_ratio",
    "volume_change",
    "amount_ma20",
    "amount_ratio",
    "momentum_20d",
    "momentum_60d",
    "reversal_5d",
    "reversal_20d",
    "bb_mid",
    "bb_upper",
    "bb_lower",
    "bb_width",
    "bb_position",
    "high_low_ratio",
    "close_open_ratio",
    "label",
    "sentiment",
    "sentiment_ma5",
    "sentiment_ma10",
    "comment_count",
    "sentiment_source",
    "data_version",
)

_CODE_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,20}$")


def _database_path(database_path: str | Path | None = None) -> Path:
    path = Path(database_path or DEMO_SERVING_DB_PATH).resolve()
    if not path.exists():
        raise FileNotFoundError(
            f"公开 SQLite 服务库不存在: {path}。"
            "请先运行 python scripts/build_demo_serving_db.py。"
        )
    return path


def _cache_key(database_path: str | Path | None = None) -> tuple[str, int, int]:
    path = _database_path(database_path)
    stat = path.stat()
    return str(path), stat.st_mtime_ns, stat.st_size


def _connect(database_path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(database_path).as_posix()}?mode=ro", uri=True)


def _read_frame(database_path: str, sql: str, params: tuple = ()) -> pd.DataFrame:
    conn = _connect(database_path)
    try:
        frame = pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()
    for column in ("date", "started_at", "finished_at", "updated_at", "data_date"):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def _validate_date(value: str | date | pd.Timestamp | None, name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValueError(f"{name} 必须是 YYYY-MM-DD 日期") from exc


def _validate_range(start_date, end_date) -> tuple[str | None, str | None]:
    start = _validate_date(start_date, "start_date")
    end = _validate_date(end_date, "end_date")
    if start and end and start > end:
        raise ValueError("start_date 不能晚于 end_date")
    return start, end


def _validate_code(code: str) -> str:
    value = str(code).strip()
    if not _CODE_PATTERN.fullmatch(value):
        raise ValueError("股票代码格式不合法")
    return value.zfill(6) if value.isdigit() else value


def _bounded_limit(value: int, *, maximum: int, name: str = "limit") -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} 必须是正整数")
    return min(value, maximum)


@st.cache_data(ttl=3600, max_entries=8, show_spinner=False)
def _get_manifest_cached(
    database_path: str, mtime_ns: int, database_size: int
) -> dict:
    frame = _read_frame(
        database_path,
        """
        SELECT run_id, pipeline_name, started_at, finished_at, status,
               input_rows, output_rows, data_start_date, data_end_date,
               source, data_version, mode, source_label, selection_rule,
               public_scope, disclaimer, database_path
        FROM pipeline_run
        WHERE status = ?
        ORDER BY finished_at DESC
        LIMIT ?
        """,
        ("SUCCESS", 1),
    )
    if frame.empty:
        return {}
    result = frame.iloc[0].to_dict()
    result["start_date"] = result.get("data_start_date")
    result["end_date"] = result.get("data_end_date")
    result["row_count"] = int(result.get("output_rows", 0))
    return result


def get_manifest(database_path: str | Path | None = None) -> dict:
    return _get_manifest_cached(*_cache_key(database_path))


@st.cache_data(ttl=3600, max_entries=8, show_spinner=False)
def _get_asset_summary_cached(
    database_path: str, mtime_ns: int, database_size: int
) -> dict:
    frame = _read_frame(
        database_path,
        """
        SELECT p.data_version, p.source_label, p.data_start_date, p.data_end_date,
               p.finished_at,
               (SELECT COUNT(1) FROM dim_stock) AS catalog_stock_count,
               (SELECT COUNT(1) FROM dim_stock WHERE has_detail = 1) AS detail_stock_count,
               (SELECT COUNT(1) FROM fact_stock_daily_demo) AS record_count,
               (SELECT COUNT(1) FROM fact_market_daily) AS trading_day_count,
               q.quality_score, q.status AS quality_status,
               q.duplicate_key_count, q.invalid_date_count,
               q.invalid_ohlc_count, q.unexpected_missing_count,
               q.column_count
        FROM pipeline_run AS p
        LEFT JOIN fact_data_quality_run AS q ON q.data_version = p.data_version
        WHERE p.status = ?
        ORDER BY p.finished_at DESC
        LIMIT ?
        """,
        ("SUCCESS", 1),
    )
    if frame.empty:
        return {}
    result = frame.iloc[0].to_dict()
    for key in (
        "catalog_stock_count",
        "detail_stock_count",
        "record_count",
        "trading_day_count",
        "duplicate_key_count",
        "invalid_date_count",
        "invalid_ohlc_count",
        "unexpected_missing_count",
        "column_count",
    ):
        result[key] = int(result.get(key, 0) or 0)
    return result


def get_asset_summary(database_path: str | Path | None = None) -> dict:
    return _get_asset_summary_cached(*_cache_key(database_path))


@st.cache_data(ttl=3600, max_entries=32, show_spinner=False)
def _get_stock_catalog_cached(
    database_path: str,
    mtime_ns: int,
    database_size: int,
    industry_l1: str | None,
    has_detail: int | None,
    limit: int,
) -> pd.DataFrame:
    conditions = []
    params: list = []
    if industry_l1:
        conditions.append("industry_l1 = ?")
        params.append(industry_l1)
    if has_detail is not None:
        conditions.append("has_detail = ?")
        params.append(has_detail)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    columns = ", ".join(CATALOG_COLUMNS)
    params.append(limit)
    return _read_frame(
        database_path,
        f"SELECT {columns} FROM dim_stock {where_clause} ORDER BY code LIMIT ?",
        tuple(params),
    )


def get_stock_catalog(
    industry_l1: str | None = None,
    has_detail: bool | None = None,
    limit: int = 6000,
    database_path: str | Path | None = None,
) -> pd.DataFrame:
    safe_limit = _bounded_limit(limit, maximum=10000)
    detail_value = None if has_detail is None else int(bool(has_detail))
    return _get_stock_catalog_cached(
        *_cache_key(database_path), industry_l1, detail_value, safe_limit
    )


@st.cache_data(ttl=1800, max_entries=64, show_spinner=False)
def _get_market_summary_cached(
    database_path: str,
    mtime_ns: int,
    database_size: int,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    conditions = []
    params: list[str] = []
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return _read_frame(
        database_path,
        """
        SELECT date, stock_count, advancing_count, declining_count, flat_count,
               total_volume, total_amount, average_close, average_return,
               median_return, average_sentiment, source, data_version
        FROM fact_market_daily
        """ + where_clause + " ORDER BY date",
        tuple(params),
    )


def get_market_summary(
    start_date=None, end_date=None, database_path: str | Path | None = None
) -> pd.DataFrame:
    start, end = _validate_range(start_date, end_date)
    return _get_market_summary_cached(*_cache_key(database_path), start, end)


@st.cache_data(ttl=900, max_entries=128, show_spinner=False)
def _get_market_snapshot_cached(
    database_path: str,
    mtime_ns: int,
    database_size: int,
    snapshot_date: str,
    limit: int,
    offset: int,
) -> pd.DataFrame:
    return _read_frame(
        database_path,
        """
        SELECT d.code, d.name, d.market, d.board, d.industry_l1,
               f.date, f.open, f.high, f.low, f.close, f.pre_close,
               f.change, f.pct_chg, f.volume, f.amount, f.ret,
               f.sentiment, f.data_version
        FROM fact_stock_daily_demo AS f
        JOIN dim_stock AS d ON d.code = f.code
        WHERE f.date = ?
        ORDER BY f.amount DESC, f.code
        LIMIT ? OFFSET ?
        """,
        (snapshot_date, limit, offset),
    )


def get_market_snapshot(
    snapshot_date=None,
    limit: int = 500,
    offset: int = 0,
    database_path: str | Path | None = None,
) -> pd.DataFrame:
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("offset 必须是非负整数")
    if snapshot_date is None:
        snapshot_date = get_manifest(database_path).get("end_date")
    safe_date = _validate_date(snapshot_date, "snapshot_date")
    if safe_date is None:
        return pd.DataFrame()
    return _get_market_snapshot_cached(
        *_cache_key(database_path), safe_date, _bounded_limit(limit, maximum=2000), offset
    )


@st.cache_data(ttl=1800, max_entries=128, show_spinner=False)
def _get_industry_summary_cached(
    database_path: str,
    mtime_ns: int,
    database_size: int,
    start_date: str | None,
    end_date: str | None,
    industries: tuple[str, ...],
) -> pd.DataFrame:
    conditions = []
    params: list[str] = []
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)
    if industries:
        conditions.append(f"industry_l1 IN ({','.join('?' for _ in industries)})")
        params.extend(industries)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return _read_frame(
        database_path,
        """
        SELECT industry_l1, date, stock_count, average_close, average_return,
               median_return, total_volume, total_amount, advancing_ratio,
               average_sentiment, data_version
        FROM fact_industry_daily
        """ + where_clause + " ORDER BY industry_l1, date",
        tuple(params),
    )


def get_industry_summary(
    start_date=None,
    end_date=None,
    industries: Iterable[str] | None = None,
    database_path: str | Path | None = None,
) -> pd.DataFrame:
    start, end = _validate_range(start_date, end_date)
    safe_industries = tuple(sorted({str(value) for value in (industries or []) if value}))
    return _get_industry_summary_cached(
        *_cache_key(database_path), start, end, safe_industries
    )


@st.cache_data(ttl=900, max_entries=256, show_spinner=False)
def _get_stock_history_cached(
    database_path: str,
    mtime_ns: int,
    database_size: int,
    code: str,
    start_date: str | None,
    end_date: str | None,
    limit: int,
) -> pd.DataFrame:
    conditions = ["code = ?"]
    params: list = [code]
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)
    params.append(limit)
    columns = ", ".join(STOCK_HISTORY_COLUMNS)
    return _read_frame(
        database_path,
        f"SELECT {columns} FROM fact_stock_daily_demo "
        f"WHERE {' AND '.join(conditions)} ORDER BY date LIMIT ?",
        tuple(params),
    )


def get_stock_history(
    code: str,
    start_date=None,
    end_date=None,
    limit: int = 2000,
    database_path: str | Path | None = None,
) -> pd.DataFrame:
    start, end = _validate_range(start_date, end_date)
    return _get_stock_history_cached(
        *_cache_key(database_path),
        _validate_code(code),
        start,
        end,
        _bounded_limit(limit, maximum=5000),
    )


@st.cache_data(ttl=1800, max_entries=128, show_spinner=False)
def _get_factor_ic_cached(
    database_path: str,
    mtime_ns: int,
    database_size: int,
    factor_names: tuple[str, ...],
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    conditions = []
    params: list[str] = []
    if factor_names:
        conditions.append(f"factor_name IN ({','.join('?' for _ in factor_names)})")
        params.extend(factor_names)
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return _read_frame(
        database_path,
        """
        SELECT factor_name, date, ic, sample_count, data_version
        FROM fact_factor_ic_daily
        """ + where_clause + " ORDER BY factor_name, date",
        tuple(params),
    )


def get_factor_ic(
    factor_names: Iterable[str] | None = None,
    start_date=None,
    end_date=None,
    database_path: str | Path | None = None,
) -> pd.DataFrame:
    start, end = _validate_range(start_date, end_date)
    safe_factors = tuple(sorted({str(value) for value in (factor_names or []) if value}))
    return _get_factor_ic_cached(*_cache_key(database_path), safe_factors, start, end)


@st.cache_data(ttl=3600, max_entries=8, show_spinner=False)
def _get_factor_catalog_cached(
    database_path: str, mtime_ns: int, database_size: int
) -> pd.DataFrame:
    return _read_frame(
        database_path,
        """
        SELECT factor_name
        FROM fact_factor_ic_daily
        GROUP BY factor_name
        ORDER BY factor_name
        """,
    )


def get_factor_catalog(
    database_path: str | Path | None = None,
) -> pd.DataFrame:
    """Return one row per published factor without loading its daily IC history."""
    return _get_factor_catalog_cached(*_cache_key(database_path))


@st.cache_data(ttl=1800, max_entries=16, show_spinner=False)
def _get_quality_runs_cached(
    database_path: str, mtime_ns: int, database_size: int, limit: int
) -> pd.DataFrame:
    return _read_frame(
        database_path,
        """
        SELECT run_id, started_at, data_date, row_count, stock_count,
               column_count, duplicate_key_count, invalid_date_count,
               invalid_ohlc_count, unexpected_missing_count,
               quality_score, status, data_version
        FROM fact_data_quality_run
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (limit,),
    )


def get_quality_runs(
    limit: int = 30, database_path: str | Path | None = None
) -> pd.DataFrame:
    return _get_quality_runs_cached(
        *_cache_key(database_path), _bounded_limit(limit, maximum=100)
    )


@st.cache_data(ttl=1800, max_entries=32, show_spinner=False)
def _get_quality_issues_cached(
    database_path: str, mtime_ns: int, database_size: int, run_id: str
) -> pd.DataFrame:
    return _read_frame(
        database_path,
        """
        SELECT run_id, rule_name, column_name, issue_count,
               severity, category, message
        FROM fact_data_quality_issue
        WHERE run_id = ?
        ORDER BY severity DESC, rule_name, column_name
        """,
        (run_id,),
    )


def get_quality_issues(
    run_id: str | None = None, database_path: str | Path | None = None
) -> pd.DataFrame:
    if run_id is None:
        runs = get_quality_runs(limit=1, database_path=database_path)
        if runs.empty:
            return pd.DataFrame()
        run_id = str(runs.iloc[0]["run_id"])
    if not re.fullmatch(r"^[A-Za-z0-9._-]{1,100}$", str(run_id)):
        raise ValueError("run_id 格式不合法")
    return _get_quality_issues_cached(*_cache_key(database_path), str(run_id))


@st.cache_data(ttl=900, max_entries=128, show_spinner=False)
def _get_latest_quotes_cached(
    database_path: str,
    mtime_ns: int,
    database_size: int,
    codes: tuple[str, ...],
    snapshot_date: str,
) -> pd.DataFrame:
    if not codes:
        return pd.DataFrame()
    placeholders = ",".join("?" for _ in codes)
    return _read_frame(
        database_path,
        f"""
        SELECT code, date, close, pct_chg, change
        FROM fact_stock_daily_demo
        WHERE date = ? AND code IN ({placeholders})
        ORDER BY code
        """,
        (snapshot_date, *codes),
    )


def get_latest_quotes(
    codes: Iterable[str], database_path: str | Path | None = None
) -> pd.DataFrame:
    safe_codes = tuple(sorted({_validate_code(code) for code in codes}))
    if len(safe_codes) > 100:
        raise ValueError("单次最多查询 100 只股票")
    snapshot_date = get_manifest(database_path).get("end_date")
    if not snapshot_date:
        return pd.DataFrame()
    return _get_latest_quotes_cached(
        *_cache_key(database_path), safe_codes, str(snapshot_date)
    )


_EXPLAIN_TEMPLATES = {
    "stock_catalog": (
        "SELECT code, name, market, board, industry_l1, has_detail "
        "FROM dim_stock WHERE has_detail = ? ORDER BY code LIMIT ?",
        (1, 100),
    ),
    "stock_history": (
        "SELECT code, date, close, volume, amount, ret, ma5, ma20, rsi, macd "
        "FROM fact_stock_daily_demo WHERE code = ? AND date BETWEEN ? AND ? "
        "ORDER BY date LIMIT ?",
        ("000001", "1900-01-01", "2999-12-31", 1000),
    ),
    "market_snapshot": (
        "SELECT code, date, close, pct_chg, volume, amount "
        "FROM fact_stock_daily_demo WHERE date = ? ORDER BY code LIMIT ?",
        ("2999-12-31", 500),
    ),
    "industry_summary": (
        "SELECT industry_l1, date, average_return, total_amount, advancing_ratio "
        "FROM fact_industry_daily WHERE industry_l1 = ? AND date BETWEEN ? AND ? "
        "ORDER BY date",
        ("银行", "1900-01-01", "2999-12-31"),
    ),
    "quality_runs": (
        "SELECT run_id, started_at, quality_score, status "
        "FROM fact_data_quality_run ORDER BY started_at DESC LIMIT ?",
        (30,),
    ),
}


@st.cache_data(ttl=3600, max_entries=32, show_spinner=False)
def _explain_named_query_cached(
    database_path: str,
    mtime_ns: int,
    database_size: int,
    query_name: str,
    bound_params: tuple,
) -> pd.DataFrame:
    sql, _ = _EXPLAIN_TEMPLATES[query_name]
    conn = _connect(database_path)
    try:
        rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}", bound_params).fetchall()
    finally:
        conn.close()
    return pd.DataFrame(rows, columns=["id", "parent", "notused", "detail"])


def explain_named_query(
    query_name: str,
    params: Iterable | Mapping | None = None,
    database_path: str | Path | None = None,
) -> pd.DataFrame:
    if query_name not in _EXPLAIN_TEMPLATES:
        raise ValueError(f"未知查询模板: {query_name}")
    sql, default_params = _EXPLAIN_TEMPLATES[query_name]
    if params is None:
        bound_params = default_params
    elif isinstance(params, Mapping):
        raise ValueError("explain_named_query 使用按顺序排列的参数，不接受字典")
    else:
        bound_params = tuple(params)
    return _explain_named_query_cached(
        *_cache_key(database_path), query_name, tuple(bound_params)
    )
