# 特征口径说明

本文说明项目中三个容易混淆的字段口径：24 个候选字段、21 个正式模型输入技术因子，以及 17 个公开 IC 展示字段。三者服务于不同环节，数量不同不代表实验结果冲突。

## 1. 24 个候选字段

候选字段定义在 `projects/01-a-stock-quant-analysis/model_training.py` 的 `CLASSIC_FEATURES`，Streamlit 本地推理兼容列表位于 `app_pro.py` 的 `FULL_FEATURES`。两处均包含 21 个技术因子和 3 个情绪候选字段。

| 类别 | 字段 |
|---|---|
| 收益与趋势 | `ret_5d`、`ma5`、`ma10`、`ma20`、`ma5_ma10_diff`、`ma5_ma20_diff` |
| 动量与反转 | `rsi`、`macd`、`macd_signal`、`momentum_20d`、`reversal_5d` |
| 波动与区间位置 | `volatility_20d`、`volatility_60d`、`bb_mid`、`bb_position` |
| 成交与量价关系 | `volume_ma5`、`volume_ratio`、`amount_ma20`、`amount_ratio`、`high_low_ratio`、`close_open_ratio` |
| 情绪候选 | `sentiment`、`sentiment_ma5`、`sentiment_ma10` |

候选列表表示代码可以识别的字段范围，不等于每次训练都会使用全部字段。

## 2. 21 个正式模型输入技术因子

当前正式 XGBoost 和 BiLSTM 实验实际使用以下 21 个字段：

```text
ret_5d
ma5
ma10
ma20
ma5_ma10_diff
ma5_ma20_diff
rsi
macd
macd_signal
momentum_20d
reversal_5d
volatility_20d
volatility_60d
bb_mid
bb_position
volume_ma5
volume_ratio
amount_ma20
amount_ratio
high_low_ratio
close_open_ratio
```

`model_training.py::_verified_model_features` 会检查情绪数据来源。当前情绪来源未达到正式训练的验证条件，因此 `sentiment`、`sentiment_ma5` 和 `sentiment_ma10` 被排除。最终训练日志中 XGBoost 和 BiLSTM 的 `feature_count` 均为 21，两个模型使用相同的正式输入集合。

对应证据：

- 训练候选定义：`model_training.py::CLASSIC_FEATURES`
- 来源过滤规则：`model_training.py::_verified_model_features`
- XGBoost 实际字段文件：`results_optimized/xgb_feature_list.txt`
- BiLSTM 实际字段文件：`results_optimized/feature_list.txt`
- 脱敏训练摘要：`portfolio_data/portfolio_training_log.json`

## 3. 17 个公开 IC 展示字段

公开 IC 页面使用 `scripts/build_demo_serving_db.py::FACTOR_IC_COLUMNS` 定义的展示子集：

```text
ret_5d
momentum_20d
reversal_5d
ma5_ma10_diff
ma5_ma20_diff
macd
rsi
volatility_20d
volatility_60d
bb_position
volume_ratio
amount_ratio
high_low_ratio
close_open_ratio
sentiment
sentiment_ma5
sentiment_ma10
```

这 17 个字段用于公开 Demo 服务库中的 IC 查询和页面展示。其中包含 14 个技术因子和 3 个情绪字段。公开 IC 展示用于说明分析流程，不等于正式模型的输入集合；情绪字段出现在展示层，也不表示它们已进入正式模型训练。

## 面试解释口径

项目先维护 24 个候选字段。由于当前情绪数据来源尚未充分验证，正式模型只使用其中 21 个技术因子。公开 Demo 为控制数据体积和页面查询范围，只发布 17 个代表性字段的 IC 结果。因此应分别表述为“24 个候选字段”“21 个正式模型输入技术因子”和“17 个公开 IC 展示字段”。

