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
                "date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
                "benchmark_return": [0.005, 0.004],
            }
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
            )

        self.assertEqual(metrics["benchmark_name"], "沪深300")
        self.assertEqual(metrics["benchmark_source"], "test_fixture")
        self.assertGreater(metrics["total_transaction_cost"], 0)
        self.assertTrue((results["portfolio_return"] < results["gross_return"]).all())
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir.name, "backtest_metrics.csv")))

    def test_fallback_benchmark_is_labeled_as_universe_equal_weight(self):
        backtester = StockBacktester(output_dir=self.temp_dir.name, n_stocks=2)

        with patch("builtins.print"):
            _, metrics = backtester.simple_strategy_backtest(self.predictions)

        self.assertEqual(metrics["benchmark_name"], "股票池等权基准")
        self.assertEqual(metrics["benchmark_source"], "universe_equal_weight")


if __name__ == "__main__":
    unittest.main()
