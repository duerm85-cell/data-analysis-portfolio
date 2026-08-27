import pandas as pd
import numpy as np
import os
import shutil
from datetime import datetime
import glob

class DataPreprocessor:
    def __init__(self, raw_dir='./data/raw/', invalid_dir='./data/raw/invalid/', 
                 clean_dir='./data/clean/', report_file='data_cleaning_report.txt'):
        self.raw_dir = raw_dir
        self.invalid_dir = invalid_dir
        self.clean_dir = clean_dir
        self.report_file = report_file
        
        self.required_columns = ['trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount']
        self.column_mapping = {'trade_date': 'date', 'vol': 'volume'}
        
        self.report = {
            'summary': {},
            'file_details': [],
            'missing_stats': {},
            'anomaly_stats': {},
            'invalid_files': []
        }
    
    def create_directories(self):
        """创建必要的目录"""
        os.makedirs(self.invalid_dir, exist_ok=True)
        os.makedirs(self.clean_dir, exist_ok=True)
        print(f"目录结构准备完成:")
        print(f"  原始数据目录: {self.raw_dir}")
        print(f"  无效文件目录: {self.invalid_dir}")
        print(f"  清洗后数据目录: {self.clean_dir}")
    
    def check_required_columns(self, df, filename):
        """检查是否包含必要的列"""
        missing_cols = [col for col in self.required_columns if col not in df.columns]
        
        if missing_cols:
            reason = f"缺少必要列: {', '.join(missing_cols)}"
            return False, reason
        return True, None
    
    def check_duplicates(self, df, code):
        """检查并删除重复行"""
        if 'trade_date' in df.columns:
            before_count = len(df)
            df = df.drop_duplicates(subset=['trade_date'], keep='first')
            after_count = len(df)
            duplicates = before_count - after_count
            
            if duplicates > 0:
                print(f"    ⚠️ 发现 {duplicates} 条重复记录，已删除")
            
            return df, duplicates
        return df, 0
    
    def check_date_format(self, df, code):
        """检查日期格式并标准化"""
        if 'trade_date' not in df.columns:
            return df, False, "无trade_date列"
        
        try:
            df['trade_date'] = pd.to_datetime(df['trade_date'], errors='coerce', format='%Y%m%d')
            
            if df['trade_date'].isna().all():
                df['trade_date'] = pd.to_datetime(df['trade_date'], errors='coerce')
            
            invalid_dates = df['trade_date'].isna().sum()
            
            if invalid_dates > 0:
                print(f"    ⚠️ 发现 {invalid_dates} 条无效日期，已删除")
                df = df.dropna(subset=['trade_date'])
            
            return df, True, None
        except Exception as e:
            return df, False, f"日期格式错误: {str(e)}"
    
    def check_anomalies(self, df, code):
        """检查异常值"""
        anomalies = {}
        
        if 'close' in df.columns:
            invalid_close = (df['close'] <= 0).sum()
            if invalid_close > 0:
                anomalies['close <= 0'] = invalid_close
                print(f"    ⚠️ 发现 {invalid_close} 条收盘价异常值")
        
        if 'vol' in df.columns:
            invalid_vol = (df['vol'] < 0).sum()
            if invalid_vol > 0:
                anomalies['volume < 0'] = invalid_vol
                print(f"    ⚠️ 发现 {invalid_vol} 条成交量异常值")
        
        if 'open' in df.columns and 'high' in df.columns and 'low' in df.columns:
            invalid_ohlc = ((df['high'] < df['low']) | 
                           (df['high'] < df['open']) | 
                           (df['high'] < df['close']) |
                           (df['low'] > df['open']) |
                           (df['low'] > df['close'])).sum()
            if invalid_ohlc > 0:
                anomalies['OHLC逻辑错误'] = invalid_ohlc
                print(f"    ⚠️ 发现 {invalid_ohlc} 条OHLC逻辑错误")
        
        return anomalies
    
    def handle_missing_values(self, df, code, max_col_missing=0.05, max_row_missing=0.10):
        """处理缺失值"""
        missing_stats = {}
        
        for col in df.columns:
            missing_rate = df[col].isna().sum() / len(df)
            missing_stats[col] = missing_rate
            
            if missing_rate > max_col_missing:
                print(f"    ⚠️ 列 '{col}' 缺失率 {missing_rate:.2%} > {max_col_missing:.0%}，删除该列")
                df = df.drop(columns=[col])
        
        row_missing_rates = df.isna().sum(axis=1) / len(df.columns)
        before_count = len(df)
        df = df[row_missing_rates <= max_row_missing]
        after_count = len(df)
        removed_rows = before_count - after_count
        
        if removed_rows > 0:
            print(f"    ⚠️ 删除 {removed_rows} 行缺失值过多的记录")
        
        return df, missing_stats, removed_rows
    
    def standardize_columns(self, df):
        """统一列名"""
        df = df.rename(columns=self.column_mapping)
        return df
    
    def process_single_file(self, filepath):
        """处理单个CSV文件"""
        filename = os.path.basename(filepath)
        code = filename.replace('_daily.csv', '')
        
        print(f"\n处理 {filename} ({code})...")
        
        try:
            df = pd.read_csv(filepath)
            original_count = len(df)
            
            if original_count == 0:
                reason = "文件为空"
                self._move_to_invalid(filepath, reason)
                return None, reason
            
            print(f"  原始记录数: {original_count}")
            
            is_valid, reason = self.check_required_columns(df, filename)
            if not is_valid:
                self._move_to_invalid(filepath, reason)
                return None, reason
            
            df, duplicates = self.check_duplicates(df, code)
            
            df, date_valid, date_reason = self.check_date_format(df, code)
            if not date_valid:
                self._move_to_invalid(filepath, date_reason)
                return None, date_reason
            
            anomalies = self.check_anomalies(df, code)
            
            df, missing_stats, removed_rows = self.handle_missing_values(df, code)
            
            df = self.standardize_columns(df)
            
            final_count = len(df)
            
            file_detail = {
                'code': code,
                'filename': filename,
                'original_count': original_count,
                'final_count': final_count,
                'duplicates_removed': duplicates,
                'anomalies': anomalies,
                'missing_stats': missing_stats,
                'removed_rows': removed_rows,
                'start_date': df['date'].min() if 'date' in df.columns else None,
                'end_date': df['date'].max() if 'date' in df.columns else None
            }
            
            self.report['file_details'].append(file_detail)
            self.report['missing_stats'][code] = missing_stats
            self.report['anomaly_stats'][code] = anomalies
            
            print(f"  ✓ 清洗完成: {original_count} → {final_count} 条记录")
            
            return df, None
            
        except Exception as e:
            reason = f"处理失败: {str(e)}"
            self._move_to_invalid(filepath, reason)
            return None, reason
    
    def _move_to_invalid(self, filepath, reason):
        """将无效文件移动到invalid目录"""
        filename = os.path.basename(filepath)
        dest_path = os.path.join(self.invalid_dir, filename)
        
        try:
            shutil.move(filepath, dest_path)
            print(f"  ❌ 文件无效，已移动到: {self.invalid_dir}")
            print(f"     原因: {reason}")
            
            self.report['invalid_files'].append({
                'filename': filename,
                'reason': reason
            })
        except Exception as e:
            print(f"  ⚠️ 移动文件失败: {str(e)}")
    
    def save_cleaned_data(self, df, filename):
        """保存清洗后的数据"""
        dest_path = os.path.join(self.clean_dir, filename)
        df.to_csv(dest_path, index=False)
        print(f"  ✓ 已保存到: {dest_path}")
    
    def generate_report(self):
        """生成数据清洗报告"""
        valid_files = len(self.report['file_details'])
        invalid_files = len(self.report['invalid_files'])
        total_files = valid_files + invalid_files
        
        self.report['summary'] = {
            'total_files': total_files,
            'valid_files': valid_files,
            'invalid_files': invalid_files,
            'valid_rate': valid_files / total_files if total_files > 0 else 0
        }
        
        with open(self.report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("股票量化分析系统 - 数据清洗报告\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("一、总体概况\n")
            f.write("-" * 80 + "\n")
            f.write(f"原始文件总数: {total_files}\n")
            f.write(f"有效文件数: {valid_files}\n")
            f.write(f"无效文件数: {invalid_files}\n")
            f.write(f"数据有效率: {self.report['summary']['valid_rate']:.2%}\n\n")
            
            if self.report['invalid_files']:
                f.write("二、无效文件列表\n")
                f.write("-" * 80 + "\n")
                for item in self.report['invalid_files']:
                    f.write(f"- {item['filename']}: {item['reason']}\n")
                f.write("\n")
            
            f.write("三、有效文件详情\n")
            f.write("-" * 80 + "\n")
            f.write(f"{'股票代码':<10} {'文件名':<25} {'起始日期':<15} {'结束日期':<15} {'原始记录':<10} {'清洗后':<10} {'删除重复':<10} {'删除缺失':<10}\n")
            f.write("-" * 80 + "\n")
            
            for detail in self.report['file_details']:
                start_date = detail['start_date'].strftime('%Y-%m-%d') if detail['start_date'] else 'N/A'
                end_date = detail['end_date'].strftime('%Y-%m-%d') if detail['end_date'] else 'N/A'
                
                f.write(f"{detail['code']:<10} {detail['filename']:<25} {start_date:<15} {end_date:<15} "
                        f"{detail['original_count']:<10} {detail['final_count']:<10} "
                        f"{detail['duplicates_removed']:<10} {detail['removed_rows']:<10}\n")
            
            f.write("\n四、缺失值统计\n")
            f.write("-" * 80 + "\n")
            for code, stats in self.report['missing_stats'].items():
                high_missing = {k: v for k, v in stats.items() if v > 0}
                if high_missing:
                    f.write(f"\n{code}:\n")
                    for col, rate in high_missing.items():
                        f.write(f"  {col}: {rate:.2%}\n")
            
            f.write("\n五、异常值统计\n")
            f.write("-" * 80 + "\n")
            for code, anomalies in self.report['anomaly_stats'].items():
                if anomalies:
                    f.write(f"\n{code}:\n")
                    for anomaly_type, count in anomalies.items():
                        f.write(f"  {anomaly_type}: {count} 条\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("报告生成完毕\n")
            f.write("=" * 80 + "\n")
        
        print(f"\n✓ 数据清洗报告已生成: {self.report_file}")
    
    def run(self):
        """执行完整的数据预处理流程"""
        print("=" * 80)
        print("股票量化分析系统 - 数据预处理模块")
        print("=" * 80)
        
        self.create_directories()
        
        csv_files = glob.glob(os.path.join(self.raw_dir, '*_daily.csv'))
        print(f"\n发现 {len(csv_files)} 个股票数据文件\n")
        
        for filepath in csv_files:
            df, error = self.process_single_file(filepath)
            
            if df is not None:
                self.save_cleaned_data(df, os.path.basename(filepath))
        
        self.generate_report()
        
        print("\n" + "=" * 80)
        print("数据预处理完成!")
        print("=" * 80)
        print(f"\n清洗后数据保存在: {self.clean_dir}")
        print(f"无效文件保存在: {self.invalid_dir}")
        print(f"清洗报告: {self.report_file}")
        print("\n请使用清洗后的数据进行后续分析。")

if __name__ == "__main__":
    preprocessor = DataPreprocessor()
    preprocessor.run()
