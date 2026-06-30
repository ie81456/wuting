import streamlit as st
import pandas as pd
import datetime
import os
import json
import io
import re
import base64
from google.oauth2.service_account import Credentials
import gspread

st.set_page_config(page_title="魔力休閒運動事業股份有限公司 - 專業勤務排班系統", layout="wide")

# ==========================================
# 🌐 Google Sheets API 與雲端資料庫連動設定
# ==========================================
SHEET_IDS = {
    'workers': '1v_iY7d8NIIU7DfcQoTHZWN2YdKzN7lff62nSF7RNSRQ',
    'sites': '1py1FaHqSbKFHSVh-TJ4-oTynlui-PEBfvDFQwJfaxmU',
    'leave_requests': '1gzogpuHPfP0ksvImtB8mkFmWn-WuqhyhAUyyhh8Wlyk',
    'schedule': '1Q16YmL40qQ2t3QmzmGkzpW6iYQ5sIbDe_wypcSWP-aQ'
}

CREDS_FILE = 'google_creds.json'
LOGO_FILE = 'image_19213a.png'
REMARKS_FILE = 'remarks.json'
COMPANY_NAME = "魔力休閒運動事業股份有限公司"

JOB_ROLES = ["會館主任", "救生員", "男湯人員", "女湯人員", "物業人員", "代班人員"]

def get_logo_html_tag():
    if os.path.exists(LOGO_FILE):
        try:
            with open(LOGO_FILE, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode()
            # 配合整體版面放大，微調 LOGO 最大高度至 65px
            return f'<img src="data:image/png;base64,{encoded_string}" style="max-height: 65px; float: left; margin-right: 18px; margin-top: 5px;">'
        except:
            return ""
    return ""

def load_remarks():
    if os.path.exists(REMARKS_FILE):
        try:
            with open(REMARKS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}
    return {}

def save_remarks(data):
    with open(REMARKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

remarks_db = load_remarks()

def clean_date_string(d_str):
    if not d_str or str(d_str).strip() == "" or str(d_str).lower() == "none":
        return ""
    s = str(d_str).strip().replace("/", "-")
    match_ad = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if match_ad:
        return f"{int(match_ad.group(1))}-{int(match_ad.group(2)):02d}-{int(match_ad.group(3)):02d}"
    return s

def init_gspread_system():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        try:
            secrets_ref = st.secrets["gcp_service_account"]
            creds_dict = json.loads(secrets_ref["json_creds"]) if "json_creds" in secrets_ref else dict(secrets_ref)
            return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=scope))
        except: st.stop()
    if os.path.exists(CREDS_FILE):
        try: return gspread.authorize(Credentials.from_service_account_file(CREDS_FILE, scopes=scope))
        except: pass
    st.stop()

gc = init_gspread_system()

def load_cloud_data(sheet_key, columns):
    if gc is None: return pd.DataFrame(columns=columns)
    try:
        sh = gc.open_by_key(SHEET_IDS[sheet_key])
        worksheet = sh.get_worksheet(0)
        raw_rows = worksheet.get_all_values()
        if not raw_rows: return pd.DataFrame(columns=columns)
        
        header = [str(h).strip() for h in raw_rows[0]]
        df_raw = pd.DataFrame(raw_rows[1:], columns=header)
        df_str = df_raw.loc[:, ~df_raw.columns.duplicated()].astype(str)
        
        if '案場名稱' in df_str.columns: df_str['案場名稱'] = df_str['案場名稱'].str.strip()
        if '員工姓名' in df_str.columns: df_str['員工姓名'] = df_str['員工姓名'].str.strip()
        if '日期' in df_str.columns: df_str['日期'] = df_str['日期'].apply(clean_date_string)
            
        for col in columns:
            if col not in df_str.columns: df_str[col] = ""
            
        if sheet_key == 'schedule':
            df_str['派駐職位'] = df_str.apply(
                lambda r: "救生員" if ("大同莊園" in str(r['案場名稱']) and (not r['派駐職位'] or str(r['派駐職位']).strip() == "" or str(r['派駐職位']).lower() == "none")) else r['派駐職位'], 
                axis=1
            )
        return df_str[columns]
    except: 
        return pd.DataFrame(columns=columns)

