# 运行报告目录

此目录存放数据质量、性能基准和流水线运行报告。默认生成文件不纳入版本控制；
`benchmark_results.json` 作为公开服务层的可复核性能证据会随代码提交。
`stage2_optimization_report.md` 和 `stage2_performance_comparison.json` 记录三阶段口径、扩容结果和解读边界。

```bash
python data_quality.py
python scripts/benchmark_queries.py
```
