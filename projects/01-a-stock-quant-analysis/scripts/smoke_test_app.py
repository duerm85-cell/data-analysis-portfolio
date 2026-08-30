"""逐页执行 Streamlit AppTest，捕获页面级运行时异常。"""

from pathlib import Path
import os
import sys

from streamlit.testing.v1 import AppTest

PROJECT_DIR = Path(__file__).resolve().parents[1]
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))


def main():
    failures = []
    first = AppTest.from_file(str(PROJECT_DIR / 'app_pro.py')).run(timeout=30)
    page_count = len(first.radio[0].options)

    for index in range(page_count):
        app = AppTest.from_file(str(PROJECT_DIR / 'app_pro.py')).run(timeout=30)
        page_name = app.radio[0].options[index]
        app.radio[0].set_value(page_name).run(timeout=30)
        errors = [exception.value for exception in app.exception]
        print(f"[{index + 1}/{page_count}] {page_name}: {'FAIL' if errors else 'OK'}")
        failures.extend(f"{page_name}: {error}" for error in errors)

    if failures:
        print('\n'.join(failures), file=sys.stderr)
        raise SystemExit(1)
    print('All Streamlit pages passed the smoke test.')


if __name__ == '__main__':
    main()
