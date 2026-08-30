"""从本地完整因子快照生成可公开部署的轻量真实数据包。"""

import argparse
import contextlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from data_quality import build_quality_report
from factor_engineering_with_sentiment import calculate_technical_factors
from portfolio_config import (
    PORTFOLIO_BACKTEST_METRICS_PATH,
    PORTFOLIO_BACKTEST_RESULTS_PATH,
    PORTFOLIO_DATA_DIR,
    PORTFOLIO_DAILY_PORTFOLIOS_PATH,
    PORTFOLIO_FACTORS_PATH,
    PORTFOLIO_MANIFEST_PATH,
    PORTFOLIO_QUALITY_PATH,
    PORTFOLIO_SENTIMENT_PATH,
    PORTFOLIO_TRAINING_LOG_PATH,
)


BOARD_QUOTAS = {
    "sh_main": 18,
    "sz_main": 15,
    "chinext": 10,
    "star": 7,
}


def _generate_codes(stock_limit):
    scale = stock_limit / sum(BOARD_QUOTAS.values())
    quotas = {
        board: max(int(round(quota * scale)), 1)
        for board, quota in BOARD_QUOTAS.items()
    }
    generators = {
        "sh_main": lambda index: f"{600001 + index:06d}",
        "sz_main": lambda index: f"{1 + index:06d}",
        "chinext": lambda index: f"{300001 + index:06d}",
        "star": lambda index: f"{688001 + index:06d}",
    }
    codes = [
        generators[board](index)
        for board, quota in quotas.items()
        for index in range(quota)
    ]
    fill_index = 0
    while len(codes) < stock_limit:
        candidate = f"{601000 + fill_index:06d}"
        if candidate not in codes:
            codes.append(candidate)
        fill_index += 1
    return codes[:stock_limit]


def _generate_synthetic_factor_frame(stock_limit, years):
    """生成可复现、与任何真实证券价格无对应关系的演示行情和因子。"""
    codes = _generate_codes(stock_limit)
    visible_periods = years * 252
    warmup_periods = 65
    dates = pd.bdate_range(end="2026-08-28", periods=visible_periods + warmup_periods)
    market_rng = np.random.default_rng(20260831)
    market_return = market_rng.normal(0.0002, 0.009, len(dates))
    frames = []

    for index, code in enumerate(codes):
        rng = np.random.default_rng(20261000 + index)
        daily_return = 0.35 * market_return + rng.normal(0.00015, 0.014, len(dates))
        close = (12 + index * 0.8) * np.exp(np.cumsum(daily_return))
        pre_close = np.r_[close[0], close[:-1]]
        open_price = pre_close * (1 + rng.normal(0, 0.004, len(dates)))
        high = np.maximum(open_price, close) * (1 + rng.uniform(0.001, 0.018, len(dates)))
        low = np.minimum(open_price, close) * (1 - rng.uniform(0.001, 0.018, len(dates)))
        volume = rng.lognormal(mean=12.0, sigma=0.45, size=len(dates))
        sentiment = pd.Series(rng.normal(0, 0.22, len(dates))).rolling(3, min_periods=1).mean()

        stock_frame = pd.DataFrame({
            "code": code,
            "date": dates,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "pre_close": pre_close,
            "change": close - pre_close,
            "pct_chg": (close / pre_close - 1) * 100,
            "volume": volume,
            "amount": volume * close,
        })
        with contextlib.redirect_stdout(io.StringIO()):
            stock_frame = calculate_technical_factors(stock_frame)
        stock_frame["sentiment"] = sentiment.to_numpy()
        stock_frame["sentiment_ma5"] = sentiment.rolling(5, min_periods=1).mean().to_numpy()
        stock_frame["sentiment_ma10"] = sentiment.rolling(10, min_periods=1).mean().to_numpy()
        stock_frame["comment_count"] = rng.integers(50, 500, len(dates))
        stock_frame["sentiment_source"] = "synthetic_demo"
        frames.append(stock_frame.tail(visible_periods))

    return pd.concat(frames, ignore_index=True), codes