def save_cloud_data(df, sheet_key, columns):
    if gc is None: return False
    try:
        sh = gc.open_by_key(SHEET_IDS[sheet_key])
        worksheet = sh.get_worksheet(0)
        worksheet.clear()
        df_save = df[columns].copy().fillna("").astype(str)
        data_to_save = [df_save.columns.values.tolist()] + df_save.values.tolist()
        worksheet.update(values=data_to_save, range_name="A1")
        return True
    except: return False

# ==========================================
# ⚡ Session State 狀態與關鍵時間變數定義
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.current_user_name = None

if 'data_loaded' not in st.session_state:
    with st.spinner("⚡ 正在安全連線至 Google 雲端資料庫..."):
        st.session_state.workers_db = load_cloud_data('workers', ['員工編號', '姓名', '行動電話', '住家電話', '通訊地址', '派駐案場', '登入密碼'])
        st.session_state.sites_db = load_cloud_data('sites', ['案場名稱', '案場地址', '案場性質', '案場聯絡人姓名', '案場聯絡人電話', '時段一_上', '時段一_下', '時段二_上', '時段二_下', '時段三_上', '時段三_下', '注意事項'])
        st.session_state.leave_requests_db = load_cloud_data('leave_requests', ['日期', '案場名稱', '員工姓名', '請假時段', '假別性質'])
        st.session_state.schedule_db = load_cloud_data('schedule', ['日期', '案場名稱', '員工姓名', '班段名稱', '時段區間', '時源工時', '派駐職位'])
        st.session_state.data_loaded = True

today = datetime.date.today()
first_day_of_next_month = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
default_next_year = first_day_of_next_month.year
default_next_month = first_day_of_next_month.month

# 員工名冊依據「員工編號」由小到大精準排序
worker_options = []
if not st.session_state.workers_db.empty:
    w_df = st.session_state.workers_db.copy()
    w_df['sort_id'] = pd.to_numeric(w_df['員工編號'], errors='coerce').fillna(999)
    w_df = w_df.sort_values(by='sort_id').reset_index(drop=True)
    st.session_state.workers_db = w_df.drop(columns=['sort_id'])
    for idx, r in st.session_state.workers_db.iterrows():
        worker_options.append(f"[{str(r['員工編號']).strip()}] {str(r['姓名']).strip()}")

# 🔐 系統管理大廳 (登入密碼 680817)
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(f"<h2 style='text-align: center;'>{COMPANY_NAME}<br>專業勤務排班系統</h2>", unsafe_allow_html=True)
        st.markdown("---")
        tab_emp, tab_admin = st.tabs(["👥 員工專區登入", "👑 系統管理者登入"])
        with tab_emp:
            if worker_options:
                login_select = st.selectbox("請選擇您的員工編號與姓名", worker_options)
                login_name = login_select.split("] ")[1].strip() if "] " in login_select else login_select
                login_pwd = st.text_input("請輸入登入密碼", type="password", key="emp_pwd_input")
                if st.button("🚪 驗證並登入", use_container_width=True, type="primary"):
                    worker_row = st.session_state.workers_db[st.session_state.workers_db['姓名'] == login_name].iloc[0]
                    valid_pwd = str(worker_row.get('登入密碼', '')).strip() if str(worker_row.get('登入密碼', '')).strip() else str(worker_row.get('行動電話', '')).strip()
                    if login_pwd == valid_pwd and login_pwd != "":
                        st.session_state.logged_in = True
                        st.session_state.user_role = "employee"
                        st.session_state.current_user_name = login_name
                        st.rerun()
                    else: st.error("❌ 密碼錯誤！")
        with tab_admin:
            admin_pwd = st.text_input("請輸入最高管理者密碼", type="password", key="admin_pwd_input")
            if st.button("👑 管理者登入", use_container_width=True, type="primary"):
                if admin_pwd == "680817":
                    st.session_state.logged_in = True
                    st.session_state.user_role = "admin"
                    st.session_state.current_user_name = "系統管理者"
                    st.rerun()
                else: st.error("❌ 密碼錯誤！")
    st.stop()

