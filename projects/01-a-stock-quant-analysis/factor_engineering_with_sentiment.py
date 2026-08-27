# factor_engineering_with_sentiment.py - 集成情绪因子的因子工程
import pandas as pd
import numpy as np
import os
from datetime import datetime

def calculate_technical_factors(df):
    """计算技术因子"""
    print("计算技术因子...")

    df = df.sort_values('date').copy()

    # 收益率
    df['ret'] = df['close'].pct_change()
    df['ret_5d'] = df['close'].pct_change(5)
    df['ret_10d'] = df['close'].pct_change(10)

    # 移动平均线
    for window in [5, 10, 20, 60]:
        df[f'ma{window}'] = df['close'].rolling(window, min_periods=1).mean()

    # 均线交叉
    df['ma5_ma10_diff'] = df['ma5'] - df['ma10']
    df['ma5_ma20_diff'] = df['ma5'] - df['ma20']

    # 波动率
    df['volatility_20d'] = df['ret'].rolling(20, min_periods=1).std()
    df['volatility_60d'] = df['ret'].rolling(60, min_periods=1).std()

    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=1).mean()
    rs = gain / (loss + 1e-10)
    df['rsi'] = 100 - (100 / (1 + rs))

    # MACD
    exp12 = df['close'].ewm(span=12, adjust=False).mean()
    exp26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp12 - exp26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # 成交量因子
    if 'volume' in df.columns:
        df['volume_ma5'] = df['volume'].rolling(5, min_periods=1).mean()
        df['volume_ratio'] = df['volume'] / (df['volume_ma5'] + 1)
        df['volume_change'] = df['volume'].pct_change()

    if 'amount' in df.columns:
        df['amount_ma20'] = df['amount'].rolling(20, min_periods=1).mean()
        df['amount_ratio'] = df['amount'] / (df['amount_ma20'] + 1)

    # 动量因子
    df['momentum_20d'] = df['close'] / df['close'].shift(20) - 1
    df['momentum_60d'] = df['close'] / df['close'].shift(60) - 1

    # 反转因子
    df['reversal_5d'] = -df['ret_5d']
    df['reversal_20d'] = -df['ret'].rolling(20, min_periods=1).mean()

    # 布林带
    df['bb_mid'] = df['close'].rolling(20, min_periods=1).mean()
    bb_std = df['close'].rolling(20, min_periods=1).std()
    df['bb_upper'] = df['bb_mid'] + 2 * bb_std
    df['bb_lower'] = df['bb_mid'] - 2 * bb_std
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']
    df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-10)

    # 价格比率
    if 'high' in df.columns and 'low' in df.columns:
        df['high_low_ratio'] = df['high'] / (df['low'] + 1e-10)
    if 'open' in df.columns:
        df['close_open_ratio'] = df['close'] / (df['open'] + 1e-10)

    # 标签
    df['label'] = df['ret'].shift(-1)

    return df


def merge_sentiment_factors(df, stock_code):
    """合并情绪因子"""
    print(f"\n合并 {stock_code} 的情绪因子...")

    sentiment_path = './data/processed/sentiment_data.parquet'

    if not os.path.exists(sentiment_path):
        print("未找到情感数据文件，添加默认情感因子...")
        df['sentiment'] = 0
        df['sentiment_ma5'] = 0
        df['sentiment_ma10'] = 0
        df['comment_count'] = 0
        return df

    try:
        sentiment_df = pd.read_parquet(sentiment_path)

        # 筛选该股票的情感数据
        if 'code' in sentiment_df.columns:
            sentiment_df = sentiment_df[sentiment_df['code'] == stock_code]

        if sentiment_df.empty:
            print(f"未找到 {stock_code} 的情感数据，添加默认情感因子...")
            df['sentiment'] = 0
            df['sentiment_ma5'] = 0
            df['sentiment_ma10'] = 0
            df['comment_count'] = 0
            return df

        # 确保日期格式一致
        df['date'] = pd.to_datetime(df['date'])
        sentiment_df['date'] = pd.to_datetime(sentiment_df['date'])

        # 合并情感数据
        df = df.merge(
            sentiment_df[['date', 'sentiment', 'sentiment_ma5', 'sentiment_ma10', 'comment_count']],
            on='date',
            how='left'
        )

        # 填充缺失值
        sentiment_cols = ['sentiment', 'sentiment_ma5', 'sentiment_ma10', 'comment_count']
        for col in sentiment_cols:
            if col in df.columns:
                df[col] = df[col].fillna(0)

        print(f"成功合并情感因子，最终数据形状: {df.shape}")
        return df

    except Exception as e:
        print(f"合并情感因子失败: {e}")
        df['sentiment'] = 0
        df['sentiment_ma5'] = 0
        df['sentiment_ma10'] = 0
        df['comment_count'] = 0
        return df


