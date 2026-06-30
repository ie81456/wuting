import streamlit as st
import pandas as pd
import datetime

# 基礎設定
st.set_page_config(layout="wide")

# 登入機制
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("系統登入")
    pwd = st.text_input("輸入密碼", type="password")
    if st.button("登入"):
        if pwd == "680817":
            st.session_state.logged_in = True
            st.rerun()
    st.stop()

# 導航選單 (功能全恢復)
menu = ["員工基本資料", "案場基本資料", "線上排休", "自動排班", "班表印製", "個人班表"]
page = st.sidebar.radio("功能選單", menu)

if st.sidebar.button("登出"):
    st.session_state.logged_in = False
    st.rerun()

# 頁面內容
st.title(f"目前頁面: {page}")

# 測試：顯示一個最基本的資料表 (證明系統已恢復執行)
if page == "員工基本資料":
    st.write("員工資料表")
    st.dataframe(pd.DataFrame({"姓名": ["範例員工"], "工號": ["001"]}))

elif page == "班表印製":
    st.write("這裡將使用原生的 Streamlit 表格來顯示，請點擊瀏覽器的「列印」功能來列印 PDF，這樣最穩定。")
    # 將您的範例資料轉為 Dataframe 顯示
    st.dataframe(pd.DataFrame({
        "日期": list(range(1, 32)),
        "休假": "",
        "星期": "三",
        "班別/人員": "沈如苹(救生員)"
    }))
