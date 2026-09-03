# Demo Serving SQLite Schema

`portfolio_data/demo_serving.db` 是公开 Streamlit 应用的只读服务层。它由
`scripts/build_demo_serving_db.py` 从公开作品集数据包离线生成，不改变本地真实研究流水线、模型训练或回测文件。

## 设计边界

- 公开交互数据与真实研究结果分离：日线和因子明细均为确定性合成数据；真实模型/回测只保留摘要文件。
- 公开规模分为5,200只资产目录、5,200只口径的3年预聚合，以及300只×252日交互明细；三种口径在 manifest 中分别记录。
- 保留原 `portfolio_factors.parquet` 的 48 个字段，以兼容现有页面；查询层按页面显式选择列，禁止 `SELECT *`。
- 市场、行业、因子 IC 和质量结果在建库阶段预聚合，网页请求不扫描整张因子宽表。
- 数据库以临时文件完整构建、校验后原子替换，因此脚本可重复执行，不会留下半成品数据库。

## 表与用途

| 表 | 粒度 | 用途 |
|---|---|---|
| `dim_stock` | 每只股票一行 | 股票目录、板块、演示行业、是否有明细 |
| `fact_stock_daily_demo` | 股票 × 交易日 | 公开日线、技术因子、合成情绪；按股票和日期查询 |
| `fact_market_daily` | 每交易日一行 | 市场宽度、成交量额、均价、平均/中位收益、平均情绪 |
| `fact_industry_daily` | 行业 × 交易日 | 行业收益、成交、上涨比例和情绪趋势 |
| `fact_factor_ic_daily` | 因子 × 交易日 | 因子与下一期标签的横截面 Spearman IC |
| `fact_data_quality_run` | 每次质量运行一行 | 数据水位、规模、核心异常数、质量评分 |
| `fact_data_quality_issue` | 运行 × 规则 × 字段 | 质量问题明细及结构性/未预期分类 |
| `pipeline_run` | 每次发布任务一行 | 数据版本、来源、口径、输入输出和运行状态；同时为 manifest 接口提供数据 |

## 索引

- `fact_stock_daily_demo` 的主键 `(code, date)` 支持单股日期范围查询，不再创建重复普通索引。
- `idx_stock_daily_date(date)` 支持某交易日市场截面。
- `idx_stock_industry_l1(industry_l1, code)` 支持行业股票筛选。
- `idx_stock_has_detail(has_detail, code)` 支持公开明细股票列表。
- `idx_industry_daily_date(date, industry_l1)` 支持某日行业横截面。
- `idx_factor_ic_date(date, factor_name)` 支持某日因子横截面。
- `idx_quality_run_started_at(started_at DESC)` 支持最近质量运行查询。

完整 DDL 位于 `sql/demo_serving_schema.sql`。建库结束后脚本执行 `ANALYZE`，查询计划可由 `app/data_access.py` 的 `explain_named_query()` 查看。
