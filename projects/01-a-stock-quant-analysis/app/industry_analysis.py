"""行业分析页：基于 fact_industry_daily 的有界预聚合查询。"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.data_access import get_industry_summary, get_manifest


RETURN_WINDOWS = (5, 20, 60)


def _compound_return(values: pd.Series, window: int) -> float:
    daily = pd.to_numeric(values, errors="coerce").dropna().tail(window)
    if daily.empty:
        return np.nan
    return float((1.0 + daily).prod() - 1.0)


def _build_industry_metrics(history: pd.DataFrame) -> pd.DataFrame:
    """从有界行业日聚合窗口中计算排名指标。"""
    rows: list[dict] = []
    for industry, group in history.groupby("industry_l1", sort=True):
        group = group.sort_values("date")
        latest = group.iloc[-1]
        amounts = pd.to_numeric(group["total_amount"], errors="coerce")
        recent_five = amounts.tail(5).mean()
        previous_five = amounts.iloc[-10:-5].mean() if len(amounts) >= 10 else np.nan
        amount_change = (
            float(recent_five / previous_five - 1.0)
            if pd.notna(previous_five) and previous_five != 0
            else np.nan
        )
        row = {
            "industry_l1": industry,
            "stock_count": int(latest["stock_count"]),
            "latest_return": float(latest["average_return"]),
            "advancing_ratio": float(latest["advancing_ratio"]),
            "total_amount": float(latest["total_amount"]),
            "amount_change_5d": amount_change,
        }
        for window in RETURN_WINDOWS:
            row[f"return_{window}d"] = _compound_return(group["average_return"], window)
        rows.append(row)
    return pd.DataFrame(rows)


def render_industry_analysis() -> None:
    st.title("🏭 行业分析")
    st.caption(
        "分析汇总层：仅查询近期行业预聚合结果，"
        "不扫描300只公开股票的日线明细。"
    )

    manifest = get_manifest()
    end_value = manifest.get("aggregate_end_date") or manifest.get("end_date")
    if not end_value:
        st.warning("当前服务库没有行业聚合日期。")
        return
    end_date = pd.Timestamp(end_value).date()
    start_date = end_date - timedelta(days=120)
    history = get_industry_summary(start_date=start_date, end_date=end_date)
    if history.empty:
        st.warning("当前日期窗口没有行业预聚合数据。")
        return

    history = history.sort_values(["industry_l1", "date"]).reset_index(drop=True)
    metrics = _build_industry_metrics(history)
    latest_date = history["date"].max().date().isoformat()
    trading_days = int(history["date"].nunique())

    summary_columns = st.columns(4)
    summary_columns[0].metric("行业数量", f"{len(metrics)} 个")
    summary_columns[1].metric("窗口交易日", f"{trading_days} 天")
    summary_columns[2].metric("最新日期", latest_date)
    summary_columns[3].metric(
        "上涨行业",
        f"{int((metrics['latest_return'] > 0).sum())}/{len(metrics)}",
    )

    st.subheader("行业涨跌排名")
    ranking_window = st.radio(
        "排名周期",
        RETURN_WINDOWS,
        index=1,
        horizontal=True,
        format_func=lambda value: f"{value}日",
        key="industry_ranking_window",
    )
    ranking_column = f"return_{ranking_window}d"
    ranking = metrics.sort_values(ranking_column, ascending=True)
    colors = ["#ef4444" if value >= 0 else "#22c55e" for value in ranking[ranking_column]]
    ranking_figure = go.Figure(
        go.Bar(
            x=ranking[ranking_column],
            y=ranking["industry_l1"],
            orientation="h",
            marker_color=colors,
            customdata=ranking[["stock_count", "advancing_ratio"]],
            hovertemplate=(
                "行业=%{y}<br>区间收益=%{x:.2%}<br>"
                "覆盖股票=%{customdata[0]:.0f}<br>"
                "最新上涨比例=%{customdata[1]:.1%}<extra></extra>"
            ),
        )
    )
    ranking_figure.update_layout(
        height=720,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        xaxis_title=f"{ranking_window}日复合收益",
        xaxis_tickformat=".1%",
    )
    st.plotly_chart(ranking_figure, width="stretch", key="industry_ranking")

    display_ranking = metrics.sort_values(ranking_column, ascending=False).copy()
    display_ranking.insert(0, "排名", range(1, len(display_ranking) + 1))
    for percentage_column in (
        "return_5d",
        "return_20d",
        "return_60d",
        "advancing_ratio",
        "amount_change_5d",
    ):
        display_ranking[percentage_column] = display_ranking[percentage_column] * 100.0
    display_ranking = display_ranking.rename(
        columns={
            "industry_l1": "行业",
            "stock_count": "资产数",
            "return_5d": "5日收益",
            "return_20d": "20日收益",
            "return_60d": "60日收益",
            "advancing_ratio": "上涨比例",
            "amount_change_5d": "近5日成交变化",
        }
    )
    st.dataframe(
        display_ranking[
            ["排名", "行业", "资产数", "5日收益", "20日收益", "60日收益", "上涨比例", "近5日成交变化"]
        ],
        width="stretch",
        hide_index=True,
        column_config={
            "5日收益": st.column_config.NumberColumn(format="%.2f%%"),
            "20日收益": st.column_config.NumberColumn(format="%.2f%%"),
            "60日收益": st.column_config.NumberColumn(format="%.2f%%"),
            "上涨比例": st.column_config.NumberColumn(format="%.2f%%"),
            "近5日成交变化": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )

    st.subheader("行业热力图")
    recent_dates = sorted(history["date"].dropna().unique())[-20:]
    heatmap_source = history[history["date"].isin(recent_dates)].copy()
    heatmap_source["date_label"] = heatmap_source["date"].dt.strftime("%m-%d")
    heatmap = heatmap_source.pivot(
        index="industry_l1", columns="date_label", values="average_return"
    ).mul(100.0)
    heatmap_figure = px.imshow(
        heatmap,
        aspect="auto",
        color_continuous_scale=[(0.0, "#16a34a"), (0.5, "#f8fafc"), (1.0, "#dc2626")],
        color_continuous_midpoint=0,
        labels={"x": "交易日", "y": "行业", "color": "日均收益(%)"},
    )
    heatmap_figure.update_layout(
        height=720,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
    )
    st.plotly_chart(heatmap_figure, width="stretch", key="industry_heatmap")

    st.subheader("成交变化")
    amount_ranking = metrics.sort_values("amount_change_5d", ascending=True)
    amount_colors = [
        "#f59e0b" if value >= 0 else "#64748b"
        for value in amount_ranking["amount_change_5d"].fillna(0)
    ]
    amount_figure = go.Figure(
        go.Bar(
            x=amount_ranking["amount_change_5d"],
            y=amount_ranking["industry_l1"],
            orientation="h",
            marker_color=amount_colors,
            hovertemplate="行业=%{y}<br>近5日均额环比=%{x:.2%}<extra></extra>",
        )
    )
    amount_figure.update_layout(
        height=720,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        xaxis_title="近5日日均成交额较前5日变化",
        xaxis_tickformat=".1%",
    )
    st.plotly_chart(amount_figure, width="stretch", key="industry_amount_change")

    st.caption(
        "5/20/60日收益由行业日均收益复合计算；成交变化为最近5个"
        "交易日的日均成交额相对前5个交易日。公开数据为合成演示数据。"
    )
