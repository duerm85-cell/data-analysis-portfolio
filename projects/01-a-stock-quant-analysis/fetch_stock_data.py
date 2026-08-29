import tushare as ts
import pandas as pd
import os
import time
from datetime import datetime, timedelta

# 从环境变量读取 Tushare Token（避免泄露敏感信息）
MY_TOKEN = os.environ.get('TUSHARE_TOKEN', '')
if not MY_TOKEN:
    print("⚠️ 请设置环境变量 TUSHARE_TOKEN，或在代码中填入你的 Tushare Token")
    print("   获取 Token: https://tushare.pro/register")
    print("   临时测试可在此行填入: MY_TOKEN = 'your_token_here'")

# 初始化Tushare接口
ts.set_token(MY_TOKEN)
pro = ts.pro_api()

# 配置参数
# 日期支持环境变量覆盖，默认取 2015 年至当前日期，避免硬编码未来日期。
start_date = os.environ.get('STOCK_DATA_START_DATE', '20150101')
end_date = os.environ.get('STOCK_DATA_END_DATE', datetime.now().strftime('%Y%m%d'))
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
raw_path = os.path.join(_BASE_DIR, 'data', 'raw')
os.makedirs(raw_path, exist_ok=True)

_end_dt = datetime.strptime(end_date, '%Y%m%d')
component_start_date = (_end_dt - timedelta(days=60)).strftime('%Y%m%d')

# 获取A股所有股票列表（沪深300成分股 + 创业板权重股）
def get_stock_list():
    """获取A股股票列表"""
    print("正在获取A股股票列表...")
    # 获取沪深300成分股
    try:
        hs300 = pro.index_weight(index_code='000300.SH', start_date=component_start_date, end_date=end_date)
        hs300_stocks = hs300['con_code'].unique().tolist()
        print(f"获取沪深300成分股: {len(hs300_stocks)} 只")
    except Exception as e:
        print(f"获取沪深300成分股失败: {e}")
        hs300_stocks = []
    
    # 获取创业板指成分股
    try:
        cyb = pro.index_weight(index_code='399006.SZ', start_date=component_start_date, end_date=end_date)
        cyb_stocks = cyb['con_code'].unique().tolist()
        print(f"获取创业板指成分股: {len(cyb_stocks)} 只")
    except Exception as e:
        print(f"获取创业板指成分股失败: {e}")
        cyb_stocks = []
    
    # 获取上证50成分股
    try:
        sz50 = pro.index_weight(index_code='000016.SH', start_date=component_start_date, end_date=end_date)
        sz50_stocks = sz50['con_code'].unique().tolist()
        print(f"获取上证50成分股: {len(sz50_stocks)} 只")
    except Exception as e:
        print(f"获取上证50成分股失败: {e}")
        sz50_stocks = []
    
    # 合并并去重
    all_stocks = list(set(hs300_stocks + cyb_stocks + sz50_stocks))
    print(f"合并去重后共 {len(all_stocks)} 只股票")
    
    return all_stocks

# 获取股票数据
def fetch_stock_data(stock_list):
    """获取股票日数据"""
    total_records = 0
    success_count = 0
    fail_count = 0
    
    for i, code in enumerate(stock_list, 1):
        try:
            print(f"\n[{i}/{len(stock_list)}] 正在获取 {code} ...")
            
            # 调用Tushare的daily接口
            df = pro.daily(ts_code=code, start_date=start_date, end_date=end_date)
            
            if not df.empty:
                # 将日期列按升序排列（确保时间序列正确，无未来信息泄露）
                df = df.sort_values('trade_date')
                
                # 从带后缀的代码中提取纯数字
                simple_code = code.split('.')[0]
                # 保存为CSV文件
                df.to_csv(os.path.join(raw_path, f"{simple_code}_daily.csv"), index=False)
                
                record_count = len(df)
                total_records += record_count
                success_count += 1
                print(f"{code} 获取成功，共 {record_count} 条数据")
                
                # 添加延迟，避免API调用过于频繁
                time.sleep(0.5)
            else:
                print(f"{code} 没有获取到数据")
                fail_count += 1
                
        except Exception as e:
            print(f"获取 {code} 数据失败: {e}")
            fail_count += 1
            time.sleep(1)
    
    print(f"\n========== 数据获取完成 ==========")
    print(f"成功获取: {success_count} 只股票")
    print(f"获取失败: {fail_count} 只股票")
    print(f"总数据条数: {total_records}")
    print(f"==================================")


def fetch_hs300_benchmark():
    """抓取真实沪深300指数日线，供回测基准使用。"""
    print("\n正在获取沪深300指数基准...")
    try:
        benchmark = pro.index_daily(
            ts_code='000300.SH', start_date=start_date, end_date=end_date
        )
        if benchmark.empty:
            print("警告: 未获取到沪深300指数数据")
            return False

        benchmark = benchmark.sort_values('trade_date')
        benchmark_path = os.path.join(raw_path, 'benchmark_hs300.csv')
        benchmark.to_csv(benchmark_path, index=False)
        print(f"沪深300指数已保存: {benchmark_path}，共 {len(benchmark):,} 条")
        return True
    except Exception as exc:
        print(f"获取沪深300指数失败: {exc}")
        return False

if __name__ == "__main__":
    # 获取股票列表
    stock_list = get_stock_list()
    
    # 如果获取股票列表失败，使用默认列表
    if not stock_list:
        print("使用默认股票列表...")
        stock_list = [
            # 沪深300权重股
            '600519.SH', '601318.SH', '600036.SH', '000858.SZ', '300750.SZ',
            '601398.SH', '600000.SH', '601988.SH', '601899.SH', '600030.SH',
            '000001.SZ', '000333.SZ', '002594.SZ', '600031.SH', '601857.SH',
            '002555.SZ', '601336.SH', '600887.SH', '000651.SZ', '600016.SH',
            # 创业板权重股
            '300059.SZ', '300124.SZ', '300033.SZ', '300760.SZ', '300015.SZ',
            '300676.SZ', '300274.SZ', '300498.SZ', '300347.SZ', '300601.SZ',
            # 上证50权重股
            '600036.SH', '601318.SH', '600519.SH', '601398.SH', '600000.SH',
            '601988.SH', '601899.SH', '600030.SH', '000001.SZ', '600031.SH',
        ]
    
    # 获取股票数据
    fetch_stock_data(stock_list)
    fetch_hs300_benchmark()
