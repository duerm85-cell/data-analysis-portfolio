"""Build the three-layer public V2 portfolio dataset with deterministic synthetic data."""

from __future__ import annotations

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

from data_quality import build_quality_report  # noqa: E402
from factor_engineering_with_sentiment import calculate_technical_factors  # noqa: E402
from portfolio_config import (  # noqa: E402
    PORTFOLIO_BACKTEST_METRICS_PATH,
    PORTFOLIO_BACKTEST_RESULTS_PATH,
    PORTFOLIO_DATA_DIR,
    PORTFOLIO_FACTORS_PATH,
    PORTFOLIO_INDUSTRY_DAILY_PATH,
    PORTFOLIO_MANIFEST_PATH,
    PORTFOLIO_MARKET_DAILY_PATH,
    PORTFOLIO_QUALITY_PATH,
    PORTFOLIO_SENTIMENT_PATH,
    PORTFOLIO_STOCK_CATALOG_PATH,
    PORTFOLIO_TRAINING_LOG_PATH,
)


DEFAULT_SEED = 20260903
DEFAULT_ASSET_COUNT = 5200
DEFAULT_DETAIL_COUNT = 300
DEFAULT_DETAIL_YEARS = 1
DEFAULT_AGGREGATE_YEARS = 3
DATA_END_DATE = "2026-08-28"

BOARD_LAYOUT = (
    ("沪市主板", "SSE", 600001, 2200),
    ("深市主板", "SZSE", 1, 1600),
    ("创业板", "SZSE", 300001, 900),
    ("科创板", "SSE", 688001, 500),
)

INDUSTRIES = (
    "农林牧渔",
    "基础化工",
    "钢铁",
    "有色金属",
    "电子",
    "家用电器",
    "食品饮料",
    "纺织服饰",
    "轻工制造",
    "医药生物",
    "公用事业",
    "交通运输",
    "房地产",
    "商贸零售",
    "社会服务",
    "综合",
    "建筑材料",
    "建筑装饰",
    "电力设备",
    "国防军工",
    "计算机",
    "传媒",
    "通信",
    "银行",
    "非银金融",
    "汽车",
    "机械设备",
    "煤炭",
    "石油石化",
    "环保",
    "美容护理",
)

INDUSTRY_WEIGHTS = np.array(
    [
        0.025,
        0.070,
        0.018,
        0.035,
        0.090,
        0.020,
        0.030,
        0.018,
        0.026,
        0.070,
        0.035,
        0.030,
        0.028,
        0.030,
        0.022,
        0.010,
        0.020,
        0.045,
        0.070,
        0.025,
        0.060,
        0.030,
        0.025,
        0.020,
        0.035,
        0.045,
        0.060,
        0.018,
        0.012,
        0.018,
        0.010,
    ],
    dtype=float,
)
INDUSTRY_WEIGHTS /= INDUSTRY_WEIGHTS.sum()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_board_codes(asset_count: int) -> list[tuple[str, str, str]]:
    if asset_count < len(BOARD_LAYOUT):
        raise ValueError("asset_count 至少应覆盖四个市场板块")
    scale = asset_count / sum(item[3] for item in BOARD_LAYOUT)
    quotas = [int(np.floor(item[3] * scale)) for item in BOARD_LAYOUT]
    for index in range(asset_count - sum(quotas)):
        quotas[index % len(quotas)] += 1

    records = []
    for (board, market, start_code, _), quota in zip(BOARD_LAYOUT, quotas):
        records.extend(
            (f"{start_code + offset:06d}", market, board)
            for offset in range(quota)
        )
    codes = [item[0] for item in records]
    if len(codes) != len(set(codes)):
        raise RuntimeError("生成的演示资产代码发生重复")
    return records


