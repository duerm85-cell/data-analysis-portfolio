import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from factor_engineering_with_sentiment import load_sentiment_data, merge_sentiment_factors


class FactorPipelineTest(unittest.TestCase):
    def test_legacy_sentiment_without_comment_count_is_normalized(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            csv_path = Path(temporary_dir) / 'sentiment_data.csv'
            pd.DataFrame(
                {
                    'code': ['1'],
                    'date': ['2026-01-02'],
                    'sentiment': [0.2],
                    'sentiment_ma5': [0.1],
                    'sentiment_ma10': [0.05],
                }
            ).to_csv(csv_path, index=False)

            def fake_path(*parts):
                return str(Path(temporary_dir) / parts[-1])

            with patch('factor_engineering_with_sentiment._P', side_effect=fake_path):
                sentiment = load_sentiment_data()

        self.assertEqual(sentiment.loc[0, 'code'], '000001')
        self.assertEqual(sentiment.loc[0, 'comment_count'], 0)
        self.assertEqual(sentiment.loc[0, 'data_source'], 'legacy_unknown')

    def test_normalized_legacy_sentiment_merges_with_explicit_provenance(self):
        factors = pd.DataFrame({'date': ['2026-01-02'], 'close': [10.0]})
        sentiment = pd.DataFrame(
            {
                'code': ['000001'],
                'date': pd.to_datetime(['2026-01-02']),
                'sentiment': [0.2],
                'sentiment_ma5': [0.1],
                'sentiment_ma10': [0.05],
                'comment_count': [0],
                'data_source': ['legacy_unknown'],
            }
        )

        merged = merge_sentiment_factors(factors, '000001', sentiment)

        self.assertAlmostEqual(merged.loc[0, 'sentiment'], 0.2)
        self.assertEqual(merged.loc[0, 'sentiment_source'], 'legacy_unknown')


if __name__ == '__main__':
    unittest.main()
