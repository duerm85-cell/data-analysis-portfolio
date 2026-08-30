"""数据质量度量与报告输出。"""

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone

import pandas as pd

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STRUCTURAL_FACTOR_COLUMNS = {
    'ret_5d', 'ret_10d', 'momentum_20d', 'momentum_60d', 'reversal_5d',
    'ma5', 'ma10', 'ma20', 'ma60', 'volatility_20d', 'volatility_60d',
    'volume_ma5', 'amount_ma20', 'sentiment_ma5', 'sentiment_ma10',
}
RAW_REQUIRED_COLUMNS = {'code', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount'}


def _P(*parts):
    return os.path.join(_BASE_DIR, *parts)


def build_quality_report(frame):
    required = {'code', 'date'}
    missing_required = required - set(frame.columns)
    if missing_required:
        raise ValueError(f"数据缺少必要字段: {sorted(missing_required)}")

    data = frame.copy()
    data['date'] = pd.to_datetime(data['date'], errors='coerce')
    duplicate_count = int(data.duplicated(subset=['code', 'date']).sum())
    missing_counts = data.isna().sum().sort_values(ascending=False)
    missing_rates = {
        column: round(float(rate), 6)
        for column, rate in data.isna().mean().sort_values(ascending=False).items()
        if rate > 0
    }
    missing_details = {}
    missing_category_counts = {
        'structural_factor': 0,
        'structural_label': 0,
        'unexpected': 0,
    }
    for column, count in missing_counts.items():
        count = int(count)
        if not count:
            continue
        if column in STRUCTURAL_FACTOR_COLUMNS:
            category = 'structural_factor'
            reason = '滚动窗口开始阶段历史长度不足'
        elif column == 'label':
            category = 'structural_label'
            reason = '每只股票末期没有下一交易日标签'
        else:
            category = 'unexpected'
            reason = '不属于已声明的结构性缺失，需要检查上游数据'
        missing_category_counts[category] += count
        missing_details[column] = {
            'count': count,
            'rate': round(count / len(data), 6) if len(data) else 0.0,
            'category': category,
            'reason': reason,
        }

    invalid_ohlc = 0
    if {'open', 'high', 'low', 'close'}.issubset(data.columns):
        invalid_mask = (
            (data['high'] < data[['open', 'close']].max(axis=1))
            | (data['low'] > data[['open', 'close']].min(axis=1))
            | (data['high'] < data['low'])
        )
        invalid_ohlc = int(invalid_mask.fillna(False).sum())

    price_columns = [column for column in ['open', 'high', 'low', 'close'] if column in data]
    nonpositive_price_count = int(
        data[price_columns].le(0).any(axis=1).sum()
    ) if price_columns else 0
    negative_volume_count = int((data['volume'] < 0).fillna(False).sum()) if 'volume' in data else 0
    zero_volume_count = int((data['volume'] == 0).fillna(False).sum()) if 'volume' in data else 0
    normalized_codes = data['code'].astype(str).str.replace(r'\.0$', '', regex=True)
    invalid_code_count = int((~normalized_codes.str.fullmatch(r'\d{6}')).sum())

    extreme_return_count = 0
    if 'close' in data:
        ordered = data.sort_values(['code', 'date'])
        returns = ordered.groupby('code')['close'].pct_change(fill_method=None)
        extreme_return_count = int((returns.abs() > 0.30).fillna(False).sum())

    valid_dates = data['date'].dropna()
    start_date = valid_dates.min() if not valid_dates.empty else None
    end_date = valid_dates.max() if not valid_dates.empty else None
    source_distribution = {}
    if 'sentiment_source' in data.columns:
        source_distribution = {
            str(key): int(value)
            for key, value in data['sentiment_source'].fillna('not_available').value_counts().items()
        }

    raw_missing_cell_count = int(
        sum(missing_counts.get(column, 0) for column in RAW_REQUIRED_COLUMNS)
    )
    fail_count = sum([
        duplicate_count,
        int(data['date'].isna().sum()),
        invalid_ohlc,
        missing_category_counts['unexpected'],
        nonpositive_price_count,
        negative_volume_count,
        invalid_code_count,
    ])
    warning_count = sum([
        missing_category_counts['structural_factor'],
        missing_category_counts['structural_label'],
        zero_volume_count,
        extreme_return_count,
    ])
    quality_status = 'FAIL' if fail_count else 'WARN' if warning_count else 'PASS'

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'row_count': int(len(data)),
        'stock_count': int(data['code'].nunique()),
        'column_count': int(len(data.columns)),
        'start_date': start_date.strftime('%Y-%m-%d') if start_date is not None else None,
        'end_date': end_date.strftime('%Y-%m-%d') if end_date is not None else None,
        'invalid_date_count': int(data['date'].isna().sum()),
        'duplicate_key_count': duplicate_count,
        'invalid_ohlc_count': invalid_ohlc,
        'missing_cell_count': int(data.isna().sum().sum()),
        'raw_missing_cell_count': raw_missing_cell_count,
        'structural_factor_missing_count': missing_category_counts['structural_factor'],
        'structural_label_missing_count': missing_category_counts['structural_label'],
        'unexpected_missing_cell_count': missing_category_counts['unexpected'],
        'missing_rates': missing_rates,
        'missing_details': missing_details,
        'nonpositive_price_count': nonpositive_price_count,
        'negative_volume_count': negative_volume_count,
        'zero_volume_count': zero_volume_count,
        'invalid_code_count': invalid_code_count,
        'extreme_return_count': extreme_return_count,
        'quality_status': quality_status,
        'sentiment_source_distribution': source_distribution,
    }


def load_factors_from_database(database_path):
    conn = sqlite3.connect(database_path)
    try:
        return pd.read_sql_query('SELECT * FROM factors', conn)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='生成量化因子数据质量报告')
    parser.add_argument('--database', default=_P('data', 'stock_data.db'))
    parser.add_argument('--output', default=_P('reports', 'data_quality.json'))
    args = parser.parse_args()

    frame = load_factors_from_database(args.database)
    report = build_quality_report(frame)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
