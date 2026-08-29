# 加工数据目录

此目录存放因子工程生成的 CSV/Parquet 数据集，不纳入版本控制。因子生成后会通过分块 upsert 同步到 `data/stock_data.db`，SQLite 是看板的首选服务层。

清洗数据准备完成后运行：

```bash
python factor_engineering_with_sentiment.py
```
