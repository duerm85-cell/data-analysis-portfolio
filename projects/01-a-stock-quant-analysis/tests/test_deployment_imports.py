"""Streamlit Cloud 嵌套入口的导入路径回归测试。"""

from pathlib import Path
import unittest


PROJECT_DIR = Path(__file__).resolve().parents[1]


class DeploymentImportTest(unittest.TestCase):
    def test_project_path_is_pinned_before_local_imports(self):
        source = (PROJECT_DIR / "app_pro.py").read_text(encoding="utf-8")
        path_setup = source.index("sys.path.insert(0, BASE_DIR)")
        data_access_import = source.index("from app.data_access import")
        config_import = source.index("from portfolio_config import")
        self.assertLess(path_setup, data_access_import)
        self.assertLess(path_setup, config_import)

    def test_expected_config_symbol_is_declared(self):
        source = (PROJECT_DIR / "portfolio_config.py").read_text(encoding="utf-8")
        self.assertIn("DEMO_SERVING_DB_PATH =", source)


if __name__ == "__main__":
    unittest.main()
