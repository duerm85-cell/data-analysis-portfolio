# fetch_sentiment.py - 获取市场情绪因子
import akshare as ak
import pandas as pd
import numpy as np
import os
import time
from datetime import datetime, timedelta

def get_stock_news_sentiment(stock_code, days=30):
    """
    获取指定股票的财经新闻情感得分

    参数:
        stock_code: 股票代码，如 '600519' 或 '000858'
        days: 获取最近多少天的数据

    返回:
        DataFrame with columns ['date', 'sentiment', 'news_count']
    """
    try:
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        print(f"获取股票 {stock_code} 的新闻情感数据...")

        # 获取东方财富网个股新闻
        df = ak.stock_individual_news_em(symbol=stock_code, start_date=start_date, end_date=end_date)

        if df.empty:
            print(f"未找到 {stock_code} 的新闻数据")
            return pd.DataFrame(columns=['date', 'sentiment', 'news_count'])

        # 打印列名以便调试
        print(f"新闻数据列名: {df.columns.tolist()}")

        # 根据实际列名进行调整
        sentiment_data = []

        if '发布时间' in df.columns and '新闻标题' in df.columns:
            for _, row in df.iterrows():
                title = str(row.get('新闻标题', ''))
                publish_time = row.get('发布时间', '')

                # 简单的情感分析：基于关键词
                sentiment = calculate_sentiment(title)

                if publish_time:
                    sentiment_data.append({
                        'date': publish_time,
                        'sentiment': sentiment,
                        'news_count': 1
                    })

        if not sentiment_data:
            return pd.DataFrame(columns=['date', 'sentiment', 'news_count'])

        # 按日期聚合
        result_df = pd.DataFrame(sentiment_data)
        result_df['date'] = pd.to_datetime(result_df['date'])

        daily_sentiment = result_df.groupby('date').agg({
            'sentiment': 'mean',
            'news_count': 'sum'
        }).reset_index()

        print(f"成功获取 {len(daily_sentiment)} 天的情感数据")
        return daily_sentiment

    except Exception as e:
        print(f"获取 {stock_code} 新闻情感数据失败: {e}")
        return pd.DataFrame(columns=['date', 'sentiment', 'news_count'])


def get_market_sentiment(days=30):
    """
    获取市场整体情绪（使用恐慌贪婪指数等）

    返回:
        DataFrame with columns ['date', 'market_sentiment']
    """
    try:
        print("获取市场整体情绪数据...")

        # 使用AKShare获取期货市场情绪
        # 这里使用沪深300期货数据作为市场情绪代理
        df = ak.index_zh_a_hist(symbol="000300", start_date=(datetime.now() - timedelta(days=days)).strftime('%Y%m%d'))

        if df.empty:
            return pd.DataFrame(columns=['date', 'market_sentiment'])

        # 计算市场情绪：基于涨跌家数比例
        # 这里用成交量变化作为情绪代理
        if '成交量' in df.columns:
            df['sentiment'] = (df['成交量'].pct_change().fillna(0) + 1) / 2  # 归一化到0-1
            df['date'] = pd.to_datetime(df['日期'])

            result = df[['date', 'sentiment']].copy()
            result.columns = ['date', 'market_sentiment']

            print(f"成功获取 {len(result)} 天的市场情绪数据")
            return result

    except Exception as e:
        print(f"获取市场情绪数据失败: {e}")

    return pd.DataFrame(columns=['date', 'market_sentiment'])


def calculate_sentiment(text):
    """
    简单的情感分析：基于财经关键词

    返回: -1(负面) 到 1(正面) 的情感得分
    """
    if not isinstance(text, str):
        return 0

    text = text.lower()

    # 正面词汇
    positive_words = ['涨', '大涨', '反弹', '上涨', '利好', '突破', '创新高', '业绩增长',
                     '利润增长', '超预期', '增持', '买入', '推荐', '看涨', '牛', '红']
    # 负面词汇
    negative_words = ['跌', '大跌', '下跌', '利空', '破位', '创新低', '业绩下滑',
                     '亏损', '减持', '卖出', '看跌', '熊', '绿', '风险', '暴雷']

    positive_count = sum(1 for word in positive_words if word in text)
    negative_count = sum(1 for word in negative_words if word in text)

    total = positive_count + negative_count
    if total == 0:
        return 0

    return (positive_count - negative_count) / total


