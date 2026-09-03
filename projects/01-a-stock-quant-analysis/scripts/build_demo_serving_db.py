"""Build the read-only SQLite serving database for the public portfolio app."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from portfolio_config import (  # noqa: E402
    PORTFOLIO_FACTORS_PATH,
    PORTFOLIO_MANIFEST_PATH,
    PORTFOLIO_QUALITY_PATH,
)


SCHEMA_PATH = PROJECT_DIR / "sql" / "demo_serving_schema.sql"
DEFAULT_OUTPUT_PATH = PROJECT_DIR / "portfolio_data" / "demo_serving.db"
INDUSTRIES = (
    "银行",
    "电子",
    "医药生物",
    "食品饮料",
    "机械设备",
    "计算机",
    "汽车",
    "基础化工",
    "公用事业",
    "非银金融",
)
FACTOR_IC_COLUMNS = (
    "ret_5d",
    "momentum_20d",
    "reversal_5d",
    "ma5_ma10_diff",
    "ma5_ma20_diff",
    "macd",
    "rsi",
    "volatility_20d",
    "volatility_60d",
    "bb_position",
    "volume_ratio",
    "amount_ratio",
    "high_low_ratio",
    "close_open_ratio",
    "sentiment",
    "sentiment_ma5",
    "sentiment_ma10",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _board(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith("688"):
        return "科创板"
    if code.startswith("3"):
        return "创业板"
    if code.startswith("0"):
        return "深市主板"
    if code.startswith("6"):
        return "沪市主板"
    return "其他"


def _market(board: str) -> str:
    return "SSE" if board in {"沪市主板", "科创板"} else "SZSE"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_source(source_path: Path) -> None:
    if source_path.exists():
        return
    from scripts.build_portfolio_dataset import build_portfolio_dataset

    build_portfolio_dataset()
    if not source_path.exists():
        raise FileNotFoundError(f"未能生成公开数据源: {source_path}")


def _normalise_source(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"code", "date", "open", "high", "low", "close", "volume", "amount"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"公开因子数据缺少必要字段: {sorted(missing)}")

    result = frame.copy()
    result["code"] = (
        result["code"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    )
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result = result.dropna(subset=["code", "date", "close"])
    result = result.sort_values(["code", "date"])
    result = result.drop_duplicates(["code", "date"], keep="last")
    result["date"] = result["date"].dt.strftime("%Y-%m-%d")
    return result.reset_index(drop=True)


def _build_stock_dimension(frame: pd.DataFrame, source_label: str, updated_at: str) -> pd.DataFrame:
    codes = sorted(frame["code"].unique())
    records = []
    for index, code in enumerate(codes):
        board = _board(code)
        records.append(
            {
                "code": code,
                "name": f"演示股票{index + 1:03d}",
                "market": _market(board),
                "board": board,
                "industry_l1": INDUSTRIES[index % len(INDUSTRIES)],
                "list_date": None,
                "is_demo": 1,
                "has_detail": 1,
                "source": source_label,
                "updated_at": updated_at,
            }
        )
    return pd.DataFrame.from_records(records)


def _build_market_daily(frame: pd.DataFrame, source_label: str, data_version: str) -> pd.DataFrame:
    work = frame.copy()
    returns = pd.to_numeric(work.get("ret"), errors="coerce").fillna(0.0)
    work["_advancing"] = (returns > 0).astype(int)
    work["_declining"] = (returns < 0).astype(int)
    work["_flat"] = (returns == 0).astype(int)
    aggregations = {
        "stock_count": ("code", "nunique"),
        "advancing_count": ("_advancing", "sum"),
        "declining_count": ("_declining", "sum"),
        "flat_count": ("_flat", "sum"),
        "total_volume": ("volume", "sum"),
        "total_amount": ("amount", "sum"),
        "average_close": ("close", "mean"),
        "average_return": ("ret", "mean"),
        "median_return": ("ret", "median"),
    }
    if "sentiment" in work.columns:
        aggregations["average_sentiment"] = ("sentiment", "mean")
    daily = work.groupby("date", as_index=False).agg(**aggregations)
    if "average_sentiment" not in daily.columns:
        daily["average_sentiment"] = np.nan
    daily["source"] = source_label
    daily["data_version"] = data_version
    return daily


def _build_industry_daily(
    frame: pd.DataFrame, stock_dimension: pd.DataFrame, data_version: str
) -> pd.DataFrame:
    work = frame.merge(
        stock_dimension[["code", "industry_l1"]], on="code", how="left", validate="many_to_one"
    )
    returns = pd.to_numeric(work.get("ret"), errors="coerce").fillna(0.0)
    work["_advancing"] = (returns > 0).astype(int)
    aggregations = {
        "stock_count": ("code", "nunique"),
        "average_close": ("close", "mean"),
        "average_return": ("ret", "mean"),
        "median_return": ("ret", "median"),
        "total_volume": ("volume", "sum"),
        "total_amount": ("amount", "sum"),
        "_advancing_count": ("_advancing", "sum"),
    }
    if "sentiment" in work.columns:
        aggregations["average_sentiment"] = ("sentiment", "mean")
    daily = work.groupby(["industry_l1", "date"], as_index=False).agg(**aggregations)
    daily["advancing_ratio"] = daily["_advancing_count"] / daily["stock_count"].clip(lower=1)
    daily = daily.drop(columns="_advancing_count")
    if "average_sentiment" not in daily.columns:
        daily["average_sentiment"] = np.nan
    daily["data_version"] = data_version
    return daily


def _spearman_ic(factor: pd.Series, label: pd.Series) -> float:
    valid = factor.notna() & label.notna()
    if int(valid.sum()) < 3:
        return np.nan
    factor_rank = factor[valid].rank(method="average")
    label_rank = label[valid].rank(method="average")
    if factor_rank.nunique() < 2 or label_rank.nunique() < 2:
        return np.nan
    return float(factor_rank.corr(label_rank))


def _build_factor_ic(frame: pd.DataFrame, data_version: str) -> pd.DataFrame:
    if "label" not in frame.columns:
        return pd.DataFrame(
            columns=["factor_name", "date", "ic", "sample_count", "data_version"]
        )
    records = []
    available = [column for column in FACTOR_IC_COLUMNS if column in frame.columns]
    for date_value, group in frame.groupby("date", sort=True):
        label = pd.to_numeric(group["label"], errors="coerce")
        for factor_name in available:
            factor = pd.to_numeric(group[factor_name], errors="coerce")
            sample_count = int((factor.notna() & label.notna()).sum())
            records.append(
                {
                    "factor_name": factor_name,
                    "date": date_value,
                    "ic": _spearman_ic(factor, label),
                    "sample_count": sample_count,
                    "data_version": data_version,
                }
            )
    return pd.DataFrame.from_records(records)


def _quality_rows(quality: dict, data_version: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    generated_at = str(quality.get("generated_at") or _utc_now())
    run_id = f"quality-{data_version[:16]}"
    critical_count = sum(
        int(quality.get(key, 0) or 0)
        for key in (
            "duplicate_key_count",
            "invalid_date_count",
            "invalid_ohlc_count",
            "nonpositive_price_count",
            "negative_volume_count",
            "invalid_code_count",
            "unexpected_missing_cell_count",
        )
    )
    row_count = int(quality.get("row_count", 0) or 0)
    quality_score = max(0.0, 100.0 - (critical_count / max(row_count, 1)) * 100.0)
    run = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "started_at": generated_at,
                "data_date": quality.get("end_date"),
                "row_count": row_count,
                "stock_count": int(quality.get("stock_count", 0) or 0),
                "column_count": int(quality.get("column_count", 0) or 0),
                "duplicate_key_count": int(quality.get("duplicate_key_count", 0) or 0),
                "invalid_date_count": int(quality.get("invalid_date_count", 0) or 0),
                "invalid_ohlc_count": int(quality.get("invalid_ohlc_count", 0) or 0),
                "unexpected_missing_count": int(
                    quality.get("unexpected_missing_cell_count", 0) or 0
                ),
                "quality_score": round(quality_score, 4),
                "status": str(quality.get("quality_status", "UNKNOWN")),
                "data_version": data_version,
            }
        ]
    )

    base_rules = (
        ("duplicate_primary_key", "", "duplicate_key_count", "ERROR", "unexpected", "重复 (code, date) 主键"),
        ("invalid_date", "date", "invalid_date_count", "ERROR", "unexpected", "无法解析的交易日期"),
        ("invalid_stock_code", "code", "invalid_code_count", "ERROR", "unexpected", "股票代码格式不合法"),
        ("invalid_ohlc", "ohlc", "invalid_ohlc_count", "ERROR", "unexpected", "OHLC 价格关系不合法"),
        ("nonpositive_price", "ohlc", "nonpositive_price_count", "ERROR", "unexpected", "价格小于等于零"),
        ("negative_volume", "volume", "negative_volume_count", "ERROR", "unexpected", "成交量小于零"),
        ("zero_volume", "volume", "zero_volume_count", "WARN", "warning", "成交量为零"),
        ("extreme_return", "ret", "extreme_return_count", "WARN", "warning", "单日绝对收益超过 30%"),
        ("unexpected_missing", "", "unexpected_missing_cell_count", "ERROR", "unexpected", "未预期字段缺失"),
    )
    issues = [
        {
            "run_id": run_id,
            "rule_name": rule_name,
            "column_name": column_name,
            "issue_count": int(quality.get(metric, 0) or 0),
            "severity": severity,
            "category": category,
            "message": message,
        }
        for rule_name, column_name, metric, severity, category, message in base_rules
    ]
    for column_name, detail in (quality.get("missing_details") or {}).items():
        category = str(detail.get("category", "unexpected"))
        issues.append(
            {
                "run_id": run_id,
                "rule_name": "missing_value",
                "column_name": str(column_name),
                "issue_count": int(detail.get("count", 0) or 0),
                "severity": "INFO" if category.startswith("structural_") else "ERROR",
                "category": category,
                "message": str(detail.get("reason", "字段缺失")),
            }
        )
    return run, pd.DataFrame.from_records(issues)


def _insert_frame(conn: sqlite3.Connection, table: str, frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    frame.to_sql(table, conn, if_exists="append", index=False, method="multi", chunksize=500)


def _database_statistics(conn: sqlite3.Connection, database_path: Path) -> dict:
    table_names = [
        "dim_stock",
        "fact_stock_daily_demo",
        "fact_market_daily",
        "fact_industry_daily",
        "fact_factor_ic_daily",
        "fact_data_quality_run",
        "fact_data_quality_issue",
        "pipeline_run",
    ]
    counts = {
        table: int(conn.execute(f'SELECT COUNT(1) FROM "{table}"').fetchone()[0])
        for table in table_names
    }
    indexes = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name"
        ).fetchall()
    ]
    return {
        "database": str(database_path),
        "size_bytes": database_path.stat().st_size if database_path.exists() else 0,
        "tables": counts,
        "indexes": indexes,
    }


def build_demo_serving_db(
    source_path: Path = PORTFOLIO_FACTORS_PATH,
    manifest_path: Path = PORTFOLIO_MANIFEST_PATH,
    quality_path: Path = PORTFOLIO_QUALITY_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> dict:
    """Rebuild the serving database in a temporary file and atomically replace it."""
    _ensure_source(source_path)
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"SQLite schema 不存在: {SCHEMA_PATH}")

    manifest = _load_json(manifest_path)
    quality = _load_json(quality_path)
    source_hash = _sha256(source_path)
    data_version = f"v2-{source_hash[:20]}"
    started_at = _utc_now()
    source_label = str(
        manifest.get("source_label", "公开作品集 · 确定性合成演示行情")
    )

    frame = _normalise_source(pd.read_parquet(source_path))
    frame["data_version"] = data_version
    stock_dimension = _build_stock_dimension(frame, source_label, started_at)
    market_daily = _build_market_daily(frame, source_label, data_version)
    industry_daily = _build_industry_daily(frame, stock_dimension, data_version)
    factor_ic = _build_factor_ic(frame, data_version)
    quality_run, quality_issues = _quality_rows(quality, data_version)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    if temporary_path.exists():
        temporary_path.unlink()

    conn = sqlite3.connect(temporary_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _insert_frame(conn, "dim_stock", stock_dimension)
        _insert_frame(conn, "fact_stock_daily_demo", frame)
        _insert_frame(conn, "fact_market_daily", market_daily)
        _insert_frame(conn, "fact_industry_daily", industry_daily)
        _insert_frame(conn, "fact_factor_ic_daily", factor_ic)
        _insert_frame(conn, "fact_data_quality_run", quality_run)
        _insert_frame(conn, "fact_data_quality_issue", quality_issues)
        pipeline_run = pd.DataFrame(
            [
                {
                    "run_id": f"serving-{data_version}",
                    "pipeline_name": "build_demo_serving_db",
                    "started_at": started_at,
                    "finished_at": _utc_now(),
                    "status": "SUCCESS",
                    "input_rows": int(len(frame)),
                    "output_rows": int(len(frame)),
                    "data_start_date": str(frame["date"].min()),
                    "data_end_date": str(frame["date"].max()),
                    "source": str(manifest.get("source_layer", "portfolio_data")),
                    "data_version": data_version,
                    "mode": str(manifest.get("mode", "portfolio_synthetic_demo")),
                    "source_label": source_label,
                    "selection_rule": str(manifest.get("selection", "")),
                    "public_scope": str(
                        manifest.get(
                            "research_artifact_scope",
                            "公开交互行情与本地研究产物分离。",
                        )
                    ),
                    "disclaimer": str(
                        manifest.get(
                            "disclaimer",
                            "仅用于工程与分析能力展示，不构成投资建议。",
                        )
                    ),
                    "database_path": output_path.name,
                    "error_message": None,
                }
            ]
        )
        _insert_frame(conn, "pipeline_run", pipeline_run)
        conn.execute("ANALYZE")
        conn.execute("PRAGMA optimize")
        conn.commit()

        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite 完整性校验失败: {integrity}")
        if conn.execute("SELECT COUNT(1) FROM fact_stock_daily_demo").fetchone()[0] != len(frame):
            raise RuntimeError("SQLite 明细行数与源数据不一致")
    except Exception:
        conn.close()
        if temporary_path.exists():
            temporary_path.unlink()
        raise
    else:
        conn.close()

    os.replace(temporary_path, output_path)
    readonly = sqlite3.connect(f"file:{output_path.as_posix()}?mode=ro", uri=True)
    try:
        statistics = _database_statistics(readonly, output_path)
    finally:
        readonly.close()
    statistics["data_version"] = data_version
    return statistics


def main() -> None:
    parser = argparse.ArgumentParser(description="构建公开 Demo SQLite 服务库")
    parser.add_argument("--source", type=Path, default=PORTFOLIO_FACTORS_PATH)
    parser.add_argument("--manifest", type=Path, default=PORTFOLIO_MANIFEST_PATH)
    parser.add_argument("--quality", type=Path, default=PORTFOLIO_QUALITY_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    statistics = build_demo_serving_db(
        source_path=args.source,
        manifest_path=args.manifest,
        quality_path=args.quality,
        output_path=args.output,
    )
    print(json.dumps(statistics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
