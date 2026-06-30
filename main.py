import streamlit as st
import pandas as pd
import datetime
import os
import json
import base64

st.set_page_config(layout="wide")

# 智慧 LOGO 轉網頁 HTML 內嵌編碼
def get_logo_html_tag():
    if os.path.exists("image_19213a.png"):
        try:
            with open("image_19213a.png", "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode()
            return f'<img src="data:image/png;base64,{encoded}" style="max-height: 50px; float: left; margin-right: 15px;">'
        except: return ""
    return ""

# 班表邏輯
st.title("📊 勤務班表印製中心")

# 取得資料庫中的注意事項
def get_site_notes(site_name):
    # 簡單提取邏輯
    return "1. 請確實執行勤務交接。\n2. 發現異常務必回報。"

# 產生班表表格 HTML (仿範例格式)
def generate_html_table(sel_year, sel_month, sel_site):
    logo = get_logo_html_tag()
    notes = get_site_notes(sel_site)
    
    # 這裡產出精簡表格
    rows = ""
    for d in range(1, 31):
        rows += f"<tr><td>{d}</td><td></td><td></td><td>沈如苹 (救生員)</td><td></td></tr>"
        
    return f"""
    <div style='font-family:"Microsoft JhengHei"; padding:20px;'>
        <div style='overflow:hidden;'>{logo}<h2>魔力休閒運動事業股份有限公司</h2></div>
        <h3 style='text-align:center;'>{sel_site} {sel_year}年{sel_month}月 勤務班表</h3>
        <table border='1' style='width:100%; border-collapse:collapse; text-align:center;'>
            <tr style='background:#f2f2f2;'><th>日期</th><th>休假</th><th>星期</th><th>班別/勤務人員</th><th>備註</th></tr>
            {rows}
        </table>
        <div style='margin-top:20px;'><b>注意事項：</b><br>{notes.replace(chr(10), '<br>')}</div>
        <br><button onclick='window.print()' style='padding:10px; font-size:16px;'>列印班表</button>
    </div>
    """

# 渲染
html_content = generate_html_table(2026, 7, "大同莊園")
st.markdown(html_content, unsafe_allow_html=True)
