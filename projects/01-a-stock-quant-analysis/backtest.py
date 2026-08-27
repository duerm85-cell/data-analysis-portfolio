# backtest.py - 回测脚本
import sys
print("=" * 60)
print("backtest.py 开始执行...")
print("=" * 60)

import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings('ignore')

class StockBacktester:
    """股票回测器"""

    def __init__(self):
        self.results_dir = './results_optimized'
        self.output_dir = './backtest_results'
        os.makedirs(self.output_dir, exist_ok=True)

    def load_data(self):
        """加载原始数据和预测结果"""
        print("加载数据...")

        data_path_parquet = './data/processed/all_factors.parquet'
        data_path_csv = './data/processed/all_factors.csv'

        if os.path.exists(data_path_parquet):
            df = pd.read_parquet(data_path_parquet)
        elif os.path.exists(data_path_csv):
            df = pd.read_csv(data_path_csv, parse_dates=['date'])
        else:
            print("错误: 找不到处理后的数据文件!")
            return None

        print(f"原始数据加载完成: {len(df):,} 条记录")
        return df

    def load_predictions(self):
        """加载预测结果"""
        print("\n加载预测结果...")

        predictions_files = [f for f in os.listdir(self.results_dir) 
                            if f.startswith('test_predictions_') and f.endswith('.csv')]

        if not predictions_files:
            print("错误: 找不到预测结果文件!")
            return None

        all_predictions = []
        for f in predictions_files:
            pred_df = pd.read_csv(os.path.join(self.results_dir, f), parse_dates=['date'])
            all_predictions.append(pred_df)

        predictions_df = pd.concat(all_predictions, ignore_index=True)
        print(f"预测结果加载完成: {len(predictions_df):,} 条记录")
        return predictions_df

    def simple_strategy_backtest(self, predictions_df):
        """简单策略回测

        回测机制：
          - 信号产生：T 日收盘后，根据当日因子计算的模型预测结果（predicted）对股票排序选股
          - 成交口径：T+1 日收益率（即 actual = ret.shift(-1) = T+1 日收益率）
          - 权重分配：等权重持有 Top-N
          - 风控规则：不单独做止盈止损，仅做日频换仓

        注意：本系统的标签 actual = T+1 日收益率，故在 date=T 时选股、actual
        用作 T+1 的成交收益，严格满足 T+1 成交，不存在“当日收盘决策、当日收盘
        成交”这样的未来函数问题。
        """
        print("\n开始简单策略回测...")

        df = predictions_df.copy()

        print(f"回测时间范围: {df['date'].min()} 至 {df['date'].max()}")
        print(f"回测股票数量: {df['code'].nunique()}")

        # 每日选股策略：选择预测收益率最高的N只股票
        N = 10  # 每日选择10只股票
        initial_capital = 1000000  # 初始资金100万

        print(f"\n策略参数:")
        print(f"  每日选股数: {N}")
        print(f"  初始资金: {initial_capital:,}")
        print(f"  成交口径: T+1 日收益率（使用 actual/label = ret.shift(-1)）")

        results = []
        daily_portfolios = []

        # 按日期分组处理
        for date, group in df.groupby('date'):
            # T 日收盘后按 predicted 排序，选出 Top-N
            group_sorted = group.sort_values('predicted', ascending=False)
            selected = group_sorted.head(N)

            if len(selected) == 0:
                continue

            # T+1 日实现收益 = actual = ret.shift(-1)
            # 即：T 日选股，T+1 日按 close-to-close 成交
            portfolio_return = selected['actual'].mean()

            results.append({
                'date': date,
                'portfolio_return': portfolio_return,
                'n_stocks': len(selected),
                'avg_predicted_return': selected['predicted'].mean(),
                'avg_actual_return': selected['actual'].mean()
            })

            # 记录每日持仓
            for _, row in selected.iterrows():
                daily_portfolios.append({
                    'date': date,
                    'code': row['code'],
                    'predicted': row['predicted'],
                    'actual': row['actual']
                })

        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values('date').reset_index(drop=True)

        # 计算累积收益率
        results_df['cumulative_return'] = (1 + results_df['portfolio_return']).cumprod()
        results_df['equity_curve'] = initial_capital * results_df['cumulative_return']

        # 计算基准：等权持有所有股票
        all_stock_returns = df.groupby('date')['actual'].mean()
        benchmark_df = pd.DataFrame({'date': all_stock_returns.index, 'benchmark_return': all_stock_returns.values})
        benchmark_df['benchmark_cumulative'] = (1 + benchmark_df['benchmark_return']).cumprod()
        benchmark_df['benchmark_equity'] = initial_capital * benchmark_df['benchmark_cumulative']

        # 合并结果
        results_df = results_df.merge(benchmark_df, on='date', how='left')

        # 计算策略指标
        total_return = results_df['cumulative_return'].iloc[-1] - 1
        benchmark_total_return = results_df['benchmark_cumulative'].iloc[-1] - 1
        
        daily_returns = results_df['portfolio_return'].dropna()
        annualized_return = (1 + daily_returns.mean()) ** 252 - 1
        annualized_volatility = daily_returns.std() * np.sqrt(252)
        
        if annualized_volatility > 0:
            sharpe_ratio = annualized_return / annualized_volatility
        else:
            sharpe_ratio = 0

        # 最大回撤
        equity = results_df['equity_curve'].values
        cummax = np.maximum.accumulate(equity)
        drawdown = (equity - cummax) / cummax
        max_drawdown = drawdown.min()

        # 胜率
        win_rate = (results_df['portfolio_return'] > 0).mean()

        print(f"\n策略表现:")
        print(f"  总收益率: {total_return:.2%}")
        print(f"  年化收益率: {annualized_return:.2%}")
        print(f"  年化波动率: {annualized_volatility:.2%}")
        print(f"  夏普比率: {sharpe_ratio:.2f}")
        print(f"  最大回撤: {max_drawdown:.2%}")
        print(f"  胜率: {win_rate:.2%}")

        print(f"\n基准表现:")
        print(f"  基准总收益率: {benchmark_total_return:.2%}")
        print(f"  策略vs基准超额收益: {total_return - benchmark_total_return:.2%}")

        # 保存回测结果
        results_df.to_csv(os.path.join(self.output_dir, 'backtest_results.csv'), index=False)
        pd.DataFrame(daily_portfolios).to_csv(os.path.join(self.output_dir, 'daily_portfolios.csv'), index=False)

        # 保存回测指标
        metrics = {
            'initial_capital': initial_capital,
            'n_stocks_per_day': N,
            'total_return': total_return,
            'annualized_return': annualized_return,
            'annualized_volatility': annualized_volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'benchmark_total_return': benchmark_total_return,
            'excess_return': total_return - benchmark_total_return
        }

        pd.DataFrame([metrics]).to_csv(os.path.join(self.output_dir, 'backtest_metrics.csv'), index=False)

        print(f"\n回测结果已保存到: {os.path.abspath(self.output_dir)}")

        return results_df, metrics

    def run(self):
        """运行回测"""
        try:
            print("=" * 60)
            print("股票量化策略回测系统")
            print("=" * 60)

            df = self.load_data()
            if df is None:
                return

            predictions_df = self.load_predictions()
            if predictions_df is None:
                return

            self.simple_strategy_backtest(predictions_df)

            print("\n" + "="*60)
            print("回测完成!")
            print("="*60)

        except Exception as e:
            print(f"\n错误: {e}")
            import traceback
            traceback.print_exc()

def main():
    backtester = StockBacktester()
    backtester.run()

if __name__ == "__main__":
    main()
