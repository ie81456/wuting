import streamlit as st
import pandas as pd
import datetime
import os
import json
import base64
import re
from google.oauth2.service_account import Credentials
import gspread
import streamlit.components.v1 as components

# 頁面基礎設定
st.set_page_config(page_title="魔力休閒運動事業股份有限公司 - 專業勤務排班系統", layout="wide")

# ==========================================
# 🌐 雲端資料庫與常數設定
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

# ==========================================
# 🛠️ 核心功能模組
# ==========================================
def get_logo_html_tag():
    if os.path.exists(LOGO_FILE):
        try:
            with open(LOGO_FILE, "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode()
            return f'<img src="data:image/png;base64,{encoded}" style="max-height: 55px;">'
        except: return ""
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
    if not d_str or str(d_str).strip() == "" or str(d_str).lower() == "none": return ""
    s = str(d_str).strip().replace("/", "-")
    match_ad = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if match_ad: return f"{int(match_ad.group(1))}-{int(match_ad.group(2)):02d}-{int(match_ad.group(3)):02d}"
    return s

def init_gspread_system():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            secrets_ref = st.secrets["gcp_service_account"]
            creds_dict = json.loads(secrets_ref["json_creds"]) if "json_creds" in secrets_ref else dict(secrets_ref)
            return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=scope))
    except: pass
    if os.path.exists(CREDS_FILE):
        try: return gspread.authorize(Credentials.from_service_account_file(CREDS_FILE, scopes=scope))
        except: pass
    return None

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
        if '日期' in df_str.columns: df_str['日期'] = df_str['日期'].apply(clean_date_string)
        for col in columns:
            if col not in df_str.columns: df_str[col] = ""
        return df_str[columns]
    except: return pd.DataFrame(columns=columns)

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
# ⚡ 狀態快取與預設變數
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.current_user_name = None

if 'data_loaded' not in st.session_state:
    with st.spinner("⚡ 正在安全連線並同步 Google 雲端資料庫..."):
        st.session_state.workers_db = load_cloud_data('workers', ['員工編號', '姓名', '行動電話', '住家電話', '通訊地址', '派駐案場', '登入密碼'])
        st.session_state.sites_db = load_cloud_data('sites', ['案場名稱', '案場地址', '案場性質', '案場聯絡人姓名', '案場聯絡人電話', '時段一_上', '時段一_下', '時段二_上', '時段二_下', '時段三_上', '時段三_下', '注意事項'])
        st.session_state.leave_requests_db = load_cloud_data('leave_requests', ['日期', '案場名稱', '員工姓名', '請假時段', '假別性質'])
        st.session_state.schedule_db = load_cloud_data('schedule', ['日期', '案場名稱', '員工姓名', '班段名稱', '時段區間', '時源工時', '派駐職位'])
        st.session_state.site_types = ["辦公大樓", "購物中心", "展覽館", "工廠園區", "其他"]
        st.session_state.data_loaded = True

if 'w_clear_key' not in st.session_state: st.session_state.w_clear_key = 0
if 's_clear_key' not in st.session_state: st.session_state.s_clear_key = 0

today = datetime.date.today()
first_day_of_next_month = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
default_next_year = first_day_of_next_month.year
default_next_month = first_day_of_next_month.month

worker_options = []
if not st.session_state.workers_db.empty:
    w_df = st.session_state.workers_db.copy()
    w_df['sort_id'] = pd.to_numeric(w_df['員工編號'], errors='coerce').fillna(999)
    w_df = w_df.sort_values(by='sort_id').reset_index(drop=True)
    st.session_state.workers_db = w_df.drop(columns=['sort_id'])
    for idx, r in st.session_state.workers_db.iterrows():
        worker_options.append(f"[{str(r['員工編號']).strip()}] {str(r['姓名']).strip()}")

# ==========================================
# 🔐 系統登入大廳
# ==========================================
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if os.path.exists(LOGO_FILE): st.image(LOGO_FILE, use_container_width=True)
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

# ==========================================
# 📍 系統選單
# ==========================================
is_admin = (st.session_state.user_role == "admin")
if is_admin:
    menu_options = ["員工基本資料設定", "案場基本資料設定", "🗓️ 線上填報排休與手工修改", "🚀 自動週期底稿鋪設與修改", "📊 班表大印製中心 (A4直向)", "📱 個人班表出勤直式查詢"]
