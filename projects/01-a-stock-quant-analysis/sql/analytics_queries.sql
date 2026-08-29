-- SQLite 分析查询示例。应用代码中的外部输入均通过 ? 占位符绑定。

-- 1. 数据覆盖范围与新鲜度
SELECT
    code,
    MIN(date) AS start_date,
    MAX(date) AS end_date,
    COUNT(*) AS trading_days
FROM factors
GROUP BY code
ORDER BY trading_days DESC;

-- 2. 指定股票最近 N 个交易日（参数：code, days）
SELECT code, date, close, ret, ma5, ma20, rsi, macd
FROM factors
WHERE code = ?
ORDER BY date DESC
LIMIT ?;

-- 3. 每日截面数据质量
SELECT
    date,
    COUNT(*) AS row_count,
    COUNT(DISTINCT code) AS stock_count,
    SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END) AS missing_close,
    SUM(CASE WHEN ret IS NULL THEN 1 ELSE 0 END) AS missing_return
FROM factors
GROUP BY date
ORDER BY date DESC;

-- 4. 最新交易日的板块宽度（代码前缀作为演示分类）
WITH latest AS (
    SELECT MAX(date) AS date FROM factors
), snapshot AS (
    SELECT
        CASE
            WHEN code LIKE '688%' THEN '科创板'
            WHEN code LIKE '3%' THEN '创业板'
            WHEN code LIKE '0%' THEN '深市主板'
            WHEN code LIKE '6%' THEN '沪市主板'
            ELSE '其他'
        END AS board,
        ret
    FROM factors, latest
    WHERE factors.date = latest.date
)
SELECT
    board,
    COUNT(*) AS stock_count,
    SUM(CASE WHEN ret > 0 THEN 1 ELSE 0 END) AS advancing,
    SUM(CASE WHEN ret < 0 THEN 1 ELSE 0 END) AS declining,
    AVG(ret) AS average_return
FROM snapshot
GROUP BY board
ORDER BY stock_count DESC;
