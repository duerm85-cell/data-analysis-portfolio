import unittest

import pandas as pd

from data_quality import build_quality_report


class DataQualityTest(unittest.TestCase):
    def test_reports_duplicate_missing_and_invalid_ohlc_rows(self):
        frame = pd.DataFrame(
            {
                'code': ['600519', '600519', '000001'],
                'date': ['2026-01-02', '2026-01-02', 'invalid'],
                'open': [10.0, 10.0, 8.0],
                'high': [11.0, 9.0, 9.0],
                'low': [9.0, 9.5, 7.0],
                'close': [10.5, 10.5, None],
                'sentiment_source': ['real', 'real', 'synthetic_demo'],
            }
        )

        report = build_quality_report(frame)

        self.assertEqual(report['row_count'], 3)
        self.assertEqual(report['duplicate_key_count'], 1)
        self.assertEqual(report['invalid_date_count'], 1)
        self.assertEqual(report['invalid_ohlc_count'], 1)
        self.assertEqual(report['missing_cell_count'], 2)
        self.assertEqual(report['sentiment_source_distribution']['synthetic_demo'], 1)


if __name__ == '__main__':
    unittest.main()
