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

# ========== 路径基准：全部以本文件所在目录为根，不依赖 cwd ==========
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
def _P(*parts):
    return os.path.join(_BASE_DIR, *parts)


class StockBacktester:
    """股票回测器"""

    def __init__(self, output_dir=None, n_stocks=10, initial_capital=1_000_000,
                 commission_rate=0.0003, stamp_duty_rate=0.0005):
        self.results_dir = _P('results_optimized')
        self.output_dir = output_dir or _P('backtest_results')
        self.n_stocks = n_stocks
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.stamp_duty_rate = stamp_duty_rate
        os.makedirs(self.output_dir, exist_ok=True)

    def load_data(self):
        """加载原始数据和预测结果"""
        print("加载数据...")

        data_path_parquet = _P('data', 'processed', 'all_factors.parquet')
        data_path_csv = _P('data', 'processed', 'all_factors.csv')

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

        if not os.path.isdir(self.results_dir):
            print("错误: 预测结果目录不存在!")
            return None

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

    def load_benchmark(self):
        """加载沪深300指数，并将 T+1 收益对齐到 T 日信号日期。"""
        candidates = [
            _P('data', 'processed', 'benchmark_hs300.parquet'),
            _P('data', 'processed', 'benchmark_hs300.csv'),
            _P('data', 'raw', 'benchmark_hs300.csv'),
        ]
        benchmark_path = next((path for path in candidates if os.path.exists(path)), None)
        if benchmark_path is None:
            print("警告: 未找到沪深300指数文件，将使用股票池等权基准")
            return None, '股票池等权基准', 'universe_equal_weight'

        if benchmark_path.endswith('.parquet'):
            benchmark = pd.read_parquet(benchmark_path)
        else:
            benchmark = pd.read_csv(benchmark_path)

        date_col = 'date' if 'date' in benchmark.columns else 'trade_date'
        if date_col not in benchmark.columns or 'close' not in benchmark.columns:
            raise ValueError(f"基准文件缺少日期或 close 列: {benchmark_path}")

        date_values = benchmark[date_col].astype(str).str.replace(r'\.0$', '', regex=True)
        benchmark['date'] = pd.to_datetime(date_values, errors='coerce')
        benchmark['close'] = pd.to_numeric(benchmark['close'], errors='coerce')
        benchmark = benchmark.dropna(subset=['date', 'close']).sort_values('date')
        benchmark = benchmark.drop_duplicates(subset=['date'], keep='last')
        benchmark['benchmark_return'] = benchmark['close'].pct_change().shift(-1)
        print(f"沪深300基准加载完成: {benchmark_path}")
        return (
            benchmark[['date', 'benchmark_return']].dropna(),
            '沪深300',
            os.path.relpath(benchmark_path, _BASE_DIR),
        )

    def simple_strategy_backtest(self, predictions_df, benchmark_df=None,
                                 benchmark_name='股票池等权基准',
                                 benchmark_source='universe_equal_weight'):
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

        required_columns = {'date', 'code', 'predicted', 'actual'}
        missing_columns = required_columns - set(predictions_df.columns)
        if missing_columns:
            raise ValueError(f"预测结果缺少列: {sorted(missing_columns)}")

        df = predictions_df.copy()
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df['predicted'] = pd.to_numeric(df['predicted'], errors='coerce')
        df['actual'] = pd.to_numeric(df['actual'], errors='coerce')
        df = df.dropna(subset=['date', 'code', 'predicted', 'actual'])

        print(f"回测时间范围: {df['date'].min()} 至 {df['date'].max()}")
        print(f"回测股票数量: {df['code'].nunique()}")

        # 每日选股策略：选择预测收益率最高的N只股票
        N = self.n_stocks
        initial_capital = self.initial_capital

        print(f"\n策略参数:")
        print(f"  每日选股数: {N}")
        print(f"  初始资金: {initial_capital:,}")
        print(f"  成交口径: T+1 日收益率（使用 actual/label = ret.shift(-1)）")

        results = []
        daily_portfolios = []
        previous_codes = set()

        # 按日期分组处理
        for date, group in df.groupby('date'):
            # T 日收盘后按 predicted 排序，选出 Top-N
            group_sorted = group.sort_values('predicted', ascending=False)
            selected = group_sorted.head(N)

            if len(selected) == 0:
                continue

            # T+1 日实现收益 = actual = ret.shift(-1)
            # 即：T 日选股，T+1 日按 close-to-close 成交
            gross_return = selected['actual'].mean()
            current_codes = set(selected['code'].astype(str))
            if previous_codes:
                sold_weight = len(previous_codes - current_codes) / len(previous_codes)
                bought_weight = len(current_codes - previous_codes) / len(current_codes)
                turnover = 0.5 * (sold_weight + bought_weight)
                transaction_cost = (
                    sold_weight * (self.commission_rate + self.stamp_duty_rate)
                    + bought_weight * self.commission_rate
                )
            else:
                turnover = 1.0
                transaction_cost = self.commission_rate

            portfolio_return = gross_return - transaction_cost
            previous_codes = current_codes

            results.append({
                'date': date,
                'portfolio_return': portfolio_return,
                'n_stocks': len(selected),
                'avg_predicted_return': selected['predicted'].mean(),
                'gross_return': gross_return,
                'transaction_cost': transaction_cost,
                'turnover': turnover,
                'avg_actual_return': gross_return,
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
        if results_df.empty:
            raise ValueError("没有可用于回测的有效预测记录")

        # 计算累积收益率
        results_df['cumulative_return'] = (1 + results_df['portfolio_return']).cumprod()
        results_df['equity_curve'] = initial_capital * results_df['cumulative_return']

        # 没有指数文件时，明确退化为股票池等权基准，不冒充沪深300。
        if benchmark_df is None:
            all_stock_returns = df.groupby('date')['actual'].mean()
            benchmark_df = pd.DataFrame({
                'date': all_stock_returns.index,
                'benchmark_return': all_stock_returns.values,
            })
            benchmark_name = '股票池等权基准'
            benchmark_source = 'universe_equal_weight'
        else:
            benchmark_df = benchmark_df.copy()
            benchmark_df['date'] = pd.to_datetime(benchmark_df['date'], errors='coerce')
            benchmark_df = benchmark_df.dropna(subset=['date', 'benchmark_return'])

        # 合并结果
        results_df = results_df.merge(
            benchmark_df[['date', 'benchmark_return']], on='date', how='left'
        )
        results_df = results_df.dropna(subset=['benchmark_return']).reset_index(drop=True)
        if results_df.empty:
            raise ValueError("策略日期与基准日期没有交集")
        results_df['benchmark_cumulative'] = (1 + results_df['benchmark_return']).cumprod()
        results_df['benchmark_equity'] = initial_capital * results_df['benchmark_cumulative']

        # 计算策略指标
        total_return = results_df['cumulative_return'].iloc[-1] - 1
        benchmark_total_return = results_df['benchmark_cumulative'].iloc[-1] - 1
        
        daily_returns = results_df['portfolio_return'].dropna()
        annualized_return = results_df['cumulative_return'].iloc[-1] ** (252 / len(daily_returns)) - 1
        annualized_volatility = daily_returns.std() * np.sqrt(252)
        
        if annualized_volatility > 0:
            sharpe_ratio = daily_returns.mean() / daily_returns.std() * np.sqrt(252)
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

        print(f"\n基准表现 ({benchmark_name}):")
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
            'average_turnover': results_df['turnover'].mean(),
            'total_transaction_cost': results_df['transaction_cost'].sum(),
            'commission_rate': self.commission_rate,
            'stamp_duty_rate': self.stamp_duty_rate,
            'benchmark_name': benchmark_name,
            'benchmark_source': benchmark_source,
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

            benchmark_df, benchmark_name, benchmark_source = self.load_benchmark()
            self.simple_strategy_backtest(
                predictions_df,
                benchmark_df=benchmark_df,
                benchmark_name=benchmark_name,
                benchmark_source=benchmark_source,
            )

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
