# FINAL RELEASE FILE LIST

版本目的：冻结量化金融 Dashboard 的最终作品集发布版本。

## 1. Final code

本次发布提交：

- `projects/01-a-stock-quant-analysis/app_pro.py`
  - 最终 Streamlit Dashboard 入口。
  - 包含已验证的五组 Sidebar 和 10 个页面入口，以及最终导航视觉样式。
  - 本次仅包含展示层样式调整，不改变页面路由、数据、模型或回测逻辑。

仓库中已存在并继续作为最终代码组成部分的核心模块包括数据处理、因子工程、模型训练、回测、SQLite 和测试代码；本次不重新改动这些文件。

## 2. Final data/result files

本次发布提交：

- `projects/01-a-stock-quant-analysis/reports/benchmark_results.json`
  - 公开服务层查询性能基准结果。
  - 被 `reports/README.md`、阶段性能说明、基准脚本和测试引用，不属于孤立临时文件。

仓库中已经存在且作为当前研究结果使用的文件包括：

- `projects/01-a-stock-quant-analysis/reports/model_comparison.csv`
- `projects/01-a-stock-quant-analysis/portfolio_data/portfolio_training_log.json`
- `projects/01-a-stock-quant-analysis/portfolio_data/portfolio_backtest_metrics.csv`
- `projects/01-a-stock-quant-analysis/portfolio_data/portfolio_backtest_results.csv`

这些文件中的当前正式口径为 21 个技术因子、XGBoost/BiLSTM 分类结果和 `next_open_v2` 回测结果。

## 3. Final documentation

本次发布提交：

- `projects/01-a-stock-quant-analysis/docs/面试作品集说明.md`
  - 面向求职展示的项目架构、数据口径、模型实验、回测边界和面试解释材料。
- `FINAL_RELEASE_FILE_LIST.md`
  - 本发布版本的文件清单和排除范围。

仓库中已存在并继续作为最终说明入口的 `projects/01-a-stock-quant-analysis/README.md` 不在本次修改范围内。

## 4. Excluded development logs

以下文件保留在本地，不进入本次提交，也不删除：

- `CLEANUP_REPORT.md`
- `FINAL_COMMIT_PLAN.md`
- `FINAL_RELEASE_CHECK.md`
- `FINAL_REPOSITORY_CLEANUP.md`
- `FINAL_SCREENSHOT_CHECKLIST.md`
- `SCREENSHOT_UPDATE_PLAN.md`
- `UI_REDESIGN_AUDIT.md`
- `UI_REDESIGN_CHANGELOG.md`
- `PHASE2_CHANGELOG.md`
- `PHASE3_CHANGELOG.md`
- `PHASE4_CHANGELOG.md`

这些文件属于过程审计、阶段记录或本地发布检查，不是运行时依赖和最终作品展示材料。

## 5. Commit 3 release scope

本次 Release Freeze 只允许暂存以下四个文件：

1. `projects/01-a-stock-quant-analysis/app_pro.py`
2. `projects/01-a-stock-quant-analysis/docs/面试作品集说明.md`
3. `projects/01-a-stock-quant-analysis/reports/benchmark_results.json`
4. `FINAL_RELEASE_FILE_LIST.md`

不执行任何代码、数据、模型、回测或 README 内容修改。
