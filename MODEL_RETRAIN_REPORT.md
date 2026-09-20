# 模型重新训练报告

## 统一实验口径

- 任务：预测下一交易日涨跌，`label > 0` 为上涨；
- 数据：同一本地研究因子表，364 只股票；
- 数据范围：2020-02-10 至 2026-08-27；
- 切分：70%/15%/15% 按时间顺序切分，不随机打乱；
- 分界：剔除会跨区间引用标签的 2024-10-10、2025-09-15；训练集截至 2024-10-09，验证集为 2024-10-11 至 2025-09-12，测试集为 2025-09-16 至 2026-08-27；
- 特征：相同 21 个技术特征；来源未验证的情绪特征不进入训练。

## 结果

| 模型 | Accuracy | AUC | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| XGBoost | 52.71% | 0.5276 | 49.06% | 42.43% | 45.50% |
| BiLSTM | 51.43% | 0.5185 | 47.83% | 48.22% | 48.03% |

两种模型的 AUC 都接近 0.5，只有很弱的样本外区分能力。XGBoost 的 Accuracy、AUC 和 Precision 略高，BiLSTM 的 Recall 和 F1 略高，但都没有形成足以支持交易优势的差距。这些结果不能解释为稳定预测能力。

XGBoost 使用完整训练表；BiLSTM 因 20 日序列的本地 CPU 计算量，从 381,668 个训练序列中按固定规则等距选取 120,000 个。BiLSTM 的 82,941 个验证目标和 83,259 个测试目标全部参与评估，测试目标与 XGBoost 使用相同日期和股票记录。这个训练样本量差异属于实验限制，不应省略。

## XGBoost Top 10 特征重要性

| 排名 | 特征 | 重要性 |
|---:|---|---:|
| 1 | `reversal_5d` | 0.0994 |
| 2 | `close_open_ratio` | 0.0673 |
| 3 | `ret_5d` | 0.0624 |
| 4 | `bb_position` | 0.0539 |
| 5 | `momentum_20d` | 0.0521 |
| 6 | `high_low_ratio` | 0.0499 |
| 7 | `amount_ratio` | 0.0479 |
| 8 | `ma10` | 0.0457 |
| 9 | `volatility_20d` | 0.0446 |
| 10 | `ma20` | 0.0443 |

短期反转、开收盘关系和近 5 日收益贡献最高，振幅、动量、布林带位置与量额特征提供补充。这里的贡献是模型内部的相对分裂重要性，不表示影响方向或因果关系。

## 输入特征

`ret_5d`、`ma5`、`ma10`、`ma20`、`ma5_ma10_diff`、`ma5_ma20_diff`、`rsi`、`macd`、`macd_signal`、`momentum_20d`、`reversal_5d`、`volatility_20d`、`volatility_60d`、`bb_mid`、`bb_position`、`volume_ma5`、`volume_ratio`、`amount_ma20`、`amount_ratio`、`high_low_ratio`、`close_open_ratio`。

## 保存产物

- XGBoost：`results_optimized/xgb_fixed.json`；
- BiLSTM：`results_optimized/lstm_fixed.pth`；
- 训练配置与切分：`training_log.json`、`results_optimized/model_config.txt`；
- 特征列表：`xgb_feature_list.txt`、`feature_list.txt`；
- XGBoost 重要性：`xgb_classifier_feature_importance.csv`；
- XGBoost 测试集概率：`test_predictions_classification.csv`。

模型权重和逐行预测是本地研究产物，由 `.gitignore` 排除；公开仓库只保存脱敏指标、重要性摘要和结果曲线。
