"""股票画像页：仅通过 SQLite Data Access Layer 按需读取公开明细。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from app.data_access import (
    get_industry_peer_history,
    get_stock_catalog,
    get_stock_history,
    get_stock_metadata,
)


def _maximum_drawdown(close: pd.Series) -> tuple[float, pd.Series]:
    """返回最大回撤和逐日回撤序列。"""
    values = pd.to_numeric(close, errors="coerce")
    drawdown = values.div(values.cummax()).sub(1.0)
    return float(drawdown.min()) if drawdown.notna().any() else np.nan, drawdown


def _stock_metrics(history: pd.DataFrame) -> dict[str, float]:
    """从单只股票的有界历史数据计算页面指标。"""
    if history.empty:
        return {}
    close = pd.to_numeric(history["close"], errors="coerce")
    returns = pd.to_numeric(history["ret"], errors="coerce")
    max_drawdown, _ = _maximum_drawdown(close)
    return {
        "latest_close": float(close.iloc[-1]),
        "period_return": float(close.iloc[-1] / close.iloc[0] - 1.0),
        "annualized_volatility": float(returns.std(ddof=1) * np.sqrt(252)),
        "max_drawdown": max_drawdown,
        "average_turnover": float(pd.to_numeric(history["amount"], errors="coerce").mean()),
    }


def _industry_percentiles(peer_history: pd.DataFrame) -> pd.DataFrame:
    """计算同行中的收益、稳健性和回撤控制分位。"""
    records: list[dict] = []
    for code, group in peer_history.groupby("code", sort=False):
        group = group.sort_values("date")
        close = pd.to_numeric(group["close"], errors="coerce").dropna()
        returns = pd.to_numeric(group["ret"], errors="coerce")
        if len(close) < 2:
            continue
        max_drawdown, _ = _maximum_drawdown(close)
        records.append(
            {
                "code": code,
                "name": str(group["name"].iloc[-1]),
                "period_return": float(close.iloc[-1] / close.iloc[0] - 1.0),
                "annualized_volatility": float(returns.std(ddof=1) * np.sqrt(252)),
                "max_drawdown": max_drawdown,
            }
        )
    peers = pd.DataFrame(records)
    if peers.empty:
        return peers
    peers["return_percentile"] = peers["period_return"].rank(pct=True)
    peers["stability_percentile"] = peers["annualized_volatility"].rank(
        pct=True, ascending=False
    )
    peers["drawdown_control_percentile"] = peers["max_drawdown"].rank(pct=True)
    return peers


def _format_money(value: float) -> str:
    if pd.isna(value):
        return "--"
    if abs(value) >= 1e8:
        return f"{value / 1e8:.2f}亿"
    if abs(value) >= 1e4:
        return f"{value / 1e4:.2f}万"
    return f"{value:,.0f}"


def render_stock_profile() -> None:
    st.title("🎯 股票画像")
    st.caption("交互明细层：选股后才查询单股时序与所属行业同行，不加载全市场明细。")

    catalog = get_stock_catalog(has_detail=True, limit=1000)
    if catalog.empty:
        st.warning("当前公开服务库没有可查询的股票明细。")
        return

    catalog = catalog.copy()
    catalog["label"] = (
        catalog["code"].astype(str)
        + " · "
        + catalog["name"].astype(str)
        + " · "
        + catalog["industry_l1"].astype(str)
    )
    left, right = st.columns([3, 1])
    with left:
        selected_label = st.selectbox(
            "选择公开分析标的",
            catalog["label"].tolist(),
            key="stock_profile_selector",
        )
    with right:
        window = st.selectbox(
            "分析窗口",
            (60, 120, 252),
            index=2,
            format_func=lambda value: f"近 {value} 交易日",
            key="stock_profile_window",
        )

    code = str(catalog.loc[catalog["label"] == selected_label, "code"].iloc[0])
    metadata = get_stock_metadata(code)
    history = get_stock_history(code, limit=252).tail(window).copy()
    if history.empty:
        st.warning(f"{code} 暂无公开明细。")
        return
    history = history.sort_values("date").reset_index(drop=True)
    metrics = _stock_metrics(history)

    st.subheader(f"{metadata.get('name', code)} · {code}")
    info_columns = st.columns(5)
    info_columns[0].metric("市场", metadata.get("market", "--"))
    info_columns[1].metric("板块", metadata.get("board", "--"))
    info_columns[2].metric("一级行业", metadata.get("industry_l1", "--"))
    info_columns[3].metric("上市日期", metadata.get("list_date", "--"))
    info_columns[4].metric("数据截止", history["date"].max().date().isoformat())

    kpis = st.columns(5)
    kpis[0].metric("最新收盘", f"{metrics['latest_close']:.2f}")
    kpis[1].metric("区间收益", f"{metrics['period_return']:.2%}")
    kpis[2].metric("年化波动率", f"{metrics['annualized_volatility']:.2%}")
    kpis[3].metric("最大回撤", f"{metrics['max_drawdown']:.2%}")
    kpis[4].metric("日均成交额", _format_money(metrics["average_turnover"]))

    price_figure = go.Figure()
    price_figure.add_trace(
        go.Scatter(x=history["date"], y=history["close"], name="收盘价", line={"width": 2})
    )
    for column, label in (("ma5", "MA5"), ("ma20", "MA20"), ("ma60", "MA60")):
        price_figure.add_trace(
            go.Scatter(x=history["date"], y=history[column], name=label, line={"width": 1})
        )
    price_figure.update_layout(
        title="价格走势与移动平均线",
        height=390,
        margin={"l": 20, "r": 20, "t": 55, "b": 20},
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.08},
    )
    st.plotly_chart(price_figure, width="stretch", key="stock_profile_price")

    volume_figure = go.Figure(go.Bar(x=history["date"], y=history["volume"], name="成交量"))
    volume_figure.add_trace(
        go.Scatter(x=history["date"], y=history["volume_ma5"], name="5日均量", line={"width": 2})
    )
    volume_figure.update_layout(
        title="成交量与均量",
        height=300,
        margin={"l": 20, "r": 20, "t": 55, "b": 20},
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.12},
    )
    st.plotly_chart(volume_figure, width="stretch", key="stock_profile_volume")

    indicator_figure = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.10,
        subplot_titles=("RSI", "MACD"),
    )
    indicator_figure.add_trace(
        go.Scatter(x=history["date"], y=history["rsi"], name="RSI"), row=1, col=1
    )
    indicator_figure.add_hline(y=70, line_dash="dot", line_color="#ef4444", row=1, col=1)
    indicator_figure.add_hline(y=30, line_dash="dot", line_color="#22c55e", row=1, col=1)
    indicator_figure.add_trace(
        go.Scatter(x=history["date"], y=history["macd"], name="MACD"), row=2, col=1
    )
    indicator_figure.add_trace(
        go.Scatter(x=history["date"], y=history["macd_signal"], name="Signal"), row=2, col=1
    )
    indicator_figure.add_trace(
        go.Bar(x=history["date"], y=history["macd_hist"], name="Histogram"), row=2, col=1
    )
    indicator_figure.update_layout(
        title="技术指标", height=500,
        margin={"l": 20, "r": 20, "t": 70, "b": 20},
        hovermode="x unified", legend={"orientation": "h", "y": 1.08},
    )
    st.plotly_chart(indicator_figure, width="stretch", key="stock_profile_indicators")

    returns = pd.to_numeric(history["ret"], errors="coerce")
    _, drawdown = _maximum_drawdown(history["close"])
    risk_figure = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12,
        subplot_titles=("日收益率", "净值回撤"),
    )
    risk_figure.add_trace(
        go.Bar(x=history["date"], y=returns, name="日收益率"), row=1, col=1
    )
    risk_figure.add_trace(
        go.Scatter(x=history["date"], y=drawdown, name="回撤", fill="tozeroy", line={"width": 1}),
        row=2, col=1,
    )
    risk_figure.update_layout(
        title="收益与风险", height=470,
        margin={"l": 20, "r": 20, "t": 70, "b": 20},
        hovermode="x unified", showlegend=False,
    )
    risk_figure.update_yaxes(tickformat=".1%")
    st.plotly_chart(risk_figure, width="stretch", key="stock_profile_risk")

    st.subheader("行业分位对比")
    peer_history = get_industry_peer_history(
        str(metadata.get("industry_l1", "")),
        start_date=history["date"].min(),
        end_date=history["date"].max(),
        limit=50000,
    )
    peers = _industry_percentiles(peer_history)
    selected_peer = peers.loc[peers["code"] == code]
    if selected_peer.empty:
        st.info("当前窗口内的同行样本不足，暂不计算分位。")
    else:
        peer = selected_peer.iloc[0]
        cols = st.columns(4)
        cols[0].metric("同行样本", f"{len(peers)} 只")
        cols[1].metric("区间收益分位", f"{peer['return_percentile']:.0%}")
        cols[2].metric("低波动稳健分位", f"{peer['stability_percentile']:.0%}")
        cols[3].metric("回撤控制分位", f"{peer['drawdown_control_percentile']:.0%}")
        comparison = peers.nlargest(min(15, len(peers)), "period_return").copy()
        comparison["label"] = comparison["code"] + " · " + comparison["name"]
        colors = ["#ef4444" if value == code else "#3b82f6" for value in comparison["code"]]
        peer_figure = go.Figure(
            go.Bar(x=comparison["period_return"], y=comparison["label"], orientation="h", marker_color=colors)
        )
        peer_figure.update_layout(
            title=f"{metadata.get('industry_l1', '')}行业区间收益 Top 15",
            height=max(340, len(comparison) * 27),
            margin={"l": 20, "r": 20, "t": 55, "b": 20},
            xaxis_tickformat=".1%", yaxis={"categoryorder": "total ascending"},
        )
        st.plotly_chart(peer_figure, width="stretch", key="stock_profile_peers")

    st.caption(
        "公开作品集页面使用固定种子生成的合成演示行情；"
        "指标只用于展示按需查询和分析能力，不构成投资建议。"
    )
