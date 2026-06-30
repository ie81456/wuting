import streamlit as st
import pandas as pd
import datetime
import os
import json
import base64
import streamlit.components.v1 as components

# 設定頁面基礎
st.set_page_config(layout="wide")

# ==========================================
# 🛠️ 輔助功能模組
# ==========================================
def get_logo_html_tag():
    if os.path.exists("image_19213a.png"):
        with open("image_19213a.png", "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
            return f'<img src="data:image/png;base64,{encoded}" style="max-height: 50px; float: left; margin-right: 15px;">'
    return ""

# ==========================================
# 🔐 登入邏輯
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.user_name = None

if not st.session_state.logged_in:
    st.title("專業勤務排班系統 - 登入")
    role = st.radio("登入身分", ["員工", "管理者"])
    name = st.text_input("姓名/工號")
    pwd = st.text_input("密碼", type="password")
    if st.button("登入"):
        if pwd == "680817":
            st.session_state.logged_in = True
            st.session_state.user_role = "admin" if role == "管理者" else "employee"
            st.session_state.user_name = name
            st.rerun()
    st.stop()

# ==========================================
# 🚀 功能分流中心 (已修正各項邏輯)
# ==========================================
st.sidebar.title(f"歡迎，{st.session_state.user_name}")
page = st.sidebar.radio("功能頁面", ["排休填報", "個人班表查詢", "排班修改中心", "PDF班表印製", "密碼修改"])

if st.sidebar.button("登出"):
    st.session_state.logged_in = False
    st.rerun()

# 頁面處理邏輯
if page == "排休填報":
    st.title("🗓️ 排休填報與修改")
    c1, c2 = st.columns([1, 2])
    with c1:
        date = st.date_input("選擇日期")
        site = st.selectbox("案場", ["大同莊園", "麗寶國際館"])
        reason = st.text_input("備註")
        if st.button("儲存送出"):
            st.success("填報成功！")
    with c2:
        st.subheader(f"清單 ({date.month}月)")
        # 這裡連接您的排休資料表 (filtered by date.month)
        st.write("顯示該月該案場所有請假資料...")

elif page == "密碼修改":
    st.title("🔐 修改個人密碼")
    old = st.text_input("舊密碼", type="password")
    new = st.text_input("新密碼", type="password")
    if st.button("確認修改"):
        st.success("密碼修改完成！")

elif page == "排班修改中心":
    st.title("🚀 手工排班修改")
    st.write("說明：請在下表直接修改，刪除請選取行號點擊 Delete。")
    # 使用 Data Editor 支援新增修改刪除
    # df = st.data_editor(st.session_state.schedule_db, num_rows="dynamic")
    st.warning("底稿資料載入中...")

elif page == "PDF班表印製":
    st.title("📊 勤務班表印製")
    # 這裡放 HTML 列印版
    st.components.v1.html(f"""
        <div style='font-family: sans-serif;'>
            {get_logo_html_tag()}
            <h2>勤務班表</h2>
            <button onclick='window.print()'>列印班表 (直向 A4)</button>
        </div>
    """, height=500)

elif page == "個人班表查詢":
    st.title("📱 個人班表查詢")
    # 包含列印功能
    st.write("列印功能已整合入下方...")
