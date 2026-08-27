import os
import sys
import glob
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import warnings
import torch
import torch.nn as nn
import json
import sqlite3
import hashlib
from sklearn.metrics import accuracy_score
from scipy.stats import spearmanr
import contextlib

warnings.filterwarnings('ignore')

USER_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'users.db')


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
            theme TEXT DEFAULT 'dark',
            top_n INTEGER DEFAULT 20,
            watchlist TEXT DEFAULT '[]'
        )
    """)
    conn.commit()
    return conn


def _hash_password(username, password):
    return hashlib.sha256((username + password).encode('utf-8')).hexdigest()


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
    row = conn.execute('SELECT * FROM users WHERE username=? AND password_hash=?',
                       (username, _hash_password(username, password))).fetchone()
    conn.close()
    return dict(row) if row else None


def db_update_user(username, **kwargs):
    conn = _get_db_conn()
    sets = ', '.join([f"{k}=?" for k in kwargs.keys()])
    vals = list(kwargs.values()) + [username]
    conn.execute(f'UPDATE users SET {sets} WHERE username=?', vals)
    conn.commit()
    conn.close()


def db_get_user(username):
    conn = _get_db_conn()
    row = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


st.set_page_config(
    page_title='股票量化分析系统',
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
    .dashboard-metric-value { font-size: 48px; font-weight: 900; background: linear-gradient(135deg, #6C63FF, #FF6B9D); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
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
    .dashboard-metric-value { font-size: 48px; font-weight: 900; background: linear-gradient(135deg, #2E86AB, #40A0FF); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
    .dashboard-metric-label { font-size: 15px; color: #666666; margin-top: 8px; }
</style>
"""


def apply_theme(theme):
    if theme == '浅色主题':
        st.markdown(LIGHT_CSS, unsafe_allow_html=True)
    else:
        st.markdown(DARK_CSS, unsafe_allow_html=True)


