# model_training_optimized.py - 优化版
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
print("=" * 60)
print("model_training_optimized.py 开始执行...")
print(f"Python版本: {sys.version}")
print("=" * 60)

import pandas as pd
print("[OK] Pandas导入成功")

import numpy as np
print("[OK] NumPy导入成功")

import xgboost as xgb
print("[OK] XGBoost导入成功")

from sklearn.metrics import mean_squared_error, r2_score, accuracy_score
from sklearn.feature_selection import SelectKBest, f_regression, mutual_info_regression
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
print("[OK] sklearn导入成功")

import matplotlib.pyplot as plt
import matplotlib
print("[OK] Matplotlib导入成功")

import os
import time
import json
import warnings
from datetime import datetime
warnings.filterwarnings('ignore')

# ========== 路径基准：全部以本文件所在目录为根，不依赖 cwd ==========
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
def _P(*parts):
    return os.path.join(_BASE_DIR, *parts)


# 设置中文字体
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

class OptimizedStockPredictor:
    """优化版股票预测模型"""

    def __init__(self):
        self.model = None
        self.baseline_model = None
        self.scaler = StandardScaler()
        self.selected_features = None
        self.results_dir = _P('results_optimized')
        os.makedirs(self.results_dir, exist_ok=True)

    def load_data(self):
        """加载因子数据"""
        print("=" * 60)
        print("股票量化分析系统 - 优化版模型训练")
        print("=" * 60)

        data_path_parquet = _P('data', 'processed', 'all_factors.parquet')
        data_path_csv = _P('data', 'processed', 'all_factors.csv')

        if os.path.exists(data_path_parquet):
            print(f"从Parquet文件读取数据: {data_path_parquet}")
            df = pd.read_parquet(data_path_parquet)
            # 确保日期列正确解析
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
        elif os.path.exists(data_path_csv):
            print(f"从CSV文件读取数据: {data_path_csv}")
            df = pd.read_csv(data_path_csv, parse_dates=['date'])
        else:
            print("错误: 找不到处理后的数据文件!")
            return None

        print(f"\n数据概览:")
        print(f"总样本数: {len(df):,}")
        print(f"特征数量: {len(df.columns)}")
        print(f"股票数量: {df['code'].nunique()}")
        print(f"日期范围: {df['date'].min().strftime('%Y-%m-%d')} 至 {df['date'].max().strftime('%Y-%m-%d')}")

        return df

    def feature_engineering(self, df):
        """优化的特征工程"""
        print("\n进行优化特征工程...")

        tech_features = [c for c in df.columns if c.startswith(('ma', 'rsi', 'macd', 'volatility', 'momentum', 'reversal', 'bb_'))]
        volume_features = [c for c in df.columns if c.startswith(('volume', 'amount'))]
        price_features = ['ret', 'ret_5d', 'ret_10d', 'high_low_ratio', 'close_open_ratio']

        # 创建更多特征交互
        if 'ma5' in df.columns and 'rsi' in df.columns:
            df['ma5_rsi_interact'] = df['ma5'] * df['rsi'] / 100
        if 'ma5' in df.columns and 'ma20' in df.columns:
            df['ma5_ma20_ratio'] = df['ma5'] / (df['ma20'] + 0.001)
        if 'momentum_20d' in df.columns and 'volatility_20d' in df.columns:
            df['momentum_volatility_ratio'] = df['momentum_20d'] / (df['volatility_20d'] + 0.001)
        if 'volume_ratio' in df.columns and 'rsi' in df.columns:
            df['volume_rsi_signal'] = df['volume_ratio'] * (df['rsi'] - 50) / 50

        # 创建趋势特征
        df['trend_ma5_ma20'] = (df['ma5'] > df['ma20']).astype(int)
        df['trend_macd'] = (df['macd'] > df['macd_signal']).astype(int)

        # 记录需要标准化的技术特征（注意：此处不立即fit_transform，
        # 改为在滚动窗口内只fit训练集，避免未来信息泄漏）
        self.tech_features = [c for c in tech_features if c in df.columns]

        return df

    def rolling_train_test_split(self, df, train_window_years=3, test_window_years=1):
        """滚动时间窗口划分"""
        print(f"\n使用滚动窗口训练: 训练窗口={train_window_years}年, 测试窗口={test_window_years}年")

        df['year'] = df['date'].dt.year
        years = sorted(df['year'].unique())

        splits = []
        for i in range(len(years) - train_window_years - test_window_years + 1):
            train_start = years[i]
            train_end = years[i + train_window_years - 1]
            test_end = years[i + train_window_years + test_window_years - 1]

            train_mask = (df['year'] >= train_start) & (df['year'] <= train_end)
            test_mask = (df['year'] > train_end) & (df['year'] <= test_end)

            splits.append({
                'train': df[train_mask].copy(),
                'test': df[test_mask].copy(),
                'period': f"{train_start}-{train_end} -> {train_end+1}-{test_end}"
            })

        print(f"生成 {len(splits)} 个滚动窗口")
        return splits

    def select_features(self, X, y, k=25):
        """改进的特征选择"""
        print(f"\n特征选择: 从 {X.shape[1]} 个特征中选择 top {k}")

        X_filled = X.fillna(0)
        y_clean = y.fillna(0)

        # 组合使用F检验和互信息
        selector = SelectKBest(f_regression, k=min(k, X_filled.shape[1]))
        selector.fit(X_filled, y_clean)

        self.selected_features = X.columns[selector.get_support()]
        print(f"选中的特征: {list(self.selected_features)}")

        return X[self.selected_features]

    def train_model(self, X_train, y_train):
        """训练优化的XGBoost模型和基线模型"""
        print("\n训练优化XGBoost模型...")
        start_time = time.time()

        # 优化的参数配置
        self.model = xgb.XGBRegressor(
            n_estimators=500,           # 更多树
            max_depth=5,                # 更小深度防止过拟合
            learning_rate=0.015,        # 更精细学习率
            subsample=0.6,              # 更强采样
            colsample_bytree=0.6,       # 特征采样
            gamma=0.3,                  # 正则化
            reg_alpha=0.1,              # L1
            reg_lambda=3.0,             # L2
            random_state=42,
            n_jobs=-1,
            objective='reg:squarederror',
            verbosity=0
        )

        self.model.fit(X_train.fillna(0), y_train)

        training_time = time.time() - start_time
        print(f"XGBoost模型训练完成，用时: {training_time:.2f} 秒")

        # 训练简单基线模型用于对比
        print("\n训练简单线性回归基线模型...")
        self.baseline_model = LinearRegression()
        self.baseline_model.fit(X_train.fillna(0), y_train)

        return self.model

    def evaluate_model(self, y_true, y_pred, y_pred_baseline=None, dataset_name="测试集"):
        """综合评估，包括基线对比"""
        mask = ~(np.isnan(y_true) | np.isnan(y_pred))
        y_true_clean = y_true[mask]
        y_pred_clean = y_pred[mask]

        if len(y_true_clean) == 0:
            return None

        # 计算各项指标
        mse = mean_squared_error(y_true_clean, y_pred_clean)
        r2 = r2_score(y_true_clean, y_pred_clean)
        
        direction_actual = np.sign(y_true_clean)
        direction_pred = np.sign(y_pred_clean)
        accuracy = accuracy_score(direction_actual, direction_pred)
        
        ic = np.corrcoef(y_true_clean, y_pred_clean)[0, 1]
        
        # 假设预测收益 > 0 则买入，否则空仓 
        signal = (y_pred_clean > 0).astype(int) 
        # 策略收益 = 信号 * 实际收益（不考虑做空） 
        strategy_return = signal * y_true_clean 
        win_rate = (strategy_return > 0).mean()

        # 计算基线模型指标
        baseline_mse = None
        baseline_r2 = None
        if y_pred_baseline is not None:
            y_pred_baseline_clean = y_pred_baseline[mask]
            baseline_mse = mean_squared_error(y_true_clean, y_pred_baseline_clean)
            baseline_r2 = r2_score(y_true_clean, y_pred_baseline_clean)

        print(f"\n{dataset_name}评估结果:")
        print(f"  MSE: {mse:.6f}")
        if baseline_mse:
            print(f"  基线模型MSE: {baseline_mse:.6f}")
            print(f"  MSE改进: {((baseline_mse - mse) / baseline_mse * 100):.2f}%")
        print(f"  R²: {r2:.4f}")
        if baseline_r2:
            print(f"  基线模型R²: {baseline_r2:.4f}")
        print(f"  方向准确率: {accuracy:.2%}")
        print(f"  信息系数(IC): {ic:.4f}")
        print(f"  胜率(正收益预测正确率): {win_rate:.2%}")

        return {
            'mse': mse,
            'r2': r2,
            'accuracy': accuracy,
            'ic': ic,
            'win_rate': win_rate,
            'baseline_mse': baseline_mse,
            'baseline_r2': baseline_r2
        }

    def plot_results(self, df, y_pred, period):
        """可视化结果"""
        if self.model is not None and self.selected_features is not None:
            importance = self.model.feature_importances_
            feat_imp = pd.Series(importance, index=self.selected_features).sort_values(ascending=False)

            plt.figure(figsize=(12, 7))
            feat_imp.head(15).plot(kind='barh', color='steelblue')
            plt.title(f'Top 15 特征重要性 ({period})', fontsize=14)
            plt.xlabel('重要性得分', fontsize=12)
            plt.ylabel('特征名称', fontsize=12)
            plt.tight_layout()

            feat_imp_path = os.path.join(self.results_dir, f'feature_importance_{period.replace(" -> ", "_")}.png')
            plt.savefig(feat_imp_path, dpi=150, bbox_inches='tight')
            plt.close()
            print(f"特征重要性图已保存: {feat_imp_path}")

            # 保存特征重要性数据
            feat_imp_csv_path = os.path.join(self.results_dir, f'feature_importance_{period.replace(" -> ", "_")}.csv')
            feat_imp.to_csv(feat_imp_csv_path)
            print(f"特征重要性数据已保存: {feat_imp_csv_path}")

    def save_results(self, df, y_pred, period, metrics):
        """保存预测结果"""
        results_df = pd.DataFrame({
            'date': df['date'].values,
            'code': df['code'].values,
            'actual': df['label'].values,
            'predicted': y_pred
        })

        results_path = os.path.join(self.results_dir, f'test_predictions_{period.replace(" -> ", "_")}.csv')
        results_df.to_csv(results_path, index=False)

        metrics_df = pd.DataFrame([metrics])
        metrics_path = os.path.join(self.results_dir, f'metrics_{period.replace(" -> ", "_")}.csv')
        metrics_df.to_csv(metrics_path, index=False)

        model_path = os.path.join(self.results_dir, f'xgboost_model_{period.replace(" -> ", "_")}.json')
        self.model.save_model(model_path)

        print(f"结果已保存到: {self.results_dir}")

    def run(self):
        """完整的训练流程"""
        try:
            df = self.load_data()
            if df is None:
                return

            df = self.feature_engineering(df)

            exclude_cols = [
                'date', 'code', 'ts_code', 'close', 'volume', 'amount',
                'ret', 'label', 'pre_close', 'change', 'pct_chg',
                'open', 'high', 'low', 'year'
            ]
            feature_cols = [c for c in df.columns if c not in exclude_cols and df[c].dtype in ['int64', 'float64']]

            print(f"\n可用特征数: {len(feature_cols)}")

            splits = self.rolling_train_test_split(df)

            all_metrics = []

            for split in splits:
                print(f"\n{'='*60}")
                print(f"处理时间窗口: {split['period']}")
                print(f"{'='*60}")

                train = split['train']
                test = split['test']

                # ---- 滚动窗口标准化（只fit训练集，防止未来信息泄漏）----
                if getattr(self, 'tech_features', []):
                    scaler = StandardScaler()
                    train_tech = train[self.tech_features].copy()
                    test_tech = test[self.tech_features].copy()
                    # 用训练集 fit，transform 训练集和测试集
                    train.loc[:, self.tech_features] = scaler.fit_transform(
                        train_tech.fillna(0)
                    )
                    test.loc[:, self.tech_features] = scaler.transform(
                        test_tech.fillna(0)
                    )
                    print(f"  ✅ 窗口内标准化完成（{len(self.tech_features)} 个技术特征，仅fit训练集）")

                print(f"训练集样本数: {len(train):,}")
                print(f"测试集样本数: {len(test):,}")

                X_train_raw = train[feature_cols]
                y_train = train['label']
                X_train = self.select_features(X_train_raw, y_train)

                self.train_model(X_train, y_train)

                X_test = test[self.selected_features]
                y_test = test['label']
                
                y_pred_train = self.model.predict(X_train.fillna(0))
                y_pred = self.model.predict(X_test.fillna(0))
                
                y_pred_baseline_train = self.baseline_model.predict(X_train.fillna(0))
                y_pred_baseline = self.baseline_model.predict(X_test.fillna(0))

                print("\n【训练集评估】")
                _ = self.evaluate_model(y_train.values, y_pred_train, y_pred_baseline_train, "训练集")

                print("\n【测试集评估】")
                metrics = self.evaluate_model(y_test.values, y_pred, y_pred_baseline, "测试集")

                if metrics:
                    metrics['period'] = split['period']
                    all_metrics.append(metrics)

                self.plot_results(test, y_pred, split['period'])
                self.save_results(test, y_pred, split['period'], metrics)

            if all_metrics:
                print("\n" + "="*60)
                print("滚动窗口训练汇总结果")
                print("="*60)

                metrics_df = pd.DataFrame(all_metrics)
                display_cols = ['period', 'r2', 'accuracy', 'ic', 'win_rate', 'baseline_r2']
                print(metrics_df[display_cols].to_string(index=False))

                metrics_df.to_csv(os.path.join(self.results_dir, 'rolling_metrics_summary.csv'), index=False)

                avg_metrics = metrics_df[['r2', 'accuracy', 'ic', 'win_rate']].mean()
                print(f"\n平均指标:")
                print(f"  平均R²: {avg_metrics['r2']:.4f}")
                print(f"  平均方向准确率: {avg_metrics['accuracy']:.2%}")
                print(f"  平均信息系数(IC): {avg_metrics['ic']:.4f}")
                print(f"  平均胜率: {avg_metrics['win_rate']:.2%}")

                if 'baseline_r2' in metrics_df.columns:
                    avg_baseline_r2 = metrics_df['baseline_r2'].mean()
                    print(f"\n对比基线模型:")
                    print(f"  基线模型平均R²: {avg_baseline_r2:.4f}")
                    print(f"  模型R²改进: {((avg_metrics['r2'] - avg_baseline_r2) / max(abs(avg_baseline_r2), 0.001) * 100):.2f}%")

            print("\n" + "="*60)
            print("优化版模型训练完成!")
            print("="*60)
            print(f"\n结果保存在: {os.path.abspath(self.results_dir)}")

        except Exception as e:
            print(f"\n错误: {e}")
            import traceback
            traceback.print_exc()