else:
    menu_options = ["🗓️ 線上填報排休與手工修改", "📱 個人班表出勤直式查詢", "🔐 員工密碼自主變更中心"]

page = st.sidebar.radio("請選擇功能頁面：", menu_options)
page_clean = page.strip()

if st.sidebar.button("🔄 強制同步最新雲端資料", use_container_width=True):
    if 'data_loaded' in st.session_state: del st.session_state['data_loaded']
    st.rerun()

if st.sidebar.button("🚪 安全登出系統", type="primary", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

# ==========================================
# 🗂️ 1. 員工基本資料設定
# ==========================================
if "員工基本資料設定" in page_clean:
    st.title("⚙️ 員工基本資料設定")
    col_left, col_right = st.columns(2)
    with col_left:
        with st.form("worker_add_form"):
            st.subheader("➕ 新增員工資料")
            k = st.session_state.w_clear_key
            emp_id = st.text_input("員工編號", key=f"w_id_{k}")
            name = st.text_input("姓名", key=f"w_name_{k}")
            mobile_phone = st.text_input("行動電話", key=f"w_mob_{k}")
            home_phone = st.text_input("住家電話", key=f"w_home_{k}")
            address = st.text_input("通訊地址", key=f"w_addr_{k}")
            available_sites = st.session_state.sites_db['案場名稱'].tolist() if not st.session_state.sites_db.empty else []
            assigned_sites = st.multiselect("支持/派駐案場 (可複選)", options=available_sites, key=f"w_sites_{k}")
            new_pwd = st.text_input("設定登入密碼 (留空則預設為行動電話)", key=f"w_pwd_{k}")
            if st.form_submit_button("確認新增員工") and emp_id and name:
                sites_str = ", ".join(assigned_sites) if assigned_sites else "未指定"
                pwd_final = new_pwd.strip() if new_pwd.strip() else mobile_phone.strip()
                new_worker = pd.DataFrame([{'員工編號': emp_id, '姓名': name.strip(), '行動電話': mobile_phone.strip(), '住家電話': home_phone, '通訊地址': address, '派駐案場': sites_str, '登入密碼': pwd_final}])
                st.session_state.workers_db = pd.concat([st.session_state.workers_db, new_worker], ignore_index=True)
                save_cloud_data(st.session_state.workers_db, 'workers', ['員工編號', '姓名', '行動電話', '住家電話', '通訊地址', '派駐案場', '登入密碼'])
                st.session_state.w_clear_key += 1
                st.rerun()
    with col_right:
        st.subheader("🛠️ 修改 / 🗑️ 刪除員工")
        if not st.session_state.workers_db.empty:
            worker_to_mod = st.selectbox("請選擇要修改的員工：", worker_options)
            emp_id_to_mod = worker_to_mod.split("] ")[0].replace("[", "")
            current_row = st.session_state.workers_db[st.session_state.workers_db['員工編號'] == emp_id_to_mod].iloc[0]
            mod_name = st.text_input("修改姓名", value=str(current_row['姓名']))
            mod_mobile = st.text_input("修改行動電話", value=str(current_row['行動電話']))
            mod_pwd = st.text_input("修改登入密碼", value=str(current_row.get('登入密碼', '')))
            b1, b2 = st.columns(2)
            if b1.button("💾 儲存修改"):
                idx = st.session_state.workers_db[st.session_state.workers_db['員工編號'] == emp_id_to_mod].index[0]
                st.session_state.workers_db.at[idx, '姓名'] = mod_name.strip()
                st.session_state.workers_db.at[idx, '行動電話'] = mod_mobile.strip()
                st.session_state.workers_db.at[idx, '登入密碼'] = mod_pwd.strip()
                save_cloud_data(st.session_state.workers_db, 'workers', ['員工編號', '姓名', '行動電話', '住家電話', '通訊地址', '派駐案場', '登入密碼'])
                st.success("員工修改成功！")
                st.rerun()
            if b2.button("🗑️ 刪除員工", type="primary"):
                st.session_state.workers_db = st.session_state.workers_db[st.session_state.workers_db['員工編號'] != emp_id_to_mod]
                save_cloud_data(st.session_state.workers_db, 'workers', ['員工編號', '姓名', '行動電話', '住家電話', '通訊地址', '派駐案場', '登入密碼'])
                st.rerun()
    st.markdown("---")
    st.dataframe(st.session_state.workers_db, use_container_width=True, hide_index=True)

# ==========================================
# 🗂️ 2. 案場基本資料設定
# ==========================================
elif "案場基本資料設定" in page_clean:
    st.title("🏢 案場基本資料設定")
    col_left, col_right = st.columns(2)
    with col_left:
        with st.form("site_add_form"):
            sk = st.session_state.s_clear_key
            st.subheader("➕ 新增案場資料")
            site_name = st.text_input("案場名稱", key=f"s_name_{sk}")
            site_addr = st.text_input("案場地址", key=f"s_addr_{sk}")
            site_type = st.selectbox("案場性質", st.session_state.site_types, key=f"s_type_{sk}")
            notes = st.text_area("填表說明/注意事項 (將呈現在PDF最下方)", key=f"s_note_{sk}")
            if st.form_submit_button("確認新增案場") and site_name:
                new_site = pd.DataFrame([{'案場名稱': site_name.strip(), '案場地址': site_addr, '案場性質': site_type, '案場聯絡人姓名': '', '案場聯絡人電話': '', '時段一_上': '', '時段一_下': '', '時段二_上': '', '時段二_下': '', '時段三_上': '', '時段三_下': '', '注意事項': notes}])
                st.session_state.sites_db = pd.concat([st.session_state.sites_db, new_site], ignore_index=True)
                save_cloud_data(st.session_state.sites_db, 'sites', ['案場名稱', '案場地址', '案場性質', '案場聯絡人姓名', '案場聯絡人電話', '時段一_上', '時段一_下', '時段二_上', '時段二_下', '時段三_上', '時段三_下', '注意事項'])
                st.session_state.s_clear_key += 1
                st.rerun()
    with col_right:
        st.subheader("🛠️ 修改 / 🗑️ 刪除案場")
        if not st.session_state.sites_db.empty:
            site_to_mod = st.selectbox("請選擇案場名稱：", st.session_state.sites_db['案場名稱'].tolist())
            s_idx = st.session_state.sites_db[st.session_state.sites_db['案場名稱'] == site_to_mod].index[0]
            s_row = st.session_state.sites_db.iloc[s_idx]
            mod_s_addr = st.text_input("修改案場地址", value=s_row.get('案場地址', ''))
            mod_s_note = st.text_area("修改注意事項", value=s_row.get('注意事項', ''), height=150)
            c1, c2 = st.columns(2)
            if c1.button("💾 儲存案場修改"):
                st.session_state.sites_db.at[s_idx, '案場地址'] = mod_s_addr
                st.session_state.sites_db.at[s_idx, '注意事項'] = mod_s_note
                save_cloud_data(st.session_state.sites_db, 'sites', ['案場名稱', '案場地址', '案場性質', '案場聯絡人姓名', '案場聯絡人電話', '時段一_上', '時段一_下', '時段二_上', '時段二_下', '時段三_上', '時段三_下', '注意事項'])
                st.success("案場修改成功！")
                st.rerun()
            if c2.button("🗑️ 刪除案場", type="primary"):
                st.session_state.sites_db = st.session_state.sites_db.drop(s_idx)
                save_cloud_data(st.session_state.sites_db, 'sites', ['案場名稱', '案場地址', '案場性質', '案場聯絡人姓名', '案場聯絡人電話', '時段一_上', '時段一_下', '時段二_上', '時段二_下', '時段三_上', '時段三_下', '注意事項'])
                st.rerun()
    st.markdown("---")
    st.dataframe(st.session_state.sites_db, use_container_width=True, hide_index=True)

# ==========================================
# 🗓️ 3. 線上填報排休與手工修改 (🌟 優化過濾連動)
# ==========================================
elif "線上填報排休" in page_clean:
    st.title("🗓️ 線上填報排休與手工修改")
    col_entry, col_view = st.columns([1, 1.5])
    with col_entry:
        st.subheader("✍️ 填報排休登記")
        with st.form("leave_submit_form"):
            select_worker = st.selectbox("1. 選擇同仁姓名：", st.session_state.workers_db['姓名'].tolist()) if is_admin else st.session_state.current_user_name
            select_site = st.selectbox("2. 選擇排休案場：", st.session_state.sites_db['案場名稱'].tolist() if not st.session_state.sites_db.empty else ["大同莊園"])
            select_date = st.date_input("3. 選擇排休日期：", today)
            select_leave_shift = st.selectbox("4. 選擇假別時段：", ["全天班", "時段一", "時段二", "時段三"])
            select_type = st.radio("5. 假別性質：", ["特休", "一般排休"])
            if st.form_submit_button("確認送出排休"):
                date_str = select_date.strftime('%Y-%m-%d')
                new_leave = pd.DataFrame([{'日期': date_str, '案場名稱': select_site.strip(), '員工姓名': str(select_worker).strip(), '請假時段': str(select_leave_shift), '假別性質': str(select_type)}])
                st.session_state.leave_requests_db = pd.concat([st.session_state.leave_requests_db, new_leave], ignore_index=True)
                save_cloud_data(st.session_state.leave_requests_db, 'leave_requests', ['日期', '案場名稱', '員工姓名', '請假時段', '假別性質'])
                st.success("排休新增成功！")
                st.rerun()
    with col_view:
        # 🌟 修正點 2：右側表格不再需要選擇月份，而是強制精準對齊左側表單選取的特定年份與月份！
        target_ym = select_date.strftime('%Y-%m')
        st.subheader(f"📋 【{select_site}】{target_ym} 月份排休連動清單")
        st.write("💡 提示：雙擊儲存格直接修改，勾選最左側可進行整列增刪，完成後請按「儲存排休表單修改」。")
        l_db = st.session_state.leave_requests_db.copy()
        mask = (l_db['日期'].str.startswith(target_ym)) & (l_db['案場名稱'] == select_site)
        filtered_l_db = l_db[mask]
        
        edited_l_df = st.data_editor(filtered_l_db, num_rows="dynamic", use_container_width=True, hide_index=True)
        if st.button("💾 儲存排休表單修改", type="primary"):
            l_db = l_db[~mask]
            l_db = pd.concat([l_db, edited_l_df], ignore_index=True)
            st.session_state.leave_requests_db = l_db
            save_cloud_data(st.session_state.leave_requests_db, 'leave_requests', ['日期', '案場名稱', '員工姓名', '請假時段', '假別性質'])
            st.success("🎉 排休表單與雲端同步更新成功！")
            st.rerun()

# ==========================================
# 🚀 4. 自動週期底稿鋪設與修改 (🌟 滑鼠點選優化)
# ==========================================
elif "自動週期底稿鋪設" in page_clean:
    st.title("🚀 自動週期底稿鋪設與排班微調控制台")
    tab_auto, tab_manual = st.tabs(["📅 引擎自動鋪底稿", "🛠️ 班表查詢與手工微調 (抽換修改)"])
    
    with tab_auto:
        st.subheader("🚀 批次週期底稿引擎鋪設")
        template_site = st.selectbox("1. 選擇指定案場：", st.session_state.sites_db['案場名稱'].tolist() if not st.session_state.sites_db.empty else ["大同莊園"])
        template_worker = st.selectbox("2. 選擇上工同仁：", st.session_state.workers_db['姓名'].tolist())
        template_role = st.selectbox("3. 指定擔任職位：", JOB_ROLES)
        mode = st.radio("選擇鋪設模式：", ["📅 模式 B：按特定日期 (日曆多選點選)", "💡 模式 A：按星期規律 (整月快速鋪設)"])
        
        if "模式 B" in mode:
            st.write("請選擇上工年份與月份，並在下拉選單中直接勾選多個日期：")
            b_year = st.selectbox("選擇年份", [2026, 2027], key="by")
            b_month = st.selectbox("選擇月份", list(range(1, 13)), index=default_next_month-1, key="bm")
            try: max_days = ((datetime.date(b_year, b_month + 1, 1) if b_month < 12 else datetime.date(b_year + 1, 1, 1)) - datetime.timedelta(days=1)).day
            except: max_days = 31
            day_options = [f"{b_year}-{b_month:02d}-{d:02d}" for d in range(1, max_days + 1)]
            selected_dates = st.multiselect("請點選要上工的所有日子：", options=day_options)
            
            if st.button("⚡ 開始依點選日期鋪設底稿", type="primary"):
                if selected_dates:
                    df_schedule = st.session_state.schedule_db.copy()
                    for d_str in selected_dates:
                        new_row = pd.DataFrame([{'日期': d_str, '案場名稱': template_site.strip(), '員工姓名': template_worker.strip(), '班段名稱': '全天', '時段區間': '依規定', '時源工時': '8', '派駐職位': template_role}])
                        df_schedule = pd.concat([df_schedule, new_row], ignore_index=True)
                    st.session_state.schedule_db = df_schedule.drop_duplicates()
                    save_cloud_data(st.session_state.schedule_db, 'schedule', ['日期', '案場名稱', '員工姓名', '班段名稱', '時段區間', '時源工時', '派駐職位'])
                    st.success("🎉 模式 B：特定日期底稿多選鋪設成功！")
                    st.rerun()
                else: st.warning("請至少點選一個日期。")
        else:
            a_year = st.selectbox("選擇年份", [2026, 2027], key="ay")
            a_month = st.selectbox("選擇月份", list(range(1, 13)), index=default_next_month-1, key="am")
            w_days = []
            c1, c2, c3, c4 = st.columns(4)
            if c1.checkbox("週一"): w_days.append(0)
            if c2.checkbox("週二"): w_days.append(1)
            if c3.checkbox("週三"): w_days.append(2)
            if c4.checkbox("週四"): w_days.append(3)
            if c1.checkbox("週五"): w_days.append(4)
            if c2.checkbox("週六"): w_days.append(5)
            if c3.checkbox("週日"): w_days.append(6)
            
            if st.button("⚡ 開始依【星期】鋪設底稿", type="primary"):
                start_date = datetime.date(a_year, a_month, 1)
                next_m = a_month + 1 if a_month < 12 else 1
                next_y = a_year if a_month < 12 else a_year + 1
                end_date = datetime.date(next_y, next_m, 1) - datetime.timedelta(days=1)
                curr = start_date
                df_schedule = st.session_state.schedule_db.copy()
                while curr <= end_date:
                    if curr.weekday() in w_days:
                        d_str = curr.strftime('%Y-%m-%d')
                        new_row = pd.DataFrame([{'日期': d_str, '案場名稱': template_site.strip(), '員工姓名': template_worker.strip(), '班段名稱': '全天', '時段區間': '依規定', '時源工時': '8', '派駐職位': template_role}])
                        df_schedule = pd.concat([df_schedule, new_row], ignore_index=True)
                    curr += datetime.timedelta(days=1)
                st.session_state.schedule_db = df_schedule.drop_duplicates()
                save_cloud_data(st.session_state.schedule_db, 'schedule', ['日期', '案場名稱', '員工姓名', '班段名稱', '時段區間', '時源工時', '派駐職位'])
                st.success("🎉 模式 A：星期規律底稿鋪設成功！")
                st.rerun()

    with tab_manual:
        # 🌟 修正點 1 & 5：手工微調控制台全面改為「滑鼠下拉點選年份/月份」，且全面放開「新增、修改、刪除」功能
        st.subheader("🛠 nighttime 班表特定月份精準手工修改與微調")
        st.write("請使用滑鼠下拉選擇案場與指定年月，下方表格支援連點兩下修改，或在最下方 ➕ 新增列，或點擊最左側行號按 Delete 刪除列。")
        col_q1, col_q2, col_q3 = st.columns(3)
        with col_q1: q_site = st.selectbox("指定微調案場：", st.session_state.sites_db['案場名稱'].tolist() if not st.session_state.sites_db.empty else ["大同莊園"], key="man_site")
        with col_q2: q_year = st.selectbox("指定微調年份：", [2026, 2027], index=0, key="man_year")
        with col_q3: q_month = st.selectbox("指定微調月份：", list(range(1, 13)), index=today.month-1, key="man_month")
        
        target_q_ym = f"{q_year}-{q_month:02d}"
        s_db = st.session_state.schedule_db.copy()
        mask_s = (s_db['日期'].str.startswith(target_q_ym)) & (s_db['案場名稱'] == q_site)
        filtered_s_df = s_db[mask_s]
        
        edited_s_df = st.data_editor(filtered_s_df, num_rows="dynamic", use_container_width=True, hide_index=True)
        if st.button("💾 儲存本日/本月班表精準微調修改", type="primary", key="man_save_btn"):
            s_db = s_db[~mask_s]
            s_db = pd.concat([s_db, edited_s_df], ignore_index=True)
            st.session_state.schedule_db = s_db
            save_cloud_data(st.session_state.schedule_db, 'schedule', ['日期', '案場名稱', '員工姓名', '班段名稱', '時段區間', '時源工時', '派駐職位'])
            st.success("🎉 排班資料庫底稿精準微調與雲端連動同步完成！")
            st.rerun()

# ==========================================
# 📊 5. 班表大印製中心 (🌟 修正點3：週六日加紅字、漂亮滿版)
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
                grouped_roles.append(f"{' / '.join(unique_names)} ({r_name})")
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
    
    # 🌟 修正點 3 & 6：生成高密度的純淨直式 A4 HTML
    html_table_rows = ""
    for r in edited_df.to_dict(orient='records'):
        is_weekend = r['星期'] in ["六", "日"]
        row_style = "style='color:red; font-weight:bold;'" if is_weekend else ""
        leave_cell = f"<td style='padding:5px; border:1px solid #000; color:red; font-weight:bold;'>{r['休假']}</td>" if r['休假'] else "<td style='padding:5px; border:1px solid #000;'></td>"
        
        html_table_rows += f"""
        <tr {row_style}>
            <td style='text-align:center; padding:5px; border:1px solid #000;'>{r['日期']}</td>
            {leave_cell}
            <td style='text-align:center; padding:5px; border:1px solid #000;'>{r['星期']}</td>
            <td style='padding:5px; border:1px solid #000; font-weight:bold;'>{r['班別 / 勤務人員']}</td>
            <td style='padding:5px; border:1px solid #000; color:#000; font-weight:normal;'>{r['備註']}</td>
        </tr>
        """
        
    site_notes_html = ""
    s_rows = st.session_state.sites_db[st.session_state.sites_db['案場名稱'] == sel_site.strip()]
    if not s_rows.empty and s_rows.iloc[0]['注意事項']:
        notes_lines = str(s_rows.iloc[0]['注意事項']).split('\n')
        site_notes_html += "<div style='margin-top:15px; font-size:14px; line-height:1.5; color:#000; text-align:left;'>"
        site_notes_html += "<b>填表說明/注意事項:</b><br>"
        for line in notes_lines:
            if line.strip():
                if any(k in line for k in ["特別注意", "重要", "嚴禁", "請先閱讀"]):
                    site_notes_html += f"<div style='margin-left:5px; color:red; font-weight:bold;'>{line}</div>"
                else:
                    site_notes_html += f"<div style='margin-left:5px;'>{line}</div>"
        site_notes_html += "</div>"

    logo_tag = get_logo_html_tag()
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{ font-family: "Microsoft JhengHei", sans-serif; background: #fff; color: #000; margin: 0; padding: 0; }}
        @media print {{
            body {{ padding: 0; margin: 0; }}
            .no-print {{ display: none !important; }}
            #printArea {{ width: 100%; padding: 0 !important; }}
            @page {{ size: A4 portrait; margin: 10mm; }}
        }}
    </style>
    </head>
    <body>
    <div id='printArea' style='padding:10px; width:100%; box-sizing:border-box;'>
        <div style='display: flex; align-items: center; justify-content: center; position: relative; margin-bottom: 15px;'>
            <div style='position: absolute; left: 0;'>{logo_tag}</div>
            <div style='text-align: center;'>
                <h2 style='margin: 0; font-size: 24px; font-weight: bold;'>{COMPANY_NAME}</h2>
                <h3 style='margin: 5px 0 0 0; font-size: 18px; color: #333;'>{sel_site} {sel_year}年{sel_month:02d}月份 勤務班表</h3>
            </div>
        </div>
        <table style='width:100%; border-collapse:collapse; font-size:14px; color:#000;'>
            <thead>
                <tr style='background-color:#f2f2f2; text-align:center; color:#000;'>
                    <th style='width:8%; border:1px solid #000; padding:8px;'>日期</th>
                    <th style='width:22%; border:1px solid #000; padding:8px; color:red;'>休假</th>
                    <th style='width:8%; border:1px solid #000; padding:8px;'>星期</th>
                    <th style='width:44%; border:1px solid #000; padding:8px;'>班別 / 勤務人員</th>
                    <th style='width:18%; border:1px solid #000; padding:8px;'>備註</th>
                </tr>
            </thead>
            <tbody>{html_table_rows}</tbody>
        </table>
        {site_notes_html}
        <div class='no-print' style='text-align:center; margin-top:20px;'>
            <button onclick='window.print()' style='padding:12px 35px; font-size:16px; font-weight:bold; background-color:#1E88E5; color:white; border:none; border-radius:5px; cursor:pointer;'>🖨️ 點擊列印 A4 直式正式班表</button>
        </div>
    </div>
    </body>
    </html>
    """
    st.markdown("---")
    components.html(full_html, height=850, scrolling=True)

# ==========================================
# 📱 6. 個人班表出勤直式查詢 (🌟 修正點 4：補回注意事項)
# ==========================================
elif "個人班表出勤直式查詢" in page_clean:
    st.title("📱 員工個人出勤班表直式查詢與 A4 列印")
    current_worker = st.session_state.current_user_name if st.session_state.current_user_name else "系統管理者"
    if worker_options:
        selected_emp_format = st.selectbox("請核對或選擇欲查詢的員工姓名：", worker_options)
        target_emp = selected_emp_format.split("] ")[1].strip() if "] " in selected_emp_format else selected_emp_format
    else:
        target_emp = st.text_input("輸入查詢員工姓名：", value=current_worker)
        
    q_year = st.selectbox("選擇查詢年份：", [2026, 2027], index=0)
    q_month = st.selectbox("選擇查詢月份：", list(range(1, 13)), index=default_next_month - 1)
    
    s_db = st.session_state.schedule_db.copy()
    if not s_db.empty and target_emp:
        s_db['Month_Int'] = s_db['日期'].apply(lambda x: int(x.split('-')[1]) if '-' in str(x) else 0)
        s_db['Year_Int'] = s_db['日期'].apply(lambda x: int(x.split('-')[0]) if '-' in str(x) else 0)
        emp_records = s_db[(s_db['員工姓名'].str.strip() == target_emp.strip()) & (s_db['Year_Int'] == q_year) & (s_db['Month_Int'] == q_month)]
        
        if not emp_records.empty:
            sorted_records = emp_records[['日期', '案場名稱', '班段名稱', '時段區間', '派駐職位']].sort_values(by='日期').reset_index(drop=True)
            st.dataframe(sorted_records, use_container_width=True, hide_index=True)
            
            # 取得該同仁當月主要案場的注意事項
            main_site_name = sorted_records.iloc[0]['案場名稱']
            site_notes_html = ""
            s_rows = st.session_state.sites_db[st.session_state.sites_db['案場名稱'] == main_site_name.strip()]
            if not s_rows.empty and s_rows.iloc[0]['注意事項']:
                notes_lines = str(s_rows.iloc[0]['注意事項']).split('\n')
                site_notes_html += "<div style='margin-top:20px; font-size:14px; line-height:1.5; color:#000; text-align:left; border-top:1px dashed #ccc; padding-top:10px;'>"
                site_notes_html += f"<b>💡 {main_site_name} 填表說明/注意事項:</b><br>"
                for line in notes_lines:
                    if line.strip():
                        site_notes_html += f"<div style='margin-left:5px;'>{line}</div>"
                site_notes_html += "</div>"
            
            grouped_rows_html = ""
            for (date_val, site_val), group in sorted_records.groupby(['日期', '案場名稱']):
                shifts_combined = "<br>".join(group['班段名稱'].tolist())
                intervals_combined = "<br>".join(group['時段區間'].tolist())
                roles_combined = "<br>".join(list(set(group['派駐職位'].tolist())))
                grouped_rows_html += f"""
                <tr>
                    <td style='text-align:center; padding:10px; border:1px solid #000; vertical-align:middle;'>{date_val}</td>
                    <td style='padding:10px; border:1px solid #000; vertical-align:middle;'>{site_val}</td>
                    <td style='text-align:center; padding:10px; border:1px solid #000; vertical-align:middle;'>{shifts_combined}</td>
                    <td style='text-align:center; padding:10px; border:1px solid #000; vertical-align:middle;'>{intervals_combined}</td>
                    <td style='padding:10px; border:1px solid #000; font-weight:bold; vertical-align:middle;'>{roles_combined}</td>
                </tr>
                """
                
            logo_tag = get_logo_html_tag()
            emp_html_doc = f"""
            <!DOCTYPE html>
            <html>
            <head>
            <style>
                body {{ font-family: "Microsoft JhengHei", sans-serif; background: #fff; color: #000; }}
                @media print {{
                    body {{ padding: 0; margin: 0; }}
                    .no-print {{ display: none !important; }}
                    @page {{ size: A4 portrait; margin: 10mm; }}
                }}
            </style>
            </head>
            <body>
            <div style='padding:15px; width:100%; box-sizing:border-box;'>
                <div style='display: flex; align-items: center; justify-content: center; position: relative; margin-bottom: 15px;'>
                    <div style='position: absolute; left: 0;'>{logo_tag}</div>
                    <div style='text-align: center;'>
                        <h2 style='margin: 0; font-size: 24px; font-weight: bold;'>{COMPANY_NAME}</h2>
                        <h3 style='margin: 5px 0 0 0; font-size: 18px; color: #333;'>同仁【{target_emp}】{q_year}年{q_month:02d}月份 出勤明細表</h3>
                    </div>
                </div>
                <table style='width:100%; border-collapse:collapse; font-size:15px; text-align:left;'>
                    <thead>
                        <tr style='background-color:#f5f5f5; text-align:center; height:38px;'>
                            <th style='border:1px solid #000; padding:10px; width:18%;'>出勤日期</th>
                            <th style='border:1px solid #000; padding:10px; width:22%;'>指派案場</th>
                            <th style='border:1px solid #000; padding:10px; width:20%;'>班段</th>
                            <th style='border:1px solid #000; padding:10px; width:25%;'>時間區間</th>
                            <th style='border:1px solid #000; padding:10px; width:15%;'>擔任職位</th>
                        </tr>
                    </thead>
                    <tbody>{grouped_rows_html}</tbody>
                </table>
                {site_notes_html}
                <div class='no-print' style='text-align:center; margin-top:20px;'>
                    <button onclick='window.print()' style='padding:12px 35px; font-size:16px; font-weight:bold; background-color:#4CAF50; color:white; border:none; border-radius:5px; cursor:pointer;'>🖨️ 列印個人直式班表 PDF</button>
                </div>
            </div>
            </body>
            </html>
            """
            st.markdown("---")
            components.html(emp_html_doc, height=650, scrolling=True)
        else: st.warning("💡 本月份該同仁暫無指派勤務。")

# ==========================================
# 🔓 7. 員工密碼自主變更中心
# ==========================================
elif "員工密碼自主變更" in page_clean:
    st.title("🔐 員工密碼自主變更中心")
    st.write(f"當前登入帳戶：**{st.session_state.current_user_name}**")
    with st.form("pwd_change_form"):
        old_pwd = st.text_input("1. 請輸入目前的使用密碼：", type="password")
        new_pwd_1 = st.text_input("2. 請設定全新的登入密碼：", type="password")
        new_pwd_2 = st.text_input("3. 再次確認全新密碼：", type="password")
        
        if st.form_submit_button("💾 確定變更個人登入密碼"):
            w_df = st.session_state.workers_db.copy()
            match_mask = w_df['姓名'] == st.session_state.current_user_name
            if not w_df[match_mask].empty:
                current_db_pwd = str(w_df[match_mask].iloc[0]['登入密碼']).strip()
                if old_pwd.strip() != current_db_pwd:
                    st.error("❌ 您輸入的『目前使用密碼』不正確，請重新核對！")
                elif new_pwd_1.strip() != new_pwd_2.strip() or new_pwd_1.strip() == "":
                    st.error("❌ 兩次輸入的新密碼不一致，或新密碼不能為空！")
                else:
                    idx = w_df[match_mask].index[0]
                    st.session_state.workers_db.at[idx, '登入密碼'] = new_pwd_1.strip()
                    save_cloud_data(st.session_state.workers_db, 'workers', ['員工編號', '姓名', '行動電話', '住家電話', '通訊地址', '派駐案場', '登入密碼'])
                    st.success("🎉 密碼修改成功！下次登入請使用新密碼。")
            else: st.error("錯誤：找不到該同仁資料。")