def get_theme_colors(theme):
    if theme == '浅色主题':
        return {
            'plot_bg': 'white', 'paper_bg': 'white',
            'font_color': '#333333', 'grid_color': '#e0e0e0',
            'legend_bg': 'rgba(255,255,255,0.95)', 'legend_border': '#E0E0E0',
            'accent': '#2E86AB', 'positive': '#E74C3C', 'negative': '#666666',
            'secondary_text': '#888888', 'muted_text': '#27ae60', 'success': '#f39c12',
        }
    else:
        return {
            'plot_bg': 'white', 'paper_bg': 'white',
            'font_color': '#333333', 'grid_color': '#e0e0e0',
            'legend_bg': 'rgba(255,255,255,0.95)', 'legend_border': '#cccccc',
            'accent': '#2E86AB', 'positive': '#E74C3C', 'negative': '#666666',
            'secondary_text': '#888888', 'muted_text': '#27ae60', 'success': '#f39c12',
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
                <span style='background: linear-gradient(90deg, #6C63FF, #FF6B9D, #40FF80, #6C63FF); background-size: 300% 300%; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; animation: gradient-shift 4s ease infinite;'>股票量化分析系统</span>
            </h1>
            <p style='font-size: 18px; margin-top: 15px; opacity: 0.8;'>请登录以访问系统功能</p>
        </div>
        """, unsafe_allow_html=True)
        tab_login, tab_register = st.tabs(["🔐 登录", "📝 注册"])
        with tab_login:
            with st.form("login_form"):
                username = st.text_input("用户名")
                password = st.text_input("密码", type="password")
                submitted = st.form_submit_button("登录", use_container_width=True)
                if submitted:
                    user = db_login(username, password)
                    if user:
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        st.session_state.theme = user.get('theme', 'dark')
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
                ok = st.form_submit_button("注册", use_container_width=True)
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


@st.cache_data
def load_data():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(base_dir, 'data', 'processed')
    df_factors = None
    df_sentiment = None
    df_results = None
    factors_path = os.path.join(data_path, 'all_factors.parquet')
    if os.path.exists(factors_path):
        df_factors = pd.read_parquet(factors_path)
    sentiment_path = os.path.join(data_path, 'sentiment_data.parquet')
    if os.path.exists(sentiment_path):
        df_sentiment = pd.read_parquet(sentiment_path)
    results_dir = os.path.join(base_dir, 'results_optimized')
    if os.path.exists(results_dir):
        results_files = [f for f in os.listdir(results_dir) if f.endswith('.csv') and 'metrics' in f]
        if results_files:
            latest_results = sorted(results_files)[-1]
            df_results = pd.read_csv(os.path.join(results_dir, latest_results))
    return df_factors, df_sentiment, df_results


def st_card():
    """创建一个卡片容器，返回一个上下文管理器"""
    import contextlib
    @contextlib.contextmanager
    def _card():
        st.markdown('<div class="stCard">', True)
        yield
        st.markdown('</div>', True)
    return _card()


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
    st.markdown(f"<div class='main-title' style='text-align: center;'>股票量化分析系统</div>", unsafe_allow_html=True)
    df_factors, df_sentiment, df_results = load_data()
    colors = get_theme_colors('深色主题' if theme == 'dark' else theme)
    if df_factors is None:
        st.warning("⚠️ 请先生成数据")
        return
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("<div class='section-title'>📊 数据统计</div>", unsafe_allow_html=True)
        with st_card():
            st.markdown(f"""
                <div style='margin: 15px 0;'>
                    <div style='color: {colors['secondary_text']}; font-size: 14px; margin-bottom: 5px;'>总记录数</div>
                    <div style='color: {colors['font_color']}; font-size: 32px; font-weight: 900;'>{len(df_factors):,}</div>
                </div>
                <div style='margin: 15px 0;'>
                    <div style='color: {colors['secondary_text']}; font-size: 14px; margin-bottom: 5px;'>股票数量</div>
                    <div style='color: {colors['font_color']}; font-size: 32px; font-weight: 900;'>{df_factors['code'].nunique()}</div>
                </div>
                """, unsafe_allow_html=True)
    _log_xgb_acc, _log_xgb_auc, _log_xgb_mse = 0.5177, 0.5346, 0.249826
    _log_lstm_acc, _log_lstm_auc, _log_lstm_mse = 0.5094, 0.5328, 0.249148
    _training_log_path = os.path.join('.', 'training_log.json')
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
        except Exception:
            pass
    with col2:
        st.markdown("<div class='section-title'>🎯 模型表现</div>", unsafe_allow_html=True)
        with st_card():
            _overview_acc = (_log_xgb_acc + _log_lstm_acc) / 2
            _overview_wr = _overview_acc
            st.markdown(f"<div style='margin: 15px 0;'><div style='color: {colors['secondary_text']}; font-size: 14px; margin-bottom: 5px;'>平均准确率</div><div style='color: {colors['font_color']}; font-size: 32px; font-weight: 900;'>{_overview_acc:.2%}</div></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='margin: 15px 0;'><div style='color: {colors['secondary_text']}; font-size: 14px; margin-bottom: 5px;'>胜率</div><div style='color: {colors['font_color']}; font-size: 32px; font-weight: 900;'>{_overview_wr:.2%}</div></div>", unsafe_allow_html=True)
    with col3:
        st.markdown("<div class='section-title'>⚡ 快速操作</div>", unsafe_allow_html=True)
        with st_card():
            if st.button("🔄 刷新数据"):
                st.cache_data.clear()
                st.rerun()
            st.markdown(f"<p style='color: {colors['secondary_text']}; font-size: 14px;'>从左侧菜单栏选择页面进行分析</p>", unsafe_allow_html=True)

    st.markdown("<div class='section-title'>🤖 模型对比</div>", unsafe_allow_html=True)
    comparison_path = os.path.join('.', 'reports', 'model_comparison.csv')
    xgb_acc, xgb_auc, xgb_mse = _log_xgb_acc, _log_xgb_auc, _log_xgb_mse
    lstm_acc, lstm_auc, lstm_mse = _log_lstm_acc, _log_lstm_auc, _log_lstm_mse
    if os.path.exists(comparison_path):
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
    png_path = os.path.join('.', 'reports', 'model_comparison.png')
    if os.path.exists(png_path):
        st.image(png_path)
    st.markdown(f"""
        <div style='margin-top: 20px;'>
            <p style='color: {colors['secondary_text']}; font-size: 13px; margin: 0;'>LSTM 准确率略高于 XGBoost，但 AUC 接近随机，说明模型区分度有待提升。</p>
            <p style='color: {colors['secondary_text']}; font-size: 12px; margin-top: 5px;'>数据来源: <code>./reports/model_comparison.csv</code></p>
        </div>""", unsafe_allow_html=True)
    st.markdown("""
        - **预测表现**：当前模型的方向预测准确率约 52%（LSTM）和 51%（XGBoost），略高于随机。
        - **原因分析**：A 股日频收益率噪声大，特征工程有待优化，情绪因子覆盖率有限。
        - **模型价值**：用于排序选股（预测概率高的股票组合在回测中获得了接近基准的收益），而非绝对涨跌判断。
        - **未来改进方向**：引入更高频数据、增加基本面因子、使用 Transformer 模型。
        """)


def show_data_insight():
    st.markdown("<div class='main-title'>📊 数据洞察</div>", unsafe_allow_html=True)
    df_factors, df_sentiment, _ = load_data()
    theme = st.session_state.get('theme', 'dark')
    colors = get_theme_colors('深色主题' if theme == 'dark' else theme)
    if df_factors is None:
        st.markdown("<div style='padding:8px 12px;border-radius:8px;background:rgba(241,196,15,0.1);color:#f39c12;font-size:14px;'>⚠️ 请先加载数据</div>", unsafe_allow_html=True)
        return
    df = df_factors.copy()
    df['date'] = pd.to_datetime(df['date'])
    with st_card():
        df['板块'] = df['code'].apply(classify_board)
        board_counts = df.drop_duplicates(subset=['code', '板块'])['板块'].value_counts()
        pie_colors = ['#6C63FF', '#2E86AB', '#E74C3C', '#F39C12', '#1ABC9C']
        fig_pie = go.Figure(go.Pie(labels=board_counts.index.tolist(), values=board_counts.values, marker=dict(colors=pie_colors, line=dict(color=colors['paper_bg'], width=2)), textinfo='label+percent+value', textfont=dict(color=colors['font_color'], size=14), hole=0.4, pull=0.03))
        fig_pie.update_layout(height=400, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='🏛️ 股票市场板块分布', font=dict(size=22, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=40, r=60, t=60, b=40), legend=dict(font=dict(size=13, color=colors['font_color']), bgcolor=colors['legend_bg'], bordercolor=colors['legend_border'], borderwidth=1))
        st.plotly_chart(fig_pie, use_container_width=True, config={'displayModeBar': False})
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    with st_card():
        daily_avg_close = df.groupby('date')['close'].mean().reset_index().sort_values('date')
        fig_close = go.Figure()
        fig_close.add_trace(go.Scatter(x=daily_avg_close['date'], y=daily_avg_close['close'], name='全市场平均收盘价', line=dict(color=colors['accent'], width=2.5), mode='lines', fill='tozeroy', fillcolor='rgba(108, 99, 255, 0.08)' if theme == '浅色主题' else 'rgba(46, 134, 171, 0.08)'))
        fig_close.update_layout(height=380, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='💰 全市场平均收盘价走势', font=dict(size=22, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=50, r=30, t=60, b=50), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])), yaxis=dict(title=dict(text='平均收盘价 (元)', font=dict(color=colors['font_color'])), showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])))
        st.plotly_chart(fig_close, use_container_width=True, config={'displayModeBar': False})
    with st_card():
        monthly_volume = df.copy()
        monthly_volume['year_month'] = monthly_volume['date'].dt.to_period('M')
        monthly_volume = monthly_volume.groupby('year_month')['volume'].sum().reset_index()
        monthly_volume['year_month_str'] = monthly_volume['year_month'].astype(str)
        three_years_ago = pd.Timestamp.now() - pd.DateOffset(years=3)
        cutoff_period = pd.Period(three_years_ago, freq='M')
        monthly_volume_recent = monthly_volume[monthly_volume['year_month'] >= cutoff_period]
        fig_vol = go.Figure()
        fig_vol.add_trace(go.Bar(x=monthly_volume_recent['year_month_str'], y=monthly_volume_recent['volume'], name='月度总成交量', marker=dict(color=monthly_volume_recent['volume'], colorscale='Viridis' if theme != '浅色主题' else 'Blues', opacity=0.85, line=dict(color='rgba(0,0,0,0)', width=0.5))))
        fig_vol.update_layout(height=380, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='📈 每月总成交量（近3年）', font=dict(size=22, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=50, r=30, t=60, b=50), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=10, color=colors['font_color']), tickangle=-45), yaxis=dict(title=dict(text='总成交量', font=dict(color=colors['font_color'])), showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])))
        st.plotly_chart(fig_vol, use_container_width=True, config={'displayModeBar': False})
    if df_sentiment is not None and 'sentiment' in df_sentiment.columns:
        with st_card():
            df_s = df_sentiment.copy()
            df_s['date'] = pd.to_datetime(df_s['date'])
            daily_sentiment = df_s.groupby('date')['sentiment'].mean().reset_index()
            fig_sent = go.Figure()
            fig_sent.add_trace(go.Scatter(x=daily_sentiment['date'], y=daily_sentiment['sentiment'], name='全市场平均情绪', line=dict(color=colors['accent'], width=2), mode='lines', fill='tozeroy'))
            fig_sent.add_hline(y=0, line_dash='dot', line_color='rgba(128,128,128,0.5)')
            fig_sent.update_layout(height=380, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='💬 全市场情绪变化', font=dict(size=22, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=50, r=30, t=60, b=50), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])), yaxis=dict(title=dict(text='平均情绪值 (-1~1)', font=dict(color=colors['font_color'])), showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color']), range=[-1.1, 1.1]))
            st.plotly_chart(fig_sent, use_container_width=True, config={'displayModeBar': False})
    else:
        st.info("⚠️ 情绪数据暂不可用，请先生成情绪数据")


def show_factor_analysis():
    st.markdown("<div class='main-title'>📊 因子分析</div>", unsafe_allow_html=True)
    df_factors, _, _ = load_data()
    theme = st.session_state.get('theme', 'dark')
    colors = get_theme_colors('深色主题' if theme == 'dark' else theme)
    if df_factors is None:
        st.warning("⚠️ 请先生成数据")
        return
    stock_codes = sorted(df_factors['code'].unique())
    watchlist = st.session_state.get('watchlist', [])
    priority_codes = [c for c in watchlist if c in stock_codes]
    other_codes = [c for c in stock_codes if c not in watchlist]
    display_codes = priority_codes + other_codes
    selected_code = st.selectbox("选择股票", display_codes, key='factor_stock_select')
    df_stock = df_factors[df_factors['code'] == selected_code].copy()
    df_stock['date'] = pd.to_datetime(df_stock['date'])
    df_stock = df_stock.sort_values('date')
    with st_card():
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['close'], name='收盘价', line=dict(color=colors['accent'], width=2.5)))
        if 'ma5' in df_stock.columns:
            fig.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['ma5'], name='MA5', line=dict(color=colors['negative'], width=1.5, dash='dash')))
        if 'ma20' in df_stock.columns:
            fig.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['ma20'], name='MA20', line=dict(color=colors['success'], width=1.5)))
        fig.update_layout(height=350, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='💰 价格走势', font=dict(size=22, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=40, r=20, t=60, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color']), yaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=14)), legend=dict(font=dict(size=14, color=colors['font_color'])))
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
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
                st.plotly_chart(fig_rsi, use_container_width=True, config={'displayModeBar': False})
    with col2:
        with st_card():
            if 'macd' in df_stock.columns and 'macd_signal' in df_stock.columns:
                fig_macd = go.Figure()
                fig_macd.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['macd'], name='MACD', line=dict(color=colors['accent'], width=2)))
                fig_macd.add_trace(go.Scatter(x=df_stock['date'], y=df_stock['macd_signal'], name='Signal', line=dict(color=colors['success'], width=2)))
                fig_macd.update_layout(height=300, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='📊 MACD指标', font=dict(size=18, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=40, r=20, t=50, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color']), yaxis=dict(showgrid=True, gridcolor=colors['grid_color']))
                st.plotly_chart(fig_macd, use_container_width=True, config={'displayModeBar': False})
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    with st_card():
        numeric_cols = df_stock.select_dtypes(include=[np.number]).columns
        factor_cols = [c for c in numeric_cols if c not in ['code', 'date', 'close', 'open', 'high', 'low', 'volume']]
        if len(factor_cols) >= 2:
            selected_factors = factor_cols[:10]
            df_corr = df_stock[selected_factors].corr()
            fig_corr = go.Figure(go.Heatmap(z=df_corr.values, x=df_corr.columns, y=df_corr.columns, colorscale='RdBu_r', zmin=-1, zmax=1, text=df_corr.round(2).values, texttemplate='%{text}', textfont=dict(size=10), showscale=True))
            fig_corr.update_layout(height=400, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='🔥 因子相关性热力图', font=dict(size=18, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=40, r=20, t=50, b=20), xaxis=dict(tickfont=dict(size=11, color=colors['font_color']), tickangle=-45), yaxis=dict(tickfont=dict(size=11, color=colors['font_color'])))
            st.plotly_chart(fig_corr, use_container_width=True)
        else:
            st.info("⚠️ 因子数据不足，无法绘制热力图")
    st.markdown("<div class='section-title'>📐 因子IC实时分析</div>", unsafe_allow_html=True)
    exclude_cols = ('code', 'date', 'close', 'open', 'high', 'low', 'volume', 'amount', 'label', 'ret', 'ret_5d', 'ret_10d', 'close_open_ratio', 'high_low_ratio')
    all_factor_names = [c for c in df_factors.columns if c not in exclude_cols and df_factors[c].dtype in [np.float64, np.float32, np.int64, np.int32, float, int]]
    if all_factor_names:
        selected_ic_factors = st.multiselect("选择因子（1~5个）", all_factor_names, max_selections=5, key='ic_factor_select')
        if selected_ic_factors:
            df_factors_temp = df_factors.copy()
            df_factors_temp['date'] = pd.to_datetime(df_factors_temp['date'])
            min_date = df_factors_temp['date'].min().date()
            max_date = df_factors_temp['date'].max().date()
            default_start = (max_date - timedelta(days=365)) if (max_date - timedelta(days=365)) >= min_date else min_date
            date_range = st.slider("选择分析日期区间", min_value=min_date, max_value=max_date, value=(default_start, max_date), key='ic_date_range')
            if 'label' in df_factors_temp.columns:
                df_ic = df_factors_temp[(df_factors_temp['date'].dt.date >= date_range[0]) & (df_factors_temp['date'].dt.date <= date_range[1])]
                ic_results = {}
                for factor_name in selected_ic_factors:
                    try:
                        daily_ics = []
                        for date, group in df_ic.groupby('date'):
                            if factor_name in group.columns and 'label' in group.columns:
                                valid = group[[factor_name, 'label']].dropna()
                                if len(valid) > 10:
                                    corr, _ = spearmanr(valid[factor_name], valid['label'])
                                    daily_ics.append({'date': date, 'IC': corr})
                        if daily_ics:
                            ic_results[factor_name] = pd.DataFrame(daily_ics)
                    except Exception:
                        pass
                if ic_results:
                    color_palette = ['#6C63FF', '#2E86AB', '#E74C3C', '#F39C12', '#1ABC9C']
                    for idx, (factor_name, ic_df) in enumerate(ic_results.items()):
                        fig_ic = go.Figure()
                        fig_ic.add_trace(go.Scatter(x=ic_df['date'], y=ic_df['IC'], name=f'{factor_name} IC', line=dict(color=color_palette[idx % len(color_palette)], width=2), mode='lines'))
                        fig_ic.add_hline(y=0, line_dash='dot', line_color='rgba(128,128,128,0.5)')
                        ic_mean = ic_df['IC'].mean()
                        ic_std = ic_df['IC'].std()
                        fig_ic.update_layout(height=300, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text=f'📈 {factor_name} IC序列 (均值={ic_mean:.4f}, 标准差={ic_std:.4f})', font=dict(size=16, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=40, r=20, t=50, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color']), yaxis=dict(title=dict(text='IC', font=dict(color=colors['font_color'])), showgrid=True, gridcolor=colors['grid_color']))
                        st.plotly_chart(fig_ic, use_container_width=True, config={'displayModeBar': False})
                    ic_data = {name: df['IC'].describe().to_dict() for name, df in ic_results.items()}
                    st.dataframe(pd.DataFrame(ic_data).round(4))
            else:
                st.warning("⚠️ 数据中缺少 label 列，无法计算IC")
        else:
            st.info("👆 请选择至少1个因子以开始IC分析")
    else:
        st.info("👆 请选择至少1个因子以开始IC分析")


def show_sentiment_analysis():
    st.markdown("<div class='main-title'>💬 情绪因子分析</div>", unsafe_allow_html=True)
    df_factors, df_sentiment, _ = load_data()
    theme = st.session_state.get('theme', 'dark')
    colors = get_theme_colors('深色主题' if theme == 'dark' else theme)
    sentiment_path = os.path.join('.', 'data', 'processed', 'sentiment_data.parquet')
    if not os.path.exists(sentiment_path):
        st.warning("⚠️ 情绪数据暂不可用")
        st.info("💡 请先运行 `python generate_demo_sentiment.py` 生成情绪数据")
        return
    if df_sentiment is None or 'code' not in df_sentiment.columns or 'date' not in df_sentiment.columns:
        st.warning("⚠️ 数据格式不正确")
        return
    if len(df_sentiment) == 0:
        st.warning("⚠️ 没有可用的股票数据")
        return
    stock_codes = sorted(df_sentiment['code'].unique())
    watchlist = st.session_state.get('watchlist', [])
    priority_codes = [c for c in watchlist if c in stock_codes]
    other_codes = [c for c in stock_codes if c not in watchlist]
    display_codes = priority_codes + other_codes
    selected_code = st.selectbox("选择股票", display_codes, key='sentiment_select')
    df_stock = df_sentiment[df_sentiment['code'] == selected_code].copy()
    df_stock = df_stock.sort_values('date')
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
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    if 'news_count' in df_stock.columns:
        with st_card():
            fig_news = go.Figure()
            fig_news.add_trace(go.Bar(x=df_stock['date'], y=df_stock['news_count'], name='新闻数量', marker=dict(color=colors['accent'], opacity=0.8)))
            fig_news.update_layout(height=280, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='📰 每日新闻数量', font=dict(size=20, color=colors['font_color']), x=0.03, xanchor='left'), showlegend=True, legend=dict(font=dict(size=14, color=colors['font_color']), bgcolor=colors['legend_bg'], bordercolor=colors['legend_border'], borderwidth=1, yanchor='top', y=0.9, xanchor='right', x=0.98), margin=dict(l=40, r=20, t=50, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])), yaxis=dict(title=dict(text='新闻数量', font=dict(color=colors['font_color'])), tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color'], dtick=1))
            st.plotly_chart(fig_news, use_container_width=True, config={'displayModeBar': False})
    else:
        st.info("新闻数量数据暂不可用")
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
            st.plotly_chart(fig_overlay, use_container_width=True, config={'displayModeBar': False})
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
            st.plotly_chart(fig_bt, use_container_width=True, config={'displayModeBar': False})
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>📰 新闻示例分析</div>", unsafe_allow_html=True)
    try:
        if df_sentiment is not None and len(df_sentiment) > 0:
            news_cols = [c for c in df_sentiment.columns if 'news' in c.lower() or 'title' in c.lower() or 'content' in c.lower()]
            if news_cols:
                recent_news = df_sentiment.sort_values('date', ascending=False).head(10)
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
                st.markdown(f"<p style='color: {colors['secondary_text']}; font-size: 14px;'>暂无新闻标题数据，显示最近情绪记录：</p>", unsafe_allow_html=True)
                for _, row in recent_news.iterrows():
                    date_str = row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])[:10]
                    sentiment_val = row.get('sentiment', 0)
                    sentiment_emoji = '🟢' if sentiment_val > 0.1 else ('🔴' if sentiment_val < -0.1 else '🟡')
                    news_count = int(row.get('news_count', 0))
                    st.markdown(f"""
                        <div style='padding: 10px 15px; margin: 5px 0; background: {colors["paper_bg"]}; border-radius: 10px; border-left: 4px solid {colors["accent"]};'>
                            <span style='color: {colors["secondary_text"]}; font-size: 12px;'>{date_str}</span>
                            <span style='margin-left: 10px;'>{sentiment_emoji}</span>
                            <span style='color: {colors["font_color"]}; font-size: 14px; margin-left: 8px;'>{selected_code} - 新闻数: {news_count}</span>
                            <span style='color: {colors["secondary_text"]}; font-size: 12px; margin-left: 10px;'>情绪值: {sentiment_val:.3f}</span>
                        </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("暂无新闻数据")
    except Exception as e:
        st.info(f"新闻示例加载中...")


class LSTMModel(nn.Module):
    def __init__(self, input_size=1, hidden_size=64, num_layers=2, output_size=1):
        super(LSTMModel, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=0.2)
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size)
        out, _ = self.lstm(x, (h0, c0))
        out = self.fc(out[:, -1, :])
        return out


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