CLASSIC_FEATURES = [
    'ret_5d', 'ma5', 'ma10', 'ma20', 'ma5_ma10_diff', 'ma5_ma20_diff',
    'rsi', 'macd', 'macd_signal', 'momentum_20d', 'reversal_5d',
    'volatility_20d', 'volatility_60d',
    'bb_mid', 'bb_position',
    'volume_ma5', 'volume_ratio', 'amount_ma20', 'amount_ratio',
    'high_low_ratio', 'close_open_ratio',
    'sentiment', 'sentiment_ma5', 'sentiment_ma10',
]

def _set_seed(seed=42):
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass

def _save_training_log(model_name, features, acc, auc, mse, data_range, params):
    log_path = _P('training_log.json')
    log = {}
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                log = json.load(f)
        except Exception:
            log = {}
    log[model_name] = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'features': features,
        'feature_count': len(features),
        'accuracy': round(acc, 4),
        'auc': round(auc, 4),
        'mse': round(mse, 6),
        'data_range': data_range,
        'params': params,
    }
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

def train_xgb_classifier():
    print("\n" + "=" * 60)
    print("训练 XGBoost 分类模型（用于股票预测页面）")
    print("=" * 60)
    _set_seed(42)
    data_path = _P('data', 'processed', 'all_factors.parquet')
    if not os.path.exists(data_path):
        print(f"[错误] 找不到数据文件: {data_path}")
        return
    df = pd.read_parquet(data_path)
    df['date'] = pd.to_datetime(df['date'])
    print(f"总样本数: {len(df):,}")
    available_features = [f for f in CLASSIC_FEATURES if f in df.columns]
    missing = set(CLASSIC_FEATURES) - set(df.columns)
    if missing:
        print(f"[警告] 缺少特征: {missing}")
    if len(available_features) < 10:
        print(f"[错误] 可用特征太少({len(available_features)}), 需要至少10个!")
        return
    print(f"使用特征数: {len(available_features)}")
    df = df.dropna(subset=['label'] + available_features)
    df = df.sort_values('date').reset_index(drop=True)
    print(f"过滤后样本数: {len(df):,}")
    data_range = f"{df['date'].min().strftime('%Y-%m-%d')} ~ {df['date'].max().strftime('%Y-%m-%d')}"
    split_date = df['date'].quantile(0.8)
    train_df = df[df['date'] <= split_date].copy()
    test_df = df[df['date'] > split_date].copy()
    X_train = train_df[available_features].fillna(0)
    y_train = (train_df['label'] > 0).astype(int)
    X_test = test_df[available_features].fillna(0)
    y_test_cls = (test_df['label'] > 0).astype(int)
    pos_count = y_train.sum()
    neg_count = len(y_train) - pos_count
    print(f"训练集 - 上涨: {pos_count}, 下跌: {neg_count}")
    print(f"数据范围: {data_range}")
    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=neg_count / max(pos_count, 1),
        random_state=42, verbosity=0,
        use_label_encoder=False, eval_metric='logloss'
    )
    model.fit(X_train, y_train)
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    y_pred_cls = (y_pred_proba > 0.5).astype(int)
    from sklearn.metrics import accuracy_score, roc_auc_score, mean_squared_error
    acc = accuracy_score(y_test_cls, y_pred_cls)
    try:
        auc = roc_auc_score(y_test_cls, y_pred_proba)
    except Exception:
        auc = 0.5
    mse = mean_squared_error(y_test_cls.astype(float), y_pred_proba)
    print(f"分类准确率: {acc:.2%}")
    print(f"AUC: {auc:.4f}")
    print(f"MSE: {mse:.6f}")
    os.makedirs(_P('results_optimized'), exist_ok=True)
    model.save_model(_P('results_optimized', 'xgb_fixed.json'))
    with open(_P('results_optimized', 'xgb_feature_list.txt'), 'w') as f:
        for feat in available_features:
            f.write(feat + '\n')
    _saved = _P('results_optimized', 'xgb_fixed.json')
    print(f"XGBoost 分类模型已保存: {_saved}")
    _save_training_log('XGBoost', available_features, acc, auc, mse, data_range,
                       {'n_estimators': 200, 'max_depth': 4, 'learning_rate': 0.05,
                        'subsample': 0.8, 'colsample_bytree': 0.8, 'random_state': 42})


