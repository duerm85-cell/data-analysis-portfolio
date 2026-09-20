# Final Screenshot Guide

这份文档用于 README 的最终作品集截图。截图只展示当前 Streamlit Dashboard 的研究结果和信息架构，不改变任何数据、模型、回测或页面逻辑。

## 统一截图规范

- 浏览器内容区建议使用 **1600 × 1000 px**，浏览器缩放保持 **100%**。
- 保持左侧 Sidebar 展开，使业务分组和当前页面名称可见。
- 使用当前浅色专业主题，截图中不要保留浏览器地址栏、开发者工具、系统通知或鼠标悬停提示。
- 五张截图使用同一窗口尺寸、同一主题和同一版本结果，便于面试官横向比较。
- 截图范围以“页面标题、定位说明、核心 KPI 和主图”为主；详细表格、日志和参数不需要全部铺开。
- 当前正式结果只能使用 Phase 3 口径：XGBoost Accuracy 52.71%、AUC 0.5276；BiLSTM Accuracy 51.43%、AUC 0.5185；`next_open_v2` 策略收益 -28.31%、沪深 300 +2.18%、最大回撤 -37.32%、Sharpe -0.88。

## README 推荐展示的 5 张截图

| 顺序 | README 页面名称 | 对应 Dashboard 页面 | 推荐文件名 | 当前状态 |
|---:|---|---|---|---|
| 1 | System Overview | 系统概览 | `docs/screenshots/system_overview.png` | 待重新截图 |
| 2 | Data Platform | 数据平台 | `docs/screenshots/data_platform.png` | 待重新截图 |
| 3 | Factor Research | 因子研究 | `docs/screenshots/factor_analysis.png` | 已有参考图，需确认是否为当前 UI |
| 4 | Model Validation | 模型验证 | `docs/screenshots/prediction_panel.png` | 已有参考图，需确认是否为当前结果 |
| 5 | Strategy Backtest | 策略回测 | `docs/screenshots/backtest_curve.png` | 已有参考图，需确认是否为当前结果 |

### 1. System Overview

对应页面：Sidebar → `SYSTEM` → `系统概览`。

截图必须展示完整研究流程卡片，并让面试官一眼看出项目的模块边界：

```text
数据采集 → 数据质量检查 → 因子工程 → 机器学习模型 → 策略回测 → Streamlit Dashboard
```

建议画面包含：

- 页面标题“量化研究系统 · Pipeline Overview”和一句话定位。
- 六个阶段卡片及其顺序、阶段编号和简短说明。
- 下方运行概览中的数据状态、模型状态和研究证据入口。
- Sidebar 中的 `DATA ENGINEERING`、`FACTOR & ML RESEARCH`、`STRATEGY RESEARCH`、`SYSTEM` 分组。

截图中避免出现：

- 把 Pipeline 截成只有一行文字、看不出阶段边界的画面。
- 展开训练日志、原始路径、缓存信息或调试异常。
- 旧版平级页面导航、旧标题或过时指标。
- 把 Pipeline 描述成生产级 Kafka、Flink、Airflow 链路。

### 2. Data Platform

对应页面：Sidebar → `DATA ENGINEERING` → `数据平台`。

截图必须同时呈现数据规模、覆盖范围和质量状态，建议画面包含：

- 页面标题“数据工程 · 数据资产与质量管理”。
- 项目定位说明：“从数据采集、质量校验、因子构建到模型验证的完整量化研究流程”。
- 五个现有资产 KPI：股票数量、数据记录数、字段数量、数据时间范围、数据质量状态。
- 数据质量概览图，能够看到通过、预期缺失和异常检查项的区别。
- 数据口径提示，明确本地真实研究数据与公开合成服务层的区别。

截图中避免出现：

- 只截到资产数量，却没有时间范围和质量状态。
- 把公开 Demo 的合成资产目录误写成真实股票行情。
- Tushare Token、数据库凭证、用户信息、完整本地路径或原始明细表。
- 把结构性因子窗口缺失隐藏成“无缺失”，或裁掉质量图的图例和状态。

### 3. Factor Research

对应页面：Sidebar → `FACTOR & ML RESEARCH` → `因子研究`。

建议画面包含：

- 页面标题“因子研究 · 21个技术因子体系”和因子分类说明。
- 选中的股票、观测天数、最新收盘、数据起始和数据截止等首屏 KPI。
- 价格与 MA5/MA20 主图。
- 如果画面空间允许，可展示因子相关性热力图的一部分，但不要让热力图压缩主图。

截图中避免出现：