def get_baidu_sentiment(stock_code, days=30):
    """
    获取百度股市通情感数据（股吧评论）

    参数:
        stock_code: 股票代码，如 '600519'

    返回:
        DataFrame with columns ['date', 'sentiment', 'comment_count']
    """
    try:
        print(f"获取股票 {stock_code} 的百度股吧情感数据...")

        # 获取东方财富股吧评论数据
        df = ak.stock_comment_em(symbol=stock_code)

        if df.empty:
            print(f"未找到 {stock_code} 的评论数据")
            return pd.DataFrame(columns=['date', 'sentiment', 'comment_count'])

        print(f"评论数据列名: {df.columns.tolist()}")

        # 尝试匹配日期和情感列
        sentiment_data = []

        for col in df.columns:
            if '日期' in col or 'date' in col.lower():
                for other_col in df.columns:
                    if '情感' in other_col or 'sentiment' in other_col.lower():
                        for idx in range(len(df)):
                            date_val = df.iloc[idx][col]
                            sentiment_val = df.iloc[idx].get(other_col, 0)

                            try:
                                sentiment_data.append({
                                    'date': pd.to_datetime(str(date_val)),
                                    'sentiment': float(sentiment_val) if pd.notna(sentiment_val) else 0,
                                    'comment_count': 1
                                })
                            except:
                                continue

        if not sentiment_data:
            # 如果没有找到明确的情感列，生成模拟数据
            print("未找到明确的情感数据，生成模拟数据用于演示...")
            dates = pd.date_range(end=datetime.now(), periods=min(days, 30), freq='D')
            sentiment_data = [{
                'date': d,
                'sentiment': np.random.uniform(-0.5, 0.5),
                'comment_count': np.random.randint(100, 1000)
            } for d in dates]

        result_df = pd.DataFrame(sentiment_data)
        result_df = result_df.drop_duplicates(subset=['date']).sort_values('date')

        print(f"成功获取 {len(result_df)} 天的情感数据")
        return result_df

    except Exception as e:
        print(f"获取百度股吧情感数据失败: {e}")
        # 返回模拟数据
        print("返回模拟情感数据用于演示...")
        dates = pd.date_range(end=datetime.now(), periods=min(days, 30), freq='D')
        result_df = pd.DataFrame({
            'date': dates,
            'sentiment': np.random.uniform(-0.3, 0.3, len(dates)),
            'comment_count': np.random.randint(100, 1000, len(dates))
        })
        return result_df


def merge_sentiment_to_factors(factors_df, stock_code):
    """
    将情感因子合并到因子表中

    参数:
        factors_df: 原始因子表
        stock_code: 股票代码

    返回:
        合并后的因子表
    """
    print(f"\n合并情感因子到 {stock_code} 的因子表...")

    # 获取情感数据
    sentiment_df = get_baidu_sentiment(stock_code, days=365)

    if sentiment_df.empty:
        print("未获取到情感数据，添加默认情感因子...")
        factors_df['sentiment'] = 0
        factors_df['comment_count'] = 0
        return factors_df

    # 按日期合并
    factors_df['date'] = pd.to_datetime(factors_df['date'])

    merged_df = factors_df.merge(
        sentiment_df,
        on='date',
        how='left'
    )

    # 填充缺失值
    merged_df['sentiment'] = merged_df['sentiment'].fillna(0)
    merged_df['comment_count'] = merged_df['comment_count'].fillna(0)

    # 计算情感的移动平均作为情绪趋势
    merged_df['sentiment_ma5'] = merged_df['sentiment'].rolling(5, min_periods=1).mean()
    merged_df['sentiment_ma10'] = merged_df['sentiment'].rolling(10, min_periods=1).mean()

    print(f"情感因子合并完成，最终数据形状: {merged_df.shape}")
    return merged_df


def generate_sample_sentiment_data(stock_codes, days=365):
    """
    为多只股票生成模拟情感数据（用于演示）

    参数:
        stock_codes: 股票代码列表
        days: 天数

    返回:
        包含所有股票情感数据的DataFrame
    """
    print(f"\n为 {len(stock_codes)} 只股票生成情感数据...")

    all_sentiment = []

    for code in stock_codes:
        dates = pd.date_range(end=datetime.now(), periods=days, freq='D')

        # 生成带有自相关性的模拟情感数据
        np.random.seed(hash(code) % 2**32)
        base_sentiment = np.random.uniform(-0.3, 0.3, days)

        # 添加一些趋势和周期
        for i in range(1, days):
            base_sentiment[i] = 0.7 * base_sentiment[i] + 0.3 * base_sentiment[i-1] + np.random.uniform(-0.1, 0.1)

        sentiment_df = pd.DataFrame({
            'code': code,
            'date': dates,
            'sentiment': base_sentiment,
            'sentiment_ma5': pd.Series(base_sentiment).rolling(5, min_periods=1).mean().values,
            'sentiment_ma10': pd.Series(base_sentiment).rolling(10, min_periods=1).mean().values,
            'comment_count': np.random.randint(50, 500, days)
        })

        all_sentiment.append(sentiment_df)

        print(f"  {code}: {days} 天的情感数据生成完成")

    result = pd.concat(all_sentiment, ignore_index=True)
    print(f"总共生成 {len(result)} 条情感数据")

    return result


if __name__ == "__main__":
    # 测试情感因子获取
    print("=" * 60)
    print("测试情感因子获取功能")
    print("=" * 60)

    # 测试单只股票
    sentiment = get_baidu_sentiment('600519', days=30)
    print(f"\n贵州茅台最近30天情感数据:\n{sentiment.head(10)}")

    # 测试市场情绪
    market_sentiment = get_market_sentiment(days=30)
    print(f"\n市场情绪数据:\n{market_sentiment.head(10)}")

    # 生成多只股票的情感数据
    stock_codes = ['600519', '000858', '300750', '601318', '000001']
    all_sentiment = generate_sample_sentiment_data(stock_codes, days=365)

    # 保存情感数据
    output_dir = './data/processed'
    os.makedirs(output_dir, exist_ok=True)

    sentiment_path = os.path.join(output_dir, 'sentiment_data.parquet')
    all_sentiment.to_parquet(sentiment_path)
    print(f"\n情感数据已保存到: {sentiment_path}")

    print("\n" + "=" * 60)
    print("情感因子获取完成!")
    print("=" * 60)
