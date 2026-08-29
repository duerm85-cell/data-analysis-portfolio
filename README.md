# 数据分析作品集 | Data Analysis Portfolio

> 数据科学与大数据技术 · Python · SQL · 数据分析 · 量化分析

## 👋 About Me

我是一名数据科学与大数据技术专业本科毕业生，主要学习与实践方向为数据处理、数据库应用与量化数据分析。

在本科阶段系统学习了 Python、MySQL/SQL、统计学、机器学习、Hadoop/Spark、数据可视化等课程，并独立完成了 A 股多因子量化分析系统——从金融数据采集、清洗落库（SQLite）、因子建模到回测与可视化看板的全链路实践（见下方项目 01）。

目前希望寻找数据开发、量化数据方向及相关岗位，希望围绕真实业务数据继续打磨数据清洗校验、数据库管理与数据处理工具开发能力。

## 🛠️ Skills

- **Programming:** Python (Pandas / NumPy)
- **Database / SQL:** MySQL（课程系统学习）· SQLite（项目实战）· SQL 建表 / 查询 / 聚合
- **Financial Data:** Tushare · AKShare · SnowNLP（金融数据源接入与文本情绪处理）
- **Data Analysis:** Statistics, Scipy, Scikit-learn
- **Big Data:** Hadoop, Spark
- **Visualization:** Matplotlib, Plotly, Streamlit
- **Machine Learning:** XGBoost, PyTorch (LSTM)
- **Development Tools:** Git, Linux, VS Code

## 📊 Projects

### 01 · A股多因子与市场情绪融合量化分析系统

**独立开发** · 端到端量化投研与数据工程实践

围绕 A 股市场构建多因子量化分析框架，自主完成从原始数据采集（Tushare/Akshare）、本地数据仓库搭建（SQLite）、因子挖掘与机器学习建模（XGBoost/PyTorch），到滚动窗口回测及 Web 交互看板（Streamlit）的全链路开发。

- 代码与完整说明：👉 [`projects/01-a-stock-quant-analysis/`](projects/01-a-stock-quant-analysis/)
- 技术栈：`Python` `Pandas` `NumPy` `PyTorch` `XGBoost` `Streamlit` `Matplotlib` `SQLite` `Tushare` `Akshare` `SnowNLP`

**主要方向：**

- A 股金融数据获取与清洗落库（Tushare / Akshare + 新闻舆情，raw → clean → processed → SQLite 分层存储，53 万行行情）
- 多因子构建与标准化处理（动量、趋势、波动、情绪共 24+ 因子）
- 因子有效性分析（IC、IR、分组检验）
- 市场情绪指标研究（SnowNLP 情感打分）
- 因子相关性分析（多因子去重与相关性热力图）
- 量化策略回测（Top-N 选股、T+1 日频换仓、严格防止未来信息泄漏）
- 数据可视化（Streamlit 交互式仪表盘：大盘概览 / 因子分析 / 预测回测）

**已做的工程化保证：**

- ✅ **T+1 成交回测**：T 日因子选股，T+1 日收益作为成交口径，不存在同 bar 信息优势
- ✅ **防止数据泄漏**：滚动 Walk-Forward 验证，标准化 scaler 仅在训练窗口 fit，不偷看测试集分布
- ✅ **Token 脱敏**：Tushare/AKShare 通过环境变量读取，不在代码中硬编码密钥
- ✅ **完整依赖清单**：`requirements.txt` 版本锁定 + `run_app.bat` 一键启动
- ✅ **Streamlit 应用**：`streamlit run app_pro.py` 即可打开完整交互界面

## 📈 Currently Learning

- Python 数据分析工程化
- SQL 多表分析与窗口函数
- 量化因子研究
- 数据可视化最佳实践
- Git / GitHub 开源协作

## 🎯 Career Goal

希望从量化数据开发 / 数据开发方向入手，围绕真实金融与业务数据，积累数据清洗校验、数据库管理、数据接口与数据处理工具开发的工程经验，成为策略研究与业务团队中可靠的数据支持角色。

---

⭐ This repository is continuously updated with new projects and analysis practices.