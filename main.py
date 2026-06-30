import streamlit as st
import pandas as pd
import datetime
import os
import json
import base64
from google.oauth2.service_account import Credentials
import gspread

# 設定頁面基礎
st.set_page_config(page_title="魔力休閒運動事業股份有限公司 - 勤務系統", layout="wide")

# 基礎檔案路徑
CREDS_FILE = 'google_creds.json'
LOGO_FILE = 'image_19213a.png'
REMARKS_FILE = 'remarks.json'
COMPANY_NAME = "魔力休閒運動事業股份有限公司"

# 初始化 GSpread 連接
def init_gspread():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        try:
            creds_dict = json.loads(st.secrets["gcp_service_account"]["json_creds"])
            return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=scope))
        except: return None
    return None

gc = init_gspread()

# 載入雲端資料
def load_data():
    if not gc: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    # 這裡為簡化版結構，請確保 Sheet ID 正確
    return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# ==========================================
# 🔐 登入邏輯 (強制最優先載入)
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None

def login_screen():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(f"<h2 style='text-align: center;'>{COMPANY_NAME}<br>專業勤務排班系統</h2>", unsafe_allow_html=True)
        st.markdown("---")
        
        # 管理者密碼登入
        admin_pwd = st.text_input("請輸入系統管理密碼", type="password")
        if st.button("👑 登入系統", use_container_width=True, type="primary"):
            if admin_pwd == "680817":
                st.session_state.logged_in = True
                st.session_state.user_role = "admin"
                st.rerun()
            else:
                st.error("❌ 密碼錯誤！")

if not st.session_state.logged_in:
    login_screen()
    st.stop()

# ==========================================
# 📊 已登入後的功能主畫面
# ==========================================
st.sidebar.title("功能選單")
if st.sidebar.button("🚪 登出系統"):
    st.session_state.logged_in = False
    st.rerun()

st.title("歡迎使用系統")
st.success("您已成功登入！")
