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
        self.assertEqual(report['unexpected_missing_cell_count'], 2)
        self.assertEqual(report['structural_factor_missing_count'], 0)
        self.assertEqual(report['structural_label_missing_count'], 0)
        self.assertEqual(report['quality_status'], 'FAIL')
        self.assertEqual(report['sentiment_source_distribution']['synthetic_demo'], 1)

    def test_separates_structural_and_unexpected_missing_values(self):
        frame = pd.DataFrame(
            {
                'code': ['600519', '600519'],
                'date': ['2026-01-02', '2026-01-03'],
                'open': [10.0, 10.5],
                'high': [11.0, 11.0],
                'low': [9.0, 10.0],
                'close': [10.5, 10.8],
                'volume': [100.0, 120.0],
                'amount': [1000.0, 1200.0],
                'momentum_60d': [None, 0.02],
                'label': [0.01, None],
            }
        )

        report = build_quality_report(frame)

        self.assertEqual(report['raw_missing_cell_count'], 0)
        self.assertEqual(report['structural_factor_missing_count'], 1)
        self.assertEqual(report['structural_label_missing_count'], 1)
        self.assertEqual(report['unexpected_missing_cell_count'], 0)
        self.assertEqual(report['quality_status'], 'WARN')


if __name__ == '__main__':
    unittest.main()
