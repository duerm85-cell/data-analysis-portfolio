"""从经过校验的因子快照原子重建 SQLite 服务层。"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from database_manager import StockDatabase


REQUIRED_COLUMNS = {
    'code', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount'
}


def rebuild_database(input_path, database_path):
    input_path = Path(input_path).resolve()
    database_path = Path(database_path).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"因子快照不存在: {input_path}")

    frame = pd.read_parquet(input_path)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"因子快照缺少服务字段: {sorted(missing)}")

    frame = frame.dropna(subset=['code', 'date', 'close']).copy()
    frame = frame.drop_duplicates(subset=['code', 'date'], keep='last')
    if 'sentiment_source' not in frame.columns:
        frame['sentiment_source'] = 'legacy_unknown'

    database_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = database_path.with_suffix('.rebuild.tmp')
    if temporary_path.exists():
        temporary_path.unlink()

    try:
        database = StockDatabase(str(temporary_path))
        imported_rows = database.import_dataframe(frame, chunk_size=10_000)

        conn = sqlite3.connect(temporary_path)
        try:
            stored_rows = conn.execute('SELECT COUNT(*) FROM factors').fetchone()[0]
            stored_columns = {
                row[1] for row in conn.execute('PRAGMA table_info(factors)').fetchall()
            }
            if stored_rows != imported_rows:
                raise RuntimeError(
                    f"服务层行数校验失败: expected={imported_rows}, actual={stored_rows}"
                )
            if REQUIRED_COLUMNS - stored_columns:
                raise RuntimeError("服务层字段校验失败")

            conn.execute(
                'CREATE TABLE IF NOT EXISTS pipeline_metadata '
                '(key TEXT PRIMARY KEY, value TEXT NOT NULL)'
            )
            metadata = {
                'source': 'processed_parquet',
                'source_path': str(input_path.relative_to(PROJECT_DIR)),
                'built_at': datetime.now(timezone.utc).isoformat(),
                'row_count': str(stored_rows),
                'stock_count': str(frame['code'].nunique()),
                'start_date': str(pd.to_datetime(frame['date']).min().date()),
                'end_date': str(pd.to_datetime(frame['date']).max().date()),
                'sentiment_provenance': 'legacy_unknown',
            }
            conn.executemany(
                'INSERT OR REPLACE INTO pipeline_metadata(key, value) VALUES (?, ?)',
                metadata.items(),
            )
            conn.commit()
        finally:
            conn.close()

        backup_path = None
        if database_path.exists():
            backup_dir = database_path.parent / 'backups'
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = backup_dir / f'{database_path.stem}_legacy_{stamp}.db'
            shutil.copy2(database_path, backup_path)

        os.replace(temporary_path, database_path)
        manifest = {
            **metadata,
            'database_path': str(database_path.relative_to(PROJECT_DIR)),
            'backup_path': (
                str(backup_path.relative_to(PROJECT_DIR)) if backup_path else None
            ),
        }
        manifest_path = PROJECT_DIR / 'data' / 'processed' / 'serving_manifest.json'
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        return manifest
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise


def main():
    parser = argparse.ArgumentParser(description='重建量化数据 SQLite 服务层')
    parser.add_argument(
        '--input', default=PROJECT_DIR / 'data' / 'processed' / 'all_factors.parquet'
    )
    parser.add_argument(
        '--database', default=PROJECT_DIR / 'data' / 'stock_data.db'
    )
    args = parser.parse_args()
    manifest = rebuild_database(args.input, args.database)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
