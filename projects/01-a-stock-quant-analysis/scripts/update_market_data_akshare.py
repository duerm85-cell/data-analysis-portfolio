"""使用 AKShare/Sina 增量更新现有股票池和沪深300基准。"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import akshare as ak
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / 'data' / 'raw'
MANIFEST_PATH = PROJECT_DIR / 'data' / 'processed' / 'market_update_manifest.json'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def _market_symbol(code):
    return f"{'sh' if code.startswith(('6', '9')) else 'sz'}{code}"


def _normalise_sina(frame, code):
    data = frame.copy()
    required = {'date', 'open', 'high', 'low', 'close', 'volume', 'amount'}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"AKShare 返回缺少字段: {sorted(missing)}")
    suffix = 'SH' if code.startswith(('6', '9')) else 'SZ'
    return pd.DataFrame(
        {
            'ts_code': f'{code}.{suffix}',
            'trade_date': pd.to_datetime(data['date']).dt.strftime('%Y%m%d'),
            'open': pd.to_numeric(data['open'], errors='coerce'),
            'high': pd.to_numeric(data['high'], errors='coerce'),
            'low': pd.to_numeric(data['low'], errors='coerce'),
            'close': pd.to_numeric(data['close'], errors='coerce'),
            # Sina 为股/元；Tushare 日线为手/千元。
            'vol': pd.to_numeric(data['volume'], errors='coerce') / 100,
            'amount': pd.to_numeric(data['amount'], errors='coerce') / 1000,
        }
    ).dropna(subset=['trade_date', 'close'])


def _merge_history(existing, incremental, code):
    old = existing.copy()
    old['trade_date'] = old['trade_date'].astype(str).str.replace(r'\.0$', '', regex=True)
    overlap = old[['trade_date', 'close', 'vol', 'amount']].merge(
        incremental[['trade_date', 'close', 'vol', 'amount']],
        on='trade_date',
        suffixes=('_old', '_new'),
    )
    if not overlap.empty:
        for column in ['close', 'vol', 'amount']:
            old_values = pd.to_numeric(overlap[f'{column}_old'], errors='coerce')
            new_values = pd.to_numeric(overlap[f'{column}_new'], errors='coerce')
            denominator = old_values.abs().clip(lower=1.0)
            max_relative_delta = float(((old_values - new_values).abs() / denominator).max())
            if max_relative_delta > 1e-6:
                raise ValueError(
                    f'{code} 重叠日期 {column} 口径不一致: '
                    f'max_relative_delta={max_relative_delta}'
                )

    standard = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount']
    combined = pd.concat([old[standard], incremental[standard]], ignore_index=True)
    combined = combined.drop_duplicates('trade_date', keep='last').sort_values('trade_date')
    combined['pre_close'] = combined['close'].shift(1)
    combined['change'] = combined['close'] - combined['pre_close']
    combined['pct_chg'] = combined['change'] / combined['pre_close'] * 100
    output_columns = [
        'ts_code', 'trade_date', 'open', 'high', 'low', 'close',
        'pre_close', 'change', 'pct_chg', 'vol', 'amount',
    ]
    return combined[output_columns]


def _update_one(path, end_date, retries=3):
    code = path.stem.split('_')[0]
    existing = pd.read_csv(path)
    last_date = pd.to_datetime(existing['trade_date'].astype(str)).max()
    # 取10个自然日重叠区间，用于跨数据源口径校验。
    start_date = (last_date - timedelta(days=10)).strftime('%Y%m%d')
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            fetched = ak.stock_zh_a_daily(
                symbol=_market_symbol(code),
                start_date=start_date,
                end_date=end_date,
                adjust='',
            )
            if fetched.empty:
                return {'code': code, 'status': 'no_data', 'old_end': last_date.date().isoformat()}
            incremental = _normalise_sina(fetched, code)
            merged = _merge_history(existing, incremental, code)
            temporary_path = path.with_suffix('.csv.tmp')
            merged.to_csv(temporary_path, index=False)
            os.replace(temporary_path, path)
            return {
                'code': code,
                'status': 'updated',
                'rows': len(merged),
                'old_end': last_date.date().isoformat(),
                'new_end': pd.to_datetime(merged['trade_date']).max().date().isoformat(),
            }
        except Exception as exc:
            last_error = str(exc)
            time.sleep(attempt * 1.5)
    return {'code': code, 'status': 'failed', 'error': last_error}


def _update_benchmark(end_date):
    benchmark = ak.stock_zh_index_daily(symbol='sh000300')
    benchmark['date'] = pd.to_datetime(benchmark['date'])
    benchmark = benchmark[benchmark['date'] <= pd.to_datetime(end_date)]
    benchmark = benchmark.sort_values('date').drop_duplicates('date', keep='last')
    output = pd.DataFrame(
        {
            'trade_date': benchmark['date'].dt.strftime('%Y%m%d'),
            'open': benchmark['open'],
            'high': benchmark['high'],
            'low': benchmark['low'],
            'close': benchmark['close'],
            'vol': benchmark['volume'],
        }
    )
    output.to_csv(RAW_DIR / 'benchmark_hs300.csv', index=False)
    return {
        'rows': len(output),
        'start_date': benchmark['date'].min().date().isoformat(),
        'end_date': benchmark['date'].max().date().isoformat(),
    }


def run_update(end_date, workers=4):
    stock_paths = sorted(RAW_DIR.glob('*_daily.csv'))
    if not stock_paths:
        raise FileNotFoundError(f'未找到股票原始文件: {RAW_DIR}')

    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_update_one, path, end_date): path for path in stock_paths
        }
        for completed, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            print(
                f"[{completed}/{len(stock_paths)}] {result['code']} "
                f"{result['status']} {result.get('new_end', '')}"
            )

    benchmark = _update_benchmark(end_date)
    status_counts = pd.Series([item['status'] for item in results]).value_counts().to_dict()
    manifest = {
        'source': 'AKShare stock_zh_a_daily / Sina',
        'adjustment': 'none',
        'requested_end_date': pd.to_datetime(end_date).date().isoformat(),
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'stock_count': len(stock_paths),
        'status_counts': {str(key): int(value) for key, value in status_counts.items()},
        'benchmark': benchmark,
        'failures': [item for item in results if item['status'] == 'failed'],
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if manifest['failures']:
        raise RuntimeError(f"{len(manifest['failures'])} 只股票更新失败，详见 manifest")
    return manifest


def main():
    parser = argparse.ArgumentParser(description='使用 AKShare 增量更新市场数据')
    parser.add_argument('--end-date', default=datetime.now().strftime('%Y%m%d'))
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 8:
        parser.error('--workers 必须在 1 到 8 之间')
    run_update(args.end_date, workers=args.workers)


if __name__ == '__main__':
    main()
