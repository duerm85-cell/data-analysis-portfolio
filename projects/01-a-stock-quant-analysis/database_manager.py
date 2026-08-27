# database_manager.py - 数据库管理器
import sqlite3
import pandas as pd
import os
from datetime import datetime

# ========== 路径基准：全部以本文件所在目录为根，不依赖 cwd ==========
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
def _P(*parts):
    return os.path.join(_BASE_DIR, *parts)

class StockDatabase:
    """股票数据库管理器 - 使用SQLite"""
    
    def __init__(self, db_path=None):
        self.db_path = db_path or _P('data', 'stock_data.db')
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
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sentiment_code_date ON sentiment(code, date)')
        
        conn.commit()
        conn.close()
        print(f"✅ 数据库初始化完成: {self.db_path}")
    
    def import_from_parquet(self, parquet_path=None):
        """从Parquet文件导入数据"""
        if not os.path.exists(parquet_path):
            print(f"❌ 文件不存在: {parquet_path}")
            return
        
        print(f"📂 正在从 {parquet_path} 导入数据...")
        df = pd.read_parquet(parquet_path)
        
        conn = sqlite3.connect(self.db_path)
        
        # 导入因子数据
        factors_cols = ['code', 'date', 'ret', 'ma5', 'ma10', 'ma20', 'rsi', 'macd', 'sentiment', 'label']
        factors_df = df[[col for col in factors_cols if col in df.columns]]
        factors_df['date'] = pd.to_datetime(factors_df['date']).dt.strftime('%Y-%m-%d')
        factors_df.to_sql('factors', conn, if_exists='replace', index=False)
        
        print(f"✅ 已导入 {len(factors_df):,} 条因子数据")
        
        conn.close()
    
    def query(self, sql):
        """执行SQL查询"""
        conn = sqlite3.connect(self.db_path)
        result = pd.read_sql(sql, conn)
        conn.close()
        return result
    
    def get_latest_data(self, code, days=30):
        """获取指定股票的最新数据"""
        sql = f'''
            SELECT * FROM factors 
            WHERE code = '{code}' 
            ORDER BY date DESC 
            LIMIT {days}
        '''
        return self.query(sql)
    
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