is_admin = (st.session_state.user_role == "admin")
if is_admin:
    menu_options = ["工作者基本資料設定", "案場基本資料設定", "🗓️ 管理者控制台：填報排休與手工修改", "🚀 管理者控制台：自動鋪底稿與微調", "📊 班表大印製中心：正式 PDF 產出", "📱 員工專專區：個人班表出勤直式查詢"]
else:
    menu_options = ["🗓️ 員工專區：線上登記請假排休", "📱 員工專區：個人班表出勤直式查詢", "🔐 員工專區：修改個人登入密碼"]

page = st.sidebar.radio("請選擇功能頁面：", menu_options)
page_clean = page.strip()

if st.sidebar.button("🔄 強制同步最新雲端資料", use_container_width=True):
    if 'data_loaded' in st.session_state: del st.session_state['data_loaded']
    st.rerun()

if st.sidebar.button("🚪 安全登出系統", type="primary", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

# 基礎分流頁面
if "工作者基本資料設定" in page_clean:
    st.title("⚙️ 工作者基本資料設定")
    st.dataframe(st.session_state.workers_db, use_container_width=True, hide_index=True)
elif "案場基本資料設定" in page_clean:
    st.title("🏢 案場基本資料設定")
    st.dataframe(st.session_state.sites_db, use_container_width=True, hide_index=True)
elif "填報排休" in page_clean or "線上登記請假排休" in page_clean:
    st.title("🗓️ 線上填報排休與手工修改")
    st.dataframe(st.session_state.leave_requests_db, use_container_width=True, hide_index=True)
elif "自動鋪底稿" in page_clean:
    st.title("🚀 自動週期底稿鋪設與職位精準抽換控制台")
    st.dataframe(st.session_state.schedule_db, use_container_width=True, hide_index=True)

# ==========================================
# 📊 正式印製中心 (橫式總班表 - A4 滿版放大優化版)
# ==========================================
elif "班表大印製中心" in page_clean:
    st.title("📊 勤務班表 PDF 印製與備註輸入中心")
    c_p1, c_p2, c_p3 = st.columns(3)
    with c_p1: sel_year = st.selectbox("設定年份：", [2026, 2027], index=0)
    with c_p2: sel_month = st.selectbox("設定月份：", list(range(1, 13)), index=default_next_month - 1)
    with c_p3: sel_site = st.selectbox("設定目標案場：", st.session_state.sites_db['案場名稱'].tolist() if not st.session_state.sites_db.empty else ["大同莊園"])
    
    try: days_count = ((datetime.date(sel_year, sel_month + 1, 1) if sel_month < 12 else datetime.date(sel_year + 1, 1, 1)) - datetime.timedelta(days=1)).day
    except: days_count = 31
    
    week_mapping = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}
    rows_list = []
    
    s_db = st.session_state.schedule_db.copy()
    l_db = st.session_state.leave_requests_db.copy()
    
    for d in range(1, days_count + 1):
        loop_date = datetime.date(sel_year, sel_month, d)
        d_str = loop_date.strftime('%Y-%m-%d')
        w_name = week_mapping[loop_date.weekday()]
        
        day_site_data = s_db[(s_db['日期'] == d_str) & (s_db['案場名稱'].str.strip() == sel_site.strip())]
        
        leave_text = ""
        if not l_db.empty:
            day_leave = l_db[(l_db['日期'] == d_str) & (l_db['案場名稱'].str.strip() == sel_site.strip())]
            if not day_leave.empty: 
                leave_text = "、".join([f"{r['員工姓名'].strip()} ({str(r['請假時段']).replace('整天全時段', '全天班')}休)" for _, r in day_leave.iterrows()])
        
        worker_shift_text = ""
        if not day_site_data.empty:
            grouped_roles = []
            for r_name, group in day_site_data.groupby('派駐職位'):
                unique_names = list(set([n.strip() for n in group['員工姓名'].tolist() if n.strip()]))
                names_combined = " / ".join(unique_names)
                final_role = "救生員" if (not r_name or str(r_name).strip() == "" or str(r_name).lower() == "none") else str(r_name).strip()
                grouped_roles.append(f"{names_combined} ({final_role})")
            worker_shift_text = " ｜ ".join(grouped_roles)
        
        date_key = f"{sel_site.strip()}_{sel_year}-{sel_month:02d}-{d:02d}"
        rows_list.append({"日期": f"{d}", "休假": leave_text, "星期": w_name, "班別 / 勤務人員": worker_shift_text, "備註": remarks_db.get(date_key, "")})
        
    final_print_df = pd.DataFrame(rows_list)
    edited_df = st.data_editor(final_print_df, use_container_width=True, disabled=["日期", "休假", "星期", "班別 / 勤務人員"], hide_index=True)
    
    if st.button("💾 儲存表格中的備註資料", type="secondary"):
        for idx, row in edited_df.iterrows():
            remarks_db[f"{sel_site.strip()}_{sel_year}-{sel_month:02d}-{int(row['日期']):02d}"] = str(row['備註'])
        save_remarks(remarks_db)
        st.success("✅ 備註資料已成功儲存！")
        
    html_table_rows = ""
    for r in edited_df.to_dict(orient='records'):
        html_table_rows += f"""
        <tr>
            <td style='text-align:center; padding:10px 6px; border:1px solid #000;'>{r['日期']}</td>
            <td style='padding:10px 8px; border:1px solid #000; color:red;'>{r['休假']}</td>
            <td style='text-align:center; padding:10px 6px; border:1px solid #000;'>{r['星期']}</td>
            <td style='padding:10px 8px; border:1px solid #000; font-weight:bold;'>{r['班別 / 勤務人員']}</td>
            <td style='padding:10px 8px; border:1px solid #000;'>{r['備註']}</td>
        </tr>
        """
    
    site_notes_html = ""
    s_rows = st.session_state.sites_db[st.session_state.sites_db['案場名稱'] == sel_site.strip()]
    if not s_rows.empty and s_rows.iloc[0]['注意事項']:
        notes_lines = str(s_rows.iloc[0]['注意事項']).split('\n')
        # 🌟 注意事項字體放大至 15px
        site_notes_html += "<div style='margin-top:20px; font-size:15px; font-family:\"Microsoft JhengHei\"; line-height:1.6; color:#000; text-align:left;'>"
        site_notes_html += "<b style='font-size:16px;'>填表說明/注意事項：</b><br>"
        for line in notes_lines:
            if line.strip():
                site_notes_html += f"<div style='margin-left:5px;'>{line}</div>"
        site_notes_html += "</div>"
        
    logo_tag = get_logo_html_tag()
    full_html_document = f"""
    <style>
        @media print {{
            body {{ background: #fff; color: #000; padding: 0; margin: 0; }}
            .no-print {{ display: none !important; }}
            #printArea {{ width: 100%; padding: 0 !important; }}
            /* 橫式班表自動導向橫向列印 */
            @page {{ size: A4 landscape; margin: 1cm; }}
        }}
    </style>
    {html_table_rows if False else ""}
    <div id='printArea' style='font-family:"Microsoft JhengHei", "Arial", sans-serif; padding:10px; background:#fff; color:#000; width:100%;box-sizing:border-box;'>
        <div style='width:100%; overflow:hidden; margin-bottom:15px;'>
            {logo_tag}
            <div style='float:left; padding-top:5px;'>
                <h2 style='margin:0; font-size:26px; font-weight:bold; letter-spacing:1px;'>{COMPANY_NAME}</h2>
                <h3 style='margin:4px 0 0 0; font-size:20px; color:#222;'>{sel_site} {sel_year}年{sel_month:02d}月份 勤務班表</h3>
            </div>
        </div>
        <table style='width:100%; border-collapse:collapse; background:#fff; font-size:16px; clear:both;'>
            <thead>
                <tr style='background-color:#f2f2f2; height:40px;'>
                    <th style='width:6%; border:1px solid #000; padding:10px;'>日期</th>
                    <th style='width:22%; border:1px solid #000; padding:10px;'>休假</th>
                    <th style='width:6%; border:1px solid #000; padding:10px;'>星期</th>
                    <th style='width:46%; border:1px solid #000; padding:10px;'>班別 / 勤務人員</th>
                    <th style='width:20%; border:1px solid #000; padding:10px;'>備註</th>
                </tr>
            </thead>
            <tbody>
                {html_table_rows}
            </tbody>
        </table>
        {site_notes_html}
    </div>
    <div class='no-print' style='text-align:center; margin-top:20px;'>
        <button onclick='window.print();' style='padding:14px 40px; font-size:18px; font-weight:bold; background-color:#1E88E5; color:white; border:none; border-radius:5px; cursor:pointer; box-shadow: 0px 3px 6px rgba(0,0,0,0.2);'>🖨️ 啟動 A4 橫式班表放大列印中心</button>
    </div>
    """
    st.markdown("---")
    st.subheader("📋 橫式總班表 A4 滿版放大預覽")
    st.components.v1.html(full_html_document, height=720, scrolling=True)

