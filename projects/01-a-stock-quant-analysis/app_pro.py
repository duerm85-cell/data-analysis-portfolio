import os
import sys

# Streamlit Cloud 从仓库根目录启动嵌套入口文件。先将本项目目录
# 放到模块搜索路径最前，避免误导入环境中的同名 app/portfolio_config 包。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR in sys.path:
    sys.path.remove(BASE_DIR)
sys.path.insert(0, BASE_DIR)

import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import warnings
import json
import sqlite3
import hashlib
import hmac
import secrets
from app.data_access import (
    get_asset_summary,
    get_factor_catalog,
    get_factor_ic,
    get_latest_quotes,
    get_manifest,
    get_market_snapshot,
    get_market_summary,
    get_quality_issues,
    get_quality_runs,
    get_stock_catalog,
    get_stock_history,
)
from app.stock_profile import render_stock_profile
from app.industry_analysis import render_industry_analysis
from portfolio_config import (
    PORTFOLIO_BACKTEST_METRICS_PATH,
    PORTFOLIO_BACKTEST_RESULTS_PATH,
    PORTFOLIO_DAILY_PORTFOLIOS_PATH,
    PORTFOLIO_TRAINING_LOG_PATH,
    is_portfolio_mode,
)
import contextlib

warnings.filterwarnings('ignore')

# ========== 路径基准：全部以 app_pro.py 所在目录为根，不依赖 cwd ==========
def _P(*parts):
    """将相对路径拼到 BASE_DIR 下，避免受命令行起始目录影响"""
    return os.path.join(BASE_DIR, *parts)

USER_DB_PATH = _P('data', 'users.db')
PORTFOLIO_MODE = is_portfolio_mode()


