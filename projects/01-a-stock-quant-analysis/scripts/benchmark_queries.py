"""Benchmark the named read queries used by the public Streamlit app."""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_DIR / "portfolio_data" / "demo_serving.db"
DEFAULT_OUTPUT = PROJECT_DIR / "reports" / "benchmark_results.json"


QUERIES = {
    "stock_catalog": """
        SELECT code, name, market, board, industry_l1, has_detail
        FROM dim_stock
        WHERE has_detail = ?
        ORDER BY code
        LIMIT ?
    """,
    "stock_latest_252": """
        SELECT code, date, open, high, low, close, volume, amount,
               ret, ma5, ma20, rsi, macd, volatility_20d, sentiment
        FROM fact_stock_daily_demo
        WHERE code = ?
        ORDER BY date DESC
        LIMIT ?
    """,
    "stock_three_years": """
        SELECT code, date, open, high, low, close, volume, amount,
               ret, ma5, ma20, rsi, macd, volatility_20d, sentiment
        FROM fact_stock_daily_demo
        WHERE code = ? AND date BETWEEN ? AND ?
        ORDER BY date
    """,
    "market_snapshot": """
        SELECT d.code, d.name, d.board, d.industry_l1,
               f.close, f.pct_chg, f.volume, f.amount, f.sentiment
        FROM fact_stock_daily_demo AS f
        JOIN dim_stock AS d ON d.code = f.code
        WHERE f.date = ?
        ORDER BY f.amount DESC, f.code
        LIMIT ?
    """,
    "industry_trend": """
        SELECT industry_l1, date, stock_count, average_close,
               average_return, median_return, total_volume, total_amount,
               advancing_ratio, average_sentiment
        FROM fact_industry_daily
        WHERE industry_l1 = ? AND date BETWEEN ? AND ?
        ORDER BY date
    """,
}


def _compact_sql(sql: str) -> str:
    return " ".join(sql.split())


def _read_context(conn: sqlite3.Connection) -> dict:
    manifest = conn.execute(
        """
        SELECT data_start_date, data_end_date, data_version
        FROM pipeline_run
        WHERE status = ?
        ORDER BY finished_at DESC
        LIMIT ?
        """,
        ("SUCCESS", 1),
    ).fetchone()
    stock = conn.execute(
        """
        SELECT code, industry_l1
        FROM dim_stock
        WHERE has_detail = ?
        ORDER BY code
        LIMIT ?
        """,
        (1, 1),
    ).fetchone()
    if manifest is None or stock is None:
        raise RuntimeError("服务库缺少可用于基准测试的数据")
    return {
        "start_date": manifest[0],
        "end_date": manifest[1],
        "data_version": manifest[2],
        "code": stock[0],
        "industry": stock[1],
    }


def _benchmark_one(
    conn: sqlite3.Connection,
    name: str,
    sql: str,
    params: tuple,
    repeats: int,
) -> dict:
    durations = []
    row_count = 0
    for _ in range(repeats):
        started = time.perf_counter_ns()
        rows = conn.execute(sql, params).fetchall()
        durations.append((time.perf_counter_ns() - started) / 1_000_000)
        row_count = len(rows)
    plan = [
        row[3]
        for row in conn.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()
    ]
    return {
        "name": name,
        "sql": _compact_sql(sql),
        "parameters": list(params),
        "returned_rows": row_count,
        "repeats": repeats,
        "first_run_ms": round(durations[0], 4),
        "median_ms": round(statistics.median(durations), 4),
        "min_ms": round(min(durations), 4),
        "max_ms": round(max(durations), 4),
        "query_plan": plan,
    }


def run_benchmarks(database_path: Path, repeats: int = 7) -> dict:
    if repeats < 1:
        raise ValueError("repeats 必须大于等于 1")
    if not database_path.exists():
        raise FileNotFoundError(f"服务库不存在: {database_path}")

    conn = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        context = _read_context(conn)
        parameters = {
            "stock_catalog": (1, 10000),
            "stock_latest_252": (context["code"], 252),
            "stock_three_years": (
                context["code"],
                context["start_date"],
                context["end_date"],
            ),
            "market_snapshot": (context["end_date"], 10000),
            "industry_trend": (
                context["industry"],
                context["start_date"],
                context["end_date"],
            ),
        }
        results = [
            _benchmark_one(conn, name, sql, parameters[name], repeats)
            for name, sql in QUERIES.items()
        ]
    finally:
        conn.close()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": str(database_path),
        "database_size_bytes": database_path.stat().st_size,
        "data_version": context["data_version"],
        "repeats": repeats,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="公开 SQLite 服务库查询性能测试")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()

    report = run_benchmarks(args.database, repeats=args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
