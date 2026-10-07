#!/usr/bin/env sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR="$REPOSITORY_ROOT/projects/01-a-stock-quant-analysis"
PYTHON_BIN=${PYTHON_BIN:-python3}

cd "$PROJECT_DIR"
"$PYTHON_BIN" -m pip install -r requirements.txt
"$PYTHON_BIN" scripts/prepare_demo.py
QUANT_APP_MODE=portfolio exec "$PYTHON_BIN" -m streamlit run app_pro.py