def build_portfolio_dataset(stock_limit=50, years=3, project_dir=PROJECT_DIR):
    frame, selected_codes = _generate_synthetic_factor_frame(stock_limit, years)
    required = {"code", "date", "open", "high", "low", "close", "volume", "amount"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"源数据缺少公开展示所需字段: {sorted(missing)}")

    public_frame = frame.sort_values(["code", "date"]).reset_index(drop=True)
    if public_frame.empty:
        raise ValueError("筛选结果为空，无法生成作品集数据包。")

    sentiment_columns = [
        column for column in [
            "code", "date", "sentiment", "sentiment_ma5", "sentiment_ma10",
            "comment_count", "sentiment_source",
        ] if column in public_frame.columns
    ]
    public_sentiment = public_frame[sentiment_columns].copy()
    if "sentiment_source" in public_sentiment.columns:
        public_sentiment = public_sentiment.rename(
            columns={"sentiment_source": "data_source"}
        )

    PORTFOLIO_DATA_DIR.mkdir(parents=True, exist_ok=True)
    public_frame.to_parquet(PORTFOLIO_FACTORS_PATH, index=False, compression="zstd")
    public_sentiment.to_parquet(
        PORTFOLIO_SENTIMENT_PATH, index=False, compression="zstd"
    )

    quality_report = build_quality_report(public_frame)
    PORTFOLIO_QUALITY_PATH.write_text(
        json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    training_log_path = project_dir / "training_log.json"
    research_artifacts = {}
    if training_log_path.exists():
        training_log = json.loads(training_log_path.read_text(encoding="utf-8"))
        PORTFOLIO_TRAINING_LOG_PATH.write_text(
            json.dumps(training_log, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        research_artifacts["model_summary"] = PORTFOLIO_TRAINING_LOG_PATH.name

    backtest_dir = project_dir / "backtest_results"
    artifact_pairs = [
        (backtest_dir / "backtest_metrics.csv", PORTFOLIO_BACKTEST_METRICS_PATH),
        (backtest_dir / "backtest_results.csv", PORTFOLIO_BACKTEST_RESULTS_PATH),
    ]
    for source_path, public_path in artifact_pairs:
        if not source_path.exists():
            continue
        artifact_frame = pd.read_csv(source_path)
        if source_path.name == "backtest_results.csv":
            public_columns = [
                "date", "equity_curve", "cumulative_return", "benchmark_cumulative"
            ]
            artifact_frame = artifact_frame[
                [column for column in public_columns if column in artifact_frame.columns]
            ]
        if "benchmark_source" in artifact_frame.columns:
            artifact_frame["benchmark_source"] = "沪深300历史快照"
        artifact_frame.to_csv(public_path, index=False, encoding="utf-8")
        research_artifacts[public_path.stem] = public_path.name
    if PORTFOLIO_DAILY_PORTFOLIOS_PATH.exists():
        PORTFOLIO_DAILY_PORTFOLIOS_PATH.unlink()

    manifest = {
        "mode": "portfolio_synthetic_demo",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_layer": "确定性随机种子生成器",
        "source_label": "公开作品集 · 确定性合成演示行情",
        "selection": "按沪深主板、创业板和科创板比例生成演示代码",
        "stock_limit": stock_limit,
        "years": years,
        "row_count": int(len(public_frame)),
        "stock_count": int(public_frame["code"].nunique()),
        "column_count": int(len(public_frame.columns)),
        "start_date": public_frame["date"].min().strftime("%Y-%m-%d"),
        "end_date": public_frame["date"].max().strftime("%Y-%m-%d"),
        "selected_codes": selected_codes,
        "research_artifacts": research_artifacts,
        "research_artifact_scope": "模型指标与归一化回测曲线来自本地完整研究；交互行情为合成演示数据。",
        "disclaimer": "仅用于工程与分析能力展示，不构成投资建议或实时行情服务。",
    }
    PORTFOLIO_MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description="生成公开作品集轻量合成数据包")
    parser.add_argument("--stocks", type=int, default=50, help="展示股票数量")
    parser.add_argument("--years", type=int, default=3, help="展示最近多少年")
    args = parser.parse_args()
    if not 10 <= args.stocks <= 100:
        parser.error("--stocks 必须在 10 到 100 之间")
    if not 1 <= args.years <= 5:
        parser.error("--years 必须在 1 到 5 之间")
    manifest = build_portfolio_dataset(args.stocks, args.years)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
