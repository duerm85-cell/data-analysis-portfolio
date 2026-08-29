"""生成明确标记的演示数据，并运行完整的本地数据流水线。"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


DEFAULT_CODES = ["600519", "000858", "300750", "601318", "000001", "600036"]


def generate_demo_inputs(base_dir, codes=None, periods=520, end_date="2025-12-31"):
    """生成确定性的 Tushare 形态行情、沪深300基准和模拟情绪数据。"""
    base_dir = Path(base_dir)
    raw_dir = base_dir / "data" / "raw"
    processed_dir = base_dir / "data" / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    codes = codes or DEFAULT_CODES
    dates = pd.bdate_range(end=end_date, periods=periods)

    sentiment_frames = []
    for index, code in enumerate(codes):
        rng = np.random.default_rng(20260000 + index)
        daily_return = rng.normal(0.00035, 0.018, periods)
        close = (10 + index * 7) * np.exp(np.cumsum(daily_return))
        pre_close = np.r_[close[0], close[:-1]]
        open_price = pre_close * (1 + rng.normal(0, 0.004, periods))
        high = np.maximum(open_price, close) * (1 + rng.uniform(0.001, 0.018, periods))
        low = np.minimum(open_price, close) * (1 - rng.uniform(0.001, 0.018, periods))
        volume = rng.lognormal(mean=11.0, sigma=0.45, size=periods)

        frame = pd.DataFrame(
            {
                "ts_code": f"{code}.SH" if code.startswith("6") else f"{code}.SZ",
                "trade_date": dates.strftime("%Y%m%d"),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "pre_close": pre_close,
                "change": close - pre_close,
                "pct_chg": (close / pre_close - 1) * 100,
                "vol": volume,
                "amount": volume * close / 10,
            }
        )
        frame.to_csv(raw_dir / f"{code}_daily.csv", index=False)

        sentiment = pd.Series(rng.normal(0, 0.22, periods)).rolling(3, min_periods=1).mean()
        sentiment_frames.append(
            pd.DataFrame(
                {
                    "code": code,
                    "date": dates,
                    "sentiment": sentiment,
                    "sentiment_ma5": sentiment.rolling(5, min_periods=1).mean(),
                    "sentiment_ma10": sentiment.rolling(10, min_periods=1).mean(),
                    "comment_count": rng.integers(50, 500, periods),
                    "data_source": "synthetic_demo",
                }
            )
        )

    benchmark_rng = np.random.default_rng(20260300)
    benchmark_close = 3500 * np.exp(
        np.cumsum(benchmark_rng.normal(0.00025, 0.011, periods))
    )
    pd.DataFrame(
        {"trade_date": dates.strftime("%Y%m%d"), "close": benchmark_close}
    ).to_csv(raw_dir / "benchmark_hs300.csv", index=False)

    sentiment_data = pd.concat(sentiment_frames, ignore_index=True)
    sentiment_data.to_csv(processed_dir / "sentiment_data.csv", index=False)
    try:
        sentiment_data.to_parquet(processed_dir / "sentiment_data.parquet", index=False)
    except ImportError:
        pass
    return {
        "mode": "synthetic_demo",
        "codes": codes,
        "periods": periods,
        "start_date": dates.min().strftime("%Y-%m-%d"),
        "end_date": dates.max().strftime("%Y-%m-%d"),
    }


def run_demo_pipeline(periods=520):
    manifest = generate_demo_inputs(PROJECT_DIR, periods=periods)

    from data_preprocessing import DataPreprocessor
    from factor_engineering_with_sentiment import main as build_factors

    DataPreprocessor().run()
    build_factors()

    manifest_path = PROJECT_DIR / "data" / "processed" / "demo_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nDemo 流水线完成，来源清单: {manifest_path}")


def main():
    parser = argparse.ArgumentParser(description="准备可复现的量化数据平台 Demo")
    parser.add_argument("--periods", type=int, default=520, help="每只股票的交易日数量")
    args = parser.parse_args()
    if args.periods < 120:
        parser.error("--periods 至少为 120，确保滚动因子有足够历史")
    run_demo_pipeline(periods=args.periods)


if __name__ == "__main__":
    main()
