# 原始数据目录

此目录存放 `fetch_stock_data.py` 抓取的逐股票原始 CSV 和 `benchmark_hs300.csv`，不纳入版本控制。文件保持贴源格式，用于追溯和重跑清洗层。

在项目目录配置 `TUSHARE_TOKEN` 后运行：

```bash
python fetch_stock_data.py
```

无 Token 的面试演示可运行 `python scripts/prepare_demo.py`；生成的数据会带有明确的演示来源标签。