def build_asset_catalog(
    asset_count: int = DEFAULT_ASSET_COUNT,
    seed: int = DEFAULT_SEED,
) -> pd.DataFrame:
    """Create a market-scale synthetic asset directory with explicit provenance."""
    rng = np.random.default_rng(seed)
    board_codes = _generate_board_codes(asset_count)
    industry_values = list(INDUSTRIES)
    if asset_count > len(INDUSTRIES):
        industry_values.extend(
            rng.choice(
                INDUSTRIES,
                size=asset_count - len(INDUSTRIES),
                replace=True,
                p=INDUSTRY_WEIGHTS,
            ).tolist()
        )
    rng.shuffle(industry_values)
    listing_dates = pd.bdate_range("1991-01-02", "2023-12-29")
    listing_choices = rng.choice(listing_dates, size=asset_count, replace=True)
    snapshot_updated_at = f"{DATA_END_DATE}T00:00:00+00:00"

    catalog = pd.DataFrame(
        {
            "code": [record[0] for record in board_codes],
            "name": [f"合成资产{index + 1:04d}" for index in range(asset_count)],
            "market": [record[1] for record in board_codes],
            "board": [record[2] for record in board_codes],
            "industry_l1": industry_values,
            "list_date": pd.to_datetime(listing_choices).strftime("%Y-%m-%d"),
            "is_demo": 1,
            "has_detail": 0,
            "source": "deterministic_synthetic_catalog",
            "updated_at": snapshot_updated_at,
        }
    )
    return catalog.sort_values("code").reset_index(drop=True)


def select_representative_assets(
    catalog: pd.DataFrame,
    detail_count: int = DEFAULT_DETAIL_COUNT,
    seed: int = DEFAULT_SEED,
) -> pd.DataFrame:
    """Select exact-size industry × board strata with a fixed random seed."""
    if not 1 <= detail_count <= len(catalog):
        raise ValueError("detail_count 必须介于 1 和资产目录行数之间")
    strata = (
        catalog.groupby(["industry_l1", "board"], sort=True)
        .size()
        .rename("size")
        .reset_index()
    )
    if detail_count < len(strata):
        raise ValueError(
            f"detail_count 至少应为 {len(strata)}，才能覆盖每个行业×板块分层"
        )
    strata["ideal"] = detail_count * strata["size"] / len(catalog)
    strata["quota"] = np.floor(strata["ideal"]).astype(int).clip(lower=1)
    strata["remainder"] = strata["ideal"] - np.floor(strata["ideal"])

    while int(strata["quota"].sum()) > detail_count:
        candidates = strata[strata["quota"] > 1].sort_values(
            ["remainder", "quota", "industry_l1", "board"],
            ascending=[True, False, True, True],
        )
        if candidates.empty:
            raise RuntimeError("无法缩减分层样本配额")
        strata.loc[candidates.index[0], "quota"] -= 1

    while int(strata["quota"].sum()) < detail_count:
        candidates = strata[strata["quota"] < strata["size"]].sort_values(
            ["remainder", "size", "industry_l1", "board"],
            ascending=[False, False, True, True],
        )
        if candidates.empty:
            raise RuntimeError("无法补足分层样本配额")
        missing = detail_count - int(strata["quota"].sum())
        for row_index in candidates.index[:missing]:
            strata.loc[row_index, "quota"] += 1

    rng = np.random.default_rng(seed + 17)
    selected_frames = []
    for row in strata.itertuples(index=False):
        group = catalog[
            (catalog["industry_l1"] == row.industry_l1)
            & (catalog["board"] == row.board)
        ]
        random_state = int(rng.integers(0, np.iinfo(np.int32).max))
        selected_frames.append(group.sample(n=int(row.quota), random_state=random_state))

    selected = pd.concat(selected_frames, ignore_index=True)
    selected = selected.sort_values(
        ["industry_l1", "board", "code"]
    ).reset_index(drop=True)
    selected["selection_rank"] = np.arange(1, len(selected) + 1)
    if len(selected) != detail_count or not selected["code"].is_unique:
        raise RuntimeError("分层样本数量或唯一性校验失败")
    return selected


