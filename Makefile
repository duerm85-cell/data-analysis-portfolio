PYTHON ?= python3
PROJECT_DIR := projects/01-a-stock-quant-analysis

.PHONY: demo install-demo prepare-demo dashboard test

install-demo:
	cd $(PROJECT_DIR) && $(PYTHON) -m pip install -r requirements.txt

prepare-demo:
	cd $(PROJECT_DIR) && $(PYTHON) scripts/prepare_demo.py

dashboard:
	cd $(PROJECT_DIR) && QUANT_APP_MODE=portfolio $(PYTHON) -m streamlit run app_pro.py

demo: install-demo prepare-demo dashboard

test:
	cd $(PROJECT_DIR) && $(PYTHON) -m pytest -q