def _get_db_conn():
    os.makedirs(os.path.dirname(USER_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(USER_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            theme TEXT DEFAULT 'light',
            top_n INTEGER DEFAULT 20,
            watchlist TEXT DEFAULT '[]'
        )
    """)
    conn.commit()
    return conn


PASSWORD_ITERATIONS = 240_000


def _hash_password(_username, password, salt=None):
    """生成带随机盐的 PBKDF2 密码摘要；用户名参数仅为兼容旧调用。"""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(username, password, stored_hash):
    if stored_hash.startswith('pbkdf2_sha256$'):
        try:
            _, iterations, salt_hex, expected_hex = stored_hash.split('$', 3)
            actual = hashlib.pbkdf2_hmac(
                'sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), int(iterations)
            )
            return hmac.compare_digest(actual.hex(), expected_hex), False
        except (TypeError, ValueError):
            return False, False

    # 兼容旧版 SHA-256 账号，登录成功后立即升级摘要。
    legacy = hashlib.sha256((username + password).encode('utf-8')).hexdigest()
    return hmac.compare_digest(legacy, stored_hash), True


def db_register(username, password):
    conn = _get_db_conn()
    try:
        conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                     (username, _hash_password(username, password)))
        conn.commit()
        return True, '注册成功'
    except sqlite3.IntegrityError:
        return False, '用户名已存在'
    finally:
        conn.close()


def db_login(username, password):
    conn = _get_db_conn()
    try:
        row = conn.execute(
            'SELECT id, username, password_hash, theme, top_n, watchlist '
            'FROM users WHERE username=?',
            (username,),
        ).fetchone()
        if row is None:
            return None
        is_valid, is_legacy = _verify_password(username, password, row['password_hash'])
        if not is_valid:
            return None
        if is_legacy:
            conn.execute(
                'UPDATE users SET password_hash=? WHERE username=?',
                (_hash_password(username, password), username),
            )
            conn.commit()
        return dict(row)
    finally:
        conn.close()


def db_update_user(username, **kwargs):
    allowed_fields = {'theme', 'top_n', 'watchlist'}
    invalid_fields = set(kwargs) - allowed_fields
    if invalid_fields:
        raise ValueError(f"不允许更新字段: {sorted(invalid_fields)}")
    if not kwargs:
        return
    conn = _get_db_conn()
    sets = ', '.join([f"{k}=?" for k in kwargs.keys()])
    vals = list(kwargs.values()) + [username]
    conn.execute(f'UPDATE users SET {sets} WHERE username=?', vals)
    conn.commit()
    conn.close()


def db_get_user(username):
    conn = _get_db_conn()
    row = conn.execute(
        'SELECT id, username, password_hash, theme, top_n, watchlist '
        'FROM users WHERE username=?',
        (username,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


st.set_page_config(
    page_title='A股量化数据工程平台',
    page_icon='📈',
    layout='wide',
    initial_sidebar_state='expanded'
)

DARK_CSS = """<style>
    * { color-scheme: dark; }
    .stApp { background: linear-gradient(135deg, #0f0f23 0%, #1a1a3a 50%, #0f0f23 100%); color: #ffffff !important; }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #181830 0%, #1f1f40 100%) !important; border-right: 2px solid rgba(108, 99, 255, 0.3) !important; box-shadow: 4px 0 20px rgba(0,0,0,0.3); }
    [data-testid="stSidebar"] * { color: #e8e8ff !important; }
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"], [data-testid="stSidebar"] .stMultiSelect div[data-baseweb="select"] { background: rgba(45, 45, 80, 0.95) !important; border: 1px solid rgba(108, 99, 255, 0.4) !important; border-radius: 10px; color: #ffffff !important; }
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] *, [data-testid="stSidebar"] .stMultiSelect div[data-baseweb="select"] * { color: #ffffff !important; }
    .card, .stCard { background: linear-gradient(135deg, rgba(40, 40, 75, 0.9) 0%, rgba(30, 30, 55, 0.95) 100%); border: 1px solid rgba(108, 99, 255, 0.2); border-radius: 16px; padding: 24px; margin: 16px 0; box-shadow: 0 8px 32px rgba(0,0,0,0.2); backdrop-filter: blur(10px); }
    .main-title { font-size: 48px; font-weight: 900; background: linear-gradient(135deg, #6C63FF 0%, #FF6B9D 50%, #40FF80 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 28px; }
    .section-title { font-size: 30px; font-weight: 800; color: #ffffff; margin-bottom: 22px; border-left: 4px solid #6C63FF; padding-left: 16px; }
    .metric-card { background: linear-gradient(135deg, rgba(50, 50, 90, 0.85) 0%, rgba(35, 35, 65, 0.9) 100%); border: 1px solid rgba(108, 99, 255, 0.3); border-radius: 16px; padding: 28px; text-align: center; box-shadow: 0 8px 24px rgba(0,0,0,0.25); backdrop-filter: blur(10px); }
    .metric-value { font-size: 46px; font-weight: 900; background: linear-gradient(135deg, #6C63FF, #FF6B9D); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
    .metric-label { font-size: 16px; color: #c0c0e0 !important; margin-top: 10px; font-weight: 600; }
    .stButton button { background: linear-gradient(135deg, #6C63FF 0%, #8B7FFF 100%); border: none; border-radius: 12px; color: white; font-weight: 700; font-size: 16px; padding: 14px 32px; box-shadow: 0 4px 15px rgba(108, 99, 255, 0.4); transition: all 0.3s ease; }
    .stButton button:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(108, 99, 255, 0.5); }
    .divider { height: 2px; background: linear-gradient(90deg, transparent, #6C63FF, #FF6B9D, transparent); margin: 38px 0; }
    .custom-info-box { background: linear-gradient(135deg, rgba(30, 40, 70, 0.9) 0%, rgba(20, 30, 55, 0.95) 100%) !important; color: #e8e8ff !important; border: 1px solid rgba(108, 99, 255, 0.3) !important; border-radius: 12px !important; padding: 16px !important; }
    .custom-info-box p, .custom-info-box div { color: #e8e8ff !important; }
    .stMarkdown, .stText, .stSelectbox label, .stMetric label, .stSubheader, h1, h2, h3, h4, h5, h6, p, div, span { color: #ffffff !important; }
    [data-testid="stMetric"] * { color: #ffffff !important; }
    .stSelectbox div[data-baseweb="select"], .stMultiSelect div[data-baseweb="select"] { background: rgba(45, 45, 80, 0.95) !important; border: 1px solid rgba(108, 99, 255, 0.4) !important; border-radius: 12px; }
    .stSelectbox div[data-baseweb="select"] *, .stMultiSelect div[data-baseweb="select"] * { color: #ffffff !important; font-weight: 600 !important; font-size: 16px !important; }
    .stSelectbox div[data-baseweb="popover"], .stMultiSelect div[data-baseweb="popover"] { background: linear-gradient(135deg, #1a1a3a 0%, #151530 100%) !important; border: 1px solid rgba(108, 99, 255, 0.4) !important; border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.4); }
    .stSelectbox div[data-baseweb="popover"] li, .stMultiSelect div[data-baseweb="popover"] li { background: transparent !important; color: #ffffff !important; font-weight: 500 !important; }
    .stSelectbox div[data-baseweb="popover"] li:hover, .stMultiSelect div[data-baseweb="popover"] li:hover { background: rgba(108, 99, 255, 0.15) !important; }
    .stSelectbox div[data-baseweb="popover"] li[data-selected="true"], .stMultiSelect div[data-baseweb="popover"] li[data-selected="true"] { background: rgba(108, 99, 255, 0.25) !important; color: #ffffff !important; }
    .stSelectbox div[data-baseweb="popover"] li span, .stMultiSelect div[data-baseweb="popover"] li span { color: #ffffff !important; font-size: 15px !important; }
    .stSelectbox div[data-baseweb="popover"] input, .stMultiSelect div[data-baseweb="popover"] input { background: rgba(40, 40, 75, 0.95) !important; color: #ffffff !important; border: 1px solid rgba(108, 99, 255, 0.4) !important; }
    .stAlert { background: linear-gradient(135deg, rgba(120, 80, 20, 0.9) 0%, rgba(80, 50, 10, 0.95) 100%) !important; border: 2px solid #FFB300 !important; color: #FFE4B3 !important; border-radius: 12px; }
    .stAlert * { color: #FFE4B3 !important; }
    .stInfo { background: linear-gradient(135deg, rgba(20, 50, 100, 0.9) 0%, rgba(10, 35, 70, 0.95) 100%) !important; border: 2px solid #40A0FF !important; color: #B3D9FF !important; border-radius: 12px; }
    .stInfo * { color: #B3D9FF !important; }
    .stSuccess { background: linear-gradient(135deg, rgba(20, 80, 50, 0.9) 0%, rgba(10, 55, 30, 0.95) 100%) !important; border: 2px solid #40FF80 !important; color: #B3FFD9 !important; border-radius: 12px; }
    .stSuccess * { color: #B3FFD9 !important; }
    .stError { background: linear-gradient(135deg, rgba(100, 30, 30, 0.9) 0%, rgba(70, 20, 20, 0.95) 100%) !important; border: 2px solid #FF6B6B !important; color: #FFB3B3 !important; border-radius: 12px; }
    .stError * { color: #FFB3B3 !important; }
    [data-testid="stHeader"] { background: linear-gradient(180deg, #0f0f23 0%, #151530 100%) !important; border-bottom: 2px solid rgba(108, 99, 255, 0.3) !important; }
    [data-testid="stHeader"] * { color: #e8e8ff !important; }
    .compare-table { width: 100%; border-collapse: collapse; margin-top: 16px; }
    .compare-table th, .compare-table td { padding: 14px 18px; text-align: center; border-bottom: 1px solid rgba(255,255,255,0.12); }
    .compare-table th { background: rgba(108, 99, 255, 0.15); color: #e8e8ff !important; font-weight: 700; }
    .compare-table tr:hover { background: rgba(108, 99, 255, 0.08); }
    .best-value { background: linear-gradient(135deg, rgba(64, 255, 128, 0.2) 0%, rgba(64, 255, 128, 0.1) 100%); border-radius: 10px; padding: 6px 12px; font-weight: 700; color: #40FF80; }
    [data-testid="stSlider"] label, [data-testid="stSlider"] span, [data-testid="stSlider"] div, [data-testid="stRadio"] label, [data-testid="stRadio"] span, [data-testid="stRadio"] div, [data-testid="stNumberInput"] label, [data-testid="stNumberInput"] span, [data-testid="stNumberInput"] div, [data-testid="stMultiSelect"] label, [data-testid="stMultiSelect"] span, [data-testid="stMultiSelect"] div, [data-testid="stCheckbox"] label, [data-testid="stCheckbox"] span, [data-testid="stDateInput"] label, [data-testid="stDateInput"] span, [data-testid="stDateInput"] div, [data-testid="stTextInput"] label, [data-testid="stTextInput"] span, [data-testid="stTextInput"] div, [data-testid="stTextArea"] label, [data-testid="stTextArea"] span, [data-testid="stTextArea"] div { color: #e8e8ff !important; }
    [data-testid="stExpander"] summary, [data-testid="stExpander"] span, [data-testid="stExpander"] p, [data-testid="stExpander"] div, [data-testid="stExpander"] label { color: #e8e8ff !important; }
    .stDataFrame td, .stDataFrame th, [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th { color: #e8e8ff !important; }
    [data-testid="stDataFrame"] { background: rgba(30, 30, 55, 0.9) !important; }
    [data-testid="stSelectSlider"] label, [data-testid="stSelectSlider"] span, [data-testid="stSelectSlider"] div { color: #e8e8ff !important; }
    .stTextInput input, .stTextArea textarea, .stNumberInput input { background: rgba(45, 45, 80, 0.95) !important; color: #ffffff !important; border: 1px solid rgba(108, 99, 255, 0.4) !important; border-radius: 10px; }
    .stTextInput input::placeholder, .stTextArea textarea::placeholder { color: rgba(232, 232, 255, 0.5) !important; }
    .stTabs [data-baseweb="tab-list"] { background: rgba(30, 30, 55, 0.6) !important; border-radius: 12px; padding: 6px; }
    .stTabs [data-baseweb="tab"] { color: #a0a0c0 !important; border-radius: 10px !important; }
    .stTabs [data-baseweb="tab"][aria-selected="true"] { background: linear-gradient(135deg, #6C63FF 0%, #8B7FFF 100%) !important; color: #ffffff !important; }
    .stProgress > div > div { background: linear-gradient(90deg, #6C63FF, #FF6B9D) !important; }
    .stFileUploader div[data-testid="stFileUploader"] { background: rgba(45, 45, 80, 0.95) !important; border: 2px dashed rgba(108, 99, 255, 0.4) !important; border-radius: 12px; }
    .stFileUploader div[data-testid="stFileUploader"] * { color: #e8e8ff !important; }
    .dashboard-title { font-size: 52px; font-weight: 900; text-align: center; background: linear-gradient(90deg, #6C63FF, #FF6B9D, #40FF80, #6C63FF); background-size: 300% 300%; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; animation: gradient-shift 4s ease infinite; margin-bottom: 30px; }
    @keyframes gradient-shift { 0%, 100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
    .dashboard-metric { background: rgba(40, 40, 75, 0.9); border-radius: 16px; padding: 20px; text-align: center; border: 1px solid rgba(108, 99, 255, 0.3); box-shadow: 0 8px 24px rgba(0,0,0,0.3); }
    .dashboard-metric-value { font-size: 48px; font-weight: 900; white-space: nowrap; background: linear-gradient(135deg, #6C63FF, #FF6B9D); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
    .dashboard-metric-label { font-size: 15px; color: #c0c0e0; margin-top: 8px; }
</style>
"""

LIGHT_CSS = """<style>
    * { color-scheme: light; }
    .stApp { background: linear-gradient(135deg, #F5F7FA 0%, #E8ECF1 50%, #F5F7FA 100%); color: #1E1E1E !important; }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%) !important; border-right: 2px solid rgba(46, 134, 171, 0.2) !important; box-shadow: 4px 0 20px rgba(0,0,0,0.08); }
    [data-testid="stSidebar"] * { color: #333333 !important; }
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"], [data-testid="stSidebar"] .stMultiSelect div[data-baseweb="select"] { background: #FFFFFF !important; border: 1px solid #D1D5DB !important; border-radius: 10px; color: #1E1E1E !important; }
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] *, [data-testid="stSidebar"] .stMultiSelect div[data-baseweb="select"] * { color: #1E1E1E !important; }
    .card, .stCard { background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%); border: 1px solid rgba(46, 134, 171, 0.15); border-radius: 16px; padding: 24px; margin: 16px 0; box-shadow: 0 8px 32px rgba(0,0,0,0.06); }
    .main-title { font-size: 48px; font-weight: 900; background: linear-gradient(135deg, #2E86AB, #40A0FF, #2ECC71); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 28px; }
    .section-title { font-size: 30px; font-weight: 800; color: #1E1E1E; margin-bottom: 22px; border-left: 4px solid #2E86AB; padding-left: 16px; }
    .metric-card { background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%); border: 1px solid rgba(46, 134, 171, 0.2); border-radius: 16px; padding: 28px; text-align: center; box-shadow: 0 8px 24px rgba(0,0,0,0.08); }
    .metric-value { font-size: 46px; font-weight: 900; background: linear-gradient(135deg, #2E86AB, #40A0FF); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
    .metric-label { font-size: 16px; color: #666666 !important; margin-top: 10px; font-weight: 600; }
    .stButton button { background: linear-gradient(135deg, #2E86AB 0%, #40A0FF 100%); border: none; border-radius: 12px; color: white; font-weight: 700; font-size: 16px; padding: 14px 32px; box-shadow: 0 4px 15px rgba(46, 134, 171, 0.3); transition: all 0.3s ease; }
    .stButton button:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(46, 134, 171, 0.4); }
    .divider { height: 2px; background: linear-gradient(90deg, transparent, #2E86AB, #40A0FF, transparent); margin: 38px 0; }
    .custom-info-box { background: linear-gradient(135deg, #F0F7FC 0%, #E8F0F8 100%) !important; color: #1E1E1E !important; border: 1px solid rgba(46, 134, 171, 0.2) !important; border-radius: 12px !important; padding: 16px !important; }
    .custom-info-box p, .custom-info-box div { color: #1E1E1E !important; }
    .stMarkdown, .stText, .stSelectbox label, .stMetric label, .stSubheader, h1, h2, h3, h4, h5, h6, p, div, span { color: #1E1E1E !important; }
    [data-testid="stMetric"] * { color: #1E1E1E !important; }
    .stSelectbox div[data-baseweb="select"], .stMultiSelect div[data-baseweb="select"] { background: #FFFFFF !important; border: 1px solid #D1D5DB !important; border-radius: 12px; }
    .stSelectbox div[data-baseweb="select"] *, .stMultiSelect div[data-baseweb="select"] * { color: #1E1E1E !important; font-weight: 600 !important; font-size: 16px !important; }
    .stSelectbox div[data-baseweb="popover"], .stMultiSelect div[data-baseweb="popover"] { background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%) !important; border: 1px solid rgba(46, 134, 171, 0.2) !important; border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.12); }
    .stSelectbox div[data-baseweb="popover"] li, .stMultiSelect div[data-baseweb="popover"] li { background: transparent !important; color: #1E1E1E !important; font-weight: 500 !important; }
    .stSelectbox div[data-baseweb="popover"] li:hover, .stMultiSelect div[data-baseweb="popover"] li:hover { background: rgba(46, 134, 171, 0.08) !important; }
    .stSelectbox div[data-baseweb="popover"] li[data-selected="true"], .stMultiSelect div[data-baseweb="popover"] li[data-selected="true"] { background: rgba(46, 134, 171, 0.12) !important; color: #1E1E1E !important; }
    .stSelectbox div[data-baseweb="popover"] li span, .stMultiSelect div[data-baseweb="popover"] li span { color: #1E1E1E !important; font-size: 15px !important; }
    .stSelectbox div[data-baseweb="popover"] input, .stMultiSelect div[data-baseweb="popover"] input { background: #FFFFFF !important; color: #1E1E1E !important; border: 1px solid #D1D5DB !important; }
    .stAlert { background: linear-gradient(135deg, #FFF9E6 0%, #FFF5CC 100%) !important; border: 2px solid #FFB300 !important; color: #996600 !important; border-radius: 12px; }
    .stAlert * { color: #996600 !important; }
    .stInfo { background: linear-gradient(135deg, #E6F3FF 0%, #CCE8FF 100%) !important; border: 2px solid #2E86AB !important; color: #1A5276 !important; border-radius: 12px; }
    .stInfo * { color: #1A5276 !important; }
    .stSuccess { background: linear-gradient(135deg, #E6FFF0 0%, #CCFFE0 100%) !important; border: 2px solid #2ECC71 !important; color: #1E8449 !important; border-radius: 12px; }
    .stSuccess * { color: #1E8449 !important; }
    .stError { background: linear-gradient(135deg, #FFE6E6 0%, #FFCCCC 100%) !important; border: 2px solid #E74C3C !important; color: #922B21 !important; border-radius: 12px; }
    .stError * { color: #922B21 !important; }
    [data-testid="stHeader"] { background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%) !important; border-bottom: 2px solid rgba(46, 134, 171, 0.15) !important; }
    [data-testid="stHeader"] * { color: #1E1E1E !important; }
    .compare-table { width: 100%; border-collapse: collapse; margin-top: 16px; }
    .compare-table th, .compare-table td { padding: 14px 18px; text-align: center; border-bottom: 1px solid #E5E7EB; }
    .compare-table th { background: rgba(46, 134, 171, 0.08); color: #1E1E1E !important; font-weight: 700; }
    .compare-table tr:hover { background: rgba(46, 134, 171, 0.04); }
    .best-value { background: linear-gradient(135deg, rgba(46, 204, 113, 0.2) 0%, rgba(46, 204, 113, 0.1) 100%); border-radius: 10px; padding: 6px 12px; font-weight: 700; color: #1E8449; }
    [data-testid="stSlider"] label, [data-testid="stSlider"] span, [data-testid="stSlider"] div, [data-testid="stRadio"] label, [data-testid="stRadio"] span, [data-testid="stRadio"] div, [data-testid="stNumberInput"] label, [data-testid="stNumberInput"] span, [data-testid="stNumberInput"] div, [data-testid="stMultiSelect"] label, [data-testid="stMultiSelect"] span, [data-testid="stMultiSelect"] div, [data-testid="stCheckbox"] label, [data-testid="stCheckbox"] span, [data-testid="stDateInput"] label, [data-testid="stDateInput"] span, [data-testid="stDateInput"] div, [data-testid="stTextInput"] label, [data-testid="stTextInput"] span, [data-testid="stTextInput"] div, [data-testid="stTextArea"] label, [data-testid="stTextArea"] span, [data-testid="stTextArea"] div { color: #333333 !important; }
    [data-testid="stExpander"] summary, [data-testid="stExpander"] span, [data-testid="stExpander"] p, [data-testid="stExpander"] div, [data-testid="stExpander"] label { color: #333333 !important; }
    .stDataFrame td, .stDataFrame th, [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th { color: #1E1E1E !important; }
    [data-testid="stDataFrame"] { background: #FFFFFF !important; }
    [data-testid="stSelectSlider"] label, [data-testid="stSelectSlider"] span, [data-testid="stSelectSlider"] div { color: #333333 !important; }
    .stTextInput input, .stTextArea textarea, .stNumberInput input { background: #FFFFFF !important; color: #1E1E1E !important; border: 1px solid #D1D5DB !important; border-radius: 10px; }
    .stTextInput input::placeholder, .stTextArea textarea::placeholder { color: rgba(102, 102, 102, 0.5) !important; }
    .stTabs [data-baseweb="tab-list"] { background: rgba(46, 134, 171, 0.06) !important; border-radius: 12px; padding: 6px; }
    .stTabs [data-baseweb="tab"] { color: #666666 !important; border-radius: 10px !important; }
    .stTabs [data-baseweb="tab"][aria-selected="true"] { background: linear-gradient(135deg, #2E86AB 0%, #40A0FF 100%) !important; color: #FFFFFF !important; }
    .stProgress > div > div { background: linear-gradient(90deg, #2E86AB, #40A0FF) !important; }
    .stFileUploader div[data-testid="stFileUploader"] { background: #FFFFFF !important; border: 2px dashed rgba(46, 134, 171, 0.3) !important; border-radius: 12px; }
    .stFileUploader div[data-testid="stFileUploader"] * { color: #333333 !important; }
    .dashboard-title { font-size: 52px; font-weight: 900; text-align: center; background: linear-gradient(90deg, #2E86AB, #40A0FF, #2ECC71, #2E86AB); background-size: 300% 300%; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; animation: gradient-shift 4s ease infinite; margin-bottom: 30px; }
    @keyframes gradient-shift { 0%, 100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
    .dashboard-metric { background: rgba(255, 255, 255, 0.9); border-radius: 16px; padding: 20px; text-align: center; border: 1px solid rgba(46, 134, 171, 0.2); box-shadow: 0 8px 24px rgba(0,0,0,0.08); }
    .dashboard-metric-value { font-size: 48px; font-weight: 900; white-space: nowrap; background: linear-gradient(135deg, #2E86AB, #40A0FF); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
    .dashboard-metric-label { font-size: 15px; color: #666666; margin-top: 8px; }
</style>
"""

PRO_DARK_CSS = """<style>
    .stApp { background: #07111F !important; font-family: Inter, "Noto Sans SC", "Microsoft YaHei", sans-serif; }
    [data-testid="stSidebar"] { background: #0B1625 !important; border-right: 1px solid #1D2A3A !important; box-shadow: none !important; }
    [data-testid="stHeader"] { background: rgba(7,17,31,.94) !important; border-bottom: 1px solid #1D2A3A !important; }
    .main-title, .dashboard-title { color: #F4F7FB !important; background: none !important; -webkit-text-fill-color: #F4F7FB !important; animation: none !important; text-align: left !important; font-size: 32px !important; font-weight: 720 !important; letter-spacing: -.02em; margin: 4px 0 20px !important; }
    .section-title { color: #E7EDF5 !important; font-size: 20px !important; font-weight: 650 !important; border-left: 3px solid #27C2D1 !important; padding-left: 12px !important; margin: 22px 0 14px !important; }
    .metric-card, .dashboard-metric, .card, .stCard { background: #0D1A2B !important; border: 1px solid #1D2E43 !important; border-radius: 12px !important; box-shadow: none !important; backdrop-filter: none !important; padding: 18px !important; }
    .metric-value, .dashboard-metric-value { color: #EAF6F7 !important; background: none !important; -webkit-text-fill-color: #EAF6F7 !important; font-size: 32px !important; font-weight: 720 !important; }
    .metric-value-compact { font-size: 24px !important; white-space: nowrap !important; letter-spacing: -.02em; }
    .metric-label, .dashboard-metric-label { color: #8FA1B7 !important; font-size: 13px !important; font-weight: 500 !important; }
    .divider { height: 1px !important; background: #1D2A3A !important; margin: 24px 0 !important; }
    .stButton button { background: #123047 !important; border: 1px solid #22506B !important; border-radius: 8px !important; box-shadow: none !important; font-size: 14px !important; padding: 9px 16px !important; }
    .stButton button:hover { background: #173C57 !important; border-color: #27C2D1 !important; transform: none !important; box-shadow: none !important; }
    .custom-info-box { background: #0D1A2B !important; border: 1px solid #1D2E43 !important; border-radius: 10px !important; }
</style>"""

PRO_LIGHT_CSS = """<style>
    .stApp { background: #F3F6FA !important; font-family: Inter, "Noto Sans SC", "Microsoft YaHei", sans-serif; }
    [data-testid="stSidebar"] { background: #FFFFFF !important; border-right: 1px solid #DDE5EE !important; box-shadow: none !important; }
    [data-testid="stHeader"] { background: rgba(243,246,250,.94) !important; border-bottom: 1px solid #DDE5EE !important; }
    .main-title, .dashboard-title { color: #132033 !important; background: none !important; -webkit-text-fill-color: #132033 !important; animation: none !important; text-align: left !important; font-size: 32px !important; font-weight: 720 !important; letter-spacing: -.02em; margin: 4px 0 20px !important; }
    .section-title { color: #1A293D !important; font-size: 20px !important; font-weight: 650 !important; border-left: 3px solid #168A9A !important; padding-left: 12px !important; margin: 22px 0 14px !important; }
    .metric-card, .dashboard-metric, .card, .stCard { background: #FFFFFF !important; border: 1px solid #DDE5EE !important; border-radius: 12px !important; box-shadow: none !important; padding: 18px !important; }
    .metric-value, .dashboard-metric-value { color: #17334A !important; background: none !important; -webkit-text-fill-color: #17334A !important; font-size: 32px !important; font-weight: 720 !important; }
    .metric-value-compact { font-size: 24px !important; white-space: nowrap !important; letter-spacing: -.02em; }
    .metric-label, .dashboard-metric-label { color: #6D7E91 !important; font-size: 13px !important; font-weight: 500 !important; }
    .divider { height: 1px !important; background: #DDE5EE !important; margin: 24px 0 !important; }
    .stButton button { background: #126E82 !important; border: 1px solid #126E82 !important; border-radius: 8px !important; box-shadow: none !important; font-size: 14px !important; padding: 9px 16px !important; }
    .stButton button:hover { background: #0E5C6D !important; transform: none !important; box-shadow: none !important; }
    .custom-info-box { background: #FFFFFF !important; border: 1px solid #DDE5EE !important; border-radius: 10px !important; }
</style>"""


def apply_theme(_theme=None):
    """应用唯一的浅色专业主题。"""
    st.markdown(LIGHT_CSS, unsafe_allow_html=True)
    st.markdown(PRO_LIGHT_CSS, unsafe_allow_html=True)


def get_theme_colors(_theme=None):
    """返回统一的浅色图表色板。"""
    return {
        'plot_bg': '#FFFFFF', 'paper_bg': '#FFFFFF',
        'font_color': '#243448', 'grid_color': '#E3E9F0',
        'legend_bg': 'rgba(255,255,255,0.95)', 'legend_border': '#E0E0E0',
        'accent': '#126E82', 'positive': '#D94B4B', 'negative': '#1F9D72',
        'secondary_text': '#6D7E91', 'muted_text': '#1F9D72', 'success': '#D6912A',
    }


def show_login_page():
    st.markdown("""
    <style>
        @keyframes gradient-shift { 0%, 100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
        @keyframes float { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-10px); } }
        .login-card { max-width: 480px; margin: 0 auto; padding: 50px 40px; border-radius: 24px; background: linear-gradient(135deg, rgba(108, 99, 255, 0.1) 0%, rgba(255, 107, 157, 0.05) 100%); backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.1); box-shadow: 0 25px 80px rgba(0, 0, 0, 0.3); }
        [data-testid="stTabs"] [data-baseweb="tab-list"] { background: rgba(255, 255, 255, 0.05) !important; border-radius: 16px; padding: 6px; gap: 8px; }
        [data-testid="stTabs"] [data-baseweb="tab"] { border-radius: 12px !important; padding: 12px 24px !important; font-weight: 600 !important; }
        [data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] { background: linear-gradient(135deg, #6C63FF 0%, #FF6B9D 100%) !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)
    _, col2, _ = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style='text-align: center; padding: 20px 0;'>
            <div style='display: inline-block; animation: float 3s ease-in-out infinite;'>
                <span style='font-size: 80px;'>📈</span>
            </div>
            <h1 style='font-size: 48px; font-weight: 900; margin-top: 20px;'>
                <span style='background: linear-gradient(90deg, #6C63FF, #FF6B9D, #40FF80, #6C63FF); background-size: 300% 300%; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; animation: gradient-shift 4s ease infinite;'>A股量化数据工程平台</span>
            </h1>
            <p style='font-size: 18px; margin-top: 15px; opacity: 0.8;'>请登录以访问系统功能</p>
        </div>
        """, unsafe_allow_html=True)
        tab_login, tab_register = st.tabs(["🔐 登录", "📝 注册"])
        with tab_login:
            with st.form("login_form"):
                username = st.text_input("用户名")
                password = st.text_input("密码", type="password")
                submitted = st.form_submit_button("登录", width='stretch')
                if submitted:
                    user = db_login(username, password)
                    if user:
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        st.session_state.theme = 'light'
                        st.session_state.watchlist = json.loads(user.get('watchlist', '[]'))
                        st.session_state.top_n = user.get('top_n', 20)
                        st.rerun()
                    else:
                        st.error("用户名或密码错误")
        with tab_register:
            with st.form("register_form"):
                reg_user = st.text_input("用户名")
                reg_pass = st.text_input("密码", type="password")
                reg_confirm = st.text_input("确认密码", type="password")
                ok = st.form_submit_button("注册", width='stretch')
                if ok:
                    if not reg_user or not reg_pass:
                        st.error("请填写用户名和密码")
                    elif reg_pass != reg_confirm:
                        st.error("两次密码不一致")
                    else:
                        ok, msg = db_register(reg_user, reg_pass)
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)


@st.cache_data
def _count_raw_records():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    raw_dir = os.path.join(base_dir, 'data', 'raw')
    if not os.path.isdir(raw_dir):
        return 0
    total = 0
    for f in os.listdir(raw_dir):
        if f.endswith('.csv'):
            try:
                df_tmp = pd.read_csv(os.path.join(raw_dir, f), usecols=[0])
                total += len(df_tmp)
            except Exception:
                pass
    return total


ANALYTIC_FACTOR_COLUMNS = [
    'ret_5d', 'momentum_20d', 'reversal_5d', 'ma5', 'ma10', 'ma20',
    'ma5_ma10_diff', 'ma5_ma20_diff', 'macd', 'macd_signal', 'rsi',
    'volatility_20d', 'volatility_60d', 'bb_mid', 'bb_position',
    'high_low_ratio', 'volume_ma5', 'volume_ratio', 'amount_ma20',
    'amount_ratio', 'close_open_ratio', 'sentiment', 'sentiment_ma5',
    'sentiment_ma10',
]


def st_card():
    """使用 Streamlit 原生边框容器，确保组件真正处于同一个 DOM 卡片内。"""
    return st.container(border=True)


def classify_board(code):
    code_str = str(code).zfill(6)
    if code_str.startswith('688'):
        return '科创板'
    elif code_str.startswith('3'):
        return '创业板'
    elif code_str.startswith('0'):
        return '深市主板'
    elif code_str.startswith('6'):
        return '沪市主板'
    return '其他'


def show_system_overview():
    theme = st.session_state.get('theme', 'dark')
    st.markdown(f"<div class='main-title' style='text-align: center;'>A股量化数据工程平台</div>", unsafe_allow_html=True)
    asset_summary = get_asset_summary()
    colors = get_theme_colors('深色主题' if theme == 'dark' else theme)
    if not asset_summary:
        st.warning("⚠️ 请先生成数据")
        return
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("<div class='section-title'>📊 数据统计</div>", unsafe_allow_html=True)
        with st_card():
            st.markdown(f"""
                <div style='margin: 15px 0;'>
                    <div style='color: {colors['secondary_text']}; font-size: 14px; margin-bottom: 5px;'>总记录数</div>
                    <div style='color: {colors['font_color']}; font-size: 32px; font-weight: 900;'>{asset_summary['record_count']:,}</div>
                </div>
                <div style='margin: 15px 0;'>
                    <div style='color: {colors['secondary_text']}; font-size: 14px; margin-bottom: 5px;'>股票数量</div>
                    <div style='color: {colors['font_color']}; font-size: 32px; font-weight: 900;'>{asset_summary['detail_stock_count']}</div>
                </div>
                """, unsafe_allow_html=True)
    _log_xgb_acc, _log_xgb_auc, _log_xgb_mse = 0.5177, 0.5346, 0.249826
    _log_lstm_acc, _log_lstm_auc, _log_lstm_mse = 0.5094, 0.5328, 0.249148
    _training_metrics_loaded = False
    _comparison_source = '内置历史参考值（请重新训练）'
    _training_log_path = (
        str(PORTFOLIO_TRAINING_LOG_PATH)
        if PORTFOLIO_MODE
        else _P('training_log.json')
    )
    if os.path.exists(_training_log_path):
        try:
            with open(_training_log_path, 'r', encoding='utf-8') as f:
                _tlog = json.load(f)
            if 'XGBoost' in _tlog:
                _log_xgb_acc = _tlog['XGBoost'].get('accuracy', _log_xgb_acc)
                _log_xgb_auc = _tlog['XGBoost'].get('auc', _log_xgb_auc)
                _log_xgb_mse = _tlog['XGBoost'].get('mse', _log_xgb_mse)
            if 'LSTM' in _tlog:
                _log_lstm_acc = _tlog['LSTM'].get('accuracy', _log_lstm_acc)
                _log_lstm_auc = _tlog['LSTM'].get('auc', _log_lstm_auc)
                _log_lstm_mse = _tlog['LSTM'].get('mse', _log_lstm_mse)
            _training_metrics_loaded = 'XGBoost' in _tlog and 'LSTM' in _tlog
            if _training_metrics_loaded:
                _comparison_source = 'training_log.json（最近一次真实训练）'
        except Exception:
            pass
    with col2:
        st.markdown("<div class='section-title'>🎯 模型表现</div>", unsafe_allow_html=True)
        with st_card():
            _overview_acc = (_log_xgb_acc + _log_lstm_acc) / 2
            _overview_auc = (_log_xgb_auc + _log_lstm_auc) / 2
            st.markdown(f"<div style='margin: 15px 0;'><div style='color: {colors['secondary_text']}; font-size: 14px; margin-bottom: 5px;'>平均准确率</div><div style='color: {colors['font_color']}; font-size: 32px; font-weight: 900;'>{_overview_acc:.2%}</div></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='margin: 15px 0;'><div style='color: {colors['secondary_text']}; font-size: 14px; margin-bottom: 5px;'>平均 AUC</div><div style='color: {colors['font_color']}; font-size: 32px; font-weight: 900;'>{_overview_auc:.4f}</div></div>", unsafe_allow_html=True)
    with col3:
        st.markdown("<div class='section-title'>⚡ 快速操作</div>", unsafe_allow_html=True)
        with st_card():
            if st.button("🔄 刷新数据"):
                st.cache_data.clear()
                st.cache_resource.clear()
                st.rerun()
            st.markdown(f"<p style='color: {colors['secondary_text']}; font-size: 14px;'>从左侧菜单栏选择页面进行分析</p>", unsafe_allow_html=True)

    st.markdown("<div class='section-title'>🤖 模型对比</div>", unsafe_allow_html=True)
    comparison_path = _P('reports', 'model_comparison.csv')
    xgb_acc, xgb_auc, xgb_mse = _log_xgb_acc, _log_xgb_auc, _log_xgb_mse
    lstm_acc, lstm_auc, lstm_mse = _log_lstm_acc, _log_lstm_auc, _log_lstm_mse
    if not _training_metrics_loaded and os.path.exists(comparison_path):
        try:
            comparison_df = pd.read_csv(comparison_path)
            for _, row in comparison_df.iterrows():
                try:
                    if 'model' in comparison_df.columns:
                        if 'XGBoost' in str(row.get('model', '')):
                            xgb_acc = float(row.get('accuracy', xgb_acc))
                            xgb_auc = float(row.get('auc', xgb_auc))
                            xgb_mse = float(row.get('mse', xgb_mse))
                        elif 'LSTM' in str(row.get('model', '')):
                            lstm_acc = float(row.get('accuracy', lstm_acc))
                            lstm_auc = float(row.get('auc', lstm_auc))
                            lstm_mse = float(row.get('mse', lstm_mse))
                except Exception:
                    pass
        except Exception:
            pass
        else:
            _comparison_source = 'reports/model_comparison.csv'
    xgb_acc_pct = xgb_acc * 100
    lstm_acc_pct = lstm_acc * 100
    xgb_acc_class = 'best-value' if xgb_acc > lstm_acc else ''
    lstm_acc_class = 'best-value' if lstm_acc > xgb_acc else ''
    xgb_auc_class = 'best-value' if xgb_auc > lstm_auc else ''
    lstm_auc_class = 'best-value' if lstm_auc > xgb_auc else ''
    xgb_mse_class = 'best-value' if xgb_mse < lstm_mse else ''
    lstm_mse_class = 'best-value' if lstm_mse < xgb_mse else ''
    table_html = f"""
        <table class='compare-table'>
            <thead><tr><th style='width: 40%;'>评估指标</th><th style='width: 30%;'>XGBoost</th><th style='width: 30%;'>LSTM</th></tr></thead>
            <tbody>
                <tr><td>测试集准确率</td><td class="{xgb_acc_class}">{xgb_acc_pct:.2f}%</td><td class="{lstm_acc_class}">{lstm_acc_pct:.2f}%</td></tr>
                <tr><td>测试集AUC</td><td class="{xgb_auc_class}">{xgb_auc:.4f}</td><td class="{lstm_auc_class}">{lstm_auc:.4f}</td></tr>
                <tr><td>测试集MSE</td><td class="{xgb_mse_class}">{xgb_mse:.6f}</td><td class="{lstm_mse_class}">{lstm_mse:.6f}</td></tr>
            </tbody>
        </table>"""
    st.markdown(table_html, unsafe_allow_html=True)
    png_path = _P('reports', 'model_comparison.png')
    if os.path.exists(png_path):
        st.image(png_path)
    accuracy_winner = 'XGBoost' if xgb_acc > lstm_acc else ('LSTM' if lstm_acc > xgb_acc else '两者')
    auc_winner = 'XGBoost' if xgb_auc > lstm_auc else ('LSTM' if lstm_auc > xgb_auc else '两者')
    mse_winner = 'XGBoost' if xgb_mse < lstm_mse else ('LSTM' if lstm_mse < xgb_mse else '两者')
    if accuracy_winner == auc_winner == mse_winner and accuracy_winner != '两者':
        comparison_conclusion = (
            f"{accuracy_winner} 在准确率、AUC 和 MSE 三项测试指标上均略优。"
        )
    else:
        comparison_conclusion = (
            f"准确率较优：{accuracy_winner}；AUC 较优：{auc_winner}；"
            f"MSE 较优：{mse_winner}。"
        )
    auc_conclusion = (
        '两种模型的 AUC 均接近 0.5，区分度仍然较弱。'
        if max(xgb_auc, lstm_auc) < 0.55
        else '至少一个模型表现出一定的样本外区分度。'
    )
    backtest_conclusion = '尚未生成修正版回测结果。'
    backtest_metrics_path = (
        str(PORTFOLIO_BACKTEST_METRICS_PATH)
        if PORTFOLIO_MODE
        else _P('backtest_results', 'backtest_metrics.csv')
    )
    if os.path.exists(backtest_metrics_path):
        try:
            backtest_metrics = pd.read_csv(backtest_metrics_path).iloc[0]
            strategy_return = float(backtest_metrics.get('total_return', 0))
            benchmark_return = float(backtest_metrics.get('benchmark_total_return', 0))
            excess_return = float(backtest_metrics.get('excess_return', strategy_return - benchmark_return))
            backtest_conclusion = (
                f"含成本 Walk-Forward 回测收益 {strategy_return:.2%}，"
                f"同期基准 {benchmark_return:.2%}，超额 {excess_return:.2%}；"
                "当前模型不具备实盘优势。"
            )
        except (OSError, ValueError, TypeError, IndexError):
            pass
    st.markdown(f"""
        <div style='margin-top: 20px;'>
            <p style='color: {colors['secondary_text']}; font-size: 13px; margin: 0;'>{comparison_conclusion} {auc_conclusion}</p>
            <p style='color: {colors['secondary_text']}; font-size: 12px; margin-top: 5px;'>数据来源: <code>{_comparison_source}</code></p>
        </div>""", unsafe_allow_html=True)
    st.markdown(f"""
        - **预测表现**：XGBoost 准确率 {xgb_acc_pct:.2f}%、AUC {xgb_auc:.4f}；LSTM 准确率 {lstm_acc_pct:.2f}%、AUC {lstm_auc:.4f}。
        - **原因分析**：A 股日频收益率噪声大；当前未验证情绪数据已从训练特征中排除。
        - **回测结论**：{backtest_conclusion}
        - **模型定位**：当前仅作为研究基线和排序信号实验，不用于宣称绝对涨跌判断能力。
        - **未来改进方向**：引入更高频数据、增加基本面因子、使用 Transformer 模型。
        """)


def show_data_insight():
    st.markdown("<div class='main-title'>📊 数据洞察</div>", unsafe_allow_html=True)
    stock_catalog = get_stock_catalog(has_detail=True)
    market_summary = get_market_summary()
    theme = st.session_state.get('theme', 'dark')
    colors = get_theme_colors('深色主题' if theme == 'dark' else theme)
    if stock_catalog.empty or market_summary.empty:
        st.markdown("<div style='padding:8px 12px;border-radius:8px;background:rgba(241,196,15,0.1);color:#f39c12;font-size:14px;'>⚠️ 请先加载数据</div>", unsafe_allow_html=True)
        return
    with st_card():
        board_counts = stock_catalog['board'].value_counts()
        pie_colors = ['#6C63FF', '#2E86AB', '#E74C3C', '#F39C12', '#1ABC9C']
        fig_pie = go.Figure(go.Pie(labels=board_counts.index.tolist(), values=board_counts.values, marker=dict(colors=pie_colors, line=dict(color=colors['paper_bg'], width=2)), textinfo='label+percent+value', textfont=dict(color=colors['font_color'], size=14), hole=0.4, pull=0.03))
        fig_pie.update_layout(height=400, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='🏛️ 股票市场板块分布', font=dict(size=22, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=40, r=60, t=60, b=40), legend=dict(font=dict(size=13, color=colors['font_color']), bgcolor=colors['legend_bg'], bordercolor=colors['legend_border'], borderwidth=1))
        st.plotly_chart(fig_pie, width='stretch', config={'displayModeBar': False})
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    with st_card():
        daily_avg_close = market_summary[['date', 'average_close']].rename(
            columns={'average_close': 'close'}
        )
        fig_close = go.Figure()
        fig_close.add_trace(go.Scatter(x=daily_avg_close['date'], y=daily_avg_close['close'], name='全市场平均收盘价', line=dict(color=colors['accent'], width=2.5), mode='lines', fill='tozeroy', fillcolor='rgba(18, 110, 130, 0.08)'))
        fig_close.update_layout(height=380, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='💰 全市场平均收盘价走势', font=dict(size=22, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=50, r=30, t=60, b=50), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])), yaxis=dict(title=dict(text='平均收盘价 (元)', font=dict(color=colors['font_color'])), showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])))
        st.plotly_chart(fig_close, width='stretch', config={'displayModeBar': False})
    with st_card():
        monthly_volume = pd.DataFrame({
            'year_month': market_summary['date'].dt.to_period('M'),
            'volume': market_summary['total_volume'],
        }).groupby('year_month', as_index=False)['volume'].sum()
        monthly_volume['year_month_str'] = monthly_volume['year_month'].astype(str)
        three_years_ago = market_summary['date'].max() - pd.DateOffset(years=3)
        cutoff_period = pd.Period(three_years_ago, freq='M')
        monthly_volume_recent = monthly_volume[monthly_volume['year_month'] >= cutoff_period]
        fig_vol = go.Figure()
        fig_vol.add_trace(go.Bar(x=monthly_volume_recent['year_month_str'], y=monthly_volume_recent['volume'], name='月度总成交量', marker=dict(color=monthly_volume_recent['volume'], colorscale='Blues', opacity=0.85, line=dict(color='rgba(0,0,0,0)', width=0.5))))
        fig_vol.update_layout(height=380, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='📈 每月总成交量（近3年）', font=dict(size=22, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=50, r=30, t=60, b=50), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=10, color=colors['font_color']), tickangle=-45), yaxis=dict(title=dict(text='总成交量', font=dict(color=colors['font_color'])), showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])))
        st.plotly_chart(fig_vol, width='stretch', config={'displayModeBar': False})
    if 'average_sentiment' in market_summary.columns and market_summary['average_sentiment'].notna().any():
        with st_card():
            daily_sentiment = market_summary[['date', 'average_sentiment']].rename(
                columns={'average_sentiment': 'sentiment'}
            )
            fig_sent = go.Figure()
            fig_sent.add_trace(go.Scatter(x=daily_sentiment['date'], y=daily_sentiment['sentiment'], name='全市场平均情绪', line=dict(color=colors['accent'], width=2), mode='lines', fill='tozeroy'))
            fig_sent.add_hline(y=0, line_dash='dot', line_color='rgba(128,128,128,0.5)')
            fig_sent.update_layout(height=380, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='💬 全市场情绪变化', font=dict(size=22, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=50, r=30, t=60, b=50), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])), yaxis=dict(title=dict(text='平均情绪值 (-1~1)', font=dict(color=colors['font_color'])), showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color']), range=[-1.1, 1.1]))
            st.plotly_chart(fig_sent, width='stretch', config={'displayModeBar': False})
    else:
        st.info("⚠️ 情绪数据暂不可用，请先生成情绪数据")


def show_factor_analysis():
    st.markdown("<div class='main-title'>📊 因子分析</div>", unsafe_allow_html=True)
    stock_catalog = get_stock_catalog(has_detail=True)
    theme = st.session_state.get('theme', 'dark')
    colors = get_theme_colors('深色主题' if theme == 'dark' else theme)
    if stock_catalog.empty:
        st.warning("⚠️ 请先生成数据")
        return
    stock_codes = stock_catalog['code'].tolist()
    watchlist = st.session_state.get('watchlist', [])
    priority_codes = [c for c in watchlist if c in stock_codes]
    other_codes = [c for c in stock_codes if c not in watchlist]
    display_codes = priority_codes + other_codes
    selected_code = st.selectbox("选择股票", display_codes, key='factor_stock_select')
    df_stock = get_stock_history(selected_code)
    if df_stock.empty:
        st.warning("⚠️ 此股票暂无可用因子明细")
        return
    with st_card():
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['close'], name='收盘价', line=dict(color=colors['accent'], width=2.5)))
        if 'ma5' in df_stock.columns:
            fig.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['ma5'], name='MA5', line=dict(color=colors['negative'], width=1.5, dash='dash')))
        if 'ma20' in df_stock.columns:
            fig.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['ma20'], name='MA20', line=dict(color=colors['success'], width=1.5)))
        fig.update_layout(height=350, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='💰 价格走势', font=dict(size=22, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=40, r=20, t=60, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color']), yaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=14)), legend=dict(font=dict(size=14, color=colors['font_color'])))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        with st_card():
            if 'rsi' in df_stock.columns:
                fig_rsi = go.Figure()
                fig_rsi.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['rsi'], name='RSI', line=dict(color=colors['success'], width=2)))
                fig_rsi.add_hline(y=70, line_dash='dash', line_color='red', annotation_text='超买')
                fig_rsi.add_hline(y=30, line_dash='dash', line_color='green', annotation_text='超卖')
                fig_rsi.update_layout(height=300, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='📈 RSI指标', font=dict(size=18, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=40, r=20, t=50, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color']), yaxis=dict(showgrid=True, gridcolor=colors['grid_color']))
                st.plotly_chart(fig_rsi, width='stretch', config={'displayModeBar': False})
    with col2:
        with st_card():
            if 'macd' in df_stock.columns and 'macd_signal' in df_stock.columns:
                fig_macd = go.Figure()
                fig_macd.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['macd'], name='MACD', line=dict(color=colors['accent'], width=2)))
                fig_macd.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['macd_signal'], name='Signal', line=dict(color=colors['success'], width=2)))
                fig_macd.update_layout(height=300, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='📊 MACD指标', font=dict(size=18, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=40, r=20, t=50, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color']), yaxis=dict(showgrid=True, gridcolor=colors['grid_color']))
                st.plotly_chart(fig_macd, width='stretch', config={'displayModeBar': False})
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    with st_card():
        factor_cols = [c for c in ANALYTIC_FACTOR_COLUMNS if c in df_stock.columns]
        if len(factor_cols) >= 2:
            selected_factors = factor_cols[:10]
            df_corr = df_stock[selected_factors].corr()
            fig_corr = go.Figure(go.Heatmap(z=df_corr.values, x=df_corr.columns, y=df_corr.columns, colorscale='RdBu_r', zmin=-1, zmax=1, text=df_corr.round(2).values, texttemplate='%{text}', textfont=dict(size=10), showscale=True))
            fig_corr.update_layout(height=400, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='🔥 因子相关性热力图', font=dict(size=18, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=40, r=20, t=50, b=20), xaxis=dict(tickfont=dict(size=11, color=colors['font_color']), tickangle=-45), yaxis=dict(tickfont=dict(size=11, color=colors['font_color'])))
            st.plotly_chart(fig_corr, width='stretch')
        else:
            st.info("⚠️ 因子数据不足，无法绘制热力图")
    st.markdown("<div class='section-title'>📐 因子IC实时分析</div>", unsafe_allow_html=True)
    factor_ic_catalog = get_factor_catalog()
    all_factor_names = (
        sorted(factor_ic_catalog['factor_name'].unique())
        if not factor_ic_catalog.empty else []
    )
    if all_factor_names:
        selected_ic_factors = st.multiselect("选择因子（1~5个）", all_factor_names, max_selections=5, key='ic_factor_select')
        if selected_ic_factors:
            min_date = factor_ic_catalog['date'].min().date()
            max_date = factor_ic_catalog['date'].max().date()
            default_start = (max_date - timedelta(days=365)) if (max_date - timedelta(days=365)) >= min_date else min_date
            date_range = st.slider("选择分析日期区间", min_value=min_date, max_value=max_date, value=(default_start, max_date), key='ic_date_range')
            queried_ic = get_factor_ic(
                selected_ic_factors,
                start_date=date_range[0],
                end_date=date_range[1],
            )
            ic_results = {
                factor_name: group.rename(columns={'ic': 'IC'})
                for factor_name, group in queried_ic.groupby('factor_name')
                if group['ic'].notna().any()
            }
            if ic_results:
                color_palette = ['#6C63FF', '#2E86AB', '#E74C3C', '#F39C12', '#1ABC9C']
                for idx, (factor_name, ic_df) in enumerate(ic_results.items()):
                    fig_ic = go.Figure()
                    fig_ic.add_trace(go.Scatter(x=ic_df['date'], y=ic_df['IC'], name=f'{factor_name} IC', line=dict(color=color_palette[idx % len(color_palette)], width=2), mode='lines'))
                    fig_ic.add_hline(y=0, line_dash='dot', line_color='rgba(128,128,128,0.5)')
                    ic_mean = ic_df['IC'].mean()
                    ic_std = ic_df['IC'].std()
                    fig_ic.update_layout(height=300, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text=f'📈 {factor_name} IC序列 (均值={ic_mean:.4f}, 标准差={ic_std:.4f})', font=dict(size=16, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=40, r=20, t=50, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color']), yaxis=dict(title=dict(text='IC', font=dict(color=colors['font_color'])), showgrid=True, gridcolor=colors['grid_color']))
                    st.plotly_chart(fig_ic, width='stretch', config={'displayModeBar': False})
                ic_data = {name: df['IC'].describe().to_dict() for name, df in ic_results.items()}
                st.dataframe(pd.DataFrame(ic_data).round(4))
            else:
                st.info("该日期范围暂无可用 IC 结果")
        else:
            st.info("👆 请选择至少1个因子以开始IC分析")
    else:
        st.info("👆 请选择至少1个因子以开始IC分析")


def show_sentiment_analysis():
    st.markdown("<div class='main-title'>💬 情绪因子分析</div>", unsafe_allow_html=True)
    stock_catalog = get_stock_catalog(has_detail=True)
    theme = st.session_state.get('theme', 'dark')
    colors = get_theme_colors('深色主题' if theme == 'dark' else theme)
    if stock_catalog.empty:
        st.warning("⚠️ 没有可用的股票数据")
        return
    stock_codes = stock_catalog['code'].tolist()
    watchlist = st.session_state.get('watchlist', [])
    priority_codes = [c for c in watchlist if c in stock_codes]
    other_codes = [c for c in stock_codes if c not in watchlist]
    display_codes = priority_codes + other_codes
    selected_code = st.selectbox("选择股票", display_codes, key='sentiment_select')
    df_stock = get_stock_history(selected_code)
    if len(df_stock) == 0:
        st.warning("⚠️ 此股票没有情绪数据")
        return
    with st_card():
        fig = go.Figure()
        if 'sentiment' in df_stock.columns:
            fig.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['sentiment'], name='情绪值', line=dict(color=colors['accent'], width=2), mode='lines'))
        if 'sentiment_ma5' in df_stock.columns:
            fig.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['sentiment_ma5'], name='MA5', line=dict(color=colors['success'], width=1.5, dash='dash')))
        if 'sentiment_ma10' in df_stock.columns:
            fig.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['sentiment_ma10'], name='MA10', line=dict(color=colors['success'], width=1, dash='dot')))
        fig.update_layout(height=320, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='📈 情绪走势', font=dict(size=22, color=colors['font_color']), x=0.03, xanchor='left'), showlegend=True, legend=dict(font=dict(size=14, color=colors['font_color']), bgcolor=colors['legend_bg'], bordercolor=colors['legend_border'], borderwidth=1, itemwidth=30, itemsizing='trace', yanchor='top', y=0.9, xanchor='right', x=0.98), margin=dict(l=40, r=60, t=60, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color']), tickformat='%Y-%m-%d'), yaxis=dict(title=dict(text='情绪值 (-1~1)', font=dict(color=colors['font_color'])), tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color'], range=[-1.1, 1.1]))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    count_column = next(
        (column for column in ('news_count', 'comment_count') if column in df_stock.columns),
        None,
    )
    if count_column:
        count_title = '每日文本/互动样本量'
        count_label = '样本量'
        with st_card():
            fig_news = go.Figure()
            fig_news.add_trace(go.Bar(x=df_stock['date'], y=df_stock[count_column], name=count_label, marker=dict(color=colors['accent'], opacity=0.8)))
            fig_news.update_layout(height=280, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text=f'📰 {count_title}', font=dict(size=20, color=colors['font_color']), x=0.03, xanchor='left'), showlegend=True, legend=dict(font=dict(size=14, color=colors['font_color']), bgcolor=colors['legend_bg'], bordercolor=colors['legend_border'], borderwidth=1, yanchor='top', y=0.9, xanchor='right', x=0.98), margin=dict(l=40, r=20, t=50, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])), yaxis=dict(title=dict(text=count_label, font=dict(color=colors['font_color'])), tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color']))
            st.plotly_chart(fig_news, width='stretch', config={'displayModeBar': False})
    else:
        st.caption("当前数据快照未包含文本/互动样本量字段。")
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    if 'sentiment' in df_stock.columns:
        col1, col2, col3 = st.columns(3)
        avg_sentiment = df_stock['sentiment'].mean()
        sentiment_status = '正面' if avg_sentiment > 0.1 else ('负面' if avg_sentiment < -0.1 else '中性')
        sentiment_color = colors['positive'] if avg_sentiment > 0.1 else (colors['negative'] if avg_sentiment < -0.1 else colors['secondary_text'])
        sentiment_std = df_stock['sentiment'].std()
        total_days = len(df_stock)
        positive_days = (df_stock['sentiment'] > 0).sum()
        positive_rate = positive_days / total_days if total_days > 0 else 0
        with col1:
            st.markdown(f"<p style='font-size: 14px; color: {colors['secondary_text']};'>平均情绪值</p><p style='color:{sentiment_color};font-size:28px;font-weight:bold;'>{avg_sentiment:.2f}</p>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<p style='font-size: 12px; color: {colors['secondary_text']};'>情绪波动</p><p style='color:{colors['font_color']};font-size:28px;font-weight:bold;'>{sentiment_std:.2f}</p>", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<p style='font-size: 12px; color: {colors['secondary_text']};'>正面情绪占比</p><p style='color:{colors['font_color']};font-size:28px;font-weight:bold;'>{positive_rate:.1%}</p>", unsafe_allow_html=True)
    if 'close' in df_stock.columns and 'sentiment' in df_stock.columns:
        df_stock['returns'] = df_stock['close'].pct_change()
        df_stock['cumulative_return'] = (1 + df_stock['returns']).cumprod()
        with st_card():
            fig_overlay = go.Figure()
            fig_overlay.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['sentiment'], name='情绪值', line=dict(color=colors['accent'], width=2), mode='lines', yaxis='y'))
            fig_overlay.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['cumulative_return'], name='累计收益率', line=dict(color=colors['success'], width=2), mode='lines', yaxis='y2'))
            fig_overlay.update_layout(height=320, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='📈 情绪与收益率叠加', font=dict(size=22, color=colors['font_color']), x=0.03, xanchor='left'), showlegend=True, legend=dict(font=dict(size=14, color=colors['font_color']), bgcolor=colors['legend_bg'], bordercolor=colors['legend_border'], borderwidth=1, yanchor='top', y=0.9, xanchor='right', x=0.98), margin=dict(l=40, r=60, t=60, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])), yaxis=dict(title=dict(text='情绪值', font=dict(color=colors['font_color'])), tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color']), yaxis2=dict(title=dict(text='累计收益率', font=dict(color=colors['font_color'])), tickfont=dict(size=12, color=colors['font_color']), overlaying='y', side='right', showgrid=False, tickformat='.0%'))
            st.plotly_chart(fig_overlay, width='stretch', config={'displayModeBar': False})
        with st_card():
            df_stock['signal'] = (df_stock['sentiment'] > df_stock['sentiment'].rolling(10).mean()).astype(int)
            df_stock['strategy_return'] = df_stock['signal'].shift(1) * df_stock['returns']
            df_stock['strategy_cumulative'] = (1 + df_stock['strategy_return']).cumprod()
            df_stock['bh_cumulative'] = (1 + df_stock['returns']).cumprod()
            fig_bt = go.Figure()
            fig_bt.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['strategy_cumulative'], name='情绪择时策略', line=dict(color=colors['accent'], width=2.5), mode='lines'))
            fig_bt.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['bh_cumulative'], name='买入持有', line=dict(color=colors['success'], width=2, dash='dash'), mode='lines'))
            fig_bt.add_hline(y=1, line_dash='dot', line_color='rgba(128,128,128,0.5)')
            fig_bt.update_layout(height=300, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='📊 情绪择时回测', font=dict(size=20, color=colors['font_color']), x=0.03, xanchor='left'), showlegend=True, legend=dict(font=dict(size=14, color=colors['font_color']), bgcolor=colors['legend_bg'], bordercolor=colors['legend_border'], borderwidth=1, yanchor='top', y=0.9, xanchor='right', x=0.98), margin=dict(l=40, r=20, t=50, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])), yaxis=dict(title=dict(text='累计收益率', font=dict(color=colors['font_color'])), tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color'], tickformat='.0%'))
            st.plotly_chart(fig_bt, width='stretch', config={'displayModeBar': False})
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    example_title = '情绪记录样例' if PORTFOLIO_MODE else '新闻示例分析'
    st.markdown(f"<div class='section-title'>📰 {example_title}</div>", unsafe_allow_html=True)
    try:
        if not df_stock.empty:
            news_cols = [c for c in df_stock.columns if 'news' in c.lower() or 'title' in c.lower() or 'content' in c.lower()]
            if news_cols:
                recent_news = df_stock.sort_values('date', ascending=False).head(10)
                for _, row in recent_news.iterrows():
                    date_str = row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])[:10]
                    sentiment_val = row.get('sentiment', 0)
                    sentiment_emoji = '🟢' if sentiment_val > 0.1 else ('🔴' if sentiment_val < -0.1 else '🟡')
                    news_text = ''
                    for col in news_cols:
                        if pd.notna(row.get(col)) and str(row.get(col)).strip():
                            news_text = str(row[col])
                            break
                    if not news_text:
                        news_text = f"{selected_code} 交易日数据"
                    st.markdown(f"""
                        <div style='padding: 10px 15px; margin: 5px 0; background: {colors["paper_bg"]}; border-radius: 10px; border-left: 4px solid {colors["accent"]};'>
                            <span style='color: {colors["secondary_text"]}; font-size: 12px;'>{date_str}</span>
                            <span style='margin-left: 10px;'>{sentiment_emoji}</span>
                            <span style='color: {colors["font_color"]}; font-size: 14px; margin-left: 8px;'>{news_text}</span>
                            <span style='color: {colors["secondary_text"]}; font-size: 12px; margin-left: 10px;'>情绪值: {sentiment_val:.3f}</span>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                recent_news = df_stock.sort_values('date', ascending=False).head(5)
                st.markdown(f"<p style='color: {colors['secondary_text']}; font-size: 14px;'>当前快照不发布原始文本，展示最近情绪记录：</p>", unsafe_allow_html=True)
                for _, row in recent_news.iterrows():
                    date_str = row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])[:10]
                    sentiment_val = row.get('sentiment', 0)
                    sentiment_emoji = '🟢' if sentiment_val > 0.1 else ('🔴' if sentiment_val < -0.1 else '🟡')
                    sample_count = int(row.get(count_column, 0)) if count_column else 0
                    st.markdown(f"""
                        <div style='padding: 10px 15px; margin: 5px 0; background: {colors["paper_bg"]}; border-radius: 10px; border-left: 4px solid {colors["accent"]};'>
                            <span style='color: {colors["secondary_text"]}; font-size: 12px;'>{date_str}</span>
                            <span style='margin-left: 10px;'>{sentiment_emoji}</span>
                            <span style='color: {colors["font_color"]}; font-size: 14px; margin-left: 8px;'>{selected_code} - 样本量: {sample_count}</span>
                            <span style='color: {colors["secondary_text"]}; font-size: 12px; margin-left: 10px;'>情绪值: {sentiment_val:.3f}</span>
                        </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("暂无新闻数据")
    except Exception as e:
        st.info(f"新闻示例加载中...")


FULL_FEATURES = [
    'ret_5d', 'ma5', 'ma10', 'ma20', 'ma5_ma10_diff', 'ma5_ma20_diff',
    'rsi', 'macd', 'macd_signal', 'momentum_20d', 'reversal_5d',
    'volatility_20d', 'volatility_60d',
    'bb_mid', 'bb_position',
    'volume_ma5', 'volume_ratio', 'amount_ma20', 'amount_ratio',
    'high_low_ratio', 'close_open_ratio',
    'sentiment', 'sentiment_ma5', 'sentiment_ma10',
]
LSTM_TRAIN_FEATURES = ['ret_5d', 'ma5', 'ma10', 'rsi', 'macd', 'volatility_20d']


def _predict_xgb(df_all, xgb_model_path, selected_code=None):
    import xgboost as xgb
    from sklearn.metrics import accuracy_score, roc_auc_score, mean_squared_error
    if not os.path.exists(xgb_model_path):
        return {'error': 'XGBoost 模型文件不存在，请离线运行 python model_training.py'}
    try:
        model = xgb.XGBClassifier()
        model.load_model(xgb_model_path)
        feature_list_path = _P('results_optimized', 'xgb_feature_list.txt')
        if os.path.exists(feature_list_path):
            with open(feature_list_path, 'r') as f:
                features = [l.strip() for l in f if l.strip()]
        else:
            features = FULL_FEATURES
        available = [c for c in features if c in df_all.columns]
        if len(available) < 3:
            return {'error': f'可用特征不足(需>3, 当前{len(available)}), 缺少: {set(features)-set(df_all.columns)}'}
        df_clean = df_all.dropna(subset=available + ['label']).copy()
        if len(df_clean) < 20:
            return {'error': f'数据量不足(需>20, 当前{len(df_clean)})'}
        split_date = df_clean['date'].quantile(0.8)
        test_df = df_clean[df_clean['date'] > split_date].copy()
        if selected_code:
            code_test = test_df[test_df['code'] == selected_code]
            if len(code_test) < 10:
                code_test = test_df
        else:
            code_test = test_df
        X_test = code_test[available].fillna(0)
        y_pred_proba = model.predict_proba(X_test)[:, 1]
        y_true_cls = (code_test['label'] > 0).astype(int).values
        y_pred_cls = (y_pred_proba > 0.5).astype(int)
        acc = accuracy_score(y_true_cls, y_pred_cls) * 100
        try:
            auc = roc_auc_score(y_true_cls, y_pred_proba)
        except Exception:
            auc = 0.5
        mse = mean_squared_error(y_true_cls.astype(float), y_pred_proba)
        pred_close = code_test['close'].values * (1 + (y_pred_proba - 0.5) * 0.02)
        return {'acc': acc, 'auc': auc, 'mse': mse, 'pred_close': pred_close,
                'test_dates': code_test['date'].values, 'test_close': code_test['close'].values}
    except Exception as e:
        err_str = str(e)
        if 'mismatch' in err_str.lower() or 'shape' in err_str.lower() or 'size' in err_str.lower():
            return {'error': '模型结构与当前代码不匹配，请离线运行 python model_training.py'}
        return {'error': f'XGBoost 预测失败: {e}'}


def _predict_lstm(df_all, lstm_model_path, selected_code=None):
    import torch
    import torch.nn as nn
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, roc_auc_score, mean_squared_error

    class BiLSTMModel(nn.Module):
        def __init__(self, input_size, hidden_size=64, num_layers=2, dropout=0.2):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                batch_first=True,
                bidirectional=True,
                dropout=dropout if num_layers > 1 else 0,
            )
            self.dropout = nn.Dropout(dropout)
            self.fc = nn.Sequential(
                nn.Linear(hidden_size * 2, 32),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(32, 1),
            )

        def forward(self, x):
            output, _ = self.lstm(x)
            output = self.dropout(output[:, -1, :])
            return self.fc(output).squeeze(-1)

    if not os.path.exists(lstm_model_path):
        return {'error': 'LSTM 模型文件不存在，请离线运行 python model_training.py'}
    try:
        config_path = _P('results_optimized', 'model_config.txt')
        hidden_size, num_layers, dropout, time_steps = 64, 2, 0.2, 20
        model_input_size = len(FULL_FEATURES)
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                for line in f:
                    if '=' in line:
                        k, v = line.strip().split('=', 1)
                        if k == 'input_size': model_input_size = int(v)
                        elif k == 'hidden_size': hidden_size = int(v)
                        elif k == 'num_layers': num_layers = int(v)
                        elif k == 'dropout': dropout = float(v)
                        elif k == 'time_steps': time_steps = int(v)
        feature_list_path = _P('results_optimized', 'feature_list.txt')
        if os.path.exists(feature_list_path):
            with open(feature_list_path, 'r') as f:
                features = [l.strip() for l in f if l.strip()]
        else:
            features = FULL_FEATURES[:model_input_size]
        available = [c for c in features if c in df_all.columns]
        if len(available) < model_input_size:
            features = [c for c in FULL_FEATURES if c in df_all.columns][:model_input_size]
            available = features
        if len(available) < 3:
            return {'error': f'可用特征不足(需>3, 当前{len(available)})'}
        df_clean = df_all.dropna(subset=available + ['label']).copy()
        df_clean = df_clean.sort_values(['code', 'date']).reset_index(drop=True)
        if len(df_clean) < time_steps + 10:
            return {'error': f'数据量不足(需>{time_steps + 10}, 当前{len(df_clean)})'}
        split_date = df_clean['date'].quantile(0.8)
        test_df = df_clean[df_clean['date'] > split_date].copy()
        if selected_code:
            code_test = test_df[test_df['code'] == selected_code]
            if len(code_test) < time_steps + 5:
                code_test = test_df
        else:
            code_test = test_df
        scaler = StandardScaler()
        scaler.fit(df_clean[df_clean['date'] <= split_date][available])
        test_scaled = scaler.transform(code_test[available].fillna(0))
        X_list, y_list, close_list, date_list = [], [], [], []
        codes = code_test['code'].values
        for code in np.unique(codes):
            idx = np.where(codes == code)[0]
            feat_seq = test_scaled[idx]
            label_seq = (code_test.iloc[idx]['label'] > 0).astype(int).values
            close_seq = code_test.iloc[idx]['close'].values
            date_seq = code_test.iloc[idx]['date'].values
            for i in range(time_steps, len(feat_seq)):
                X_list.append(feat_seq[i - time_steps:i])
                y_list.append(label_seq[i])
                close_list.append(close_seq[i])
                date_list.append(date_seq[i])
        if len(X_list) < 5:
            return {'error': f'测试样本不足(需>5, 当前{len(X_list)})'}
        X_tensor = torch.tensor(np.array(X_list), dtype=torch.float32)
        model = BiLSTMModel(input_size=model_input_size, hidden_size=hidden_size,
                            num_layers=num_layers, dropout=dropout)
        state = torch.load(lstm_model_path, map_location='cpu', weights_only=True)
        model.load_state_dict(state)
        model.eval()
        with torch.no_grad():
            logits = model(X_tensor).numpy()
            y_pred_proba = 1.0 / (1.0 + np.exp(-logits))
        y_true = np.array(y_list)
        y_pred_cls = (y_pred_proba > 0.5).astype(int)
        acc = accuracy_score(y_true, y_pred_cls) * 100
        try:
            auc = roc_auc_score(y_true, y_pred_proba)
        except Exception:
            auc = 0.5
        mse = mean_squared_error(y_true.astype(float), y_pred_proba)
        pred_close = np.array(close_list) * (1 + (y_pred_proba - 0.5) * 0.02)
        return {'acc': acc, 'auc': auc, 'mse': mse, 'pred_close': pred_close,
                'test_dates': np.array(date_list), 'test_close': np.array(close_list)}
    except Exception as e:
        err_str = str(e)
        if 'missing key' in err_str.lower() or 'unexpected key' in err_str.lower() or 'mismatch' in err_str.lower() or 'size' in err_str.lower():
            return {'error': '模型结构与当前代码不匹配，请在项目目录离线运行 python model_training.py'}
        return {'error': f'LSTM 预测失败: {e}'}


def show_prediction():
    st.markdown("<div class='main-title'>🎯 股票预测</div>", unsafe_allow_html=True)
    stock_catalog = get_stock_catalog(has_detail=True)
    theme = st.session_state.get('theme', 'dark')
    colors = get_theme_colors('深色主题' if theme == 'dark' else theme)
    if stock_catalog.empty:
        st.markdown("<div style='padding:8px 12px;border-radius:8px;background:rgba(241,196,15,0.1);color:#f39c12;font-size:14px;'>⚠️ 请先处理数据</div>", unsafe_allow_html=True)
        return
    training_log_path = (
        str(PORTFOLIO_TRAINING_LOG_PATH)
        if PORTFOLIO_MODE
        else _P('training_log.json')
    )
    if not os.path.exists(training_log_path):
        st.warning(
            "现有模型文件缺少与当前数据快照对应的训练清单，属于历史产物。"
            "页面行情可以浏览，但模型指标与预测结果需重新训练后才可作为当前版本结论。"
        )
    stock_codes = stock_catalog['code'].tolist()
    watchlist = st.session_state.get('watchlist', [])
    priority_codes = [c for c in watchlist if c in stock_codes]
    other_codes = [c for c in stock_codes if c not in watchlist]
    display_codes = priority_codes + other_codes
    default_idx = display_codes.index('000001') if '000001' in display_codes else 0
    col_top1, col_top2 = st.columns([2, 1])
    with col_top1:
        selected_code = st.selectbox("选择股票代码", display_codes, index=default_idx, key='pred_select')
    with col_top2:
        selected_model = st.radio("选择模型", ["XGBoost", "LSTM"], horizontal=True, key='pred_model_radio')
    portfolio_evaluation = None
    if PORTFOLIO_MODE and os.path.exists(training_log_path):
        try:
            with open(training_log_path, 'r', encoding='utf-8') as file:
                portfolio_evaluation = json.load(file).get(selected_model)
        except (OSError, ValueError, TypeError):
            portfolio_evaluation = None
    df_stock = get_stock_history(selected_code)
    if df_stock.empty:
        st.warning("所选股票暂无可用行情明细。")
        return
    if st.session_state.get('_pred_code') != selected_code or st.session_state.get('_pred_model') != selected_model:
        st.session_state.pop('_pred_result', None)
        st.session_state['_pred_code'] = selected_code
        st.session_state['_pred_model'] = selected_model
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    xgb_model_path = _P('results_optimized', 'xgb_fixed.json')
    lstm_model_path = _P('results_optimized', 'lstm_fixed.pth')
    selected_model_path = lstm_model_path if selected_model == 'LSTM' else xgb_model_path
    if PORTFOLIO_MODE:
        data_range = (
            portfolio_evaluation.get('data_range', '未记录')
            if portfolio_evaluation else '未记录'
        )
        st.info(
            f"公开版展示 {selected_model} 的离线样本外评估快照（{data_range}）。"
            "为避免发布训练权重和重依赖，网页不执行实时推理。"
        )
    elif st.button("📊 开始预测", key='pred_btn', width='stretch'):
        if os.path.exists(selected_model_path):
            with st.spinner("🔄 预测中，请稍候..."):
                if selected_model == 'LSTM':
                    result = _predict_lstm(
                        df_stock, lstm_model_path, selected_code=selected_code
                    )
                else:
                    result = _predict_xgb(
                        df_stock, xgb_model_path, selected_code=selected_code
                    )
                st.session_state['_pred_result'] = result
            st.rerun()
        else:
            st.error(
                f"{selected_model} 模型文件不存在。请在项目目录离线运行 "
                "`python model_training.py` 后再预测。"
            )
    if PORTFOLIO_MODE:
        if portfolio_evaluation:
            st.success(f"{selected_model} 样本外评估快照已加载 · 只读展示")
        else:
            st.warning(f"{selected_model} 样本外评估快照暂不可用")
    elif os.path.exists(selected_model_path):
        recommendation = ' · 当前推荐' if selected_model == 'XGBoost' else ' · 对照模型'
        st.success(f"{selected_model} 模型已就绪{recommendation}（当前股票：{selected_code}）")
    else:
        st.warning(f"{selected_model} 模型尚未生成，请先执行离线训练流水线。")
    with st.expander("ℹ️ 模型与训练说明", expanded=False):
        st.markdown(
            "预测页面只加载已训练模型进行推理，不会按股票重复训练。当前样本外评估中，"
            "XGBoost 的准确率、AUC 和 MSE 均略优于 LSTM，因此作为默认推荐模型；"
            "LSTM 保留为时序模型对照实验。需要更新模型时，请在项目目录运行：\n\n"
            "```powershell\npython model_training.py\npython backtest.py\n```"
        )
    with st.expander("📊 训练日志", expanded=False):
        log_path = training_log_path
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    log = json.load(f)
                for model_name, info in log.items():
                    st.markdown(f"**{model_name}** - 最近训练: {info.get('timestamp', 'N/A')}")
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        st.metric("准确率", f"{info.get('accuracy', 0)*100:.2f}%")
                    with c2:
                        st.metric("AUC", f"{info.get('auc', 0):.4f}")
                    with c3:
                        st.metric("MSE", f"{info.get('mse', 0):.6f}")
                    with c4:
                        st.metric("特征数", f"{info.get('feature_count', 'N/A')}")
                    st.caption(f"数据范围: {info.get('data_range', 'N/A')} | 特征: {', '.join(info.get('features', []))}")
                    st.divider()
            except Exception:
                st.markdown("<div style='padding:8px 12px;border-radius:8px;background:rgba(52,152,219,0.1);color:#3498db;font-size:14px;'>训练日志读取失败</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='padding:8px 12px;border-radius:8px;background:rgba(52,152,219,0.1);color:#3498db;font-size:14px;'>暂无训练日志，请先训练模型</div>", unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    result_title = '样本外评估快照' if PORTFOLIO_MODE else '预测结果'
    st.markdown(f"<div class='section-title'>📋 {result_title}</div>", unsafe_allow_html=True)
    pred_result = st.session_state.get('_pred_result')
    if PORTFOLIO_MODE and portfolio_evaluation:
        pred_result = {
            'acc': float(portfolio_evaluation.get('accuracy', 0)) * 100,
            'auc': float(portfolio_evaluation.get('auc', 0)),
            'mse': float(portfolio_evaluation.get('mse', 0)),
        }
    if pred_result and 'error' in pred_result:
        st.markdown(f"<div style='padding:12px;border-radius:8px;background:rgba(231,76,60,0.15);color:#e74c3c;border:1px solid rgba(231,76,60,0.3);'>❌ {pred_result['error']}</div>", unsafe_allow_html=True)
    elif pred_result and 'acc' in pred_result:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"<div class='metric-card'><div class='metric-value'>{pred_result['acc']:.2f}%</div><div class='metric-label'>准确率</div></div>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<div class='metric-card'><div class='metric-value'>{pred_result['auc']:.4f}</div><div class='metric-label'>AUC</div></div>", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<div class='metric-card'><div class='metric-value'>{pred_result['mse']:.6f}</div><div class='metric-label'>MSE</div></div>", unsafe_allow_html=True)
    else:
        empty_message = (
            f'暂无 {selected_model} 样本外评估快照'
            if PORTFOLIO_MODE
            else f'点击「开始预测」查看 {selected_code} 的 {selected_model} 预测结果'
        )
        st.markdown(f"<div style='padding:8px 12px;border-radius:8px;background:rgba(52,152,219,0.1);color:#3498db;font-size:14px;'>📊 {empty_message}</div>", unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    chart_section = '合成行情技术参考' if PORTFOLIO_MODE else '价格预测走势'
    st.markdown(f"<div class='section-title'>📈 {chart_section}</div>", unsafe_allow_html=True)
    with st_card():
        recent_data = df_stock.tail(60).copy()
        recent_data['date_str'] = recent_data['date'].dt.strftime('%Y-%m-%d')
        fig = go.Figure()
        pred_label = 'LSTM预测价格' if selected_model == 'LSTM' else 'XGBoost预测价格'
        fig.add_trace(go.Scatter(
            x=recent_data['date_str'], y=recent_data['close'],
            name='真实价格', line=dict(color='#2E86AB', width=2.5)
        ))
        if pred_result and 'acc' in pred_result and pred_result.get('pred_close') is not None:
            pred_close = pred_result['pred_close']
            test_dates = pred_result.get('test_dates')
            if test_dates is not None and len(test_dates) == len(pred_close):
                date_strs = pd.to_datetime(test_dates).strftime('%Y-%m-%d')
                fig.add_trace(go.Scatter(
                    x=date_strs, y=pred_close,
                    name=pred_label, line=dict(color='#E74C3C', width=2, dash='dash')
                ))
            else:
                n_pred = min(len(pred_close), len(recent_data))
                fig.add_trace(go.Scatter(
                    x=recent_data['date_str'].iloc[-n_pred:],
                    y=pred_close[-n_pred:],
                    name=pred_label, line=dict(color='#E74C3C', width=2, dash='dash')
                ))
        elif 'ma5' in recent_data.columns:
            fig.add_trace(go.Scatter(
                x=recent_data['date_str'], y=recent_data['ma5'],
                name='MA5(参考)', line=dict(color='#E74C3C', width=1.5, dash='dot')
            ))
        chart_title = (
            f'📈 合成行情价格与 MA5 参考 - {selected_code}'
            if PORTFOLIO_MODE
            else f'📈 {selected_model} 价格预测走势 - {selected_code}'
        )
        fig.update_layout(
            height=400, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'],
            font=dict(color=colors['font_color']),
            title=dict(text=chart_title, font=dict(size=20, color=colors['font_color']), x=0.03, xanchor='left'),
            margin=dict(l=60, r=20, t=60, b=50),
            xaxis=dict(title=dict(text='日期', font=dict(color=colors['font_color'])), showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=10, color=colors['font_color']), tickangle=45),
            yaxis=dict(title=dict(text='价格 (元)', font=dict(color=colors['font_color'])), showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])),
            legend=dict(font=dict(size=13, color=colors['font_color']), bgcolor=colors['legend_bg'], bordercolor=colors['legend_border'], borderwidth=1, yanchor='top', y=0.95, xanchor='right', x=0.98)
        )
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})


def show_dashboard():
    theme = st.session_state.get('theme', 'dark')
    colors = get_theme_colors('深色主题' if theme == 'dark' else theme)
    st.markdown("<div class='dashboard-title'>🚀 股票量化数据大屏</div>", unsafe_allow_html=True)
    manifest = get_manifest()
    asset_summary = get_asset_summary()
    df_latest = get_market_snapshot(manifest.get('end_date'), limit=2000)
    if not manifest or not asset_summary or df_latest.empty:
        st.markdown("<div style='padding:8px 12px;border-radius:8px;background:rgba(241,196,15,0.1);color:#f39c12;font-size:14px;'>⚠️ 请先加载数据</div>", unsafe_allow_html=True)
        return
    source_label = manifest.get('source_label', 'SQLite 服务层')
    st.markdown(
        f"<p style='text-align:center;color:{colors['secondary_text']};font-size:14px;margin-top:-20px;'>"
        f"数据来源：{source_label}｜批处理快照，非实时行情</p>",
        unsafe_allow_html=True,
    )
    latest_date = pd.Timestamp(manifest['end_date'])
    stock_count = asset_summary['detail_stock_count']
    total_records = asset_summary['record_count']
    start_date = str(manifest['start_date'])
    end_date = str(manifest['end_date'])
    avg_close = df_latest['close'].mean() if len(df_latest) > 0 else 0
    avg_volume = df_latest['volume'].mean() if len(df_latest) > 0 else 0
    up_count = 0
    down_count = 0
    if len(df_latest) > 0 and 'open' in df_latest.columns:
        up_count = (df_latest['close'] > df_latest['open']).sum()
        down_count = (df_latest['close'] <= df_latest['open']).sum()
    # 五张指标卡：中间最小，向两边依次放大（对称阶梯布局）
    stair = [
        # (value字号, 卡片内边距)
        ('46px', '34px 20px'),   # 卡1 股票总数（最大）
        ('38px', '28px 20px'),   # 卡2 数据记录数
        ('28px', '22px 20px'),   # 卡3 起始日期（中间最小）
        ('38px', '28px 20px'),   # 卡4 上涨家数
        ('46px', '34px 20px'),   # 卡5 下跌家数（最大）
    ]
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        fs, pad = stair[0]
        st.markdown(f"""
            <div class='dashboard-metric' style='padding: {pad};'>
                <div class='dashboard-metric-value' style='font-size: {fs};'>{stock_count}</div>
                <div class='dashboard-metric-label'>📈 股票总数</div>
            </div>
        """, unsafe_allow_html=True)
    with col2:
        fs, pad = stair[1]
        st.markdown(f"""
            <div class='dashboard-metric' style='padding: {pad};'>
                <div class='dashboard-metric-value' style='font-size: {fs};'>{total_records:,}</div>
                <div class='dashboard-metric-label'>💾 数据记录数</div>
            </div>
        """, unsafe_allow_html=True)
    with col3:
        fs, pad = stair[2]
        st.markdown(f"""
            <div class='dashboard-metric' style='padding: {pad};'>
                <div class='dashboard-metric-value' style='font-size: {fs};'>{start_date}</div>
                <div class='dashboard-metric-label'>📅 起始日期</div>
            </div>
        """, unsafe_allow_html=True)
    with col4:
        fs, pad = stair[3]
        st.markdown(f"""
            <div class='dashboard-metric' style='padding: {pad};'>
                <div class='dashboard-metric-value' style='color: #40FF80; font-size: {fs};'>{up_count}</div>
                <div class='dashboard-metric-label'>🟢 上涨家数</div>
            </div>
        """, unsafe_allow_html=True)
    with col5:
        fs, pad = stair[4]
        st.markdown(f"""
            <div class='dashboard-metric' style='padding: {pad};'>
                <div class='dashboard-metric-value' style='color: #FF6B6B; font-size: {fs};'>{down_count}</div>
                <div class='dashboard-metric-label'>🔴 下跌家数</div>
            </div>
        """, unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>📋 最新交易日股票行情</div>", unsafe_allow_html=True)
    if len(df_latest) > 0:
        display_cols = ['code', 'open', 'high', 'low', 'close', 'volume']
        available_cols = [c for c in display_cols if c in df_latest.columns]
        df_display = df_latest[available_cols].copy()
        df_display['涨跌幅'] = ((df_display['close'] - df_display['open']) / df_display['open'] * 100).round(2)
        df_display['板块'] = df_latest['board'].values
        if 'volume' in df_display.columns:
            df_display['成交量(万手)'] = (df_display['volume'] / 10000).round(2)
            df_display = df_display.drop(columns=['volume'])
        df_display = df_display.sort_values('涨跌幅', ascending=False)
        df_display = df_display.rename(columns={
            'code': '股票代码', 'open': '开盘价', 'high': '最高价',
            'low': '最低价', 'close': '收盘价'
        })
        col_filter1, col_filter2 = st.columns(2)
        with col_filter1:
            board_options = ['全部'] + df_display['板块'].unique().tolist()
            selected_board = st.selectbox("筛选板块", board_options, key='dash_board_filter')
        with col_filter2:
            sort_col = st.selectbox("排序依据", ['涨跌幅', '收盘价', '成交量(万手)'], key='dash_sort')
        if selected_board != '全部':
            df_display = df_display[df_display['板块'] == selected_board]
        df_display = df_display.sort_values(sort_col, ascending=False)
        st.dataframe(df_display, width='stretch', height=400)
        date_str = latest_date.strftime("%Y-%m-%d")
        st.markdown(f"<p style='text-align: right; color: {colors['secondary_text']}; font-size: 12px;'>数据日期: {date_str} | 共 {len(df_display)} 只股票</p>", unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>🏆 涨幅榜 & 跌幅榜</div>", unsafe_allow_html=True)
    if len(df_latest) > 0 and 'open' in df_latest.columns:
        df_latest_copy = df_latest.copy()
        df_latest_copy['pct_change'] = (df_latest_copy['close'] - df_latest_copy['open']) / df_latest_copy['open'] * 100
        col_top, col_bottom = st.columns(2)
        with col_top:
            with st_card():
                top_gainers = df_latest_copy.nlargest(10, 'pct_change')
                fig_gain = go.Figure(go.Bar(
                    x=top_gainers['pct_change'].round(2),
                    y=top_gainers['code'],
                    orientation='h',
                    marker=dict(color=top_gainers['pct_change'], colorscale='Greens', opacity=0.85),
                    text=top_gainers['pct_change'].round(2).astype(str) + '%',
                    textposition='outside',
                    textfont=dict(color=colors['font_color'], size=12)
                ))
                fig_gain.update_layout(
                    height=350, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'],
                    font=dict(color=colors['font_color']),
                    title=dict(text='🟢 涨幅 TOP10', font=dict(size=20, color=colors['font_color']), x=0.03, xanchor='left'),
                    margin=dict(l=60, r=40, t=50, b=20),
                    xaxis=dict(title=dict(text='涨跌幅(%)', font=dict(color=colors['font_color'])), tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color']),
                    yaxis=dict(tickfont=dict(size=12, color=colors['font_color']), showgrid=False)
                )
                st.plotly_chart(fig_gain, width='stretch', config={'displayModeBar': False})
        with col_bottom:
            with st_card():
                top_losers = df_latest_copy.nsmallest(10, 'pct_change')
                fig_loss = go.Figure(go.Bar(
                    x=top_losers['pct_change'].round(2),
                    y=top_losers['code'],
                    orientation='h',
                    marker=dict(color=top_losers['pct_change'], colorscale='Reds_r', opacity=0.85),
                    text=top_losers['pct_change'].round(2).astype(str) + '%',
                    textposition='outside',
                    textfont=dict(color=colors['font_color'], size=12)
                ))
                fig_loss.update_layout(
                    height=350, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'],
                    font=dict(color=colors['font_color']),
                    title=dict(text='🔴 跌幅 TOP10', font=dict(size=20, color=colors['font_color']), x=0.03, xanchor='left'),
                    margin=dict(l=60, r=40, t=50, b=20),
                    xaxis=dict(title=dict(text='涨跌幅(%)', font=dict(color=colors['font_color'])), tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color']),
                    yaxis=dict(tickfont=dict(size=12, color=colors['font_color']), showgrid=False)
                )
                st.plotly_chart(fig_loss, width='stretch', config={'displayModeBar': False})
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>📊 板块成交额分布</div>", unsafe_allow_html=True)
    if len(df_latest) > 0:
        with st_card():
            board_amount = (
                df_latest.groupby('board', as_index=False)['amount'].sum()
                .rename(columns={'board': '板块'})
                .sort_values('amount', ascending=False)
            )
            if board_amount is not None and len(board_amount) > 0:
                amount_col = 'amount'
                total_amount = board_amount[amount_col].sum()
                board_amount['百分比'] = (board_amount[amount_col] / total_amount * 100).round(1)
                custom_text = []
                for _, row in board_amount.iterrows():
                    val = row[amount_col]
                    if val >= 1e8:
                        val_str = f'{val/1e8:,.2f}亿'
                    elif val >= 1e4:
                        val_str = f'{val/1e4:,.2f}万'
                    else:
                        val_str = f'{val:,.2f}'
                    custom_text.append(f"{row['板块']}<br>{val_str}<br>{row['百分比']}%")
                pie_colors = ['#6C63FF', '#2E86AB', '#E74C3C', '#F39C12', '#1ABC9C']
                fig_board = go.Figure(go.Pie(
                    labels=board_amount['板块'].tolist(),
                    values=board_amount[amount_col].values,
                    marker=dict(colors=pie_colors, line=dict(color=colors['grid_color'], width=2)),
                    text=custom_text,
                    textinfo='text',
                    textfont=dict(color=colors['font_color'], size=14),
                    hovertemplate='%{label}<br>成交额: %{value:,.2f}<br>占比: %{percent}<extra></extra>',
                    hole=0.45,
                    pull=[0.03] * len(board_amount)
                ))
            else:
                df_latest_board = df_latest.copy()
                df_latest_board['板块'] = df_latest_board['code'].apply(classify_board)
                if 'amount' in df_latest_board.columns:
                    board_amount = df_latest_board.groupby('板块')['amount'].sum().reset_index()
                    amount_col = 'amount'
                else:
                    board_amount = df_latest_board.groupby('板块')['volume'].sum().reset_index()
                    amount_col = 'volume'
                board_amount = board_amount.sort_values(amount_col, ascending=False)
                pie_colors = ['#6C63FF', '#2E86AB', '#E74C3C', '#F39C12', '#1ABC9C']
                fig_board = go.Figure(go.Pie(
                    labels=board_amount['板块'].tolist(),
                    values=board_amount[amount_col].values,
                    marker=dict(colors=pie_colors, line=dict(color=colors['grid_color'], width=2)),
                    textinfo='label+percent+value',
                    textfont=dict(color=colors['font_color'], size=14),
                    hole=0.45,
                    pull=[0.03] * len(board_amount)
                ))
            fig_board.update_layout(
                height=380, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'],
                font=dict(color=colors['font_color']),
                title=dict(text='🏛️ 板块成交额分布（最新交易日）', font=dict(size=20, color=colors['font_color']), x=0.03, xanchor='left'),
                margin=dict(l=40, r=20, t=60, b=20),
                legend=dict(font=dict(size=14, color=colors['font_color']), bgcolor=colors['legend_bg'], bordercolor=colors['legend_border'], borderwidth=1)
            )
            st.plotly_chart(fig_board, width='stretch', config={'displayModeBar': False})
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>💹 收盘价分布 & 成交量分布</div>", unsafe_allow_html=True)
    if len(df_latest) > 0:
        col_dist1, col_dist2 = st.columns(2)
        with col_dist1:
            with st_card():
                fig_hist = go.Figure(go.Histogram(
                    x=df_latest['close'],
                    nbinsx=30,
                    marker=dict(color=colors['accent'], opacity=0.75, line=dict(color='rgba(255,255,255,0.1)', width=1)),
                    hovertemplate='价格区间: %{x}<br>数量: %{y}<extra></extra>'
                ))
                fig_hist.update_layout(
                    height=320, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'],
                    font=dict(color=colors['font_color']),
                    title=dict(text='💹 收盘价分布', font=dict(size=18, color=colors['font_color']), x=0.03, xanchor='left'),
                    margin=dict(l=40, r=20, t=50, b=20),
                    xaxis=dict(title=dict(text='收盘价 (元)', font=dict(color=colors['font_color'])), tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color']),
                    yaxis=dict(title=dict(text='股票数量', font=dict(color=colors['font_color'])), tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color'])
                )
                st.plotly_chart(fig_hist, width='stretch', config={'displayModeBar': False})
        with col_dist2:
            with st_card():
                fig_vol_hist = go.Figure(go.Histogram(
                    x=df_latest['volume'],
                    nbinsx=30,
                    marker=dict(color='#2E86AB', opacity=0.75, line=dict(color='rgba(255,255,255,0.1)', width=1)),
                    hovertemplate='成交量区间: %{x}<br>数量: %{y}<extra></extra>'
                ))
                fig_vol_hist.update_layout(
                    height=320, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'],
                    font=dict(color=colors['font_color']),
                    title=dict(text='📊 成交量分布', font=dict(size=18, color=colors['font_color']), x=0.03, xanchor='left'),
                    margin=dict(l=40, r=20, t=50, b=20),
                    xaxis=dict(title=dict(text='成交量', font=dict(color=colors['font_color'])), tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color']),
                    yaxis=dict(title=dict(text='股票数量', font=dict(color=colors['font_color'])), tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color'])
                )
                st.plotly_chart(fig_vol_hist, width='stretch', config={'displayModeBar': False})
    st.markdown(f"""
        <div style='text-align: center; padding: 20px; color: {colors['secondary_text']}; font-size: 13px;'>
            数据来源: {source_label} | 数据水位: {end_date} | 仅供研究，不构成投资建议
        </div>
    """, unsafe_allow_html=True)


@st.cache_data(ttl=600)
def _load_backtest_results():
    """读取 backtest.py 输出的真实回测结果（T+1 成交口径）"""
    if PORTFOLIO_MODE:
        metrics_path = str(PORTFOLIO_BACKTEST_METRICS_PATH)
        daily_path = str(PORTFOLIO_BACKTEST_RESULTS_PATH)
        hold_path = str(PORTFOLIO_DAILY_PORTFOLIOS_PATH)
    else:
        metrics_path = _P('backtest_results', 'backtest_metrics.csv')
        daily_path = _P('backtest_results', 'backtest_results.csv')
        hold_path = _P('backtest_results', 'daily_portfolios.csv')
    df_m = pd.read_csv(metrics_path) if os.path.exists(metrics_path) else None
    df_r = pd.read_csv(daily_path, parse_dates=['date']) if os.path.exists(daily_path) else None
    df_h = pd.read_csv(hold_path, parse_dates=['date']) if os.path.exists(hold_path) else None
    return df_m, df_r, df_h


def show_backtest():
    st.markdown("<div class='main-title'>📊 策略回测</div>", unsafe_allow_html=True)
    theme = st.session_state.get('theme', 'dark')
    colors = get_theme_colors('深色主题' if theme == 'dark' else theme)

    # ===== 直接读取 backtest.py 生成的真实回测结果 =====
    df_metrics, df_bt, df_hold = _load_backtest_results()
    if df_metrics is None or df_bt is None or df_bt.empty:
        st.markdown("<div style='padding:12px 16px;border-radius:8px;background:rgba(241,196,15,0.12);color:#f39c12;font-size:15px;'>"
                    "⚠️ 未找到真实回测结果文件（backtest_results/backtest_metrics.csv）。<br>"
                    "请先在项目目录运行 <code>python backtest.py</code> 生成回测结果，完成后刷新本页。</div>", unsafe_allow_html=True)
        return
    corrected_fields = {
        'average_turnover', 'commission_rate', 'stamp_duty_rate',
        'benchmark_name', 'benchmark_source',
    }
    if corrected_fields - set(df_metrics.columns):
        st.warning(
            "检测到旧版回测产物：未记录交易成本、换手率或基准来源，"
            "因此不展示为可信结果。请重新运行 `python backtest.py`。"
        )
        return
    m = df_metrics.iloc[0]
    df_bt = df_bt.sort_values('date').reset_index(drop=True)
    dates = df_bt['date']
    equity = df_bt['equity_curve']
    strat_cum = df_bt['cumulative_return'] - 1
    bench_cum = df_bt['benchmark_cumulative'] - 1
    drawdown_arr = equity / equity.cummax() - 1

    win_rate = float(m['win_rate'])
    annual_return = float(m['annualized_return'])
    sharpe = float(m['sharpe_ratio'])
    max_dd = float(m['max_drawdown'])
    total_return = float(m['total_return'])
    excess_return = float(m['excess_return'])
    ann_vol = float(m['annualized_volatility'])
    bench_total = float(m['benchmark_total_return'])
    init_capital = float(m['initial_capital'])
    n_per_day = int(m['n_stocks_per_day'])
    benchmark_name = str(m.get('benchmark_name', '股票池等权基准'))
    average_turnover = float(m.get('average_turnover', 0))
    has_cost_model = 'commission_rate' in df_metrics.columns
    commission_rate = float(m.get('commission_rate', 0))
    stamp_duty_rate = float(m.get('stamp_duty_rate', 0))
    start_d = dates.iloc[0].strftime('%Y-%m-%d')
    end_d = dates.iloc[-1].strftime('%Y-%m-%d')

    st.markdown(f"""
        <div class="custom-info-box">
            <p style="margin: 0;">⚙️ 回测配置（真实回测结果，由 <code>backtest.py</code> 按滚动窗口 Walk-Forward 生成）：</p>
            <p style="margin: 5px 0 0 20px;">- 回测区间：<b>{start_d} ~ {end_d}</b> ｜ 初始资金：<b>{init_capital:,.0f}</b> ｜ 每日持股：<b>{n_per_day} 只</b> ｜ 平均换手：<b>{average_turnover:.1%}</b></p>
        </div>
    """, unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    holdings_title = '研究产物说明' if PORTFOLIO_MODE else '每日持仓明细'
    st.markdown(f"<div class='section-title'>📋 {holdings_title}</div>", unsafe_allow_html=True)
    if PORTFOLIO_MODE:
        st.info(
            "公开版展示脱敏回测指标和归一化净值曲线；"
            "逐日持仓明细仅作为本地研究流水线产物，不随网站发布。"
        )
    elif df_hold is not None and not df_hold.empty:
        bt_dates = sorted(df_bt['date'].dt.date.unique())
        min_bt_date, max_bt_date = bt_dates[0], bt_dates[-1]
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            bt_start = st.date_input("起始日期", value=min_bt_date, min_value=min_bt_date, max_value=max_bt_date, key='bt_hold_start')
        with filter_col2:
            bt_end = st.date_input("结束日期", value=max_bt_date, min_value=min_bt_date, max_value=max_bt_date, key='bt_hold_end')
        df_hold_f = df_hold[(df_hold['date'].dt.date >= bt_start) & (df_hold['date'].dt.date <= bt_end)].copy()
        if not df_hold_f.empty:
            df_hold_f = df_hold_f.sort_values(['date', 'code'])
            df_show = pd.DataFrame({
                '日期': df_hold_f['date'].dt.strftime('%Y-%m-%d'),
                '股票代码': df_hold_f['code'].apply(lambda x: str(int(x)).zfill(6)),
                '预测收益': df_hold_f['predicted'].round(4),
                '实际收益': df_hold_f['actual'].round(4),
            })
            st.dataframe(df_show, width='stretch', height=380)
            csv_data = df_show.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 下载持仓明细 CSV",
                data=csv_data,
                file_name=f'每日持仓明细_{bt_start}_{bt_end}.csv',
                mime='text/csv',
                key='download_holdings_csv'
            )
        else:
            st.info("该日期范围内无持仓记录")
    else:
        st.info("未找到每日持仓文件（backtest_results/daily_portfolios.csv）")
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>🎯 回测指标</div>", unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"<div class='metric-card'><div class='metric-value'>{win_rate:.1%}</div><div class='metric-label'>胜率</div></div>", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<div class='metric-card'><div class='metric-value'>{annual_return:.1%}</div><div class='metric-label'>年化收益率</div></div>", unsafe_allow_html=True)
    with col3:
        st.markdown(f"<div class='metric-card'><div class='metric-value'>{sharpe:.2f}</div><div class='metric-label'>夏普比率</div></div>", unsafe_allow_html=True)
    with col4:
        st.markdown(f"<div class='metric-card'><div class='metric-value' style='color:#e74c3c; -webkit-text-fill-color:#e74c3c;'>{max_dd:.1%}</div><div class='metric-label'>最大回撤</div></div>", unsafe_allow_html=True)
    # 第二行：宽幅"策略 vs 基准"收益对比条 + 窄幅波动率卡，主次分明不呆板
    col_a, col_b = st.columns([2.6, 1])
    with col_a:
        max_val = max(abs(total_return), abs(bench_total)) or 1
        w_strat = abs(total_return) / max_val * 100
        w_bench = abs(bench_total) / max_val * 100
        excess_color = '#e74c3c' if excess_return < 0 else '#27ae60'
        txt = colors.get('secondary_text', '#7a8ba6')
        track = colors.get('grid_color', '#e9eef5')
        st.markdown(f"""
            <div class='metric-card' style='padding: 20px 26px;'>
                <div style='display:flex; justify-content:space-between; align-items:baseline; margin-bottom:16px;'>
                    <span style='font-size:14px; color:{txt}; font-weight:600;'>📊 累计收益对比（{start_d[:4]}–{end_d[:4]}）</span>
                    <span style='font-size:14px; color:{excess_color}; font-weight:700;'>超额收益 {excess_return:+.1%}</span>
                </div>
                <div style='margin-bottom:14px;'>
                    <div style='display:flex; justify-content:space-between; font-size:14px; color:{txt}; margin-bottom:5px;'>
                        <span>🚀 策略</span><b style='color:#40A0FF;'>{total_return:+.1%}</b>
                    </div>
                    <div style='background:{track}; border-radius:6px; height:16px;'>
                        <div style='width:{w_strat:.0f}%; height:100%; border-radius:6px; background:linear-gradient(90deg,#2E86AB,#40A0FF);'></div>
                    </div>
                </div>
                <div>
                    <div style='display:flex; justify-content:space-between; font-size:14px; color:{txt}; margin-bottom:5px;'>
                        <span>📉 {benchmark_name}</span><b style='color:#e67e22;'>{bench_total:+.1%}</b>
                    </div>
                    <div style='background:{track}; border-radius:6px; height:16px;'>
                        <div style='width:{w_bench:.0f}%; height:100%; border-radius:6px; background:linear-gradient(90deg,#e67e22,#f5b041);'></div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    with col_b:
        st.markdown(f"<div class='metric-card'><div class='metric-value'>{ann_vol:.1%}</div><div class='metric-label'>年化波动率</div></div>", unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    with st_card():
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=strat_cum, name='策略净值', line=dict(color=colors['accent'], width=2.5), mode='lines'))
        fig.add_trace(go.Scatter(x=dates, y=bench_cum, name=benchmark_name, line=dict(color=colors['success'], width=2, dash='dot'), showlegend=True))
        fig.update_layout(height=300, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='📈 策略净值曲线', font=dict(size=20, color=colors['font_color']), x=0.03, xanchor='left'), showlegend=True, legend=dict(font=dict(size=14, color=colors['font_color']), bgcolor=colors['legend_bg'], bordercolor=colors['legend_border'], borderwidth=1, yanchor='top', y=0.9, xanchor='right', x=0.98), margin=dict(l=40, r=50, t=50, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color']), tickformat='%Y'), yaxis=dict(title=dict(text='累计收益率', font=dict(color=colors['font_color'])), tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color'], tickformat='.0%'))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': True})
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    with st_card():
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=dates, y=drawdown_arr, name='回撤', line=dict(color=colors['accent'], width=2), mode='lines', fill='tonexty', fillcolor='rgba(255,102,64,0.2)'))
        fig_dd.add_hline(y=0, line_dash='dash', line_color='rgba(128,128,128,0.5)')
        fig_dd.update_layout(height=260, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='📉 动态回撤曲线', font=dict(size=18, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=40, r=20, t=50, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])), yaxis=dict(tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color'], tickformat='.0%'))
        st.plotly_chart(fig_dd, width='stretch', config={'displayModeBar': True})
    cost_description = (
        f"佣金单边 {commission_rate:.2%}、卖出印花税 {stamp_duty_rate:.2%}"
        if has_cost_model else "旧结果未计入交易成本，请重新运行 backtest.py"
    )
    st.markdown(f"""
        <div class="custom-info-box">
            <p style="margin: 0;">💡 回测说明（真实口径）：</p>
            <p style="margin: 5px 0 0 20px;">- 策略：基于多因子综合评分（动量、RSI、MACD、波动率等）排序，每日买入评分最高的前 N 只股票</p>
            <p style="margin: 5px 0 0 20px;">- 成交口径：T 日收盘后生成信号，T+1 日收盘价成交（T+1 规则，避免未来函数）</p>
            <p style="margin: 5px 0 0 20px;">- 模型：XGBoost 滚动窗口 Walk-Forward 训练，仅用历史窗口数据，杜绝数据泄露</p>
            <p style="margin: 5px 0 0 20px;">- 交易成本：{cost_description}；基准：{benchmark_name}</p>
        </div>
    """, unsafe_allow_html=True)


def show_data_platform():
    """面向数据开发岗位的数据资产、质量和血缘监控首页。"""
    st.markdown("<div class='main-title'>数据资产驾驶舱</div>", unsafe_allow_html=True)
    st.caption("A 股量化数据工程平台 · 资产目录、研究覆盖、在线分析与质量状态")
    manifest = get_manifest()
    asset_summary = get_asset_summary()
    quality_runs = get_quality_runs(limit=1)
    quality_issues = get_quality_issues()
    if not manifest or not asset_summary or quality_runs.empty:
        st.warning(
            "尚未发现可用服务库。运行 `python scripts/build_demo_serving_db.py` 可重建公开 SQLite 服务层。"
        )
        return
    quality_row = quality_runs.iloc[0]
    structural_factor_count = int(
        quality_issues.loc[
            quality_issues['category'] == 'structural_factor', 'issue_count'
        ].sum()
    ) if not quality_issues.empty else 0
    structural_label_count = int(
        quality_issues.loc[
            quality_issues['category'] == 'structural_label', 'issue_count'
        ].sum()
    ) if not quality_issues.empty else 0
    issue_counts = (
        quality_issues.groupby('rule_name')['issue_count'].sum().to_dict()
        if not quality_issues.empty else {}
    )
    unexpected_missing_count = int(quality_row['unexpected_missing_count'])
    missing_cell_count = structural_factor_count + structural_label_count + unexpected_missing_count
    missing_details = {
        str(row['column_name']): {
            'count': int(row['issue_count']),
            'rate': int(row['issue_count']) / max(int(quality_row['row_count']), 1),
            'category': row['category'],
            'reason': row['message'],
        }
        for _, row in quality_issues[quality_issues['rule_name'] == 'missing_value'].iterrows()
    }
    report = {
        'row_count': int(asset_summary['record_count']),
        'stock_count': int(asset_summary['detail_stock_count']),
        'column_count': int(asset_summary['column_count']),
        'start_date': str(manifest['start_date']),
        'end_date': str(manifest['end_date']),
        'duplicate_key_count': int(quality_row['duplicate_key_count']),
        'invalid_date_count': int(quality_row['invalid_date_count']),
        'invalid_ohlc_count': int(quality_row['invalid_ohlc_count']),
        'raw_missing_cell_count': 0,
        'structural_factor_missing_count': structural_factor_count,
        'structural_label_missing_count': structural_label_count,
        'unexpected_missing_cell_count': unexpected_missing_count,
        'missing_details': missing_details,
        'quality_status': str(quality_row['status']),
        'sentiment_source_distribution': {'synthetic_demo': int(asset_summary['record_count'])},
        'nonpositive_price_count': int(issue_counts.get('nonpositive_price', 0)),
        'negative_volume_count': int(issue_counts.get('negative_volume', 0)),
        'zero_volume_count': int(issue_counts.get('zero_volume', 0)),
        'extreme_return_count': int(issue_counts.get('extreme_return', 0)),
    }
    aggregate_end_date = manifest.get('aggregate_end_date', manifest['end_date'])
    latest_date = pd.to_datetime(aggregate_end_date)
    freshness_days = max((pd.Timestamp.now().normalize() - latest_date).days, 0)
    source_label = manifest.get('source_label', 'SQLite 服务层')
    research_scale = manifest.get('research_scale') or {}
    research_stock_count = int(research_scale.get('stock_count', 0) or 0)
    research_record_count = int(research_scale.get('record_count', 0) or 0)
    catalog_stock_count = int(
        manifest.get('asset_catalog_stock_count', asset_summary['catalog_stock_count'])
    )
    public_stock_count = int(
        manifest.get('public_detail_stock_count', asset_summary['detail_stock_count'])
    )
    public_record_count = int(
        manifest.get('public_detail_record_count', asset_summary['record_count'])
    )
    aggregate_trading_days = int(
        manifest.get('aggregate_trading_day_count', asset_summary['trading_day_count'])
    )
    finished_at = pd.to_datetime(manifest.get('finished_at'), errors='coerce')
    updated_text = (
        finished_at.strftime('%Y-%m-%d %H:%M UTC')
        if pd.notna(finished_at) else '未记录'
    )
    quality_score = float(asset_summary.get('quality_score', 0) or 0)
    if freshness_days > 7:
        st.warning(
            f"当前聚合数据水位为 {aggregate_end_date}，距今天 {freshness_days} 天；"
            "页面展示的是历史快照，不是实时行情。"
        )

    st.info(
        "三种口径严格分离：资产目录与在线行情为确定性合成数据；"
        "研究覆盖数字来自本地真实数据质量报告；公开网页不分发真实逐日行情。"
    )
    metric_values = [
        (f"{catalog_stock_count:,}", "资产目录", "完整规模目录"),
        (f"{research_stock_count:,}", "本地研究覆盖", f"{research_record_count:,} 条真实研究记录"),
        (f"{public_stock_count:,}", "在线分析资产", "分层代表样本"),
        (f"{public_record_count:,}", "在线明细记录", "SQLite 按需查询"),
        (f"{aggregate_trading_days:,}", "聚合交易日", f"水位 {aggregate_end_date}"),
        (f"{quality_score:.1f}", "数据质量评分", f"状态 {report['quality_status']}"),
    ]
    for row_start in (0, 3):
        columns = st.columns(3)
        for column, (value, label, description) in zip(
            columns, metric_values[row_start:row_start + 3]
        ):
            with column:
                st.markdown(
                    "<div class='metric-card'>"
                    f"<div class='metric-value'>{value}</div>"
                    f"<div class='metric-label'>{label}</div>"
                    f"<div style='font-size:12px;color:#8FA1B7;margin-top:6px;'>{description}</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )

    st.caption(
        f"服务库发布：{updated_text} ｜ 数据版本：{manifest.get('data_version', 'N/A')} ｜ "
        f"查询模式：只读 SQLite + 参数化 SQL + st.cache_data"
    )

    st.markdown("<div class='section-title'>数据血缘与服务链路</div>", unsafe_allow_html=True)
    lineage_stages = [
        ("SOURCE", "本地真实研究 / 公开合成源"),
        ("RAW · CLEAN", "贴源留存、标准化与质量规则"),
        ("FACTOR", "技术因子、标签与研究产物"),
        ("AGGREGATE", "市场、行业、因子 IC 预聚合"),
        ("SERVING", "SQLite 索引与只读查询"),
        ("PRODUCT", "Streamlit 数据产品"),
    ]
    stage_columns = st.columns(len(lineage_stages))
    for index, (stage, description) in enumerate(lineage_stages):
        with stage_columns[index]:
            st.markdown(
                "<div class='metric-card' style='text-align:center;min-height:142px;padding:16px 10px;'>"
                "<div style='font-size:11px;color:#33C58E;font-weight:700;'>READY</div>"
                f"<div style='font-size:15px;font-weight:800;margin:8px 0;'>{stage}</div>"
                f"<div style='font-size:11px;color:#8FA1B7;line-height:1.5;'>{description}</div>"
                "</div>"
                + ("<div style='text-align:center;color:#2E86AB;font-size:22px;'>→</div>" if index < len(lineage_stages) - 1 else ""),
                unsafe_allow_html=True,
            )

    st.markdown("<div class='section-title'>数据质量概览</div>", unsafe_allow_html=True)
    left, right = st.columns([1.5, 1])
    with left:
        quality_frame = pd.DataFrame({
            '检查项': [
                '重复主键', '无效日期', 'OHLC 异常', '原始字段缺失',
                '因子窗口缺失', '标签末期缺失', '未预期缺失',
            ],
            '异常数': [
                report['duplicate_key_count'],
                report['invalid_date_count'],
                report['invalid_ohlc_count'],
                report.get('raw_missing_cell_count', 0),
                report.get('structural_factor_missing_count', 0),
                report.get('structural_label_missing_count', 0),
                report.get('unexpected_missing_cell_count', missing_cell_count),
            ],
            '状态': ['失败', '失败', '失败', '失败', '预期', '预期', '失败'],
        })
        quality_frame.loc[
            (quality_frame['异常数'] == 0) & (quality_frame['状态'] == '失败'), '状态'
        ] = '通过'
        fig_quality = px.bar(
            quality_frame,
            x='检查项',
            y='异常数',
            color='状态',
            color_discrete_map={'通过': '#33C58E', '预期': '#E8A84B', '失败': '#F05A67'},
        )
        colors = get_theme_colors('浅色主题' if st.session_state.get('theme') == 'light' else '深色主题')
        fig_quality.update_layout(
            height=300,
            showlegend=False,
            plot_bgcolor=colors['plot_bg'],
            paper_bgcolor=colors['paper_bg'],
            font=dict(color=colors['font_color']),
            margin=dict(l=30, r=20, t=20, b=30),
            yaxis=dict(gridcolor=colors['grid_color']),
        )
        st.plotly_chart(fig_quality, width='stretch', config={'displayModeBar': False})
        missing_details = report.get('missing_details', {})
        if missing_details:
            category_labels = {
                'structural_factor': '结构性因子缺失',
                'structural_label': '结构性标签缺失',
                'unexpected': '未预期缺失',
            }
            detail_frame = pd.DataFrame([
                {
                    '字段': column,
                    '缺失数量': detail['count'],
                    '缺失率': f"{detail['rate']:.2%}",
                    '分类': category_labels.get(detail['category'], detail['category']),
                    '原因与处理': detail['reason'],
                }
                for column, detail in missing_details.items()
            ])
            with st.expander("查看缺失字段明细", expanded=False):
                st.dataframe(detail_frame, width='stretch', hide_index=True)
    with right:
        source_distribution = report.get('sentiment_source_distribution', {})
        st.markdown("#### 数据口径")
        st.write(f"当前读取：{source_label}")
        st.write(f"覆盖区间：{report['start_date']} → {report['end_date']}")
        st.write(f"字段数量：{report['column_count']}")
        st.write(f"情绪来源：{source_distribution or {'not_available': report['row_count']}}")
        storage_label = "SQLite Serving Layer + 参数化按需查询"
        st.write(f"存储策略：{storage_label}")
        status = report.get('quality_status', 'N/A')
        st.write(f"质量结论：{status}（结构性缺失记为提示，不记为原始数据失败）")
        st.write(
            "扩展检查："
            f"非正价格 {report.get('nonpositive_price_count', 0)}、"
            f"负成交量 {report.get('negative_volume_count', 0)}、"
            f"零成交量 {report.get('zero_volume_count', 0)}、"
            f"单日绝对收益超过 30% {report.get('extreme_return_count', 0)}"
        )
        if PORTFOLIO_MODE:
            st.caption("公开交互行情为确定性合成演示数据；真实数据仅用于本地研究，不构成投资建议。")
        if 'legacy_unknown' in source_distribution:
            st.caption("情绪字段来自历史产物，来源尚未核验，不作为真实新闻情绪结论。")


def main():
    require_login = (
        os.environ.get('QUANT_REQUIRE_LOGIN', '0') == '1'
        and not PORTFOLIO_MODE
    )
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'username' not in st.session_state:
        st.session_state.username = ''
    st.session_state.theme = 'light'
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = []
    if 'top_n' not in st.session_state:
        st.session_state.top_n = 20

    if require_login and not st.session_state.logged_in:
        show_login_page()
        return
    if not require_login and not st.session_state.username:
        st.session_state.username = '访客' if PORTFOLIO_MODE else 'demo'

    apply_theme()

    try:
        serving_manifest = get_manifest()
        stock_catalog = get_stock_catalog(has_detail=True)
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        st.error(f"SQLite 服务层不可用：{exc}")
        st.info("请在项目目录运行 `python scripts/build_demo_serving_db.py` 后重试。")
        return
    if not serving_manifest or stock_catalog.empty:
        st.error("SQLite 服务层没有可展示的数据。")
        return

    st.sidebar.title("Quant Data Platform")
    st.sidebar.caption("量化数据开发与研究工作台")
    if PORTFOLIO_MODE:
        st.sidebar.info("公开作品集模式 · 合成演示行情 · 只读访问")
    st.sidebar.markdown(f"用户：**{st.session_state.username}**")
    if require_login and st.sidebar.button("退出登录", width='stretch', key='logout_btn'):
        st.session_state.logged_in = False
        st.session_state.username = ''
        st.rerun()
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📱 页面导航")
    pages = [('数据平台', 'platform'), ('市场总览', 'dashboard'), ('股票画像', 'stock_profile'), ('行业分析', 'industry'), ('系统概览', 'overview'), ('数据洞察', 'data_insight'), ('因子研究', 'factor'), ('情绪分析', 'sentiment'), ('模型预测', 'prediction'), ('策略回测', 'backtest')]
    page_labels = [p[0] for p in pages]
    page = st.sidebar.radio("页面导航", page_labels, index=0, label_visibility='collapsed', key='main_page')
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⭐ 自选股管理")
    if not stock_catalog.empty:
        all_codes = stock_catalog['code'].tolist()
        current_watchlist = st.session_state.get('watchlist', [])
        valid_watchlist = [c for c in current_watchlist if c in all_codes]
        selected_watchlist = st.sidebar.multiselect("选择自选股", all_codes, default=valid_watchlist, key='watchlist_select')
        save_label = "保存到当前会话" if PORTFOLIO_MODE else "💾 保存自选股"
        if st.sidebar.button(save_label, key='save_watchlist_btn'):
            st.session_state.watchlist = selected_watchlist
            if st.session_state.username and not PORTFOLIO_MODE:
                db_update_user(st.session_state.username, watchlist=json.dumps(selected_watchlist, ensure_ascii=False))
            st.session_state.watchlist_saved = True
            st.rerun()
        if st.session_state.get('watchlist_saved', False):
            st.sidebar.success("自选股已保存！")
            st.session_state.watchlist_saved = False
        saved_wl = st.session_state.get('watchlist', [])
        if saved_wl:
            st.sidebar.markdown("#### 📋 自选股行情")
            df_latest = get_latest_quotes(saved_wl)
            for code in saved_wl:
                row = df_latest[df_latest['code'] == code]
                if len(row) > 0:
                    r = row.iloc[0]
                    chg = r.get('pct_chg', 0)
                    if pd.isna(chg):
                        chg = r.get('change', 0)
                    if pd.isna(chg):
                        chg = 0
                    close_price = r.get('close', 0)
                    color = '#e74c3c' if chg > 0 else '#2ecc71' if chg < 0 else '#95a5a6'
                    arrow = '▲' if chg > 0 else '▼' if chg < 0 else '—'
                    st.sidebar.markdown(
                        f"<div style='display:flex;justify-content:space-between;align-items:center;padding:2px 0;'>"
                        f"<span style='font-size:13px;font-weight:600;'>{code}</span>"
                        f"<span style='font-size:12px;color:#888;'>{close_price:.2f}</span>"
                        f"<span style='font-size:12px;color:{color};'>{arrow}{abs(chg):.2f}%</span></div>",
                        unsafe_allow_html=True)
    st.sidebar.markdown("---")
    st.sidebar.markdown("A股量化数据工程平台 · 仅供研究，不构成投资建议")

    if page == "数据平台":
        show_data_platform()
    elif page == "市场总览":
        show_dashboard()
    elif page == "股票画像":
        render_stock_profile()
    elif page == "行业分析":
        render_industry_analysis()
    elif page == "系统概览":
        show_system_overview()
    elif page == "数据洞察":
        show_data_insight()
    elif page == "因子研究":
        show_factor_analysis()
    elif page == "情绪分析":
        show_sentiment_analysis()
    elif page == "模型预测":
        show_prediction()
    elif page == "策略回测":
        show_backtest()


if __name__ == "__main__":
    main()
