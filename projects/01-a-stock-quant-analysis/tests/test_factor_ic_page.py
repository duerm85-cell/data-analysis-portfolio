"""因子 IC 详细分析的 Streamlit 交互回归测试。"""

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from app import data_access


PROJECT_DIR = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_DIR / "app_pro.py"
APP_TIMEOUT_SECONDS = int(os.getenv("STREAMLIT_SMOKE_TIMEOUT", "90"))


class FactorIcPageInteractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_mode = os.environ.get("QUANT_APP_MODE")
        os.environ["QUANT_APP_MODE"] = "portfolio"
        cls.app = AppTest.from_file(str(APP_PATH)).run(timeout=APP_TIMEOUT_SECONDS)
        factor_button = next(
            item for item in cls.app.button if item.key == "nav_factor"
        )
        cls.app = factor_button.click().run(timeout=APP_TIMEOUT_SECONDS)
        if cls.app.exception:
            raise AssertionError(
                f"因子研究页初始渲染失败：{[item.value for item in cls.app.exception]}"
            )

    @classmethod
    def tearDownClass(cls):
        if cls.previous_mode is None:
            os.environ.pop("QUANT_APP_MODE", None)
        else:
            os.environ["QUANT_APP_MODE"] = cls.previous_mode

    @classmethod
    def _select_factors(cls, factor_names):
        selector = next(
            item for item in cls.app.multiselect if item.key == "ic_factor_select"
        )
        cls.app = selector.set_value(factor_names).run(timeout=APP_TIMEOUT_SECONDS)
        return cls.app

    def assert_factor_selection_renders(self, factor_names):
        app = self._select_factors(factor_names)
        self.assertEqual(
            [item.value for item in app.exception],
            [],
            f"选择 {factor_names} 时出现页面异常",
        )
        result_tables = [
            item.value
            for item in app.dataframe
            if set(factor_names).issubset(set(item.value.columns))
        ]
        self.assertTrue(result_tables, f"未找到 {factor_names} 的 IC 统计结果")

    def test_single_and_multiple_factor_combinations_render(self):
        combinations = (
            ["high_low_ratio"],
            ["macd", "amount_ratio"],
            [
                "high_low_ratio",
                "macd",
                "amount_ratio",
                "bb_position",
                "close_open_ratio",
            ],
            [
                "ma5_ma10_diff",
                "momentum_20d",
                "ret_5d",
                "rsi",
                "volume_ratio",
            ],
        )
        for factor_names in combinations:
            with self.subTest(factor_names=factor_names):
                self.assert_factor_selection_renders(factor_names)

    def test_unavailable_factor_is_skipped_without_breaking_valid_result(self):
        original_get_factor_ic = data_access.get_factor_ic

        def without_high_low_ratio(factor_names, *args, **kwargs):
            available_names = [
                factor_name
                for factor_name in factor_names
                if factor_name != "high_low_ratio"
            ]
            return original_get_factor_ic(available_names, *args, **kwargs)

        with patch("app.data_access.get_factor_ic", side_effect=without_high_low_ratio):
            app = self._select_factors(["high_low_ratio", "macd"])

        self.assertEqual([item.value for item in app.exception], [])
        self.assertTrue(
            any(
                "当前数据源暂无该因子的 IC 结果，已跳过。" in item.value
                and "high_low_ratio" in item.value
                for item in app.info
            )
        )
        self.assertTrue(
            any("macd" in set(item.value.columns) for item in app.dataframe),
            "跳过不可用因子后未继续展示 macd IC 结果",
        )

    def test_all_unavailable_factors_end_module_safely(self):
        original_get_factor_ic = data_access.get_factor_ic

        def without_selected_factors(factor_names, *args, **kwargs):
            return original_get_factor_ic(
                ["ret_5d"], *args, **kwargs
            ).iloc[0:0]

        with patch("app.data_access.get_factor_ic", side_effect=without_selected_factors):
            app = self._select_factors(["high_low_ratio"])

        self.assertEqual([item.value for item in app.exception], [])
        self.assertTrue(
            any(
                "当前数据源暂无该因子的 IC 结果，已跳过。" in item.value
                and "high_low_ratio" in item.value
                for item in app.info
            )
        )


if __name__ == "__main__":
    unittest.main()
