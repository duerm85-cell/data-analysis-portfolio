# database_manager.py - 数据库管理器
import sqlite3
import pandas as pd
import os
import re

# ========== 路径基准：全部以本文件所在目录为根，不依赖 cwd ==========
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
def _P(*parts):
    return os.path.join(_BASE_DIR, *parts)

class StockDatabase:
    """股票数据库管理器 - 使用SQLite"""
    
    def __init__(self, db_path=None):
        self.db_path = db_path or _P('data', 'stock_data.db')
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(db_dir, exist_ok=True)
        self.init_database()
    
    def init_database(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建股票基本信息表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stocks (
                code TEXT PRIMARY KEY,
                name TEXT,
                market TEXT,
                list_date TEXT
            )
        ''')
        
        # 创建日线数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                date TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                amount REAL,
                UNIQUE(code, date)
            )
        ''')
        
        # 创建因子数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS factors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                date TEXT,
                ret REAL,
                ma5 REAL,
                ma10 REAL,
                ma20 REAL,
                rsi REAL,
                macd REAL,
                sentiment REAL,
                label REAL,
                UNIQUE(code, date)
            )
        ''')
        
        # 创建情感数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sentiment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                date TEXT,
                sentiment REAL,
                sentiment_ma5 REAL,
                sentiment_ma10 REAL,
                comment_count INTEGER,
                news_count INTEGER,
                UNIQUE(code, date)
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_code_date ON daily_data(code, date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_factors_code_date ON factors(code, date)')
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_factors_code_date ON factors(code, date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sentiment_code_date ON sentiment(code, date)')
        
        conn.commit()
        conn.close()
        print(f"✅ 数据库初始化完成: {self.db_path}")
    
    @staticmethod
    def _validate_columns(columns):
        invalid = [column for column in columns if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', column)]
        if invalid:
            raise ValueError(f"存在不安全的字段名: {invalid}")

    @staticmethod
    def _sqlite_type(dtype):
        if pd.api.types.is_integer_dtype(dtype) or pd.api.types.is_bool_dtype(dtype):
            return 'INTEGER'
        if pd.api.types.is_float_dtype(dtype):
            return 'REAL'
        return 'TEXT'

    def _ensure_factor_columns(self, conn, frame):
        existing = {
            row[1] for row in conn.execute('PRAGMA table_info(factors)').fetchall()
        }
        for column in frame.columns:
            if column not in existing:
                column_type = self._sqlite_type(frame[column].dtype)
                conn.execute(f'ALTER TABLE factors ADD COLUMN "{column}" {column_type}')

    def import_from_parquet(self, parquet_path=None, chunk_size=5000):
        """从Parquet文件导入数据。

        未指定路径时，默认导入数据流水线生成的因子文件。
        """
        parquet_path = parquet_path or _P('data', 'processed', 'all_factors.parquet')
        if not os.path.exists(parquet_path):
            print(f"❌ 文件不存在: {parquet_path}")
            return
        
        print(f"📂 正在从 {parquet_path} 导入数据...")
        df = pd.read_parquet(parquet_path)
        return self.import_dataframe(df, chunk_size=chunk_size)

    def import_dataframe(self, df, chunk_size=5000):
        """将因子 DataFrame 分块增量写入 SQLite。"""
        required_columns = {'code', 'date'}
        missing_columns = required_columns - set(df.columns)
        if missing_columns:
            raise ValueError(f"因子文件缺少必要字段: {sorted(missing_columns)}")
        if not isinstance(chunk_size, int) or chunk_size <= 0:
            raise ValueError("chunk_size 必须是正整数")

        factors_df = df.copy()
        # 空代码必须在字符串化前剔除，否则 NaN 会被写成无效的 ``000nan``。
        factors_df = factors_df.dropna(subset=['code', 'date']).copy()
        factors_df['code'] = factors_df['code'].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(6)
        factors_df['date'] = pd.to_datetime(factors_df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
        factors_df = factors_df.dropna(subset=['date'])
        factors_df = factors_df.drop_duplicates(subset=['code', 'date'], keep='last')
        columns = factors_df.columns.tolist()
        self._validate_columns(columns)

        quoted_columns = ', '.join(f'"{column}"' for column in columns)
        placeholders = ', '.join('?' for _ in columns)
        update_columns = [column for column in columns if column not in {'code', 'date'}]
        update_clause = ', '.join(
            f'"{column}" = excluded."{column}"' for column in update_columns
        )
        conflict_clause = (
            f'DO UPDATE SET {update_clause}' if update_clause else 'DO NOTHING'
        )
        sql = (
            f'INSERT INTO factors ({quoted_columns}) VALUES ({placeholders}) '
            f'ON CONFLICT(code, date) {conflict_clause}'
        )

        conn = sqlite3.connect(self.db_path)
        try:
            self._ensure_factor_columns(conn, factors_df)
            for start in range(0, len(factors_df), chunk_size):
                chunk = factors_df.iloc[start:start + chunk_size].astype(object)
                chunk = chunk.where(pd.notna(chunk), None)
                rows = list(chunk.itertuples(index=False, name=None))
                conn.executemany(sql, rows)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        print(f"✅ 已增量写入 {len(factors_df):,} 条因子数据")
        return len(factors_df)
    
    def query(self, sql, params=None):
        """执行只读 SQL 查询，并通过 params 绑定外部输入。"""
        conn = sqlite3.connect(self.db_path)
        try:
            return pd.read_sql_query(sql, conn, params=params)
        finally:
            conn.close()
    
    def get_latest_data(self, code, days=30):
        """获取指定股票的最新数据"""
        if not isinstance(days, int) or isinstance(days, bool) or days <= 0:
            raise ValueError("days 必须是正整数")

        sql = '''
            SELECT * FROM factors 
            WHERE code = ?
            ORDER BY date DESC 
            LIMIT ?
        '''
        return self.query(sql, (str(code), days))
    
    def get_stock_list(self):
        """获取所有股票列表"""
        return self.query("SELECT DISTINCT code FROM factors ORDER BY code")
    
    def get_data_count(self):
        """获取数据统计"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM factors")
        factors_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT code) FROM factors")
        stock_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'factors_count': factors_count,
            'stock_count': stock_count
        }

def main():
    print("=" * 60)
    print("数据库管理器")
    print("=" * 60)
    
    # 创建数据库实例
    db = StockDatabase()
    
    # 导入数据
    db.import_from_parquet()
    
    # 查看统计
    stats = db.get_data_count()
    print(f"\n📊 数据库统计:")
    print(f"  因子数据: {stats['factors_count']:,} 条")
    print(f"  股票数量: {stats['stock_count']} 只")
    
    # 示例查询
    print("\n📝 示例查询 - 获取贵州茅台最近5天数据:")
    df = db.get_latest_data('600519', days=5)
    print(df)

if __name__ == "__main__":
    main()