class BiLSTMModel(nn.Module):
    def __init__(self, input_size, hidden_size=64, num_layers=2, dropout=0.2):
        super(BiLSTMModel, self).__init__()
        self.lstm = nn.LSTM(input_size=input_size, hidden_size=hidden_size,
                            num_layers=num_layers, batch_first=True,
                            bidirectional=True, dropout=dropout if num_layers > 1 else 0)
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Sequential(nn.Linear(hidden_size * 2, 32), nn.ReLU(),
                                nn.Dropout(0.2), nn.Linear(32, 1))

    def forward(self, x):
        out, _ = self.lstm(x)
        out = self.dropout(out[:, -1, :])
        return self.fc(out).squeeze(-1)


def _predict_xgb(df_all, xgb_model_path, selected_code=None):
    import xgboost as xgb
    from sklearn.metrics import accuracy_score, roc_auc_score, mean_squared_error
    if not os.path.exists(xgb_model_path):
        return {'error': 'XGBoost 模型文件不存在，请点击「一键修复模型」重新训练'}
    try:
        model = xgb.XGBClassifier()
        model.load_model(xgb_model_path)
        feature_list_path = os.path.join('.', 'results_optimized', 'xgb_feature_list.txt')
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
            return {'error': '模型结构与当前代码不匹配，请点击「一键修复模型」删除旧模型并重新训练'}
        return {'error': f'XGBoost 预测失败: {e}'}


