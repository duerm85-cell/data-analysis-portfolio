# 工程整理记录

**日期：** 2026-10-07

## 整理范围

本轮整理面向个人数据分析项目的公开展示，主要改善项目入口、运行说明、数据来源文档、测试覆盖和 Streamlit 使用体验。

未修改数据处理公式、21 个正式模型输入、XGBoost、BiLSTM、`next_open_v2`、交易成本或已生成实验结果。

## 主要修改

- `README.md`：改为中文为主的项目入口，保留技术名称、架构、结果、运行方式和限制。
- `.gitignore`：补充环境变量、模型权重、本地数据库和缓存规则。
- `.env.example`：提供安全的 Tushare 环境变量示例。
- `Makefile`、`run_demo.sh`：提供 Demo 安装、数据准备和 Streamlit 启动入口。
- `docs/DATA_SOURCE.md`：说明 Demo Mode 与 Research Mode 的数据来源和公开边界。
- `docs/PROJECT_DESIGN.md`：说明研究问题、模型选择、时间切分、回测时序和限制。
- `tests/test_pipeline_smoke.py`：使用临时目录连接合成数据、因子函数、模型实验快照和回测执行。
- `app_pro.py`：补充项目状态、数据模式和免责声明，并统一页面标题。
- `scripts/smoke_test_app.py`：增加单次点击后导航 active 标记同步检查。

## 导航状态修复

原导航在按钮返回点击结果后才更新 `st.session_state.main_page`。此时该轮脚本中的侧栏按钮已经按旧状态渲染，所以右侧使用新页面，左侧仍显示旧 active 标记。

修复后，按钮通过 `on_click` 回调更新 `main_page`。Streamlit 会在整页重跑前执行回调，因此同一次点击后的页面内容、按钮类型和 `●` 标记使用同一状态。项目没有使用 query parameter 路由，不需要增加第二套页面状态。

## 文档边界

公开 `docs/` 只保留数据来源、字段定义、项目设计和工程记录。简历描述已保留到本地 `docs/history/personal_notes/`，建议继续作为本地个人材料，不提交公开仓库。现有阶段审计和发布检查文档也应继续保留在本地历史目录。

## 验证项目

- Python compile check
- pytest
- Streamlit 10 页 AppTest
- Streamlit 本地健康检查
- README 本地链接检查
- `git diff --check`

测试结果以本轮最终输出为准。

## 当前状态

项目结构和说明已经符合本科个人数据分析项目的公开展示需求。正式研究结论仍受数据授权、历史股票池、复权、停牌、涨跌停和成交近似等条件限制。
