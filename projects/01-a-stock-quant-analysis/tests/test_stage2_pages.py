"""阶段2页面指标的纯函数测试。"""

import unittest

import pandas as pd

from app.industry_analysis import _build_industry_metrics
from app.stock_profile import _industry_percentiles, _stock_metrics


class Stage2PageMetricTests(unittest.TestCase):
    def test_stock_metrics_and_peer_percentiles(self):
        dates = pd.date_range("2026-01-01", periods=3)
        history = pd.DataFrame(
            {
                "date": dates,
                "close": [100.0, 110.0, 99.0],
                "ret": [0.0, 0.1, -0.1],
                "amount": [10.0, 20.0, 30.0],
            }
        )
        metrics = _stock_metrics(history)
        self.assertAlmostEqual(metrics["period_return"], -0.01)
        self.assertAlmostEqual(metrics["max_drawdown"], -0.10)
        self.assertAlmostEqual(metrics["average_turnover"], 20.0)

        peers = pd.concat(
            [
                history.assign(code="000001", name="A", industry_l1="测试行业"),
                history.assign(
                    code="000002",
                    name="B",
                    industry_l1="测试行业",
                    close=[100.0, 105.0, 120.0],
                    ret=[0.0, 0.05, 120 / 105 - 1],
                ),
            ],
            ignore_index=True,
        )
        ranked = _industry_percentiles(peers)
        winner = ranked.loc[ranked["code"] == "000002"].iloc[0]
        self.assertEqual(winner["return_percentile"], 1.0)

    def test_industry_metrics_compound_returns_and_amount_change(self):
        dates = pd.date_range("2026-01-01", periods=10)
        history = pd.DataFrame(
            {
                "industry_l1": ["银行"] * 10,
                "date": dates,
                "stock_count": [100] * 10,
                "average_return": [0.01] * 10,
                "advancing_ratio": [0.6] * 10,
                "total_amount": [100.0] * 5 + [120.0] * 5,
            }
        )
        metrics = _build_industry_metrics(history).iloc[0]
        self.assertAlmostEqual(metrics["return_5d"], 1.01**5 - 1)
        self.assertAlmostEqual(metrics["amount_change_5d"], 0.2)
        self.assertEqual(metrics["stock_count"], 100)


if __name__ == "__main__":
    unittest.main()