def train_lstm_model():
    print("\n" + "=" * 60)
    print("训练 LSTM 分类模型（用于股票预测页面）")
    print("=" * 60)
    _set_seed(42)
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, roc_auc_score, mean_squared_error

    class BiLSTMModel(nn.Module):
        def __init__(self, input_size, hidden_size=64, num_layers=2, dropout=0.2):
            super(BiLSTMModel, self).__init__()
            self.lstm = nn.LSTM(input_size=input_size, hidden_size=hidden_size,
                                num_layers=num_layers, batch_first=True,
                                bidirectional=True, dropout=dropout if num_layers > 1 else 0)
            self.dropout = nn.Dropout(dropout)
            self.fc = nn.Sequential(nn.Linear(hidden_size * 2, 32), nn.ReLU(),
                                    nn.Dropout(0.2), nn.Linear(32, 1))

        def forward(self, x):
            out, _ = self.lstm(x)
            out = self.dropout(out[:, -1, :])
            return self.fc(out).squeeze(-1)

    data_path = _P('data', 'processed', 'all_factors.parquet')
    if not os.path.exists(data_path):
        print(f"[错误] 找不到数据文件: {data_path}")
        return
    df = pd.read_parquet(data_path)
    df['date'] = pd.to_datetime(df['date'])
    print(f"总样本数: {len(df):,}")
    available_features = [f for f in CLASSIC_FEATURES if f in df.columns]
    missing = set(CLASSIC_FEATURES) - set(df.columns)
    if missing:
        print(f"[警告] 缺少特征: {missing}")
    if len(available_features) < 10:
        print(f"[错误] 可用特征太少({len(available_features)}), 需要至少10个!")
        return
    print(f"使用特征数: {len(available_features)}")
    df = df.dropna(subset=['label'] + available_features)
    df = df.sort_values(['code', 'date']).reset_index(drop=True)
    print(f"过滤后样本数: {len(df):,}")
    data_range = f"{df['date'].min().strftime('%Y-%m-%d')} ~ {df['date'].max().strftime('%Y-%m-%d')}"
    train_end = df['date'].quantile(0.70)
    validation_end = df['date'].quantile(0.85)
    train_df = df[df['date'] <= train_end].copy()
    validation_df = df[(df['date'] > train_end) & (df['date'] <= validation_end)].copy()
    test_df = df[df['date'] > validation_end].copy()
    y_train_cls = (train_df['label'] > 0).astype(int)
    y_validation_cls = (validation_df['label'] > 0).astype(int)
    y_test_cls = (test_df['label'] > 0).astype(int)
    scaler = StandardScaler()
    train_features = scaler.fit_transform(train_df[available_features])
    validation_features = scaler.transform(validation_df[available_features])
    test_features = scaler.transform(test_df[available_features])
    time_steps = 20

    def create_ts(features, labels, codes, ts=20):
        X, y = [], []
        for code in np.unique(codes):
            idx = codes == code
            feat_seq = features[idx]
            label_seq = labels[idx]
            for i in range(ts, len(feat_seq)):
                X.append(feat_seq[i - ts:i])
                y.append(label_seq[i])
        return np.array(X), np.array(y)

    X_train, y_train_ts = create_ts(train_features, y_train_cls.values, train_df['code'].values, time_steps)
    X_validation, y_validation_ts = create_ts(
        validation_features,
        y_validation_cls.values,
        validation_df['code'].values,
        time_steps,
    )
    X_test, y_test_ts = create_ts(test_features, y_test_cls.values, test_df['code'].values, time_steps)
    print(
        f"训练数据: {X_train.shape}, 验证数据: {X_validation.shape}, "
        f"测试数据: {X_test.shape}"
    )
    if len(X_train) == 0 or len(X_validation) == 0 or len(X_test) == 0:
        print("[错误] 训练、验证或测试时间序列数据为空!")
        return
    X_train_t = torch.tensor(X_train, dtype=torch.float32)
    y_train_t = torch.tensor(y_train_ts, dtype=torch.float32)
    X_validation_t = torch.tensor(X_validation, dtype=torch.float32)
    y_validation_t = torch.tensor(y_validation_ts, dtype=torch.float32)
    X_test_t = torch.tensor(X_test, dtype=torch.float32)
    y_test_t = torch.tensor(y_test_ts, dtype=torch.float32)
    train_dataset = TensorDataset(X_train_t, y_train_t)
    train_loader = DataLoader(train_dataset, batch_size=512, shuffle=True, num_workers=0)
    input_size = X_train.shape[2]
    hidden_size = 64
    model = BiLSTMModel(input_size=input_size, hidden_size=hidden_size, num_layers=2, dropout=0.2)
    print(f"模型结构: input_size={input_size}, hidden_size={hidden_size}, bidirectional=True")
    print(f"数据范围: {data_range}")
    pos_weight = (len(y_train_ts) - y_train_ts.sum()) / max(y_train_ts.sum(), 1)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight]))
    optimizer = optim.Adam(model.parameters(), lr=0.003, weight_decay=1e-5)
    num_epochs = 20
    best_val_loss = float('inf')
    patience = 4
    patience_counter = 0
    os.makedirs(_P('results_optimized'), exist_ok=True)
    for epoch in range(num_epochs):
        model.train()
        train_loss = 0.0
        for batch_X, batch_y in train_loader:
            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = criterion(outputs, batch_y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += loss.item() * batch_X.size(0)
        train_loss /= len(train_loader.dataset)
        model.eval()
        with torch.no_grad():
            val_outputs = model(X_validation_t)
            val_loss = criterion(val_outputs, y_validation_t).item()
        print(f"Epoch {epoch + 1}/{num_epochs} - train_loss: {train_loss:.6f}, val_loss: {val_loss:.6f}")
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0
            torch.save(model.state_dict(), _P('results_optimized', 'lstm_fixed.pth'))
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"早停于第 {epoch + 1} 轮")
                break
    model.load_state_dict(torch.load(_P('results_optimized', 'lstm_fixed.pth'), weights_only=True))
    model.eval()
    with torch.no_grad():
        logits = model(X_test_t)
        y_pred_proba = torch.sigmoid(logits).numpy()
    y_pred_cls = (y_pred_proba > 0.5).astype(int)
    acc = accuracy_score(y_test_ts, y_pred_cls)
    try:
        auc = roc_auc_score(y_test_ts, y_pred_proba)
    except Exception:
        auc = 0.5
    mse = mean_squared_error(y_test_ts.astype(float), y_pred_proba)
    print(f"分类准确率: {acc:.2%}")
    print(f"AUC: {auc:.4f}")
    print(f"MSE: {mse:.6f}")
    with open(_P('results_optimized', 'model_config.txt'), 'w') as f:
        f.write(f"input_size={input_size}\n")
        f.write(f"hidden_size={hidden_size}\n")
        f.write(f"num_layers=2\n")
        f.write(f"dropout=0.2\n")
        f.write(f"time_steps={time_steps}\n")
        f.write(f"bidirectional=True\n")
        f.write(f"task=classification\n")
    with open(_P('results_optimized', 'feature_list.txt'), 'w') as f:
        for feat in available_features:
            f.write(feat + '\n')
    np.save(_P('results_optimized', 'scaler_mean.npy'), scaler.mean_)
    np.save(_P('results_optimized', 'scaler_std.npy'), scaler.scale_)
    print("LSTM 分类模型已保存: ./results_lstm/lstm_fixed.pth")
    print("模型配置已保存: ./results_lstm/model_config.txt")
    _save_training_log('LSTM', available_features, acc, auc, mse, data_range,
                       {'input_size': input_size, 'hidden_size': hidden_size,
                        'num_layers': 2, 'dropout': 0.2, 'bidirectional': True,
                        'time_steps': time_steps, 'epochs': num_epochs,
                        'lr': 0.003, 'batch_size': 512, 'patience': patience})


def main():
    predictor = OptimizedStockPredictor()
    predictor.run()
    train_xgb_classifier()
    train_lstm_model()

if __name__ == "__main__":
    main()