def _generate_detail_factors(
    selected: pd.DataFrame,
    years: int,
    seed: int,
) -> pd.DataFrame:
    visible_periods = years * 252
    warmup_periods = 65
    dates = pd.bdate_range(
        end=DATA_END_DATE, periods=visible_periods + warmup_periods
    )
    market_rng = np.random.default_rng(seed + 100)
    market_return = market_rng.normal(0.0002, 0.0085, len(dates))
    industry_returns = {
        industry: np.random.default_rng(seed + 1000 + index).normal(
            0.00005, 0.006, len(dates)
        )
        for index, industry in enumerate(INDUSTRIES)
    }
    frames = []

    for row in selected.itertuples(index=False):
        stock_seed = seed + int(row.code) + int(row.selection_rank) * 997
        rng = np.random.default_rng(stock_seed)
        daily_return = (
            0.45 * market_return
            + 0.20 * industry_returns[row.industry_l1]
            + rng.normal(0.0001, 0.012, len(dates))
        )
        base_price = 8.0 + (int(row.selection_rank) % 80) * 0.55
        close = base_price * np.exp(np.cumsum(daily_return))
        pre_close = np.r_[close[0], close[:-1]]
        open_price = pre_close * (1 + rng.normal(0, 0.0035, len(dates)))
        high = np.maximum(open_price, close) * (
            1 + rng.uniform(0.001, 0.016, len(dates))
        )
        low = np.minimum(open_price, close) * (
            1 - rng.uniform(0.001, 0.016, len(dates))
        )
        volume = rng.lognormal(mean=12.1, sigma=0.42, size=len(dates))
        sentiment = pd.Series(
            5 * daily_return + rng.normal(0, 0.18, len(dates))
        ).rolling(3, min_periods=1).mean().clip(-1, 1)

        stock_frame = pd.DataFrame(
            {
                "code": row.code,
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
            }
        )
        with contextlib.redirect_stdout(io.StringIO()):
            stock_frame = calculate_technical_factors(stock_frame)
        stock_frame["sentiment"] = sentiment.to_numpy()
        stock_frame["sentiment_ma5"] = (
            sentiment.rolling(5, min_periods=1).mean().to_numpy()
        )
        stock_frame["sentiment_ma10"] = (
            sentiment.rolling(10, min_periods=1).mean().to_numpy()
        )
        stock_frame["comment_count"] = rng.integers(50, 600, len(dates))
        stock_frame["sentiment_source"] = "synthetic_demo"
        frames.append(stock_frame.tail(visible_periods))

    return pd.concat(frames, ignore_index=True).sort_values(
        ["code", "date"]
    ).reset_index(drop=True)


