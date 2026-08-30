"""公开作品集运行模式的集中配置。"""

import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
PORTFOLIO_DATA_DIR = PROJECT_DIR / "portfolio_data"
PORTFOLIO_FACTORS_PATH = PORTFOLIO_DATA_DIR / "portfolio_factors.parquet"
PORTFOLIO_SENTIMENT_PATH = PORTFOLIO_DATA_DIR / "portfolio_sentiment.parquet"
PORTFOLIO_MANIFEST_PATH = PORTFOLIO_DATA_DIR / "portfolio_manifest.json"
PORTFOLIO_QUALITY_PATH = PORTFOLIO_DATA_DIR / "portfolio_quality.json"
PORTFOLIO_TRAINING_LOG_PATH = PORTFOLIO_DATA_DIR / "portfolio_training_log.json"
PORTFOLIO_BACKTEST_METRICS_PATH = PORTFOLIO_DATA_DIR / "portfolio_backtest_metrics.csv"
PORTFOLIO_BACKTEST_RESULTS_PATH = PORTFOLIO_DATA_DIR / "portfolio_backtest_results.csv"
PORTFOLIO_DAILY_PORTFOLIOS_PATH = PORTFOLIO_DATA_DIR / "portfolio_daily_portfolios.csv"


def get_app_mode():
    """返回 local 或 portfolio；云端缺少完整数据时自动使用作品集数据。"""
    configured_mode = os.getenv("QUANT_APP_MODE", "").strip().lower()
    if configured_mode in {"local", "portfolio"}:
        return configured_mode

    full_data_exists = any([
        (PROJECT_DIR / "data" / "processed" / "all_factors.parquet").exists(),
        (PROJECT_DIR / "data" / "processed" / "all_factors.csv").exists(),
        (PROJECT_DIR / "data" / "stock_data.db").exists(),
    ])
    if PORTFOLIO_FACTORS_PATH.exists() and not full_data_exists:
        return "portfolio"
    return "local"


def is_portfolio_mode():
    return get_app_mode() == "portfolio"