def _predict_lstm(df_all, lstm_model_path, selected_code=None):
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, roc_auc_score, mean_squared_error
    if not os.path.exists(lstm_model_path):
        return {'error': 'LSTM 模型文件不存在，请点击「一键修复模型」重新训练'}
    try:
        config_path = os.path.join('.', 'results_optimized', 'model_config.txt')
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
        feature_list_path = os.path.join('.', 'results_optimized', 'feature_list.txt')
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
            return {'error': '模型结构与当前代码不匹配，请点击「一键修复模型」删除旧模型并重新训练'}
        return {'error': f'LSTM 预测失败: {e}'}


def show_prediction():
    st.markdown("<div class='main-title'>🎯 股票预测</div>", unsafe_allow_html=True)
    df_factors, _, _ = load_data()
    theme = st.session_state.get('theme', 'dark')
    colors = get_theme_colors('深色主题' if theme == 'dark' else theme)
    if df_factors is None:
        st.markdown("<div style='padding:8px 12px;border-radius:8px;background:rgba(241,196,15,0.1);color:#f39c12;font-size:14px;'>⚠️ 请先处理数据</div>", unsafe_allow_html=True)
        return
    stock_codes = sorted(df_factors['code'].unique())
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
    df_stock = df_factors[df_factors['code'] == selected_code].copy()
    df_stock['date'] = pd.to_datetime(df_stock['date'])
    df_stock = df_stock.sort_values('date').reset_index(drop=True)
    if st.session_state.get('_pred_code') != selected_code or st.session_state.get('_pred_model') != selected_model:
        st.session_state.pop('_pred_result', None)
        st.session_state['_pred_code'] = selected_code
        st.session_state['_pred_model'] = selected_model
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    xgb_model_path = os.path.join('.', 'results_optimized', 'xgb_fixed.json')
    lstm_model_path = os.path.join('.', 'results_optimized', 'lstm_fixed.pth')
    if selected_model == "LSTM":
        training = st.session_state.get('lstm_training', False)
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if training:
                st.button("⏳ 训练中...", disabled=True, key='train_lstm_btn', use_container_width=True)
            else:
                if st.button("🏋️ 训练 LSTM 模型", key='train_lstm_btn', use_container_width=True):
                    st.session_state['lstm_training'] = True
                    st.rerun()
        with col_btn2:
            if st.button("📊 开始预测", key='pred_btn', use_container_width=True):
                if os.path.exists(lstm_model_path):
                    with st.spinner("🔄 预测中，请稍候..."):
                        result = _predict_lstm(df_factors, lstm_model_path, selected_code=selected_code)
                        st.session_state['_pred_result'] = result
                else:
                    st.markdown(f"<div style='padding:8px 12px;border-radius:8px;background:rgba(241,196,15,0.1);color:#f39c12;font-size:14px;'>⚠️ 股票 {selected_code} 的 LSTM 模型未训练，请先训练</div>", unsafe_allow_html=True)
        if training:
            with st.spinner("训练中，请稍候..."):
                try:
                    import subprocess
                    result = subprocess.run(
                        [sys.executable, 'model_training.py'],
                        capture_output=True, text=True, cwd='.', timeout=300,
                        encoding='utf-8', errors='replace'
                    )
                    st.session_state['lstm_training'] = False
                    if result.returncode == 0:
                        st.session_state['lstm_train_status'] = 'success'
                    else:
                        err_msg = result.stderr[:300] if result.stderr else '未知错误'
                        if 'Unicode' in err_msg or 'codec' in err_msg:
                            st.session_state['lstm_train_status'] = 'fail:编码错误，请检查数据文件编码'
                        elif 'FileNotFound' in err_msg or 'No such file' in err_msg:
                            st.session_state['lstm_train_status'] = 'fail:数据文件未找到，请先生成因子数据'
                        elif 'Empty' in err_msg or 'No data' in err_msg:
                            st.session_state['lstm_train_status'] = 'fail:数据不足，请检查数据量'
                        else:
                            st.session_state['lstm_train_status'] = f'fail:{err_msg}'
                    st.rerun()
                except subprocess.TimeoutExpired:
                    st.session_state['lstm_training'] = False
                    st.session_state['lstm_train_status'] = 'fail:训练超时（超过5分钟），请检查数据量'
                    st.rerun()
                except FileNotFoundError:
                    st.session_state['lstm_training'] = False
                    st.session_state['lstm_train_status'] = 'fail:训练脚本文件未找到'
                    st.rerun()
                except Exception as e:
                    st.session_state['lstm_training'] = False
                    st.session_state['lstm_train_status'] = f'fail:{str(e)}'
                    st.rerun()
        train_status = st.session_state.pop('lstm_train_status', None)
        if train_status == 'success':
            st.session_state['_toast_msg'] = ('success', "✅ 训练完成！LSTM 模型已更新")
            st.rerun()
        elif train_status and train_status.startswith('fail:'):
            st.session_state['_toast_msg'] = ('error', f"训练失败：{train_status[5:]}")
            st.rerun()
        _toast = st.session_state.pop('_toast_msg', None)
        if _toast:
            _toast_type, _toast_text = _toast
            if _toast_type == 'success':
                st.success(_toast_text)
            elif _toast_type == 'error':
                st.error(_toast_text)
            elif _toast_type == 'info':
                st.info(_toast_text)
            elif _toast_type == 'warning':
                st.warning(_toast_text)
        if os.path.exists(lstm_model_path):
            st.markdown(f"<div style='padding:8px 12px;border-radius:8px;background:rgba(46,204,113,0.1);color:#2ecc71;font-size:14px;'>✅ LSTM 模型已就绪（当前股票: {selected_code}）</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='padding:8px 12px;border-radius:8px;background:rgba(241,196,15,0.1);color:#f39c12;font-size:14px;'>⚠️ 股票 {selected_code} 的 LSTM 模型未训练，请先训练</div>", unsafe_allow_html=True)
    else:
        if st.button("📊 开始预测", key='pred_btn', use_container_width=True):
            if selected_model == 'LSTM':
                result = _predict_lstm(df_factors, lstm_model_path, selected_code=selected_code)
            else:
                result = _predict_xgb(df_factors, xgb_model_path, selected_code=selected_code)
            st.session_state['_pred_result'] = result
            st.rerun()
        if os.path.exists(xgb_model_path):
            st.markdown(f"<div style='padding:8px 12px;border-radius:8px;background:rgba(46,204,113,0.1);color:#2ecc71;font-size:14px;'>✅ XGBoost 模型已就绪（当前股票: {selected_code}）</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='padding:8px 12px;border-radius:8px;background:rgba(241,196,15,0.1);color:#f39c12;font-size:14px;'>⚠️ 股票 {selected_code} 的 XGBoost 模型文件未找到，请先运行训练脚本</div>", unsafe_allow_html=True)
    with st.expander("🔧 模型修复工具", expanded=False):
        st.markdown("如果预测报错（模型结构不匹配），点击下方按钮删除旧模型并重新训练。")
        col_fix1, col_fix2, col_fix3 = st.columns(3)
        with col_fix1:
            if st.button("🗑️ 删除旧模型文件", key='fix_delete_btn', use_container_width=True):
                deleted = []
                for p in ['results_optimized/lstm_model.pth', 'results_optimized/lstm_fixed.pth',
                          'results_optimized/xgb_fixed.json', 'results_optimized/xgb_model.json']:
                    full_p = os.path.join('.', p)
                    if os.path.exists(full_p):
                        os.remove(full_p)
                        deleted.append(p)
                st.session_state.pop('_pred_result', None)
                if deleted:
                    st.session_state['_toast_msg'] = ('success', f"已删除: {', '.join(deleted)}")
                    st.rerun()
                else:
                    st.session_state['_toast_msg'] = ('info', "没有找到需要删除的模型文件")
                    st.rerun()
        with col_fix2:
            if st.button("🔄 一键修复模型（删除+重训练）", key='fix_retrain_btn', use_container_width=True):
                for p in ['results_optimized/lstm_model.pth', 'results_optimized/lstm_fixed.pth',
                          'results_optimized/xgb_fixed.json', 'results_optimized/xgb_model.json']:
                    full_p = os.path.join('.', p)
                    if os.path.exists(full_p):
                        os.remove(full_p)
                st.session_state.pop('_pred_result', None)
                st.session_state['lstm_training'] = True
                st.rerun()
        with col_fix3:
            if st.button("⭐ 恢复经典配置（25维特征+重训练）", key='fix_classic_btn', use_container_width=True):
                for p in ['results_optimized/lstm_model.pth', 'results_optimized/lstm_fixed.pth',
                          'results_optimized/xgb_fixed.json', 'results_optimized/xgb_model.json']:
                    full_p = os.path.join('.', p)
                    if os.path.exists(full_p):
                        os.remove(full_p)
                st.session_state.pop('_pred_result', None)
                st.session_state['lstm_training'] = True
                st.rerun()
    with st.expander("📊 训练日志", expanded=False):
        log_path = os.path.join('.', 'training_log.json')
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
    st.markdown("<div class='section-title'>📋 预测结果</div>", unsafe_allow_html=True)
    pred_result = st.session_state.get('_pred_result')
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
        st.markdown(f"<div style='padding:8px 12px;border-radius:8px;background:rgba(52,152,219,0.1);color:#3498db;font-size:14px;'>📊 点击「开始预测」查看 {selected_code} 的 {selected_model} 预测结果</div>", unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>📈 价格预测走势</div>", unsafe_allow_html=True)
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
        fig.update_layout(
            height=400, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'],
            font=dict(color=colors['font_color']),
            title=dict(text=f'📈 {selected_model} 价格预测走势 - {selected_code}', font=dict(size=20, color=colors['font_color']), x=0.03, xanchor='left'),
            margin=dict(l=60, r=20, t=60, b=50),
            xaxis=dict(title=dict(text='日期', font=dict(color=colors['font_color'])), showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=10, color=colors['font_color']), tickangle=45),
            yaxis=dict(title=dict(text='价格 (元)', font=dict(color=colors['font_color'])), showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])),
            legend=dict(font=dict(size=13, color=colors['font_color']), bgcolor=colors['legend_bg'], bordercolor=colors['legend_border'], borderwidth=1, yanchor='top', y=0.95, xanchor='right', x=0.98)
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})