- 将候选字段、公开 IC 展示字段和 21 个正式模型输入因子混为一谈。
- 展开过多 IC 序列、原始数据表或无法解释的参数。
- 使用旧版因子标题、旧截图指标或声称因子具有因果预测能力。

### 4. Model Validation

对应页面：Sidebar → `FACTOR & ML RESEARCH` → `模型验证`。

建议画面包含：

- 页面标题“机器学习模型验证”和任务说明：预测下一交易日涨跌。
- XGBoost 与 BiLSTM 的统一实验对比表。
- 当前模型核心 KPI：Accuracy、AUC、Precision、Recall、F1。
- XGBoost Top 10 特征重要性入口或图表，以及“相对贡献、不代表因果”的说明。
- 页面底部的技术参考图可以保留，但应明确它不是价格预测图。

截图中避免出现：

- 旧 AUC、旧 Accuracy、旧截图或历史实验数字。
- “股票预测系统”“AI 交易机器人”“稳定盈利”等描述。
- 需要本地模型权重的实时预测按钮、训练日志堆栈或本地文件路径。
- 裁掉任务定义、数据切分和模型限制说明。

### 5. Strategy Backtest

对应页面：Sidebar → `STRATEGY RESEARCH` → `策略回测`。

建议画面包含：

- 页面标题“策略研究 · 回测评价”。
- Current Results 区域的策略收益、沪深 300、超额收益、最大回撤、Sharpe、换手率、成交笔数和缺少开盘价阻塞。
- 策略净值与沪深 300 基准净值曲线。
- 能够看到策略低于基准的完整曲线，不要裁掉负收益区间。
- 回测时序或成本说明入口：T 日收盘生成信号、T+1 开盘执行、佣金、印花税和滑点。

截图中避免出现：

- 只截取策略局部上涨区间，或隐藏后段回撤。
- 用旧 close-to-close 结果替代 `next_open_v2`。
- 隐藏负收益、最大回撤、负 Sharpe、高换手率或成交阻塞。
- 把回测曲线描述成稳定盈利、实盘验证或投资建议。

## 当前 10 页布局检查记录

| 业务分组 | 页面 | 当前首屏结构 | 详细内容位置 |
|---|---|---|---|
| DATA ENGINEERING | 数据平台 | 标题、定位说明、5 个资产与质量 KPI、质量概览图 | 服务层规模、数据血缘、缺失字段明细在 Expander |
| DATA ENGINEERING | 数据洞察 | 标题、定位说明、4 个市场结构 KPI、板块分布图 | 收盘趋势、成交量、情绪变化在 Expander |
| MARKET ANALYSIS | 市场总览 | 标题、定位说明、涨跌和成交 KPI、核心行情/排行图 | 明细表、分布和次要排行在 Expander |
| MARKET ANALYSIS | 股票画像 | 标题、定位说明、个股信息与风险 KPI、价格和成交量图 | RSI/MACD、收益风险、同行排名在 Expander |
| MARKET ANALYSIS | 行业分析 | 标题、定位说明、行业数量/窗口/日期/上涨行业 KPI、行业排名图 | 明细表、热力图、成交变化在 Expander |
| MARKET ANALYSIS | 情绪分析 | 标题、定位说明、平均情绪/波动/正面占比/样本量 KPI、情绪走势 | 样本量、情绪收益关系、情绪择时和记录样例在 Expander |
| FACTOR & ML RESEARCH | 因子研究 | 标题、定位说明、标的与窗口 KPI、价格和均线图 | RSI/MACD、相关性细节、IC 分析在 Expander |
| FACTOR & ML RESEARCH | 模型验证 | 标题、任务说明、模型对比、当前模型 KPI | 训练说明、日志、特征重要性细节在 Expander |
| STRATEGY RESEARCH | 策略回测 | 标题、定位说明、Current Results KPI、策略与基准净值图 | 结果解释、持仓、其他指标、回撤和成本在 Expander |
| SYSTEM | 系统概览 | 标题、定位说明、六阶段 Pipeline、数据/模型运行概览 | 模型对比和研究解释在 Expander |

## 截图交付前检查

- 截图中的 Sidebar 只有一套分组导航，不能出现旧版“页面导航”radio。
- 页面标题、页面定位和截图文件名与 README 保持一致。
- 模型和回测数字与 `Current Results` 唯一口径一致。
- System Overview 和 Data Platform 的截图需补齐后，才算完成五张最终作品集截图。
- 截图不包含密钥、用户信息、原始数据明细、本地绝对路径或调试堆栈。
- 只把确认过与当前 UI 和结果一致的图片放入 README；`main_panel.png` 属于旧版布局，不作为最终五张截图之一。
