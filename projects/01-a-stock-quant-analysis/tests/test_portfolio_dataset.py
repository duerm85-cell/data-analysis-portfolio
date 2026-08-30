import unittest

from scripts.build_portfolio_dataset import _generate_codes


class PortfolioDatasetTest(unittest.TestCase):
    def test_code_generation_respects_limit_and_is_deterministic(self):
        first = _generate_codes(40)
        second = _generate_codes(40)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 40)
        self.assertEqual(len(set(first)), 40)


if __name__ == "__main__":
    unittest.main()