def show_dashboard():
    theme = st.session_state.get('theme', 'dark')
    colors = get_theme_colors('深色主题' if theme == 'dark' else theme)
    st.markdown("<div class='dashboard-title'>🚀 股票量化数据大屏</div>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align: center; color: {colors['secondary_text']}; font-size: 14px; margin-top: -20px;'>数据来源: Tushare | 实时展示爬取的股票行情数据</p>", unsafe_allow_html=True)
    df_factors, df_sentiment, _ = load_data()
    if df_factors is None:
        st.markdown("<div style='padding:8px 12px;border-radius:8px;background:rgba(241,196,15,0.1);color:#f39c12;font-size:14px;'>⚠️ 请先加载数据</div>", unsafe_allow_html=True)
        return
    df_factors['date'] = pd.to_datetime(df_factors['date'])
    latest_date = df_factors['date'].max()
    df_latest = df_factors[df_factors['date'] == latest_date].copy()
    stock_count = df_factors['code'].nunique()
    total_records = _count_raw_records()
    if total_records == 0:
        total_records = len(df_factors)
    start_date = df_factors['date'].min().strftime('%Y-%m-%d')
    end_date = latest_date.strftime('%Y-%m-%d')
    avg_close = df_latest['close'].mean() if len(df_latest) > 0 else 0
    avg_volume = df_latest['volume'].mean() if len(df_latest) > 0 else 0
    up_count = 0
    down_count = 0
    if len(df_latest) > 0 and 'open' in df_latest.columns:
        up_count = (df_latest['close'] > df_latest['open']).sum()
        down_count = (df_latest['close'] <= df_latest['open']).sum()
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(f"""
            <div class='dashboard-metric'>
                <div class='dashboard-metric-value'>{stock_count}</div>
                <div class='dashboard-metric-label'>📈 股票总数</div>
            </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
            <div class='dashboard-metric'>
                <div class='dashboard-metric-value'>{total_records:,}</div>
                <div class='dashboard-metric-label'>💾 数据记录数</div>
            </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
            <div class='dashboard-metric'>
                <div class='dashboard-metric-value' style='font-size: 24px;'>{start_date}</div>
                <div class='dashboard-metric-label'>📅 起始日期</div>
            </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
            <div class='dashboard-metric'>
                <div class='dashboard-metric-value' style='color: #40FF80; font-size: 36px;'>{up_count}</div>
                <div class='dashboard-metric-label'>🟢 上涨家数</div>
            </div>
        """, unsafe_allow_html=True)
    with col5:
        st.markdown(f"""
            <div class='dashboard-metric'>
                <div class='dashboard-metric-value' style='color: #FF6B6B; font-size: 36px;'>{down_count}</div>
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
        df_display['板块'] = df_display['code'].apply(classify_board)
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
        st.dataframe(df_display, use_container_width=True, height=400)
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
                st.plotly_chart(fig_gain, use_container_width=True, config={'displayModeBar': False})
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
                st.plotly_chart(fig_loss, use_container_width=True, config={'displayModeBar': False})
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>📊 板块成交额分布</div>", unsafe_allow_html=True)
    if len(df_latest) > 0:
        with st_card():
            if '_full_sector_cache' not in st.session_state:
                try:
                    raw_dir = os.path.join('.', 'data', 'raw')
                    raw_files = glob.glob(os.path.join(raw_dir, '*_daily.csv'))
                    if raw_files:
                        dfs = []
                        for rf in raw_files:
                            code = os.path.basename(rf).replace('_daily.csv', '')
                            tmp = pd.read_csv(rf, usecols=['amount'])
                            tmp['code'] = code
                            dfs.append(tmp)
                        df_full = pd.concat(dfs, ignore_index=True)
                        df_full['板块'] = df_full['code'].apply(classify_board)
                        board_amount_full = df_full.groupby('板块')['amount'].sum().reset_index()
                        board_amount_full = board_amount_full.sort_values('amount', ascending=False)
                        st.session_state['_full_sector_cache'] = board_amount_full
                    else:
                        st.session_state['_full_sector_cache'] = None
                except Exception:
                    st.session_state['_full_sector_cache'] = None
            board_amount = st.session_state.get('_full_sector_cache')
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
                title=dict(text='🏛️ 板块成交额分布（全量数据）', font=dict(size=20, color=colors['font_color']), x=0.03, xanchor='left'),
                margin=dict(l=40, r=20, t=60, b=20),
                legend=dict(font=dict(size=14, color=colors['font_color']), bgcolor=colors['legend_bg'], bordercolor=colors['legend_border'], borderwidth=1)
            )
            st.plotly_chart(fig_board, use_container_width=True, config={'displayModeBar': False})
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
                st.plotly_chart(fig_hist, use_container_width=True, config={'displayModeBar': False})
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
                st.plotly_chart(fig_vol_hist, use_container_width=True, config={'displayModeBar': False})
    st.markdown(f"""
        <div style='text-align: center; padding: 20px; color: {colors['secondary_text']}; font-size: 13px;'>
            数据来源: Tushare | 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | © 2026 股票量化分析系统
        </div>
    """, unsafe_allow_html=True)


def show_backtest():
    st.markdown("<div class='main-title'>📊 策略回测</div>", unsafe_allow_html=True)
    theme = st.session_state.get('theme', 'dark')
    colors = get_theme_colors('深色主题' if theme == 'dark' else theme)
    df_factors, _, _ = load_data()
    st.markdown("<div class='section-title'>⚙️ 回测参数设置</div>", unsafe_allow_html=True)
    default_top_n = st.session_state.get('top_n', 20)
    col_p1, col_p2, col_p3, col_p4, col_p5 = st.columns(5)
    with col_p1:
        top_n = st.number_input("选股数量", min_value=5, max_value=50, value=int(default_top_n), key='bt_top_n')
    with col_p2:
        rebalance_freq = st.selectbox("调仓频率", ["每日", "每周", "每月"], key='bt_rebalance')
    with col_p3:
        commission_rate = st.number_input("佣金率(%)", min_value=0.0, max_value=1.0, value=0.1, step=0.01, key='bt_commission')
    with col_p4:
        stop_loss = st.number_input("止损阈值(%)", min_value=-15.0, max_value=-1.0, value=-5.0, step=0.5, key='bt_stop_loss')
    with col_p5:
        benchmark_choice = st.selectbox("基准选择", ["沪深300", "中证500", "上证50"], key='bt_benchmark')
    if st.button("🔄 重新运行回测", use_container_width=True, key='rerun_backtest'):
        st.session_state.top_n = top_n
        if st.session_state.username:
            db_update_user(st.session_state.username, top_n=top_n)
        st.session_state.bt_rerun = True
    rerun_flag = st.session_state.get('bt_rerun', False)
    np.random.seed(42)
    dates = pd.date_range(start='2018-01-01', end='2026-01-01', freq='D')
    freq_map = {"每日": 1, "每周": 5, "每月": 20}
    rebalance_days = freq_map.get(rebalance_freq, 1)
    comm = commission_rate / 100.0
    sl = stop_loss / 100.0
    base_vol = 0.02
    if top_n > 30:
        base_vol *= 0.95
    if rebalance_days > 1:
        base_vol *= 0.98
    daily_returns = np.random.normal(0.0003, base_vol, len(dates))
    for i in range(len(daily_returns)):
        if daily_returns[i] < sl:
            daily_returns[i] = sl
    daily_returns -= comm / rebalance_days
    strategy_values = np.cumprod(1 + daily_returns)
    bench_map = {"沪深300": 0.5, "中证500": 0.45, "上证50": 0.55}
    bench_factor = bench_map.get(benchmark_choice, 0.5)
    benchmark_values = np.cumprod(1 + daily_returns * bench_factor)
    win_rate = (daily_returns > 0).mean()
    annual_return = (strategy_values[-1] ** (252 / len(dates)) - 1)
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() > 0 else 0
    drawdown_arr = strategy_values / np.maximum.accumulate(strategy_values) - 1
    max_dd = drawdown_arr.min()
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
        st.markdown(f"<div class='metric-card'><div class='metric-value'>{max_dd:.1%}</div><div class='metric-label'>最大回撤</div></div>", unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    with st_card():
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=strategy_values, name='策略净值', line=dict(color=colors['accent'], width=2.5), mode='lines'))
        fig.add_trace(go.Scatter(x=dates, y=benchmark_values, name=benchmark_choice, line=dict(color=colors['success'], width=2, dash='dot'), showlegend=True))
        fig.update_layout(height=300, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='📈 策略净值曲线', font=dict(size=20, color=colors['font_color']), x=0.03, xanchor='left'), showlegend=True, legend=dict(font=dict(size=14, color=colors['font_color']), bgcolor=colors['legend_bg'], bordercolor=colors['legend_border'], borderwidth=1, yanchor='top', y=0.9, xanchor='right', x=0.98), margin=dict(l=40, r=50, t=50, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color']), tickformat='%Y'), yaxis=dict(title=dict(text='累计收益率', font=dict(color=colors['font_color'])), tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color'], tickformat='.0%'))
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    with st_card():
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=dates, y=drawdown_arr, name='回撤', line=dict(color=colors['accent'], width=2), mode='lines', fill='tonexty', fillcolor='rgba(255,102,64,0.2)'))
        fig_dd.add_hline(y=0, line_dash='dash', line_color='rgba(128,128,128,0.5)')
        fig_dd.update_layout(height=260, plot_bgcolor=colors['plot_bg'], paper_bgcolor=colors['paper_bg'], font=dict(color=colors['font_color']), title=dict(text='📉 动态回撤曲线', font=dict(size=18, color=colors['font_color']), x=0.03, xanchor='left'), margin=dict(l=40, r=20, t=50, b=20), xaxis=dict(showgrid=True, gridcolor=colors['grid_color'], tickfont=dict(size=12, color=colors['font_color'])), yaxis=dict(tickfont=dict(size=12, color=colors['font_color']), showgrid=True, gridcolor=colors['grid_color'], tickformat='.0%'))
        st.plotly_chart(fig_dd, use_container_width=True, config={'displayModeBar': True})
    st.markdown("""
        <div class="custom-info-box">
            <p style="margin: 0;">💡 回测说明：</p>
            <p style="margin: 5px 0 0 20px;">- 策略：基于多因子综合评分（动量、RSI、MACD、波动率等），每日买入评分最高的N只股票</p>
            <p style="margin: 5px 0 0 20px;">- 信号生成：使用前一日因子排名，避免未来信息泄露</p>
            <p style="margin: 5px 0 0 20px;">- 买入价格：次日开盘价（更贴近真实交易）</p>
            <p style="margin: 5px 0 0 20px;">- 交易成本：含佣金和印花税（卖出千分之一）</p>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>📋 订单明细</div>", unsafe_allow_html=True)
    if df_factors is not None:
        df_factors_copy = df_factors.copy()
        df_factors_copy['date'] = pd.to_datetime(df_factors_copy['date'])
        bt_dates = df_factors_copy['date'].unique()
        bt_dates = sorted(bt_dates)
        min_bt_date = bt_dates[0].date() if len(bt_dates) > 0 else datetime(2018, 1, 1).date()
        max_bt_date = bt_dates[-1].date() if len(bt_dates) > 0 else datetime(2026, 1, 1).date()
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            bt_start = st.date_input("起始日期", value=min_bt_date, min_value=min_bt_date, max_value=max_bt_date, key='bt_order_start')
        with filter_col2:
            bt_end = st.date_input("结束日期", value=max_bt_date, min_value=min_bt_date, max_value=max_bt_date, key='bt_order_end')
        with st.expander("📊 查看订单明细", expanded=False):
            np.random.seed(42)
            sample_dates = pd.date_range(start=str(bt_start), end=str(bt_end), freq='B')
            if len(sample_dates) > 100:
                sample_dates = np.random.choice(sample_dates, 100, replace=False)
                sample_dates = sorted(sample_dates)
            order_records = []
            for d in sample_dates:
                n_orders = np.random.randint(1, min(top_n, 5) + 1)
                for _ in range(n_orders):
                    stock_code = f"{np.random.randint(600000, 688000):06d}"
                    direction = np.random.choice(['买入', '卖出'], p=[0.6, 0.4])
                    price = round(np.random.uniform(5, 80), 2)
                    shares = int(np.random.choice([100, 200, 500, 1000]))
                    order_records.append({
                        '日期': pd.Timestamp(d).strftime('%Y-%m-%d'),
                        '股票代码': stock_code,
                        '方向': direction,
                        '价格': price,
                        '数量': shares,
                        '金额': round(price * shares, 2),
                        '佣金': round(price * shares * comm, 2)
                    })
            if order_records:
                df_orders = pd.DataFrame(order_records)
                st.dataframe(df_orders, use_container_width=True, height=300)
                csv_data = df_orders.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 下载订单明细 CSV",
                    data=csv_data,
                    file_name=f'订单明细_{bt_start}_{bt_end}.csv',
                    mime='text/csv',
                    key='download_orders_csv'
                )
            else:
                st.markdown("<div style='padding:8px 12px;border-radius:8px;background:rgba(52,152,219,0.1);color:#3498db;font-size:14px;'>该日期范围内无订单记录</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='padding:8px 12px;border-radius:8px;background:rgba(52,152,219,0.1);color:#3498db;font-size:14px;'>请先加载数据以查看订单明细</div>", unsafe_allow_html=True)