def main():
    print("=" * 60)
    print("因子工程 - 集成情绪因子版")
    print("=" * 60)

    # 路径设置
    base_dir = os.path.dirname(os.path.abspath(__file__))
    raw_path = os.path.join(base_dir, 'data', 'raw')
    processed_path = os.path.join(base_dir, 'data', 'processed')

    os.makedirs(processed_path, exist_ok=True)

    # 获取所有股票文件
    files = [f for f in os.listdir(raw_path) if f.endswith('_daily.csv')]
    print(f"\n找到 {len(files)} 个股票数据文件")

    all_dfs = []

    for i, file in enumerate(files):
        try:
            code = file.replace('_daily.csv', '')
            file_path = os.path.join(raw_path, file)
            print(f"\n[{i+1}/{len(files)}] 处理 {code}...")

            # 读取数据
            df = pd.read_csv(file_path)
            print(f"  原始数据: {len(df)} 行")

            # 重命名列
            rename_map = {
                'trade_date': 'date',
                'vol': 'volume'
            }
            if 'trade_date' in df.columns or 'vol' in df.columns:
                df.rename(columns=rename_map, inplace=True)

            # 确保日期格式
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date')

            # 计算技术因子
            df = calculate_technical_factors(df)

            # 合并情绪因子
            df = merge_sentiment_factors(df, code)

            # 删除缺失值（除了标签列的最后几行）
            initial_rows = len(df)
            df = df.dropna(subset=['close', 'ma5', 'volatility_20d', 'rsi'])
            print(f"  删除缺失值后: {len(df)} 行 (删除了 {initial_rows - len(df)} 行)")

            if len(df) > 0:
                df['code'] = code
                all_dfs.append(df)
                print(f"  ✓ {code} 处理完成")

        except Exception as e:
            print(f"  ✗ 处理 {file} 时出错: {e}")
            continue

    # 合并所有数据
    if all_dfs:
        print(f"\n合并所有股票数据...")
        df_all = pd.concat(all_dfs, ignore_index=True)
        df_all = df_all.sort_values(['code', 'date'])

        print(f"合并后总行数: {len(df_all):,}")

        # 保存
        csv_path = os.path.join(processed_path, 'all_factors.csv')
        parquet_path = os.path.join(processed_path, 'all_factors.parquet')

        print(f"\n保存数据...")
        df_all.to_csv(csv_path, index=False)
        print(f"✓ CSV已保存: {csv_path}")

        try:
            df_all.to_parquet(parquet_path)
            print(f"✓ Parquet已保存: {parquet_path}")
        except Exception as e:
            print(f"Parquet保存失败: {e}")

        # 统计
        print(f"\n数据统计:")
        print(f"  股票数量: {df_all['code'].nunique()}")
        print(f"  总行数: {len(df_all):,}")
        print(f"  特征数量: {len(df_all.columns)}")
        print(f"  日期范围: {df_all['date'].min()} 至 {df_all['date'].max()}")

    else:
        print("\n没有成功处理任何股票数据!")

    print("\n" + "=" * 60)
    print("因子工程完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