def _generate_full_market_aggregates(
    catalog: pd.DataFrame,
    years: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range(end=DATA_END_DATE, periods=years * 252)
    market_rng = np.random.default_rng(seed + 200)
    market_return = market_rng.normal(0.00018, 0.008, len(dates))
    industry_counts = catalog["industry_l1"].value_counts().sort_index()
    industry_frames = []

    for index, (industry, stock_count) in enumerate(industry_counts.items()):
        rng = np.random.default_rng(seed + 2000 + index)
        average_return = 0.60 * market_return + rng.normal(
            0.00005, 0.006, len(dates)
        )
        median_return = average_return + rng.normal(0, 0.0015, len(dates))
        average_close = (18 + index * 0.7) * np.exp(np.cumsum(average_return))
        per_stock_volume = rng.lognormal(
            mean=12.0 + (index % 5) * 0.04,
            sigma=0.18,
            size=len(dates),
        )
        total_volume = per_stock_volume * int(stock_count)
        total_amount = total_volume * average_close
        advancing_ratio = np.clip(
            0.5 + average_return * 18 + rng.normal(0, 0.05, len(dates)),
            0.02,
            0.98,
        )
        average_sentiment = pd.Series(
            average_return * 8 + rng.normal(0, 0.08, len(dates))
        ).rolling(3, min_periods=1).mean().clip(-1, 1)
        industry_frames.append(
            pd.DataFrame(
                {
                    "industry_l1": industry,
                    "date": dates,
                    "stock_count": int(stock_count),
                    "average_close": average_close,
                    "average_return": average_return,
                    "median_return": median_return,
                    "total_volume": total_volume,
                    "total_amount": total_amount,
                    "advancing_ratio": advancing_ratio,
                    "average_sentiment": average_sentiment,
                }
            )
        )

    industry_daily = pd.concat(industry_frames, ignore_index=True)
    work = industry_daily.copy()
    work["weighted_close"] = work["average_close"] * work["stock_count"]
    work["weighted_return"] = work["average_return"] * work["stock_count"]
    work["weighted_median"] = work["median_return"] * work["stock_count"]
    work["weighted_sentiment"] = work["average_sentiment"] * work["stock_count"]
    work["advancing_count"] = np.rint(
        work["advancing_ratio"] * work["stock_count"]
    ).astype(int)
    market_daily = work.groupby("date", as_index=False).agg(
        stock_count=("stock_count", "sum"),
        advancing_count=("advancing_count", "sum"),
        total_volume=("total_volume", "sum"),
        total_amount=("total_amount", "sum"),
        weighted_close=("weighted_close", "sum"),
        weighted_return=("weighted_return", "sum"),
        weighted_median=("weighted_median", "sum"),
        weighted_sentiment=("weighted_sentiment", "sum"),
    )
    market_daily["declining_count"] = (
        market_daily["stock_count"] - market_daily["advancing_count"]
    )
    market_daily["flat_count"] = 0
    market_daily["average_close"] = (
        market_daily["weighted_close"] / market_daily["stock_count"]
    )
    market_daily["average_return"] = (
        market_daily["weighted_return"] / market_daily["stock_count"]
    )
    market_daily["median_return"] = (
        market_daily["weighted_median"] / market_daily["stock_count"]
    )
    market_daily["average_sentiment"] = (
        market_daily["weighted_sentiment"] / market_daily["stock_count"]
    )
    market_daily = market_daily[
        [
            "date",
            "stock_count",
            "advancing_count",
            "declining_count",
            "flat_count",
            "total_volume",
            "total_amount",
            "average_close",
            "average_return",
            "median_return",
            "average_sentiment",
        ]
    ]
    return market_daily, industry_daily


def _load_research_scale(research_quality_path: Path) -> dict:
    if not research_quality_path.exists():
        return {"status": "not_available"}
    quality = json.loads(research_quality_path.read_text(encoding="utf-8"))
    return {
        "status": "validated_local_snapshot",
        "stock_count": int(quality.get("stock_count", 0) or 0),
        "record_count": int(quality.get("row_count", 0) or 0),
        "start_date": quality.get("start_date"),
        "end_date": quality.get("end_date"),
        "quality_status": quality.get("quality_status"),
    }


def build_portfolio_v2_dataset(
    asset_count: int = DEFAULT_ASSET_COUNT,
    detail_count: int = DEFAULT_DETAIL_COUNT,
    detail_years: int = DEFAULT_DETAIL_YEARS,
    aggregate_years: int = DEFAULT_AGGREGATE_YEARS,
    seed: int = DEFAULT_SEED,
    research_quality_path: Path = PROJECT_DIR / "reports" / "data_quality.json",
) -> dict:
    catalog = build_asset_catalog(asset_count=asset_count, seed=seed)
    selected = select_representative_assets(
        catalog, detail_count=detail_count, seed=seed
    )
    catalog.loc[catalog["code"].isin(selected["code"]), "has_detail"] = 1
    detail = _generate_detail_factors(selected, detail_years, seed)
    market_daily, industry_daily = _generate_full_market_aggregates(
        catalog, aggregate_years, seed
    )

    quality_report = build_quality_report(detail)
    sentiment_columns = [
        column
        for column in (
            "code",
            "date",
            "sentiment",
            "sentiment_ma5",
            "sentiment_ma10",
            "comment_count",
            "sentiment_source",
        )
        if column in detail.columns
    ]
    sentiment = detail[sentiment_columns].rename(
        columns={"sentiment_source": "data_source"}
    )
    research_scale = _load_research_scale(research_quality_path)
    selected_by_industry = (
        selected.groupby("industry_l1")["code"].count().sort_index().to_dict()
    )
    selected_by_board = (
        selected.groupby("board")["code"].count().sort_index().to_dict()
    )
    research_artifacts = {
        key: path.name
        for key, path in {
            "model_summary": PORTFOLIO_TRAINING_LOG_PATH,
            "backtest_metrics": PORTFOLIO_BACKTEST_METRICS_PATH,
            "backtest_results": PORTFOLIO_BACKTEST_RESULTS_PATH,
        }.items()
        if path.exists()
    }
    selection_rule = (
        f"固定随机种子 {seed}；按一级行业×上市板块比例分层抽样，"
        f"每个非空分层至少 1 只，共 {detail_count} 只；仅生成最近 {detail_years} 年明细。"
    )
    manifest = {
        "version": "portfolio_v2",
        "mode": "portfolio_synthetic_demo",
        "generated_at": _utc_now(),
        "source_layer": "确定性合成目录、分层明细与离线预聚合",
        "source_label": "公开作品集 · 全市场规模合成分析快照",
        "selection": selection_rule,
        "random_seed": seed,
        "asset_catalog_stock_count": int(len(catalog)),
        "aggregate_market_stock_count": int(market_daily["stock_count"].max()),
        "aggregate_trading_day_count": int(len(market_daily)),
        "aggregate_start_date": market_daily["date"].min().strftime("%Y-%m-%d"),
        "aggregate_end_date": market_daily["date"].max().strftime("%Y-%m-%d"),
        "public_detail_stock_count": int(detail["code"].nunique()),
        "public_detail_record_count": int(len(detail)),
        "public_detail_start_date": detail["date"].min().strftime("%Y-%m-%d"),
        "public_detail_end_date": detail["date"].max().strftime("%Y-%m-%d"),
        "research_scale": research_scale,
        "stock_limit": int(detail["code"].nunique()),
        "stock_count": int(detail["code"].nunique()),
        "row_count": int(len(detail)),
        "column_count": int(len(detail.columns)),
        "start_date": detail["date"].min().strftime("%Y-%m-%d"),
        "end_date": detail["date"].max().strftime("%Y-%m-%d"),
        "selected_codes": selected["code"].tolist(),
        "selected_by_industry": selected_by_industry,
        "selected_by_board": selected_by_board,
        "research_artifacts": research_artifacts,
        "research_artifact_scope": (
            "本地研究规模来自质量报告；公开目录、聚合行情和交互明细均为确定性合成数据。"
        ),
        "public_scope": {
            "catalog": f"{asset_count} 只规模化合成资产目录，不对应真实证券名称",
            "aggregates": "基于完整合成目录离线生成的市场与行业分析快照",
            "details": f"{detail_count} 只分层代表资产的按需查询明细",
        },
        "disclaimer": "仅用于工程与分析能力展示，不构成投资建议或实时行情服务。",
    }

    PORTFOLIO_DATA_DIR.mkdir(parents=True, exist_ok=True)
    catalog.to_csv(PORTFOLIO_STOCK_CATALOG_PATH, index=False, encoding="utf-8")
    detail.to_parquet(PORTFOLIO_FACTORS_PATH, index=False, compression="zstd")
    sentiment.to_parquet(PORTFOLIO_SENTIMENT_PATH, index=False, compression="zstd")
    market_daily.to_parquet(
        PORTFOLIO_MARKET_DAILY_PATH, index=False, compression="zstd"
    )
    industry_daily.to_parquet(
        PORTFOLIO_INDUSTRY_DAILY_PATH, index=False, compression="zstd"
    )
    PORTFOLIO_QUALITY_PATH.write_text(
        json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    PORTFOLIO_MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="生成公开作品集 V2 三层数据包")
    parser.add_argument("--assets", type=int, default=DEFAULT_ASSET_COUNT)
    parser.add_argument("--details", type=int, default=DEFAULT_DETAIL_COUNT)
    parser.add_argument("--detail-years", type=int, default=DEFAULT_DETAIL_YEARS)
    parser.add_argument("--aggregate-years", type=int, default=DEFAULT_AGGREGATE_YEARS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--research-quality",
        type=Path,
        default=PROJECT_DIR / "reports" / "data_quality.json",
    )
    args = parser.parse_args()
    if not 1000 <= args.assets <= 6000:
        parser.error("--assets 必须在 1000 到 6000 之间")
    if not 50 <= args.details <= 500:
        parser.error("--details 必须在 50 到 500 之间")
    if args.details > args.assets:
        parser.error("--details 不能超过 --assets")
    if not 1 <= args.detail_years <= 3:
        parser.error("--detail-years 必须在 1 到 3 之间")
    if not 1 <= args.aggregate_years <= 5:
        parser.error("--aggregate-years 必须在 1 到 5 之间")
    manifest = build_portfolio_v2_dataset(
        asset_count=args.assets,
        detail_count=args.details,
        detail_years=args.detail_years,
        aggregate_years=args.aggregate_years,
        seed=args.seed,
        research_quality_path=args.research_quality,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