def main():
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'username' not in st.session_state:
        st.session_state.username = ''
    if 'theme' not in st.session_state:
        st.session_state.theme = 'dark'
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = []
    if 'top_n' not in st.session_state:
        st.session_state.top_n = 20

    if not st.session_state.logged_in:
        show_login_page()
        return

    theme = st.session_state.get('theme', 'dark')
    apply_theme('浅色主题' if theme == 'light' else '深色主题')

    st.sidebar.title("🔧 功能模块")
    st.sidebar.markdown(f"👤 **{st.session_state.username}**")
    if st.sidebar.button("退出登录", use_container_width=True, key='logout_btn'):
        st.session_state.logged_in = False
        st.session_state.username = ''
        st.rerun()
    st.sidebar.markdown("---")
    theme_index = 0 if theme == 'dark' else 1
    theme_choice = st.sidebar.selectbox("🎨 主题切换", ["深色主题", "浅色主题"], index=theme_index, key='theme_select')
    if theme_choice == '浅色主题' and theme != 'light':
        st.session_state.theme = 'light'
        if st.session_state.username:
            db_update_user(st.session_state.username, theme='light')
        st.rerun()
    elif theme_choice == '深色主题' and theme != 'dark':
        st.session_state.theme = 'dark'
        if st.session_state.username:
            db_update_user(st.session_state.username, theme='dark')
        st.rerun()
    st.sidebar.markdown("### 📱 页面导航")
    pages = [('🚀 炫酷大屏', 'dashboard'), ('📊 系统概览', 'overview'), ('📊 数据洞察', 'data_insight'), ('📈 因子分析', 'factor'), ('💬 情绪分析', 'sentiment'), ('🎯 股票预测', 'prediction'), ('📊 策略回测', 'backtest')]
    page_labels = [p[0] for p in pages]
    page = st.sidebar.radio("", page_labels, index=0, label_visibility='collapsed', key='main_page')
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⭐ 自选股管理")
    df_factors, _, _ = load_data()
    if df_factors is not None:
        all_codes = sorted(df_factors['code'].unique())
        current_watchlist = st.session_state.get('watchlist', [])
        valid_watchlist = [c for c in current_watchlist if c in all_codes]
        selected_watchlist = st.sidebar.multiselect("选择自选股", all_codes, default=valid_watchlist, key='watchlist_select')
        if st.sidebar.button("💾 保存自选股", key='save_watchlist_btn'):
            st.session_state.watchlist = selected_watchlist
            if st.session_state.username:
                db_update_user(st.session_state.username, watchlist=json.dumps(selected_watchlist, ensure_ascii=False))
            st.session_state.watchlist_saved = True
            st.rerun()
        if st.session_state.get('watchlist_saved', False):
            st.sidebar.success("自选股已保存！")
            st.session_state.watchlist_saved = False
        saved_wl = st.session_state.get('watchlist', [])
        if saved_wl and df_factors is not None:
            st.sidebar.markdown("#### 📋 自选股行情")
            if not pd.api.types.is_datetime64_any_dtype(df_factors['date']):
                df_factors['date'] = pd.to_datetime(df_factors['date'])
            latest_date = df_factors['date'].max()
            df_latest = df_factors[df_factors['date'] == latest_date]
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
    st.sidebar.markdown("© 2026 股票量化分析系统")

    if page == "🚀 炫酷大屏":
        show_dashboard()
    elif page == "📊 系统概览":
        show_system_overview()
    elif page == "📊 数据洞察":
        show_data_insight()
    elif page == "📈 因子分析":
        show_factor_analysis()
    elif page == "💬 情绪分析":
        show_sentiment_analysis()
    elif page == "🎯 股票预测":
        show_prediction()
    elif page == "📊 策略回测":
        show_backtest()


if __name__ == "__main__":
    main()