"""T 日收盘信号、下一市场交易日开盘调仓的现金/持仓回测。"""

from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
METHODOLOGY_VERSION = 'next_open_v2'


def _normalize(frame, keys=('code', 'date')):
    data = frame.copy()
    data['date'] = pd.to_datetime(data['date'], errors='raise').dt.normalize()
    if 'code' in keys:
        data['code'] = data['code'].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(6)
        if not data['code'].str.fullmatch(r'\d{6}').all():
            raise ValueError('无效股票代码')
    if data[list(keys)].isna().any().any() or data.duplicated(list(keys)).any():
        raise ValueError('日期/股票主键为空或重复；禁止混合重叠实验预测')
    return data.sort_values(list(keys)).reset_index(drop=True)


class StockBacktester:
    def __init__(self, output_dir=None, n_stocks=10, initial_capital=1_000_000,
                 commission_rate=0.0003, stamp_duty_rate=0.0005, slippage_rate=0.001):
        if n_stocks < 1 or initial_capital <= 0:
            raise ValueError('持仓数和资金必须为正')
        if any(not 0 <= rate < 1 for rate in (commission_rate, stamp_duty_rate, slippage_rate)):
            raise ValueError('费率必须位于 [0, 1)')
        self.results_dir = BASE_DIR / 'results_optimized'
        self.output_dir = Path(output_dir or BASE_DIR / 'backtest_results')
        self.n_stocks, self.initial_capital = n_stocks, initial_capital
        self.commission_rate = commission_rate
        self.stamp_duty_rate, self.slippage_rate = stamp_duty_rate, slippage_rate

    def load_data(self):
        path = BASE_DIR / 'data/processed/all_factors.parquet'
        if path.exists():
            return pd.read_parquet(path)
        return pd.read_csv(path.with_suffix('.csv'), dtype={'code': str})

    def load_predictions(self):
        classification_path = self.results_dir / 'test_predictions_classification.csv'
        if not classification_path.exists():
            raise FileNotFoundError('缺少统一口径的样本外分类预测：test_predictions_classification.csv')
        return _normalize(pd.read_csv(classification_path, dtype={'code': str}))

    def load_benchmark(self):
        for relative in ('data/processed/benchmark_hs300.parquet',
                         'data/processed/benchmark_hs300.csv', 'data/raw/benchmark_hs300.csv'):
            path = BASE_DIR / relative
            if path.exists():
                frame = pd.read_parquet(path) if path.suffix == '.parquet' else pd.read_csv(path)
                frame = frame.rename(columns={'trade_date': 'date'})
                frame['date'] = pd.to_datetime(frame['date'].astype(str).str.replace(r'\.0$', '', regex=True))
                if 'open' not in frame:
                    raise ValueError('基准缺少 open；不得退回不同区间的收盘收益')
                return frame[['date', 'open']], '沪深300', relative
        return None, '股票池等权基准', 'universe_equal_weight_open'

    @staticmethod
    def _blocked(row, side):
        # 缺少该市场日记录时，不跳到该股票未来某条记录成交。
        if row is None or not np.isfinite(row.get('open', np.nan)) or row['open'] <= 0:
            return 'missing_open'
        # 日总量为零只能作为保守的事后不可交易筛选，不证明开盘流动性。
        if not np.isfinite(row.get('volume', np.nan)) or row['volume'] <= 0:
            return 'missing_or_zero_volume'
        if pd.notna(row.get('is_suspended')) and bool(row['is_suspended']):
            return 'suspended'
        if pd.notna(row.get('can_' + side)) and not bool(row['can_' + side]):
            return 'explicit_block'
        # 有真实逐日限价才判断；不假定全市场统一 10%。缺少限价在报告中声明。
        bound = row.get('limit_up' if side == 'buy' else 'limit_down', np.nan)
        if pd.notna(bound) and ((side == 'buy' and row['open'] >= bound) or
                                (side == 'sell' and row['open'] <= bound)):
            return 'price_limit'
        return None

    def simple_strategy_backtest(self, predictions_df, benchmark_df=None,
                                 benchmark_name='股票池等权基准',
                                 benchmark_source='universe_equal_weight_open', *, market_df=None):
        if market_df is None:
            raise ValueError('必须提供行情执行价格；禁止使用 actual 标签回退计算收益')
        signals = _normalize(predictions_df)
        signals['predicted'] = pd.to_numeric(signals['predicted'], errors='raise')
        if signals.empty or not np.isfinite(signals['predicted']).all():
            raise ValueError('预测为空或包含无效值')
        market = _normalize(market_df)
        for column in ('open', 'volume'):
            market[column] = pd.to_numeric(market[column], errors='coerce')
        calendar = pd.DatetimeIndex(sorted(market['date'].unique()))
        if not signals['date'].isin(calendar).all():
            raise ValueError('信号日期必须属于行情市场日历')
        # 末端信号没有次日执行和再下一日估值，按可执行区间自然截断。
        executable_cutoff = calendar[-3]
        signals = signals[signals['date'] <= executable_cutoff].copy()
        if signals.empty:
            raise ValueError('没有同时具备次日执行和再下一日估值的信号')
        first, last = calendar.get_loc(signals['date'].min()), calendar.get_loc(signals['date'].max())
        dates = calendar[first + 1:last + 3]
        # 全部收益区间先对齐，再计算净值；缺失基准不能事后删掉策略日期。
        if benchmark_df is not None:
            benchmark = _normalize(benchmark_df, ('date',)).set_index('date')['open'].reindex(dates)
            benchmark = pd.to_numeric(benchmark, errors='coerce')
            if not np.isfinite(benchmark).all() or (benchmark <= 0).any():
                raise ValueError('基准开盘价覆盖不完整')
            benchmark_curve = benchmark / benchmark.iloc[0]
        else:
            universe = market[market['code'].isin(signals['code'].unique())].pivot(
                index='date', columns='code', values='open').reindex(dates)
            if universe.empty or not np.isfinite(universe).all().all() or (universe <= 0).any().any():
                raise ValueError('等权基准缺少开盘价；请提供完整指数基准')
            benchmark_curve = (1 + universe.pct_change(fill_method=None).mean(axis=1).fillna(0)).cumprod()

        signal_days = {day: group for day, group in signals.groupby('date')}
        bars = {(r['date'], r['code']): r for r in market.to_dict('records')}
        cash, previous_nav = float(self.initial_capital), float(self.initial_capital)
        shares, marks = {}, {}
        results, holdings, orders = [], [], []
        for i, day in enumerate(dates):
            stale_marks = 0
            for code in shares:
                row = bars.get((day, code))
                if row is not None and np.isfinite(row['open']) and row['open'] > 0:
                    marks[code] = row['open']
                else:
                    # 卖不掉的持仓继续保留，按上次有效开盘价暂估，不能凭空变回现金。
                    stale_marks += 1
            before = cash + sum(q * marks[c] for c, q in shares.items())
            costs, slippage, traded = 0.0, 0.0, 0.0
            signal_day = calendar[calendar.get_loc(day) - 1]
            group = signal_days.get(signal_day)
            if i < len(dates) - 1 and group is not None:
                selected = group.sort_values(['predicted', 'code'], ascending=[False, True]).head(self.n_stocks)
                scores = selected.set_index('code')['predicted'].to_dict()
                # 入选失败不补位、不把剩余股票放大至满仓；Top-N 策略保持原意。
                budget = before / self.n_stocks
                desired = {}
                for code in scores:
                    row = bars.get((day, code))
                    price = row.get('open', np.nan) if row else np.nan
                    desired[code] = budget / price if np.isfinite(price) and price > 0 else shares.get(code, 0)
                    if not np.isfinite(price) or price <= 0:
                        orders.append(dict(date=day, signal_date=signal_day, code=code, side='buy',
                                           status='blocked', reason='missing_open', quantity=0))
                # 先卖已有仓位，再买；今天新买的股票不会在今天卖出，满足 T+1 最短持有。
                for side in ('sell', 'buy'):
                    codes = sorted(shares) if side == 'sell' else list(scores)
                    for code in codes:
                        quantity = (shares.get(code, 0) - desired.get(code, 0)) if side == 'sell' else (
                            desired.get(code, 0) - shares.get(code, 0))
                        if quantity <= 1e-10:
                            continue
                        row = bars.get((day, code))
                        reason = self._blocked(row, side)
                        if reason:
                            orders.append(dict(date=day, signal_date=signal_day, code=code, side=side,
                                               status='blocked', reason=reason, quantity=quantity))
                            continue
                        reference = row['open']
                        price = reference * (1 + self.slippage_rate if side == 'buy' else 1 - self.slippage_rate)
                        rate = self.commission_rate + (self.stamp_duty_rate if side == 'sell' else 0)
                        if side == 'buy':
                            quantity = min(quantity, max(cash, 0) / (price * (1 + rate)))
                        if quantity <= 1e-10:
                            continue
                        value, fee = quantity * price, quantity * price * rate
                        cash += value - fee if side == 'sell' else -value - fee
                        shares[code] = shares.get(code, 0) + (-quantity if side == 'sell' else quantity)
                        marks[code] = reference
                        costs += fee
                        slippage += quantity * abs(price - reference)
                        traded += quantity * reference
                        orders.append(dict(date=day, signal_date=signal_day, code=code, side=side,
                                           status='filled', reason='', quantity=quantity, price=price, fee=fee))
                shares = {c: q for c, q in shares.items() if q > 1e-10}
            nav = cash + sum(q * marks[c] for c, q in shares.items())
            results.append(dict(date=day, signal_date=signal_day, portfolio_return=nav / previous_nav - 1,
                                gross_return=before / previous_nav - 1, equity_curve=nav,
                                cumulative_return=nav / self.initial_capital,
                                transaction_cost=costs / previous_nav, transaction_cost_amount=costs,
                                slippage_amount=slippage, turnover=traded / (2 * before),
                                cash=cash, n_stocks=len(shares), stale_price_positions=stale_marks))
            for code, quantity in shares.items():
                holdings.append(dict(date=day, code=code, quantity=quantity, mark_price=marks[code]))
            previous_nav = nav
        result = pd.DataFrame(results)
        result['benchmark_cumulative'] = benchmark_curve.to_numpy()
        result['benchmark_return'] = benchmark_curve.pct_change(fill_method=None).fillna(0).to_numpy()
        result['benchmark_equity'] = result['benchmark_cumulative'] * self.initial_capital
        values = np.r_[self.initial_capital, result['equity_curve']]
        drawdown = values / np.maximum.accumulate(values) - 1
        returns = result['portfolio_return']
        vol = returns.std() * np.sqrt(252)
        total, bench_total = values[-1] / self.initial_capital - 1, benchmark_curve.iloc[-1] - 1
        filled_order_count = sum(order['status'] == 'filled' for order in orders)
        blocked_order_count = sum(order['status'] == 'blocked' for order in orders)
        blocked_missing_open_count = sum(
            order['status'] == 'blocked' and order['reason'] == 'missing_open'
            for order in orders
        )
        metrics = dict(methodology_version=METHODOLOGY_VERSION, execution_price_source='next_market_open',
                       initial_capital=self.initial_capital, n_stocks_per_day=self.n_stocks,
                       total_return=total, benchmark_total_return=bench_total, excess_return=total - bench_total,
                       annualized_return=(1 + total) ** (252 / (len(dates) - 1)) - 1,
                       annualized_volatility=vol, sharpe_ratio=returns.mean() * 252 / vol if vol > 0 else 0,
                       max_drawdown=drawdown.min(), win_rate=(returns > 0).mean(),
                       average_turnover=result['turnover'].mean(), total_transaction_cost=result['transaction_cost'].sum(),
                       transaction_cost_amount=result['transaction_cost_amount'].sum(),
                       slippage_amount=result['slippage_amount'].sum(), commission_rate=self.commission_rate,
                       stamp_duty_rate=self.stamp_duty_rate, slippage_rate=self.slippage_rate,
                       benchmark_name=benchmark_name, benchmark_source=benchmark_source,
                       signal_source='xgboost_direction_probability', final_holdings_policy='mark_only_no_liquidation',
                       filled_order_count=filled_order_count, blocked_order_count=blocked_order_count,
                       blocked_missing_open_count=blocked_missing_open_count,
                       price_limit_data_available=all(c in market and market[c].notna().all()
                                                     for c in ('limit_up', 'limit_down')),
                       suspension_data_available='is_suspended' in market and market['is_suspended'].notna().all())
        self.output_dir.mkdir(parents=True, exist_ok=True)
        result.to_csv(self.output_dir / 'backtest_results.csv', index=False)
        pd.DataFrame([metrics]).to_csv(self.output_dir / 'backtest_metrics.csv', index=False)
        pd.DataFrame(holdings).to_csv(self.output_dir / 'daily_portfolios.csv', index=False)
        pd.DataFrame(orders).to_csv(self.output_dir / 'execution_log.csv', index=False)
        return result, metrics

    def run(self):
        benchmark, name, source = self.load_benchmark()
        result, metrics = self.simple_strategy_backtest(self.load_predictions(), benchmark, name, source,
                                                        market_df=self.load_data())
        print(f"{METHODOLOGY_VERSION}: {len(result)} 开盘估值点；收益 {metrics['total_return']:.2%}")


if __name__ == '__main__':
    StockBacktester().run()