# ==========================================
# 📱 員工個人出勤直式查詢 (直式 A4 滿版放大版)
# ==========================================
elif "個人班表出勤直式查詢" in page_clean:
    st.title("📱 員工個人出勤班表直式查詢與 PDF 產出")
    
    current_worker = st.session_state.current_user_name if st.session_state.current_user_name else "系統管理者"
    
    if worker_options:
        selected_emp_format = st.selectbox("請核對或選擇欲查詢的員工工號及姓名：", worker_options)
        target_emp = selected_emp_format.split("] ")[1].strip() if "] " in selected_emp_format else selected_emp_format
    else:
        target_emp = st.text_input("輸入查詢員工姓名：", value=current_worker)
        
    q_year = st.selectbox("選擇查詢年份：", [2026, 2027], index=0)
    q_month = st.selectbox("選擇查詢月份：", list(range(1, 13)), index=default_next_month - 1)
    
    s_db = st.session_state.schedule_db.copy()
    
    if not s_db.empty:
        s_db['Month_Int'] = s_db['日期'].apply(lambda x: int(x.split('-')[1]) if '-' in str(x) else 0)
        s_db['Year_Int'] = s_db['日期'].apply(lambda x: int(x.split('-')[0]) if '-' in str(x) else 0)
        
        emp_records = s_db[(s_db['員工姓名'].str.strip() == target_emp.strip()) & (s_db['Year_Int'] == q_year) & (s_db['Month_Int'] == q_month)]
        
        if not emp_records.empty:
            sorted_records = emp_records[['日期', '案場名稱', '班段名稱', '時段區間', '派駐職位']].sort_values(by='日期').reset_index(drop=True)
            
            grouped_rows_html = ""
            preview_list = []
            distinct_sites = []
            
            for (date_val, site_val), group in sorted_records.groupby(['日期', '案場名稱']):
                shifts_combined = "<br>".join(group['班段名稱'].tolist())
                intervals_combined = "<br>".join(group['時段區間'].tolist())
                roles_combined = "<br>".join(list(set(group['派駐職位'].tolist())))
                
                if site_val not in distinct_sites:
                    distinct_sites.append(site_val)
                
                preview_list.append({
                    "出勤日期": date_val,
                    "指派案場": site_val,
                    "班段": shifts_combined.replace('<br>', ' / '),
                    "時間區間": intervals_combined.replace('<br>', ' / '),
                    "擔任職位": roles_combined.replace('<br>', ' / ')
                })
                
                grouped_rows_html += f"""
                <tr>
                    <td style='text-align:center; padding:12px; border:1px solid #000; vertical-align:middle;'>{date_val}</td>
                    <td style='padding:12px; border:1px solid #000; vertical-align:middle;'>{site_val}</td>
                    <td style='text-align:center; padding:12px; border:1px solid #000; vertical-align:middle;'>{shifts_combined}</td>
                    <td style='text-align:center; padding:12px; border:1px solid #000; vertical-align:middle;'>{intervals_combined}</td>
                    <td style='padding:12px; border:1px solid #000; font-weight:bold; vertical-align:middle;'>{roles_combined}</td>
                </tr>
                """
            
            st.success(f"📋 已優化【{target_emp}】當月直式班表為『一天一列』明細：")
            st.dataframe(pd.DataFrame(preview_list), use_container_width=True, hide_index=True)
            
            emp_notes_html = ""
            if distinct_sites:
                emp_s_rows = st.session_state.sites_db[st.session_state.sites_db['案場名稱'].isin(distinct_sites)]
                if not emp_s_rows.empty:
                    # 🌟 直式注意事項也同步放大
                    emp_notes_html += "<div style='margin-top:20px; font-size:14px; font-family:\"Microsoft JhengHei\"; line-height:1.6; color:#000; text-align:left;'>"
                    emp_notes_html += "<b style='font-size:15px;'>指派案場注意事項說明：</b>"
                    for _, s_row in emp_s_rows.iterrows():
                        if s_row['注意事項']:
                            emp_notes_html += f"<div style='margin-top:6px; font-weight:bold; color:#1E88E5;'>【{s_row['案場名稱']}】</div>"
                            for line in str(s_row['注意事項']).split('\n'):
                                if line.strip():
                                    emp_notes_html += f"<div style='margin-left:10px;'>{line}</div>"
                    emp_notes_html += "</div>"
            
            logo_tag = get_logo_html_tag()
            emp_html_doc = f"""
            <style>
                @media print {{
                    body {{ background: #fff; color: #000; padding: 0; margin: 0; }}
                    .no-print {{ display: none !important; }}
                    #printArea {{ width: 100%; padding: 0 !important; }}
                    @page {{ size: A4 portrait; margin: 1.2cm; }}
                }}
            </style>
            <div id='printArea' style='font-family:"Microsoft JhengHei", "Arial", sans-serif; padding:10px; background:#fff; color:#000;'>
                <div style='width:100%; overflow:hidden; margin-bottom:15px;'>
                    {logo_tag}
                    <div style='float:left; padding-top:5px;'>
                        <h3 style='margin:0; font-size:24px; font-weight:bold; letter-spacing:1px;'>{COMPANY_NAME}</h3>
                        <h4 style='margin:4px 0 0 0; font-size:18px; color:#222;'>同仁【{target_emp}】{q_year}年{q_month:02d}月份 個人出勤直式明細表</h4>
                    </div>
                </div>
                <table style='width:100%; border-collapse:collapse; background:#fff; font-size:15px; clear:both;'>
                    <thead>
                        <tr style='background-color:#f5f5f5; height:38px;'>
                            <th style='border:1px solid #000; padding:10px; width:15%;'>出勤日期</th>
                            <th style='border:1px solid #000; padding:10px; width:25%;'>指派案場</th>
                            <th style='border:1px solid #000; padding:10px; width:20%;'>班段</th>
                            <th style='border:1px solid #000; padding:10px; width:25%;'>時間區間</th>
                            <th style='border:1px solid #000; padding:10px; width:15%;'>擔任職位</th>
                        </tr>
                    </thead>
                    <tbody>
                        {grouped_rows_html}
                    </tbody>
                </table>
                {emp_notes_html}
            </div>
            <div class='no-print' style='text-align:center; margin-top:20px;'>
                <button onclick='window.print();' style='padding:12px 35px; font-size:16px; font-weight:bold; background-color:#4CAF50; color:white; border:none; border-radius:4px; cursor:pointer; box-shadow: 0px 2px 5px rgba(0,0,0,0.2);'>🖨️ 啟動 A4 直式個人班表放大列印</button>
            </div>
            """
            st.markdown("---")
            st.subheader("📄 直式個人班表 A4 滿版放大預覽")
            st.components.v1.html(emp_html_doc, height=580, scrolling=True)
        else:
            st.info(f"ℹ️ 雲端資料庫中目前尚無【{target_emp}】在 {q_year} 年 {q_month} 月的出勤記錄。")
