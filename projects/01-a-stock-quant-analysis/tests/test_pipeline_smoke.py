"""Public pipeline contract: synthetic input, features, model snapshot, and backtest."""

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest import METHODOLOGY_VERSION, StockBacktester
from data_preprocessing import DataPreprocessor
from factor_engineering_with_sentiment import calculate_technical_factors
from portfolio_config import PORTFOLIO_TRAINING_LOG_PATH
from scripts.prepare_demo import generate_demo_inputs


class PipelineSmokeTest(unittest.TestCase):
    def test_demo_features_model_snapshot_and_backtest_connect(self):
        """Exercise the public pipeline without training or shipping private weights."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            codes = ["600519", "000858"]
            manifest = generate_demo_inputs(root, codes=codes, periods=140)
            self.assertEqual(manifest["mode"], "synthetic_demo")

            clean_dir = root / "data" / "clean"
            preprocessor = DataPreprocessor(
                raw_dir=root / "data" / "raw",
                invalid_dir=root / "data" / "raw" / "invalid",
                clean_dir=clean_dir,
                report_file=root / "data_cleaning_report.txt",
            )
            preprocessor.create_directories()

            factor_frames = []
            market_frames = []
            for code in codes:
                raw_path = root / "data" / "raw" / f"{code}_daily.csv"
                clean, error = preprocessor.process_single_file(raw_path)
                self.assertIsNone(error)
                self.assertIsNotNone(clean)
                preprocessor.save_cleaned_data(clean, f"{code}_daily.csv")

                clean = clean.sort_values("date").reset_index(drop=True)
                factors = calculate_technical_factors(clean)
                factors["code"] = code
                factor_frames.append(factors)
                market_frames.append(clean.assign(code=code)[["date", "code", "open", "volume"]])

            feature_data = pd.concat(factor_frames, ignore_index=True)
            market_data = pd.concat(market_frames, ignore_index=True)

            # Public mode intentionally loads an evaluation snapshot. Trained weights
            # remain local because the licensed research dataset is not distributed.
            model_summary = json.loads(
                Path(PORTFOLIO_TRAINING_LOG_PATH).read_text(encoding="utf-8")
            )
            model_features = model_summary["XGBoost"]["features"]
            self.assertEqual(len(model_features), 21)
            self.assertTrue(set(model_features).issubset(feature_data.columns))

            usable = feature_data.dropna(subset=model_features).copy()
            signal_dates = sorted(usable["date"].unique())[-5:-3]
            signals = usable[usable["date"].isin(signal_dates)].copy()
            signals["predicted"] = signals.groupby("date")["momentum_20d"].rank(
                pct=True, method="first"
            )

            output_dir = root / "backtest"
            backtester = StockBacktester(output_dir=output_dir, n_stocks=1)
            results, metrics = backtester.simple_strategy_backtest(
                signals[["date", "code", "predicted"]],
                market_df=market_data,
            )

            self.assertFalse(results.empty)
            self.assertEqual(metrics["methodology_version"], METHODOLOGY_VERSION)
            self.assertEqual(metrics["execution_price_source"], "next_market_open")
            self.assertTrue((output_dir / "backtest_metrics.csv").exists())
            self.assertTrue((output_dir / "execution_log.csv").exists())


if __name__ == "__main__":
    unittest.main()
