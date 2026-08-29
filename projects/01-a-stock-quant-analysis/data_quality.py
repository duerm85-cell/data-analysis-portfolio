"""数据质量度量与报告输出。"""

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone

import pandas as pd

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


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
    missing_rates = {
        column: round(float(rate), 6)
        for column, rate in data.isna().mean().sort_values(ascending=False).items()
        if rate > 0
    }

    invalid_ohlc = 0
    if {'open', 'high', 'low', 'close'}.issubset(data.columns):
        invalid_mask = (
            (data['high'] < data[['open', 'close']].max(axis=1))
            | (data['low'] > data[['open', 'close']].min(axis=1))
            | (data['high'] < data['low'])
        )
        invalid_ohlc = int(invalid_mask.fillna(False).sum())

    valid_dates = data['date'].dropna()
    start_date = valid_dates.min() if not valid_dates.empty else None
    end_date = valid_dates.max() if not valid_dates.empty else None
    source_distribution = {}
    if 'sentiment_source' in data.columns:
        source_distribution = {
            str(key): int(value)
            for key, value in data['sentiment_source'].fillna('not_available').value_counts().items()
        }

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
        'missing_rates': missing_rates,
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
