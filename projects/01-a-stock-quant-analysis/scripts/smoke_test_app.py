"""逐页执行 Streamlit AppTest，验证分组 Sidebar 和页面级运行时状态。"""

from html import unescape
from pathlib import Path
import os
import re
import sys
import time

from streamlit.testing.v1 import AppTest


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_DIR.parents[1]
APP_TIMEOUT_SECONDS = int(os.getenv("STREAMLIT_SMOKE_TIMEOUT", "90"))

NAVIGATION_GROUPS = {
    "DATA ENGINEERING": {
        "数据平台": "nav_platform",
        "数据洞察": "nav_data_insight",
    },
    "MARKET ANALYSIS": {
        "市场总览": "nav_dashboard",
        "股票画像": "nav_stock_profile",
        "行业分析": "nav_industry",
        "情绪分析": "nav_sentiment",
    },
    "FACTOR & ML RESEARCH": {
        "因子研究": "nav_factor",
        "模型验证": "nav_prediction",
    },
    "STRATEGY RESEARCH": {
        "策略回测": "nav_backtest",
    },
    "SYSTEM": {
        "系统概览": "nav_overview",
    },
}
EXPECTED_GROUPS = tuple(NAVIGATION_GROUPS)
EXPECTED_PAGES = tuple(
    page_name
    for group_pages in NAVIGATION_GROUPS.values()
    for page_name in group_pages
)
NAVIGATION_KEYS = {
    page_name: button_key
    for group_pages in NAVIGATION_GROUPS.values()
    for page_name, button_key in group_pages.items()
}

# 模拟 Streamlit Cloud 从 Git 仓库根目录启动嵌套入口文件。
os.chdir(REPOSITORY_ROOT)


def _navigation_buttons(app):
    """按稳定的 Streamlit 控件 key 获取二级导航按钮。"""
    return {
        item.key: item
        for item in app.button
        if getattr(item, "key", "") in NAVIGATION_KEYS.values()
    }


def _sidebar_group_labels(app):
    """从 Sidebar 的结构化 CSS class 中提取一级业务分组。"""
    labels = set()
    pattern = re.compile(r"class=['\"]sidebar-group['\"]>(.*?)</div>", re.DOTALL)
    for item in app.markdown:
        value = str(getattr(item, "value", ""))
        match = pattern.search(value)
        if match:
            labels.add(unescape(match.group(1)).strip())
    return labels


def _legacy_page_radios(app):
    """旧版页面导航 radio 不属于当前 Sidebar；模型选择 radio 可以存在。"""
    return [
        item
        for item in app.radio
        if "页面导航" in str(getattr(item, "label", ""))
    ]


def _run_app():
    return AppTest.from_file(str(PROJECT_DIR / "app_pro.py")).run(
        timeout=APP_TIMEOUT_SECONDS
    )


def _validate_navigation_shell(app):
    failures = [f"应用入口: {exception.value}" for exception in app.exception]
    if _legacy_page_radios(app):
        failures.append("检测到旧版页面导航 radio")

    groups = _sidebar_group_labels(app)
    missing_groups = sorted(set(EXPECTED_GROUPS) - groups)
    if missing_groups:
        failures.append(f"缺少一级业务分组：{missing_groups}")

    navigation = _navigation_buttons(app)
    expected_keys = set(NAVIGATION_KEYS.values())
    if set(navigation) != expected_keys:
        failures.append(
            f"二级页面入口不完整：期望 {sorted(expected_keys)}，实际 {sorted(navigation)}"
        )
    if len(navigation) != len(EXPECTED_PAGES):
        failures.append(
            f"页面数量不符合预期：期望 {len(EXPECTED_PAGES)}，实际 {len(navigation)}"
        )
    return failures, navigation


def _validate_page_specific_constraints(app, page_name):
    failures = [f"{page_name}: {exception.value}" for exception in app.exception]
    if page_name == "情绪分析":
        failures.extend(
            f"{page_name}: {item.value}"
            for item in app.warning
            if "情绪数据暂不可用" in item.value
        )
    if page_name == "模型验证":
        live_prediction_buttons = [
            item.label for item in app.button if "开始预测" in item.label
        ]
        if live_prediction_buttons:
            failures.append("公开模式不应提供需要本地模型权重的实时预测按钮")
    if page_name == "策略回测":
        failures.extend(
            f"{page_name}: {item.value}"
            for item in app.info
            if "未找到每日持仓文件" in item.value
        )
    return failures


def main():
    if os.getenv("QUANT_APP_MODE", "").strip().lower() != "portfolio":
        raise SystemExit("请设置 QUANT_APP_MODE=portfolio 后运行公开模式冒烟测试。")

    first = _run_app()
    failures, _ = _validate_navigation_shell(first)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        raise SystemExit(1)

    for index, page_name in enumerate(EXPECTED_PAGES, 1):
        started_at = time.perf_counter()
        app = _run_app()
        shell_failures, navigation = _validate_navigation_shell(app)
        page_failures = list(shell_failures)
        button_key = NAVIGATION_KEYS[page_name]
        target = navigation.get(button_key)
        if target is None:
            page_failures.append(f"{page_name}: 未找到导航按钮 {button_key}")
        else:
            app = target.click().run(timeout=APP_TIMEOUT_SECONDS)
            page_failures.extend(_validate_page_specific_constraints(app, page_name))
            try:
                current_page = app.session_state["main_page"]
            except KeyError:
                page_failures.append(f"{page_name}: st.session_state.main_page 不存在")
            else:
                if current_page != page_name:
                    page_failures.append(
                        f"{page_name}: 页面状态未更新，实际为 {current_page!r}"
                    )

        elapsed = time.perf_counter() - started_at
        status = "FAIL" if page_failures else "OK"
        print(f"[{index}/{len(EXPECTED_PAGES)}] {page_name}: {status} ({elapsed:.2f}s)")
        failures.extend(page_failures)

    if failures:
        print("\n".join(failures), file=sys.stderr)
        raise SystemExit(1)
    print(
        f"All {len(EXPECTED_PAGES)} grouped-sidebar pages passed the public-mode smoke test."
    )


if __name__ == "__main__":
    main()
