import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import pandas as pd

from app import data_access
from scripts.benchmark_queries import run_benchmarks
from scripts.build_demo_serving_db import build_demo_serving_db


REQUIRED_TABLES = {
    "dim_stock",
    "fact_stock_daily_demo",
    "fact_market_daily",
    "fact_industry_daily",
    "fact_factor_ic_daily",
    "fact_data_quality_run",
    "fact_data_quality_issue",
    "pipeline_run",
}

REQUIRED_INDEXES = {
    "idx_stock_daily_date",
    "idx_stock_industry_l1",
    "idx_stock_has_detail",
    "idx_industry_daily_date",
    "idx_factor_ic_date",
    "idx_quality_run_started_at",
}


class DemoServingDatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        root = Path(cls.temp_dir.name)
        cls.source_path = root / "portfolio_factors.parquet"
        cls.manifest_path = root / "portfolio_manifest.json"
        cls.quality_path = root / "portfolio_quality.json"
        cls.database_path = root / "demo_serving.db"

        records = []
        dates = pd.bdate_range("2026-01-05", periods=12)
        for code_index, code in enumerate(("000001", "600519", "688001")):
            for date_index, current_date in enumerate(dates):
                close = 10.0 + code_index * 5 + date_index * 0.1
                daily_return = 0.0 if date_index == 0 else 0.01 * (code_index - 1)
                records.append(
                    {
                        "code": code,
                        "date": current_date,
                        "open": close - 0.05,
                        "high": close + 0.15,
                        "low": close - 0.15,
                        "close": close,
                        "pre_close": close - 0.1,
                        "change": 0.1,
                        "pct_chg": daily_return * 100,
                        "volume": 100_000 + date_index,
                        "amount": (100_000 + date_index) * close,
                        "ret": daily_return,
                        "ret_5d": daily_return * 5,
                        "ma5": close - 0.2,
                        "ma20": close - 0.5,
                        "rsi": 50 + code_index,
                        "macd": daily_return,
                        "volatility_20d": 0.02,
                        "label": daily_return,
                        "sentiment": 0.1 * code_index,
                    }
                )
        frame = pd.DataFrame.from_records(records)
        frame.to_parquet(cls.source_path, index=False)
        cls.manifest_path.write_text(
            json.dumps(
                {
                    "mode": "portfolio_synthetic_demo",
                    "source_layer": "unit_test",
                    "source_label": "测试演示数据",
                    "selection": "three deterministic codes",
                    "research_artifact_scope": "测试公开层与研究层分离",
                    "disclaimer": "仅用于测试",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cls.quality_path.write_text(
            json.dumps(
                {
                    "generated_at": "2026-01-21T00:00:00+00:00",
                    "end_date": "2026-01-20",
                    "row_count": len(frame),
                    "stock_count": 3,
                    "column_count": len(frame.columns),
                    "duplicate_key_count": 0,
                    "invalid_date_count": 0,
                    "invalid_ohlc_count": 0,
                    "nonpositive_price_count": 0,
                    "negative_volume_count": 0,
                    "invalid_code_count": 0,
                    "unexpected_missing_cell_count": 0,
                    "quality_status": "PASS",
                    "missing_details": {},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        cls.first_build = build_demo_serving_db(
            cls.source_path,
            cls.manifest_path,
            cls.quality_path,
            cls.database_path,
        )
        cls.second_build = build_demo_serving_db(
            cls.source_path,
            cls.manifest_path,
            cls.quality_path,
            cls.database_path,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_build_is_repeatable_and_integrity_is_valid(self):
        self.assertEqual(self.first_build["tables"], self.second_build["tables"])
        self.assertEqual(self.second_build["tables"]["fact_stock_daily_demo"], 36)
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_schema_contains_only_required_serving_tables_and_indexes(self):
        with closing(sqlite3.connect(self.database_path)) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            indexes = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'index' AND sql IS NOT NULL"
                )
            }
            daily_index_columns = [
                tuple(column[2] for column in connection.execute(
                    f'PRAGMA index_info("{row[1]}")'
                ))
                for row in connection.execute(
                    'PRAGMA index_list("fact_stock_daily_demo")'
                )
            ]

        self.assertEqual(tables, REQUIRED_TABLES)
        self.assertEqual(indexes, REQUIRED_INDEXES)
        self.assertEqual(daily_index_columns.count(("code", "date")), 1)

    def test_data_access_reads_bounded_slices(self):
        manifest = data_access.get_manifest(self.database_path)
        catalog = data_access.get_stock_catalog(database_path=self.database_path)
        history = data_access.get_stock_history(
            "000001", limit=5, database_path=self.database_path
        )
        snapshot = data_access.get_market_snapshot(
            manifest["end_date"], database_path=self.database_path
        )
        factor_ic = data_access.get_factor_ic(
            ["ret_5d"], database_path=self.database_path
        )
        factor_catalog = data_access.get_factor_catalog(self.database_path)

        self.assertEqual(manifest["row_count"], 36)
        self.assertEqual(len(catalog), 3)
        self.assertEqual(len(history), 5)
        self.assertEqual(set(history["code"]), {"000001"})
        self.assertEqual(len(snapshot), 3)
        self.assertEqual(set(factor_ic["factor_name"]), {"ret_5d"})
        self.assertEqual(factor_catalog["factor_name"].is_unique, True)

    def test_query_plan_uses_primary_key_for_stock_history(self):
        plan = data_access.explain_named_query(
            "stock_history",
            ("000001", "2026-01-01", "2026-12-31", 100),
            self.database_path,
        )
        details = " ".join(plan["detail"].astype(str)).upper()
        self.assertIn("PRIMARY KEY", details)

    def test_benchmark_covers_all_required_queries(self):
        report = run_benchmarks(self.database_path, repeats=2)
        results = {item["name"]: item for item in report["results"]}
        self.assertEqual(
            set(results),
            {
                "stock_catalog",
                "stock_latest_252",
                "stock_three_years",
                "market_snapshot",
                "industry_trend",
            },
        )
        self.assertTrue(all(item["returned_rows"] > 0 for item in results.values()))

    def test_data_access_rejects_unbounded_or_unsafe_parameters(self):
        with self.assertRaises(ValueError):
            data_access.get_stock_history("000001' OR 1=1", database_path=self.database_path)
        with self.assertRaises(ValueError):
            data_access.get_market_snapshot(limit=0, database_path=self.database_path)
        with self.assertRaises(ValueError):
            data_access.get_stock_history(
                "000001",
                start_date="2026-02-01",
                end_date="2026-01-01",
                database_path=self.database_path,
            )

    def test_public_data_access_has_no_full_table_read(self):
        source = Path(data_access.__file__).read_text(encoding="utf-8").upper()
        self.assertNotIn("SELECT *", source)
        self.assertNotIn("READ_PARQUET", source)


if __name__ == "__main__":
    unittest.main()
