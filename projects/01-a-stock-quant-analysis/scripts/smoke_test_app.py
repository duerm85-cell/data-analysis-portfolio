"""逐页执行 Streamlit AppTest，捕获页面级运行时异常。"""

from pathlib import Path
import os
import sys
import time

from streamlit.testing.v1 import AppTest

PROJECT_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_DIR.parents[1]
APP_TIMEOUT_SECONDS = int(os.getenv('STREAMLIT_SMOKE_TIMEOUT', '90'))
# 模拟 Streamlit Cloud 从 Git 仓库根目录启动嵌套入口文件。
os.chdir(REPOSITORY_ROOT)


def main():
    failures = []
    portfolio_mode = os.getenv('QUANT_APP_MODE', '').strip().lower() == 'portfolio'
    first = AppTest.from_file(str(PROJECT_DIR / 'app_pro.py')).run(timeout=APP_TIMEOUT_SECONDS)
    page_count = len(first.radio[0].options)

    for index in range(page_count):
        started_at = time.perf_counter()
        app = AppTest.from_file(str(PROJECT_DIR / 'app_pro.py')).run(timeout=APP_TIMEOUT_SECONDS)
        page_name = app.radio[0].options[index]
        app.radio[0].set_value(page_name).run(timeout=APP_TIMEOUT_SECONDS)
        errors = [exception.value for exception in app.exception]
        if portfolio_mode and page_name == '情绪分析':
            unavailable = [
                item.value for item in app.warning
                if '情绪数据暂不可用' in item.value
            ]
            errors.extend(unavailable)
        if portfolio_mode and page_name == '模型预测':
            live_prediction_buttons = [
                item.label for item in app.button if '开始预测' in item.label
            ]
            if live_prediction_buttons:
                errors.append('公开模式不应提供需要本地模型权重的实时预测按钮')
        if portfolio_mode and page_name == '策略回测':
            missing_holdings = [
                item.value for item in app.info
                if '未找到每日持仓文件' in item.value
            ]
            errors.extend(missing_holdings)
        elapsed = time.perf_counter() - started_at
        print(
            f"[{index + 1}/{page_count}] {page_name}: "
            f"{'FAIL' if errors else 'OK'} ({elapsed:.2f}s)"
        )
        failures.extend(f"{page_name}: {error}" for error in errors)

    if failures:
        print('\n'.join(failures), file=sys.stderr)
        raise SystemExit(1)
    print('All Streamlit pages passed the smoke test.')


if __name__ == '__main__':
    main()
