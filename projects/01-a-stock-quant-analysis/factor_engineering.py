import pandas as pd
import numpy as np
import os
import traceback
import time

def main():
    try:
        # 使用绝对路径（先定义变量）
        base_dir = os.path.dirname(os.path.abspath(__file__))
        raw_path = os.path.join(base_dir, 'data', 'raw')
        processed_path = os.path.join(base_dir, 'data', 'processed')

        print(f"当前工作目录: {os.getcwd()}")
        print(f"基础目录: {base_dir}")
        print(f"原始数据路径: {raw_path}")
        print(f"处理后数据路径: {processed_path}")

        # 确保目录存在
        os.makedirs(raw_path, exist_ok=True)
        os.makedirs(processed_path, exist_ok=True)

        print(f"原始数据目录存在: {os.path.exists(raw_path)}")
        print(f"处理后数据目录存在: {os.path.exists(processed_path)}")

        # 获取股票文件
        files = [f for f in os.listdir(raw_path) if f.endswith('_daily.csv')]
        print(f"找到 {len(files)} 个股票文件")

        # 按股票代码排序，确保处理顺序一致
        files.sort()

        all_dfs = []
        total_rows_before = 0
        total_rows_after = 0

        start_time = time.time()

        for i, file in enumerate(files, 1):
            try:
                # 提取股票代码
                code = file.replace('_daily.csv', '')
                file_path = os.path.join(raw_path, file)

                # 读取数据
                df = pd.read_csv(file_path)
                total_rows_before += len(df)

                # 确保必要的列存在
                required_cols = ['trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount']
                if not all(col in df.columns for col in required_cols):
                    print(f"[{i}/{len(files)}] 跳过 {code}: 缺少必要列")
                    continue

                # 重命名列（统一字段名）
                df = df.rename(columns={
                    'trade_date': 'date',
                    'vol': 'volume'
                })

                # 转换日期格式
                df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')

                # 按日期升序排列（确保时间序列正确，无未来信息泄露）
                df = df.sort_values('date').reset_index(drop=True)

                # === 计算因子（严格使用过去数据，无未来信息泄露）===

                # 1. 收益率因子
                df['ret'] = df['close'].pct_change()
                df['ret_5d'] = df['close'].pct_change(5)
                df['ret_10d'] = df['close'].pct_change(10)

                # 2. 均线因子
                df['ma5'] = df['close'].rolling(5).mean()
                df['ma10'] = df['close'].rolling(10).mean()
                df['ma20'] = df['close'].rolling(20).mean()
                df['ma60'] = df['close'].rolling(60).mean()

                # 3. 均线交叉信号
                df['ma5_ma10_diff'] = df['ma5'] - df['ma10']
                df['ma5_ma20_diff'] = df['ma5'] - df['ma20']

                # 4. 波动率因子（使用过去数据）
                df['volatility_20d'] = df['ret'].rolling(20).std()
                df['volatility_60d'] = df['ret'].rolling(60).std()

                # 5. RSI (14日)
                delta = df['close'].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                df['rsi'] = 100 - (100 / (1 + gain / loss))

                # 6. MACD
                ema12 = df['close'].ewm(span=12, adjust=False).mean()
                ema26 = df['close'].ewm(span=26, adjust=False).mean()
                df['macd'] = ema12 - ema26
                df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

                # 7. 成交量因子
                df['volume_ma5'] = df['volume'].rolling(5).mean()
                df['volume_ma20'] = df['volume'].rolling(20).mean()
                df['volume_ratio'] = df['volume'] / df['volume_ma20']
                df['volume_change'] = df['volume'].pct_change()

                # 8. 量价关系
                df['amount_ma20'] = df['amount'].rolling(20).mean()
                df['amount_ratio'] = df['amount'] / df['amount_ma20']

                # 9. 动量因子
                df['momentum_20d'] = (df['close'] / df['close'].shift(20)) - 1
                df['momentum_60d'] = (df['close'] / df['close'].shift(60)) - 1

                # 10. 反转因子
                df['reversal_5d'] = -df['ret'].rolling(5).sum()
                df['reversal_20d'] = -df['ret'].rolling(20).sum()

                # 11. 高低价因子
                df['high_low_ratio'] = df['high'] / df['low']
                df['close_open_ratio'] = df['close'] / df['open']

                # 12. 布林带
                df['bb_mid'] = df['close'].rolling(20).mean()
                df['bb_std'] = df['close'].rolling(20).std()
                df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
                df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
                df['bb_width'] = df['bb_upper'] - df['bb_lower']
                df['bb_position'] = (df['close'] - df['bb_lower']) / df['bb_width']

                # === 生成标签（下一日收益率，无未来信息泄露）===
                df['label'] = df['ret'].shift(-1)

                # 删除缺失值（滚动窗口导致的NaN）
                df = df.dropna(subset=[
                    'close', 'label', 'ma20', 'volatility_20d', 'rsi',
                    'macd', 'volume_ma20', 'momentum_20d'
                ])

                total_rows_after += len(df)

                if len(df) > 0:
                    df['code'] = code
                    all_dfs.append(df)

                    if i % 50 == 0:
                        elapsed = time.time() - start_time
                        print(f"[{i}/{len(files)}] 已处理 {len(all_dfs)} 只股票, 累计数据 {total_rows_after:,} 条, 用时 {elapsed:.1f}s")
                else:
                    print(f"[{i}/{len(files)}] 跳过 {code}: 没有有效数据")

            except Exception as e:
                print(f"[{i}/{len(files)}] 处理 {file} 时出错: {e}")
                continue

        # 合并数据
        if all_dfs:
            print(f"\n合并 {len(all_dfs)} 只股票的数据...")
            df_all = pd.concat(all_dfs, ignore_index=True)

            # 按日期排序（确保时间顺序正确）
            df_all = df_all.sort_values(['date', 'code']).reset_index(drop=True)

            print(f"合并完成，总行数: {len(df_all):,}")
            print(f"列数: {len(df_all.columns)}")
            print(f"特征列示例: {[c for c in df_all.columns if c not in ['date', 'code', 'label']][:10]}")

            # 保存CSV文件
            csv_path = os.path.join(processed_path, 'all_factors.csv')
            print(f"\n保存CSV文件: {csv_path}")

            df_all.to_csv(csv_path, index=False)
            file_size = os.path.getsize(csv_path) / (1024 * 1024)  # MB
            print(f"CSV文件保存成功! 文件大小: {file_size:.2f} MB")

            # 保存为Parquet格式（更高效）
            parquet_path = os.path.join(processed_path, 'all_factors.parquet')
            print(f"保存Parquet文件: {parquet_path}")
            df_all.to_parquet(parquet_path)
            parquet_size = os.path.getsize(parquet_path) / (1024 * 1024)
            print(f"Parquet文件保存成功! 文件大小: {parquet_size:.2f} MB")

            # 输出统计信息
            print(f"\n========== 数据处理统计 ==========")
            print(f"股票数量: {len(all_dfs)}")
            print(f"原始总行数: {total_rows_before:,}")
            print(f"处理后总行数: {total_rows_after:,}")
            print(f"日期范围: {df_all['date'].min().strftime('%Y-%m-%d')} 至 {df_all['date'].max().strftime('%Y-%m-%d')}")
            print(f"==================================")

        else:
            print("没有成功处理任何股票数据")

    except Exception as e:
        print(f"主程序出错: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
