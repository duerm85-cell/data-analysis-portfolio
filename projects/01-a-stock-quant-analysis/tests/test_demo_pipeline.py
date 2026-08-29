import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.prepare_demo import generate_demo_inputs


class DemoPipelineTest(unittest.TestCase):
    def test_demo_inputs_are_reproducible_and_labeled(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first_manifest = generate_demo_inputs(first_dir, codes=["600519"], periods=120)
            second_manifest = generate_demo_inputs(second_dir, codes=["600519"], periods=120)

            first_raw = Path(first_dir) / "data" / "raw" / "600519_daily.csv"
            second_raw = Path(second_dir) / "data" / "raw" / "600519_daily.csv"
            self.assertEqual(first_raw.read_bytes(), second_raw.read_bytes())
            self.assertEqual(first_manifest["mode"], "synthetic_demo")

            sentiment = pd.read_csv(
                Path(first_dir) / "data" / "processed" / "sentiment_data.csv"
            )
            self.assertEqual(set(sentiment["data_source"]), {"synthetic_demo"})


if __name__ == "__main__":
    unittest.main()
