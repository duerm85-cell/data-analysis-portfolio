import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from backtest import StockBacktester


class StockBacktesterTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.predictions = pd.DataFrame(
            [
                ("2026-01-02", "000001", 0.9, 0.010),
                ("2026-01-02", "000002", 0.8, 0.020),
                ("2026-01-02", "000003", 0.1, -0.010),
                ("2026-01-05", "000001", 0.2, -0.010),
                ("2026-01-05", "000002", 0.9, 0.030),
                ("2026-01-05", "000003", 0.8, 0.020),
            ],
            columns=["date", "code", "predicted", "actual"],
        )
        self.benchmark = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
                "open": [101.0, 102.0, 103.0],
            }
        )
        self.market = pd.DataFrame(
            [
                ("2026-01-02", "000001", 100.0, 1000),
                ("2026-01-02", "000002", 100.0, 1000),
                ("2026-01-02", "000003", 100.0, 1000),
                ("2026-01-05", "000001", 101.0, 1000),
                ("2026-01-05", "000002", 102.0, 1000),
                ("2026-01-05", "000003", 99.0, 1000),
                ("2026-01-06", "000001", 102.0, 1000),
                ("2026-01-06", "000002", 101.0, 1000),
                ("2026-01-06", "000003", 100.0, 1000),
                ("2026-01-07", "000001", 103.0, 1000),
                ("2026-01-07", "000002", 102.0, 1000),
                ("2026-01-07", "000003", 101.0, 1000),
            ],
            columns=["date", "code", "open", "volume"],
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_uses_named_benchmark_and_deducts_transaction_costs(self):
        backtester = StockBacktester(
            output_dir=self.temp_dir.name,
            n_stocks=2,
            commission_rate=0.001,
            stamp_duty_rate=0.002,
        )

        with patch("builtins.print"):
            results, metrics = backtester.simple_strategy_backtest(
                self.predictions,
                benchmark_df=self.benchmark,
                benchmark_name="沪深300",
                benchmark_source="test_fixture",
                market_df=self.market,
            )

        self.assertEqual(metrics["benchmark_name"], "沪深300")
        self.assertEqual(metrics["benchmark_source"], "test_fixture")
        self.assertGreater(metrics["total_transaction_cost"], 0)
        self.assertTrue((results["portfolio_return"] <= results["gross_return"]).all())
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir.name, "backtest_metrics.csv")))
        orders = pd.read_csv(os.path.join(self.temp_dir.name, "execution_log.csv"))
        self.assertEqual(metrics["filled_order_count"], int((orders["status"] == "filled").sum()))
        self.assertEqual(metrics["blocked_order_count"], int((orders["status"] == "blocked").sum()))
        self.assertEqual(
            metrics["blocked_missing_open_count"],
            int(((orders["status"] == "blocked") & (orders["reason"] == "missing_open")).sum()),
        )

    def test_fallback_benchmark_is_labeled_as_universe_equal_weight(self):
        backtester = StockBacktester(output_dir=self.temp_dir.name, n_stocks=2)

        with patch("builtins.print"):
            _, metrics = backtester.simple_strategy_backtest(
                self.predictions, market_df=self.market
            )

        self.assertEqual(metrics["benchmark_name"], "股票池等权基准")
        self.assertEqual(metrics["benchmark_source"], "universe_equal_weight_open")


if __name__ == "__main__":
    unittest.main()
