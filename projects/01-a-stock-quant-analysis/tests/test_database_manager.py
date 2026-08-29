import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from database_manager import StockDatabase, _P


class StockDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "stock_data.db")
        with patch("builtins.print"):
            self.database = StockDatabase(self.db_path)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.executemany(
                "INSERT INTO factors (code, date, ret) VALUES (?, ?, ?)",
                [
                    ("600519", "2026-01-02", 1400.0),
                    ("600519", "2026-01-03", 1410.0),
                    ("000001", "2026-01-03", 12.5),
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_import_uses_default_parquet_path(self):
        expected_path = _P("data", "processed", "all_factors.parquet")
        with patch("database_manager.os.path.exists", return_value=False) as exists:
            with patch("builtins.print"):
                self.database.import_from_parquet()

        exists.assert_called_once_with(expected_path)

    def test_stock_code_is_bound_as_a_query_parameter(self):
        malicious_code = "600519' OR 1=1 --"
        result = self.database.get_latest_data(malicious_code, days=10)

        self.assertTrue(result.empty)
        self.assertEqual(self.database.get_data_count()["factors_count"], 3)

    def test_days_must_be_a_positive_integer(self):
        for invalid_days in (0, -1, 1.5, "10", True):
            with self.subTest(days=invalid_days):
                with self.assertRaises(ValueError):
                    self.database.get_latest_data("600519", days=invalid_days)


if __name__ == "__main__":
    unittest.main()
