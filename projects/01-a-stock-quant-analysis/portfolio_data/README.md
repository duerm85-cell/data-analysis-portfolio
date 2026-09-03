# 公开作品集数据包

本目录的公开数据由两个可重复步骤生成：

1. `python scripts/build_portfolio_dataset.py` 使用固定随机种子生成离线 Parquet 构建源；
2. `python scripts/build_demo_serving_db.py` 生成 Streamlit 实际读取的 `demo_serving.db`。

- 交互行情是与任何真实证券价格无对应关系的确定性合成数据，不再分发数据源逐日行情。
- 不包含 Tushare Token、用户数据库、密码摘要或其他凭证。
- 页面会明确标注样本范围、生成时间和“非实时、非投资建议”口径。
- 模型指标与回测曲线只保存小型研究摘要，不包含模型权重或逐样本预测文件。
- 模型指标和归一化回测曲线来自完整本地研究；交互行情来自合成数据，两种口径不会混写。
- Streamlit 不读取整张 `portfolio_factors.parquet`；页面通过 `app/data_access.py` 参数化查询 SQLite，并缓存股票目录、聚合指标和选中股票切片。
- `demo_serving.db` 内含股票维表、公开日线/因子明细、市场与行业日聚合、因子 IC、质量运行和流水线运行记录。
- 完整本地数据库继续由 `.gitignore` 排除，不会上传到 GitHub。

重新生成后应运行 `python scripts/benchmark_queries.py`、单元测试和 Streamlit 逐页冒烟测试，再决定是否提交数据文件。
