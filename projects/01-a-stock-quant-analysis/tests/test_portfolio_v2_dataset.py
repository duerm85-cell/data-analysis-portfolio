import unittest

import pandas as pd

from scripts.build_portfolio_v2_dataset import (
    _generate_full_market_aggregates,
    build_asset_catalog,
    select_representative_assets,
)


class PortfolioV2DatasetTest(unittest.TestCase):
    def test_catalog_and_stratified_selection_are_reproducible(self):
        first_catalog = build_asset_catalog(asset_count=5200, seed=20260903)
        second_catalog = build_asset_catalog(asset_count=5200, seed=20260903)
        pd.testing.assert_frame_equal(first_catalog, second_catalog)

        first_selected = select_representative_assets(
            first_catalog, detail_count=300, seed=20260903
        )
        second_selected = select_representative_assets(
            second_catalog, detail_count=300, seed=20260903
        )
        pd.testing.assert_frame_equal(first_selected, second_selected)

        self.assertEqual(len(first_catalog), 5200)
        self.assertEqual(first_catalog["code"].nunique(), 5200)
        self.assertEqual(len(first_selected), 300)
        self.assertEqual(first_selected["code"].nunique(), 300)
        self.assertEqual(set(first_selected["board"]), set(first_catalog["board"]))
        self.assertEqual(
            set(first_selected["industry_l1"]), set(first_catalog["industry_l1"])
        )

        catalog_strata = set(
            first_catalog[["industry_l1", "board"]].itertuples(
                index=False, name=None
            )
        )
        selected_strata = set(
            first_selected[["industry_l1", "board"]].itertuples(
                index=False, name=None
            )
        )
        self.assertEqual(selected_strata, catalog_strata)

    def test_preaggregates_represent_the_full_catalog(self):
        catalog = build_asset_catalog(asset_count=124, seed=20260903)
        market_daily, industry_daily = _generate_full_market_aggregates(
            catalog, years=1, seed=20260903
        )

        self.assertEqual(len(market_daily), 252)
        self.assertEqual(int(market_daily["stock_count"].min()), 124)
        self.assertEqual(int(market_daily["stock_count"].max()), 124)
        self.assertEqual(industry_daily["industry_l1"].nunique(), 31)
        per_date_counts = industry_daily.groupby("date")["stock_count"].sum()
        self.assertTrue((per_date_counts == 124).all())


if __name__ == "__main__":
    unittest.main()
