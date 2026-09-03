PRAGMA foreign_keys = ON;

CREATE TABLE dim_stock (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market TEXT NOT NULL,
    board TEXT NOT NULL,
    industry_l1 TEXT NOT NULL,
    list_date TEXT,
    is_demo INTEGER NOT NULL DEFAULT 1 CHECK (is_demo IN (0, 1)),
    has_detail INTEGER NOT NULL DEFAULT 1 CHECK (has_detail IN (0, 1)),
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE fact_stock_daily_demo (
    code TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    pre_close REAL,
    change REAL,
    pct_chg REAL,
    volume REAL,
    amount REAL,
    ret REAL,
    ret_5d REAL,
    ret_10d REAL,
    ma5 REAL,
    ma10 REAL,
    ma20 REAL,
    ma60 REAL,
    ma5_ma10_diff REAL,
    ma5_ma20_diff REAL,
    volatility_20d REAL,
    volatility_60d REAL,
    rsi REAL,
    macd REAL,
    macd_signal REAL,
    macd_hist REAL,
    volume_ma5 REAL,
    volume_ratio REAL,
    volume_change REAL,
    amount_ma20 REAL,
    amount_ratio REAL,
    momentum_20d REAL,
    momentum_60d REAL,
    reversal_5d REAL,
    reversal_20d REAL,
    bb_mid REAL,
    bb_upper REAL,
    bb_lower REAL,
    bb_width REAL,
    bb_position REAL,
    high_low_ratio REAL,
    close_open_ratio REAL,
    label REAL,
    sentiment REAL,
    sentiment_ma5 REAL,
    sentiment_ma10 REAL,
    comment_count INTEGER,
    sentiment_source TEXT,
    data_version TEXT NOT NULL,
    PRIMARY KEY (code, date),
    FOREIGN KEY (code) REFERENCES dim_stock(code)
) WITHOUT ROWID;

CREATE TABLE fact_market_daily (
    date TEXT PRIMARY KEY,
    stock_count INTEGER NOT NULL,
    advancing_count INTEGER NOT NULL,
    declining_count INTEGER NOT NULL,
    flat_count INTEGER NOT NULL,
    total_volume REAL,
    total_amount REAL,
    average_close REAL,
    average_return REAL,
    median_return REAL,
    average_sentiment REAL,
    source TEXT NOT NULL,
    data_version TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE fact_industry_daily (
    industry_l1 TEXT NOT NULL,
    date TEXT NOT NULL,
    stock_count INTEGER NOT NULL,
    average_close REAL,
    average_return REAL,
    median_return REAL,
    total_volume REAL,
    total_amount REAL,
    advancing_ratio REAL,
    average_sentiment REAL,
    data_version TEXT NOT NULL,
    PRIMARY KEY (industry_l1, date)
) WITHOUT ROWID;

CREATE TABLE fact_factor_ic_daily (
    factor_name TEXT NOT NULL,
    date TEXT NOT NULL,
    ic REAL,
    sample_count INTEGER NOT NULL,
    data_version TEXT NOT NULL,
    PRIMARY KEY (factor_name, date)
) WITHOUT ROWID;

CREATE TABLE fact_data_quality_run (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    data_date TEXT,
    row_count INTEGER NOT NULL,
    stock_count INTEGER NOT NULL,
    column_count INTEGER NOT NULL,
    duplicate_key_count INTEGER NOT NULL,
    invalid_date_count INTEGER NOT NULL,
    invalid_ohlc_count INTEGER NOT NULL,
    unexpected_missing_count INTEGER NOT NULL,
    quality_score REAL NOT NULL,
    status TEXT NOT NULL,
    data_version TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE fact_data_quality_issue (
    run_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    column_name TEXT NOT NULL DEFAULT '',
    issue_count INTEGER NOT NULL,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    PRIMARY KEY (run_id, rule_name, column_name),
    FOREIGN KEY (run_id) REFERENCES fact_data_quality_run(run_id)
) WITHOUT ROWID;

CREATE TABLE pipeline_run (
    run_id TEXT PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    input_rows INTEGER NOT NULL,
    output_rows INTEGER NOT NULL,
    data_start_date TEXT,
    data_end_date TEXT,
    source TEXT NOT NULL,
    data_version TEXT NOT NULL,
    mode TEXT NOT NULL,
    source_label TEXT NOT NULL,
    selection_rule TEXT,
    public_scope TEXT NOT NULL,
    disclaimer TEXT NOT NULL,
    database_path TEXT NOT NULL,
    error_message TEXT
) WITHOUT ROWID;

CREATE INDEX idx_stock_daily_date
ON fact_stock_daily_demo(date);

CREATE INDEX idx_stock_industry_l1
ON dim_stock(industry_l1, code);

CREATE INDEX idx_stock_has_detail
ON dim_stock(has_detail, code);

CREATE INDEX idx_industry_daily_date
ON fact_industry_daily(date, industry_l1);

CREATE INDEX idx_factor_ic_date
ON fact_factor_ic_daily(date, factor_name);

CREATE INDEX idx_quality_run_started_at
ON fact_data_quality_run(started_at DESC);
