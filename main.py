import streamlit as st
import pandas as pd
import datetime
import os
import json
import io
import urllib.request
from google.oauth2.service_account import Credentials
import gspread

# PDF 專用套件
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, portrait
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

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
FONT_FILE = 'ch_font.ttf'  # 雲端下載暫存路徑
REMARKS_FILE = 'remarks.json'
COMPANY_NAME = "魔力休閒運動事業股份有限公司"

# --- 備註資料本地端儲存邏輯 ---
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

def init_cloud_font():
    """💡 本地字體安全鎖定：字體已直接由 GitHub 隨附上傳，不需聯網下載，保證 PDF 100% 出字"""
    if not os.path.exists(FONT_FILE):
        st.error(f"❌ 嚴重錯誤：GitHub 倉庫中找不到 {FONT_FILE} 字型檔！請確保已上傳該檔案。")
        st.stop()

def init_gspread_system(*args, **kwargs):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    
    try: init_cloud_font()
    except: pass
    
    if "gcp_service_account" in st.secrets:
        try:
            secrets_ref = st.secrets["gcp_service_account"]
            if "json_creds" in secrets_ref:
                creds_dict = json.loads(secrets_ref["json_creds"])
            else:
                creds_dict = dict(secrets_ref)
            return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=scope))
        except Exception as e:
            st.error(f"❌ 雲端密鑰解析失敗，請檢查 Secrets 格式：{str(e)}")
            st.stop()
            
    if os.path.exists(CREDS_FILE):
        try: return gspread.authorize(Credentials.from_service_account_file(CREDS_FILE, scopes=scope))
        except Exception as e: st.error(f"本地憑證檔案解析失敗：{str(e)}")
        
    st.error("❌ 系統尚未配置任何安全密鑰！一般員工請通知後台管理者。")
    st.stop()

gc = init_gspread_system()

def load_cloud_data(sheet_key, columns):
    if gc is None: return pd.DataFrame(columns=columns)
    try:
        sh = gc.open_by_key(SHEET_IDS[sheet_key])
        worksheet = sh.get_worksheet(0)
        records = worksheet.get_all_records()
        if not records: return pd.DataFrame(columns=columns)
        df = pd.DataFrame(records).astype(str)
        for col in columns:
            if col not in df.columns: df[col] = ""
        return df
    except: return pd.DataFrame(columns=columns)

def save_cloud_data(df, sheet_key, columns):
    if gc is None: return
    try:
        sh = gc.open_by_key(SHEET_IDS[sheet_key])
        worksheet = sh.get_worksheet(0)
        worksheet.clear()
        df_save = df[columns].copy().fillna("").astype(str)
        data_to_save = [df_save.columns.values.tolist()] + df_save.values.tolist()
        try: worksheet.update(values=data_to_save, range_name="A1")
        except:
            try: worksheet.update("A1", data_to_save)
            except: worksheet.update_values("A1", data_to_save)
    except Exception as e: st.error(f"☁️ 雲端同步失敗：{str(e)}")

def load_site_types():
    default_types = ["辦公大樓", "購物中心", "展覽館", "工廠園區", "其他"]
    if gc is None: return default_types
    try:
        sh = gc.open_by_key(SHEET_IDS['sites'])
        try:
            ws = sh.worksheet("SiteTypes")
            records = ws.col_values(1)
            return records if records else default_types
        except:
            ws = sh.add_worksheet(title="SiteTypes", rows=100, cols=1)
            ws.update(values=[[t] for t in default_types], range_name="A1")
            return default_types
    except: return default_types

def save_site_types(types_list):
    if gc is None: return
    try:
        sh = gc.open_by_key(SHEET_IDS['sites'])
        ws = sh.worksheet("SiteTypes")
        ws.clear()
        ws.update(values=[[t] for t in types_list], range_name="A1")
    except Exception as e: st.error(f"選單同步寫入失敗：{str(e)}")


# ==========================================
# ⚡ Session State 智慧快取與登入狀態管理
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.current_user_name = None

if 'data_loaded' not in st.session_state:
    with st.spinner("⚡ 正在與 Google 雲端安全資料庫進行同步..."):
        st.session_state.workers_db = load_cloud_data('workers', ['員工編號', '姓名', '行動電話', '住家電話', '通訊地址', '派駐案場', '登入密碼'])
        st.session_state.sites_db = load_cloud_data('sites', ['案場名稱', '案場地址', '案場性質', '案場聯絡人姓名', '案場聯絡人電話', '時段一_上', '時段一_下', '時段二_上', '時段二_下', '時段三_上', '時段三_下', '注意事項'])
        st.session_state.leave_requests_db = load_cloud_data('leave_requests', ['日期', '案場名稱', '員工姓名', '請假時段', '假別性質'])
        st.session_state.schedule_db = load_cloud_data('schedule', ['日期', '案場名稱', '員工姓名', '班段名稱', '時段區間', '時源工時'])
        st.session_state.site_types = load_site_types()
        st.session_state.data_loaded = True

if 'w_clear_key' not in st.session_state: st.session_state.w_clear_key = 0
if 's_clear_key' not in st.session_state: st.session_state.s_clear_key = 0


# ==========================================
# 🔐 系統登入大廳 (Gatekeeper)
# ==========================================
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if os.path.exists(LOGO_FILE):
            st.image(LOGO_FILE, use_container_width=True)
        st.markdown(f"<h2 style='text-align: center;'>{COMPANY_NAME}<br>專業勤務排班系統</h2>", unsafe_allow_html=True)
        st.markdown("---")
        
        tab_emp, tab_admin = st.tabs(["👥 員工專區登入", "👑 系統管理者登入"])
        
        with tab_emp:
            st.subheader("員工身分驗證")
            emp_names = st.session_state.workers_db['姓名'].tolist() if not st.session_state.workers_db.empty and st.session_state.workers_db['姓名'].tolist()[0] != "" else []
            if emp_names:
                login_name = st.selectbox("請選擇您的姓名", emp_names)
                login_pwd = st.text_input("請輸入登入密碼 (預設為您的行動電話號碼，如0912-345-678，不可省略「-」)", type="password")
                if st.button("🚪 驗證並登入", use_container_width=True, type="primary"):
                    worker_row = st.session_state.workers_db[st.session_state.workers_db['姓名'] == login_name].iloc[0]
                    db_pwd = str(worker_row.get('登入密碼', '')).strip()
                    db_phone = str(worker_row.get('行動電話', '')).strip()
                    valid_pwd = db_pwd if db_pwd else db_phone
                    
                    if login_pwd == valid_pwd and login_pwd != "":
                        st.session_state.logged_in = True
                        st.session_state.user_role = "employee"
                        st.session_state.current_user_name = login_name
                        st.rerun()
                    else: st.error("❌ 密碼錯誤！")
            else: st.info("系統尚未建立任何員工資料，請管理者先登入建立。")

        with tab_admin:
            st.subheader("管理者特權驗證")
            ADMIN_PASSWORD = "680817"
            admin_pwd = st.text_input("請輸入最高管理者密碼", type="password")
            if st.button("👑 管理者登入", use_container_width=True, type="primary"):
                if admin_pwd == ADMIN_PASSWORD:
                    st.session_state.logged_in = True
                    st.session_state.user_role = "admin"
                    st.session_state.current_user_name = "系統管理者"
                    st.rerun()
                else: st.error("❌ 密碼錯誤！")
    st.stop()

# ==========================================
# 📱 已登入狀態：側邊欄導覽列
# ==========================================
st.sidebar.markdown(f"### 🏢 {COMPANY_NAME}")
if os.path.exists(LOGO_FILE):
    st.sidebar.image(LOGO_FILE, use_container_width=True)

st.sidebar.markdown("---")
is_admin = (st.session_state.user_role == "admin")

if is_admin:
    st.sidebar.success("👑 當前身分：最高管理者")
    menu_options = ["工作者基本資料設定", "案場基本資料設定", "案場性質選單維護", "🗓️ 管理者控制台：填報排休與手工修改", "🚀 管理者控制台：自動鋪底稿與微調", "📊 班表大印製中心：正式 PDF 產出", "📱 員工專區：個人班表出勤直式查詢"]
else:
    st.sidebar.info(f"👥 當前身分：{st.session_state.current_user_name} (一般員工)")
    menu_options = ["🗓️ 員工專區：線上登記請假排休", "📱 員工專區：個人班表出勤直式查詢"]

page = st.sidebar.radio("請選擇功能頁面：", menu_options)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 強制同步最新雲端資料", use_container_width=True):
    if 'data_loaded' in st.session_state: del st.session_state['data_loaded']
    st.rerun()

if st.sidebar.button("🚪 安全登出系統", type="primary", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.current_user_name = None
    if 'data_loaded' in st.session_state: del st.session_state['data_loaded']
    st.rerun()

st.sidebar.caption("專業勤務排班系統 雲端網頁正式版 V8.7")

# 通用函數
def parse_single_shift_hours(t_in, t_out):
    if t_in and t_out:
        try:
            fmt = '%H:%M'
            td = datetime.datetime.strptime(str(t_out), fmt) - datetime.datetime.strptime(str(t_in), fmt)
            hrs = float(td.total_seconds() / 3600.0)
            if hrs < 0: hrs += 24
            return round(hrs, 1)
        except: return 0.0
    return 0.0

def get_site_active_shifts(site_name):
    """💡 智慧時段引擎：若案場僅設定一個時段，自動將時段名稱轉換為『全天時段』"""
    site_rows = st.session_state.sites_db[st.session_state.sites_db['案場名稱'] == site_name]
    if site_rows.empty: return {}
    site_data = site_rows.iloc[0]
    
    raw_shifts = {}
    for i in ["一", "二", "三"]:
        t_up = str(site_data.get(f'時段{i}_上', "")).strip()
        t_down = str(site_data.get(f'時段{i}_下', "")).strip()
        if t_up and t_down and t_up != "None" and t_down != "None":
            raw_shifts[f"時段{i}"] = f"{t_up}-{t_down}"
            
    # 💡 核心優化：若只有單一時段被啟用，直接正名為「全天時段」
    if len(raw_shifts) == 1 and "時段一" in raw_shifts:
        return {"全天時段": raw_shifts["時段一"]}
        
    return raw_shifts

# ==========================================
# 各頁面邏輯區塊
# ==========================================
if page == "工作者基本資料設定":
    st.title("⚙️ 工作者基本資料設定")
    col_left, col_right = st.columns(2)
    with col_left:
        with st.form("worker_add_form", clear_on_submit=False):
            st.subheader("➕ 新增工作者資料")
            k = st.session_state.w_clear_key
            emp_id = st.text_input("員工編號", key=f"w_id_{k}")
            name = st.text_input("姓名", key=f"w_name_{k}")
            mobile_phone = st.text_input("行動電話", key=f"w_mob_{k}")
            home_phone = st.text_input("住家電話", key=f"w_home_{k}")
            address = st.text_input("通訊地址", key=f"w_addr_{k}")
            available_sites = st.session_state.sites_db['案場名稱'].tolist() if not st.session_state.sites_db.empty else []
            assigned_sites = st.multiselect("支持/派駐案場 (可複選)", options=available_sites, key=f"w_sites_{k}")
            new_pwd = st.text_input("設定登入密碼 (留空則預設為行動電話)", key=f"w_pwd_{k}")
            
            submit_worker = st.form_submit_button("確認新增員工")
            if submit_worker and emp_id and name:
                if emp_id in st.session_state.workers_db['員工編號'].astype(str).values: st.error("❌ 編號重複！")
                else:
                    sites_str = ", ".join(assigned_sites) if assigned_sites else "未指定"
                    new_worker = pd.DataFrame([{'員工編號': emp_id, '姓名': name, '行動電話': mobile_phone, '住家電話': home_phone, '通訊地址': address, '派駐案場': sites_str, '登入密碼': new_pwd}])
                    st.session_state.workers_db = pd.concat([st.session_state.workers_db, new_worker], ignore_index=True)
                    save_cloud_data(st.session_state.workers_db, 'workers', ['員工編號', '姓名', '行動電話', '住家電話', '通訊地址', '派駐案場', '登入密碼'])
                    st.success(f"✅ 已成功寫入雲端試算表：{name}")
                    st.session_state.w_clear_key += 1
                    st.rerun()
    with col_right:
        st.subheader("🛠️ 修改 / 🗑️ 刪除工作者")
        if not st.session_state.workers_db.empty and st.session_state.workers_db['員工編號'].tolist()[0] != "":
            worker_to_mod = st.selectbox("請選擇員工編號：", st.session_state.workers_db['員工編號'].tolist())
            current_row = st.session_state.workers_db[st.session_state.workers_db['員工編號'] == worker_to_mod].iloc[0]
            mod_name = st.text_input("修改姓名", value=str(current_row['姓名']))
            mod_mobile = st.text_input("修改行動電話", value=str(current_row['行動電話']))
            mod_home = st.text_input("修改住家電話", value=str(current_row['住家電話']))
            mod_address = st.text_input("修改通訊地址", value=str(current_row['通訊地址']))
            mod_pwd = st.text_input("修改登入密碼", value=str(current_row.get('登入密碼', '')))
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("💾 儲存修改項目並同步雲端"):
                    idx = st.session_state.workers_db[st.session_state.workers_db['員工編號'] == worker_to_mod].index[0]
                    st.session_state.workers_db.at[idx, '姓名'] = mod_name
                    st.session_state.workers_db.at[idx, '行動電話'] = mod_mobile
                    st.session_state.workers_db.at[idx, '住家電話'] = mod_home
                    st.session_state.workers_db.at[idx, '通訊地址'] = mod_address
                    st.session_state.workers_db.at[idx, '登入密碼'] = mod_pwd
                    save_cloud_data(st.session_state.workers_db, 'workers', ['員工編號', '姓名', '行動電話', '住家電話', '通訊地址', '派駐案場', '登入密碼'])
                    st.success("✅ 雲端員工資料更新成功！")
                    st.rerun()
            with btn_col2:
                if st.button("🗑️ 刪除此員工並自雲端抹除", type="primary"):
                    st.session_state.workers_db = st.session_state.workers_db[st.session_state.workers_db['員工編號'] != worker_to_mod]
                    save_cloud_data(st.session_state.workers_db, 'workers', ['員工編號', '姓名', '行動電話', '住家電話', '通訊地址', '派駐案場', '登入密碼'])
                    st.success("🗑️ 雲端資料已同步抹除！")
                    st.rerun()
    st.markdown("---")
    st.dataframe(st.session_state.workers_db, use_container_width=True)

elif page == "案場基本資料設定":
    st.title("🏢 案場基本資料設定")
    col_left, col_right = st.columns(2)
    with col_left:
        with st.form("site_add_form", clear_on_submit=False):
            st.subheader("➕ 新增案場與工作時間設定")
            sk = st.session_state.s_clear_key
            site_name = st.text_input("案場名稱", key=f"s_name_{sk}")
            site_addr = st.text_input("案場地址", key=f"s_addr_{sk}")
            site_type = st.selectbox("案場性質", st.session_state.site_types, key=f"s_type_{sk}")
            manager_name = st.text_input("案場聯絡人姓名", key=f"s_mn_{sk}")
            manager_phone = st.text_input("案場聯絡人電話", key=f"s_mp_{sk}")
            st.markdown("⏱️ **自訂工作時間區段 (最多三段，若一天只有一段，請僅填報時段一)**")
            c1, c2 = st.columns(2)
            s1_in = c1.text_input("時段一 上班 (例: 08:00)", key=f"s_s1i_{sk}")
            s1_out = c2.text_input("時段一 下班 (例: 12:00)", key=f"s_s1o_{sk}")
            s2_in = c1.text_input("時段二 上班 (例: 13:00)", key=f"s_s2i_{sk}")
            s2_out = c2.text_input("時段二 下班 (例: 17:00)", key=f"s_s2o_{sk}")
            s3_in = c1.text_input("時段三 上班", key=f"s_s3i_{sk}")
            s3_out = c2.text_input("時段三 下班", key=f"s_s3o_{sk}")
            notes = st.text_area("工作注意事項", key=f"s_note_{sk}")
            submit_site = st.form_submit_button("確認新增案場")
            if submit_site and site_name:
                if site_name in st.session_state.sites_db['案場名稱'].astype(str).values: st.error("❌ 案場已存在！")
                else:
                    new_site = pd.DataFrame([{'案場名稱': site_name, '案場地址': site_addr, '案場性質': site_type, '案場聯絡人姓名': manager_name, '案場聯絡人電話': manager_phone, '時段一_上': s1_in, '時段一_下': s1_out, '時段二_上': s2_in, '時段二_下': s2_out, '時段三_上': s3_in, '時段三_下': s3_out, '注意事項': notes}])
                    st.session_state.sites_db = pd.concat([st.session_state.sites_db, new_site], ignore_index=True)
                    save_cloud_data(st.session_state.sites_db, 'sites', ['案場名稱', '案場地址', '案場性質', '案場聯絡人姓名', '案場聯絡人電話', '時段一_上', '時段一_下', '時段二_上', '時段二_下', '時段三_上', '時段三_下', '注意事項'])
                    st.success(f"✅ 已成功同步雲端新案場：{site_name}")
                    st.session_state.s_clear_key += 1
                    st.rerun()
    with col_right:
        st.subheader("🛠️ 修改 / 🗑️ 刪除案場")
        if not st.session_state.sites_db.empty and st.session_state.sites_db['案場名稱'].tolist()[0] != "":
            site_to_mod = st.selectbox("請選擇案場名稱：", st.session_state.sites_db['案場名稱'].tolist())
            current_site = st.session_state.sites_db[st.session_state.sites_db['案場名稱'] == site_to_mod].iloc[0]
            mod_addr = st.text_input("修改案場地址", value=str(current_site['案場地址']))
            mod_type = st.selectbox("修改案場性質", st.session_state.site_types, index=st.session_state.site_types.index(current_site['案場性質']) if current_site['案場性質'] in st.session_state.site_types else 0)
            mod_m_name = st.text_input("修改聯絡人姓名", value=str(current_site['案場聯絡人姓名']))
            mod_m_phone = st.text_input("修改聯絡人電話", value=str(current_site['案場聯絡人電話']))
            st.markdown("⏱️ **修改工作時間區段**")
            mc1, mc2 = st.columns(2)
            ms1_in = mc1.text_input("修改時段一 上班", value=str(current_site['時段一_上']))
            ms1_out = mc2.text_input("修改時段一 下班", value=str(current_site['時段一_下']))
            ms2_in = mc1.text_input("修改時段二 上班", value=str(current_site['時段二_上']))
            ms2_out = mc2.text_input("修改時段二 下班", value=str(current_site['時段二_下']))
            ms3_in = mc1.text_input("修改時段三 上班", value=str(current_site['時段三_上']))
            ms3_out = mc2.text_input("修改時段三 下班", value=str(current_site['時段三_下']))
            mod_notes = st.text_area("修改注意事項", value=str(current_site['注意事項']))
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("💾 儲存修改案場並同步"):
                    idx = st.session_state.sites_db[st.session_state.sites_db['案場名稱'] == site_to_mod].index[0]
                    st.session_state.sites_db.at[idx, '案場地址'] = mod_addr
                    st.session_state.sites_db.at[idx, '案場性質'] = mod_type
                    st.session_state.sites_db.at[idx, '案場聯絡人姓名'] = mod_m_name
                    st.session_state.sites_db.at[idx, '案場聯絡人電話'] = mod_m_phone
                    st.session_state.sites_db.at[idx, '時段一_上'] = ms1_in
                    st.session_state.sites_db.at[idx, '時段一_下'] = ms1_out
                    st.session_state.sites_db.at[idx, '時段二_上'] = ms2_in
                    st.session_state.sites_db.at[idx, '時段二_下'] = ms2_out
                    st.session_state.sites_db.at[idx, '時段三_上'] = ms3_in
                    st.session_state.sites_db.at[idx, '時段三_下'] = ms3_out
                    st.session_state.sites_db.at[idx, '注意事項'] = mod_notes
                    save_cloud_data(st.session_state.sites_db, 'sites', ['案場名稱', '案場地址', '案場性質', '案場聯絡人姓名', '案場聯絡人電話', '時段一_上', '時段一_下', '時段二_上', '時段二_下', '時段三_上', '時段三_下', '注意事項'])
                    st.success("✅ 雲端案場維護成功！")
                    st.rerun()
            with btn_col2:
                if st.button("🗑️ 刪除此案場並自雲端抹除", type="primary"):
                    st.session_state.sites_db = st.session_state.sites_db[st.session_state.sites_db['案場名稱'] != site_to_mod]
                    save_cloud_data(st.session_state.sites_db, 'sites', ['案場名稱', '案場地址', '案場性質', '案場聯絡人姓名', '案場聯絡人電話', '時段一_上', '時段一_下', '時段二_上', '時段二_下', '時段三_上', '時段三_下', '注意事項'])
                    st.success("🗑️ 案場資料已自雲端抹除！")
                    st.rerun()
    st.markdown("---")
    st.dataframe(st.session_state.sites_db, use_container_width=True)

elif page == "案場性質選單維護":
    st.title("🛠️ 案場性質選單維護")
    col1, col2 = st.columns(2)
    with col1:
        with st.form("type_add_form", clear_on_submit=True):
            new_type = st.text_input("➕ 新增案場性質名稱")
            add_btn = st.form_submit_button("確認新增項目")
            if add_btn and new_type:
                if new_type not in st.session_state.site_types:
                    st.session_state.site_types.append(new_type)
                    save_site_types(st.session_state.site_types)
                    st.success(f"✅ 成功新增並已同步至雲端：{new_type}")
                    st.rerun()
                else: st.warning("⚠️ 該性質項目已經存在！")
    with col2:
        st.subheader("🗑️ 刪除案場性質項目")
        if st.session_state.site_types:
            type_to_del = st.selectbox("請選擇要移除的性質：", st.session_state.site_types)
            if st.button("❌ 確認刪除此性質", type="primary"):
                st.session_state.site_types.remove(type_to_del)
                save_site_types(st.session_state.site_types)
                st.success(f"🗑️ 已成功自雲端移除！")
                st.rerun()

elif "線上登記請假排休" in page or "填報排休與手工修改" in page:
    st.title("🗓️ 線上填報排休與衝突看板")
    if is_admin:
        calculated_alerts = []
        if not st.session_state.leave_requests_db.empty and st.session_state.leave_requests_db['日期'].tolist()[0] != "":
            df_scan = st.session_state.leave_requests_db.copy()
            for (date_val, site_val, shift_val), g in df_scan.groupby(['日期', '案場名稱', '請假時段']):
                if len(g) >= 2:
                    names_str = "、".join(g['員工姓名'].tolist())
                    calculated_alerts.append(f"❌ **【時段人力警報】** 在 **{date_val}** 的 **{site_val} ({shift_val})**，同時有 {len(g)} 人（{names_str}）登記排休！")
        st.subheader("📢 即時人力衝突協調通知看板")
        if calculated_alerts:
            for alert in calculated_alerts: st.error(alert)
        else: st.success("✅ 目前各案場時段排休人力皆足夠。")
        st.markdown("---")

    col_entry, col_view = st.columns([1, 1])
    with col_entry:
        st.subheader("✍️ 填報特定時段休假")
        if is_admin:
            worker_options = st.session_state.workers_db['姓名'].tolist() if not st.session_state.workers_db.empty and st.session_state.workers_db['姓名'].tolist()[0] != "" else ["請先建立員工"]
            select_worker = st.selectbox("1. 請選擇填報姓名：", worker_options)
        else:
            st.info(f"🔒 安全鎖定：您目前只能為【{st.session_state.current_user_name}】進行排休操作。")
            select_worker = st.session_state.current_user_name

        if not st.session_state.workers_db.empty and not st.session_state.sites_db.empty:
            worker_rows = st.session_state.workers_db[st.session_state.workers_db['姓名'] == select_worker]
            if not worker_rows.empty:
                worker_info = worker_rows.iloc[0]
                assigned_sites_str = worker_info['派駐案場']
                worker_allowed_sites = [s.strip() for s in str(assigned_sites_str).split(',')] if pd.notna(assigned_sites_str) and assigned_sites_str != "未指定" else []
                if worker_allowed_sites and worker_allowed_sites[0] != "":
                    select_site = st.selectbox("2. 請選擇所屬案場：", worker_allowed_sites)
                    s_shifts = get_site_active_shifts(select_site)
                    
                    # 💡 智慧相容：如果對應的是「全天時段」，請假選項做優化調整
                    has_all_day_only = "全天時段" in s_shifts
                    shift_leave_options = ["全天班"] if has_all_day_only else ["整天全時段"] + list(s_shifts.keys())
                    
                    with st.form("leave_submit_form"):
                        select_date = st.date_input("3. 請選擇欲排休日期：", datetime.date(2026, 7, 1))
                        select_leave_shift = st.selectbox("4. 請選擇欲請假的精確時段：", shift_leave_options)
                        select_type = st.radio("5. 請選擇假別性質：", ["特休 (勞基法最高優先權)", "輪休 (一般排休)"])
                        submit_leave = st.form_submit_button("確認送出填報並同步雲端")
                        if submit_leave:
                            date_str = select_date.strftime('%Y-%m-%d')
                            if not st.session_state.leave_requests_db.empty:
                                st.session_state.leave_requests_db = st.session_state.leave_requests_db[~((st.session_state.leave_requests_db['日期'].astype(str) == date_str) & (st.session_state.leave_requests_db['員工姓名'].astype(str) == str(select_worker)) & (st.session_state.leave_requests_db['請假時段'].astype(str) == str(select_leave_shift)))]
                            new_leave = pd.DataFrame([{'日期': date_str, '案場名稱': str(select_site), '員工姓名': str(select_worker), '請假時段': str(select_leave_shift), '假別性質': str(select_type)}])
                            st.session_state.leave_requests_db = pd.concat([st.session_state.leave_requests_db, new_leave], ignore_index=True)
                            save_cloud_data(st.session_state.leave_requests_db, 'leave_requests', ['日期', '案場名稱', '員工姓名', '請假時段', '假別性質'])
                            st.success(f"✅ 成功寫入雲端資料庫！")
                            st.rerun()
                else: st.warning(f"⚠️ 提示：此帳號目前尚未指派任何派駐案場。")
            
    with col_view:
        st.subheader("📋 目前已登記的排休清單")
        if not st.session_state.leave_requests_db.empty and st.session_state.leave_requests_db['日期'].tolist()[0] != "":
            df_display = st.session_state.leave_requests_db.sort_values(by='日期').copy()
            if not is_admin:
                df_display = df_display[df_display['員工姓名'] == st.session_state.current_user_name]

            if df_display.empty: st.info("您目前尚無登記排休資料。")
            else: st.dataframe(df_display, use_container_width=True)
            
            if is_admin:
                st.markdown("---")
                st.subheader("🔧 管理者手工修改控制台")
                df_all = st.session_state.leave_requests_db.sort_values(by='日期').copy()
                df_all['選單標籤'] = df_all['日期'].astype(str) + " | " + df_all['員工姓名'].astype(str) + " (" + df_all['請假時段'].astype(str) + ") - " + df_all['案場名稱'].astype(str)
                target_leave_label = st.selectbox("請選擇您想調整或撤回的排休紀錄：", df_all['選單標籤'].tolist())
                match_row = df_all[df_all['選單標籤'] == target_leave_label].iloc[0]
                o_date, o_worker, o_site, o_shift = match_row['日期'], match_row['員工姓名'], match_row['案場名稱'], match_row['請假時段']
                db_ref = st.session_state.leave_requests_db
                idx = db_ref[(db_ref['日期'].astype(str) == str(o_date)) & (db_ref['員工姓名'].astype(str) == str(o_worker)) & (db_ref['案場名稱'].astype(str) == str(o_site)) & (db_ref['請假時段'].astype(str) == str(o_shift))].index[0]
                mod_date = st.date_input("修改請假日期：", datetime.datetime.strptime(str(o_date), '%Y-%m-%d').date())
                s_shifts_mod = get_site_active_shifts(o_site)
                
                if "全天時段" in s_shifts_mod:
                    mod_shift_options = ["全天班"]
                else:
                    mod_shift_options = ["整天全時段"] + list(s_shifts_mod.keys())
                    
                mod_shift = st.selectbox("修改請假時段：", mod_shift_options, index=mod_shift_options.index(o_shift) if o_shift in mod_shift_options else 0)
                mod_type = st.radio("修改假別類型：", ["特休 (勞基法最高優先權)", "輪休 (一般排休)"], index=0 if "特休" in str(match_row['假別性質']) else 1)
                btn_m1, btn_m2 = st.columns(2)
                with btn_m1:
                    if st.button("💾 儲存修改並同步雲端", use_container_width=True):
                        st.session_state.leave_requests_db.at[idx, '日期'] = mod_date.strftime('%Y-%m-%d')
                        st.session_state.leave_requests_db.at[idx, '請假時段'] = mod_shift
                        st.session_state.leave_requests_db.at[idx, '假別性質'] = mod_type
                        save_cloud_data(st.session_state.leave_requests_db, 'leave_requests', ['日期', '案場名稱', '員工姓名', '請假時段', '假別性質'])
                        st.success("✅ 雲端排休修改成功！")
                        st.rerun()
                with btn_m2:
                    if st.button("🗑️ 撤回並自雲端刪除此登記", type="primary", use_container_width=True):
                        st.session_state.leave_requests_db = st.session_state.leave_requests_db.drop(idx).reset_index(drop=True)
                        save_cloud_data(st.session_state.leave_requests_db, 'leave_requests', ['日期', '案場名稱', '員工姓名', '請假時段', '假別性質'])
                        st.success("🗑️ 紀錄已自雲端安全抹除！")
                        st.rerun()
        else: st.info("目前尚無任何登記排休資料。")

elif page == "🚀 管理者控制台：自動鋪底稿與微調":
    st.title("🚀 自動週期底稿鋪設與時段精準微調")
    if st.session_state.workers_db.empty or st.session_state.sites_db.empty or st.session_state.sites_db['案場名稱'].tolist()[0] == "":
        st.warning("⚠️ 請先建立工作者與案場基本資料。")
    else:
        st.subheader("🗓️ 模組一：快速鋪設整月週期底稿樣板")
        with st.expander("🛠️ 展開週期底稿引擎設定", expanded=True):
            col_t1, col_t2 = st.columns([1, 1])
            with col_t1:
                template_site = st.selectbox("1. 選擇要套用規律的案場：", st.session_state.sites_db['案場名稱'].tolist(), key="t_site")
                template_worker = st.selectbox("2. 選擇固定上工的人員：", st.session_state.workers_db['姓名'].tolist(), key="t_worker")
            
            with col_t2:
                # 💡 核心功能：讓管理者自由切換「星期勾選」或「日曆點選」
                鋪底稿模式 = st.radio("3. 請選擇底稿鋪設依據：", ["按星期規律（整月快速鋪設）", "按特定日期（日曆多選點面）"], horizontal=True)

            st.markdown("---")
            
            # 定義排班日期容器
            target_dates = []

            if 鋪底稿模式 == "按星期規律（整月快速鋪設）":
                col_w1, col_w2 = st.columns([1, 2])
                with col_w1:
                    target_year = st.selectbox("年份：", [2026, 2027], key="p_year")
                    target_month = st.selectbox("月份：", list(range(1, 13)), index=datetime.datetime.now().month - 1 if datetime.datetime.now().month <= 12 else 6, key="p_month")
                with col_w2:
                    st.markdown("**勾選固定出勤的星期：**")
                    w_days = []
                    cw1, cw2, cw3, cw4 = st.columns(4)
                    if cw1.checkbox("週一"): w_days.append(0)
                    if cw2.checkbox("週二"): w_days.append(1)
                    if cw3.checkbox("週三"): w_days.append(2)
                    if cw4.checkbox("週四"): w_days.append(3)
                    if cw1.checkbox("週五"): w_days.append(4)
                    if cw2.checkbox("週六"): w_days.append(5)
                    if cw3.checkbox("週日"): w_days.append(6)
                
                # 根據星期規律算出該月所有符合的日期
                if st.button("⚡ 開始依【星期】鋪設底稿（自動過濾排休）", type="primary"):
                    if not w_days:
                        st.error("❌ 請至少勾選一個出勤星期！")
                    else:
                        start_date = datetime.date(target_year, target_month, 1)
                        next_m = target_month + 1 if target_month < 12 else 1
                        next_y = target_year if target_month < 12 else target_year + 1
                        end_date = datetime.date(next_y, next_m, 1) - datetime.timedelta(days=1)
                        
                        curr = start_date
                        while curr <= end_date:
                            if curr.weekday() in w_days:
                                target_dates.append(curr)
                            curr += datetime.timedelta(days=1)

            else:
                # 💡 核心優化：彈出精美直式日曆表，允許滑鼠或手機連續多選特定日期
                st.markdown("**📅 請在下方日曆表中，點選所有欲上工的日期（可多選）：**")
                # 使用標準的多選日期陣列設定
                selected_calendar_dates = st.date_input(
                    "點擊輸入框會彈出日曆表，點選完日期後，再次點擊輸入框可繼續加選其他日期：",
                    value=[datetime.date(2026, 7, 1)],
                    key="calendar_multi_select"
                )
                
                if st.button("⚡ 開始依【日曆選定日期】鋪設底稿（自動過濾排休）", type="primary"):
                    # 🚀 超強防呆解析：管它返回什麼格式，一網打盡轉成乾淨的日期清單
                    if hasattr(selected_calendar_dates, '__iter__') and not isinstance(selected_calendar_dates, (str, bytes)):
                        target_dates = list(selected_calendar_dates)
                    elif selected_calendar_dates:
                        target_dates = [selected_calendar_dates]
                    else:
                        target_dates = []
                        
                    # 額外安全性防呆：如果使用者選了範圍導致有怪資料，過濾出真正的 date 物件
                    target_dates = [d for d in target_dates if isinstance(d, datetime.date)]
                    
                    if not target_dates:
                        st.error("❌ 偵測不到任何已選取的日期！請確認輸入框內有勾選的日期標籤。")

            # ⚙️ 統一的核心鋪設底稿引擎 (兩者共用後端)
            if target_dates:
                added_count = 0
                active_shifts = get_site_active_shifts(template_site)
                df_schedule = st.session_state.schedule_db.copy()
                
                for current_date in target_dates:
                    d_str = current_date.strftime('%Y-%m-%d')
                    for s_name, s_range in active_shifts.items():
                        is_shift_on_leave = False
                        
                        # 安全檢查是否有排休
                        if not st.session_state.leave_requests_db.empty and st.session_state.leave_requests_db['日期'].tolist()[0] != "":
                            l_db = st.session_state.leave_requests_db
                            match_leave = l_db[(l_db['日期'].astype(str) == d_str) & 
                                               (l_db['員工姓名'].astype(str) == template_worker) & 
                                               ((l_db['請假時段'] == "整天全時段") | (l_db['請假時段'] == "全天班") | (l_db['請假時段'] == s_name))]
                            if not match_leave.empty: 
                                is_shift_on_leave = True
                        
                        # 若沒請假，則自動鋪底稿
                        if not is_shift_on_leave:
                            t_up, t_down = s_range.split('-')
                            s_hours = parse_single_shift_hours(t_up, t_down)
                            if not df_schedule.empty:
                                df_schedule = df_schedule[~((df_schedule['日期'].astype(str) == d_str) & (df_schedule['案場名稱'].astype(str) == template_site) & (df_schedule['班段名稱'].astype(str) == s_name))]
                            
                            new_sch_row = pd.DataFrame([{'日期': d_str, '案場名稱': template_site, '員工姓名': template_worker, '班段名稱': s_name, '時段區間': s_range, '時源工時': str(s_hours)}])
                            df_schedule = pd.concat([df_schedule, new_sch_row], ignore_index=True)
                            added_count += 1
                            
                st.session_state.schedule_db = df_schedule
                save_cloud_data(df_schedule, 'schedule', ['日期', '案場名稱', '員工姓名', '班段名稱', '時段區間', '時源工時'])
                st.success(f"🎉 雲端底稿鋪设完畢！共成功寫入 {added_count} 筆班表數據。")
                st.rerun()
        st.markdown("---")
        st.subheader("📋 模組二：現有總班表名冊與時段精準微調")
        col_m1, col_m2 = st.columns([1, 2])
        with col_m1:
            st.markdown("🔧 **時段特定人員微調與抽換**")
            m_date = st.date_input("1. 調整日期：", datetime.date(2026, 7, 1))
            m_site = st.selectbox("2. 調整案場：", st.session_state.sites_db['案場名稱'].tolist())
            site_shifts = get_site_active_shifts(m_site)
            if site_shifts:
                shift_options = [f"{k} ({v})" for k, v in site_shifts.items()]
                selected_shift_opt = st.selectbox("3. 請選擇要修改的具體時段：", shift_options)
                target_shift_name = selected_shift_opt.split(' ')[0]
                target_time_range = site_shifts[target_shift_name]
                t_up, t_down = target_time_range.split('-')
                target_hours = parse_single_shift_hours(t_up, t_down)
                m_worker = st.selectbox("4. 指派該時段人員：", ["🗑️ 設為無人上班"] + st.session_state.workers_db['姓名'].tolist())
                if st.button("💾 確認儲存此時段調整變更並同步雲端", use_container_width=True):
                    d_str = m_date.strftime('%Y-%m-%d')
                    df_schedule_run = st.session_state.schedule_db.copy()
                    if not df_schedule_run.empty:
                        df_schedule_run = df_schedule_run[~((df_schedule_run['日期'].astype(str) == d_str) & (df_schedule_run['案場名稱'].astype(str) == m_site) & (df_schedule_run['班段名稱'].astype(str) == target_shift_name))]
                    if m_worker != "🗑️ 設為無人上班":
                        is_on_leave = False
                        if not st.session_state.leave_requests_db.empty and st.session_state.leave_requests_db['日期'].tolist()[0] != "":
                            l_db = st.session_state.leave_requests_db
                            is_on_leave = not l_db[(l_db['日期'].astype(str) == d_str) & (l_db['員工姓名'].astype(str) == m_worker) & ((l_db['請假時段'] == "整天全時段") | (l_db['請假時段'] == target_shift_name))].empty
                        if is_on_leave: st.error(f"❌ 錯誤：【{m_worker}】當天該時段已登記排休，不可重複指派！")
                        else:
                            new_row = pd.DataFrame([{'日期': d_str, '案場名稱': m_site, '員工姓名': m_worker, '班段名稱': target_shift_name, '時段區間': target_time_range, '時源工時': str(target_hours)}])
                            df_schedule_run = pd.concat([df_schedule_run, new_row], ignore_index=True)
                            st.session_state.schedule_db = df_schedule_run
                            save_cloud_data(df_schedule_run, 'schedule', ['日期', '案場名稱', '員工姓名', '班段名稱', '時段區間', '時源工時'])
                            st.success(f"✅ 【{m_worker}】該時段微調更新完畢！")
                            st.rerun()
                    else:
                        st.session_state.schedule_db = df_schedule_run
                        save_cloud_data(df_schedule_run, 'schedule', ['日期', '案場名稱', '員工姓名', '班段名稱', '時段區間', '時源工時'])
                        st.success(f"🗑️ 已成功撤除該時段值班人員。")
                        st.rerun()
            else: st.warning(f"⚠️ 提示：該案場目前未設定任何工作時間區段。")
        with col_m2:
            st.markdown("📊 **雲端已發布總排班名冊**")
            if not st.session_state.schedule_db.empty and st.session_state.schedule_db['日期'].tolist()[0] != "":
                # 💡 核心優化：優先以『案場名稱』做首層分組排序，次層再依據『日期』排序
                df_sorted = st.session_state.schedule_db.sort_values(by=['案場名稱', '日期', '班段名稱']).copy()
                st.dataframe(df_sorted, use_container_width=True)
                if st.button("🚨 重置與清空雲端排班庫"):
                    st.session_state.schedule_db = pd.DataFrame(columns=['日期', '案場名稱', '員工姓名', '班段名稱', '時段區間', '時源工時'])
                    save_cloud_data(st.session_state.schedule_db, 'schedule', ['日期', '案場名稱', '員工姓名', '班段名稱', '時段區間', '時源工時'])
                    st.rerun()

elif page == "📊 班表大印製中心：正式 PDF 產出":
    st.title("📊 勤務班表 PDF 印製與備註輸入中心")
    if st.session_state.schedule_db.empty or st.session_state.schedule_db['日期'].tolist()[0] == "":
        st.warning("⚠️ 目前雲端資料庫內尚無任何發布班表。")
    else:
        c_p1, c_p2, c_p3 = st.columns(3)
        with c_p1: sel_year = st.selectbox("設定年份：", [2026, 2027], index=0)
        with c_p2: sel_month = st.selectbox("設定月份：", list(range(1, 13)), index=6)
        with c_p3: sel_site = st.selectbox("設定目標案場：", st.session_state.sites_db['案場名稱'].tolist())
        
        try:
            start_date = datetime.date(sel_year, sel_month, 1)
            next_m = sel_month + 1 if sel_month < 12 else 1
            next_y = sel_year if sel_month < 12 else sel_year + 1
            end_date = datetime.date(next_y, next_m, 1) - datetime.timedelta(days=1)
            days_count = end_date.day
        except: days_count = 31
        
        
        week_mapping = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}
        rows_list = []
        for d in range(1, days_count + 1):
            loop_date = datetime.date(sel_year, sel_month, d)
            d_str = loop_date.strftime('%Y-%m-%d')
            w_idx = loop_date.weekday()
            w_name = week_mapping[w_idx]
            
            s_db = st.session_state.schedule_db
            day_site_data = s_db[(s_db['日期'] == d_str) & (s_db['案場名稱'] == sel_site)]
            
            l_db = st.session_state.leave_requests_db
            leave_text = ""
            if not l_db.empty and l_db['日期'].tolist()[0] != "":
                day_leave = l_db[(l_db['日期'] == d_str) & (l_db['案場名稱'] == sel_site)]
                if not day_leave.empty: 
                    leave_text = "、".join([f"{r['員工姓名']} ({str(r['請假時段']).replace('整天全時段', '全天班').replace('全天時段', '全天班')}休)" for _, r in day_leave.iterrows()])
            
            # 💡 核心優化：取消強制換行，且自動將時段名稱替換為「全天班」
            worker_shift_text = ""
            if not day_site_data.empty: 
                worker_shift_text = " / ".join([f"{r['員工姓名']} ({str(r['班段名稱']).replace('全天時段', '全天班')})" for _, r in day_site_data.iterrows()])
            
            date_key = f"{sel_site}_{sel_year}-{sel_month:02d}-{d:02d}"
            remark_text = remarks_db.get(date_key, "")
            rows_list.append({"日期": f"{d}", "休假": leave_text, "星期": w_name, "班別 / 勤務人員": worker_shift_text, "備註": remark_text})
            
        final_print_df = pd.DataFrame(rows_list)
        
        st.markdown("---")
        st.subheader("📝 第一步：編輯每日備註資料")
        edited_df = st.data_editor(final_print_df, use_container_width=True, disabled=["日期", "休假", "星期", "班別 / 勤務人員"], hide_index=True)
        
        if st.button("💾 儲存表格中的備註資料", type="secondary"):
            for idx, row in edited_df.iterrows():
                date_key = f"{sel_site}_{sel_year}-{sel_month:02d}-{int(row['日期']):02d}"
                remarks_db[date_key] = str(row['備註'])
            save_remarks(remarks_db)
            st.success("✅ 備註資料已成功儲存！")
            
        st.markdown("---")
        st.subheader("🖨️ 第二步：匯出正式 PDF 班表")
        
        if st.button("📥 一鍵產生並下載 PDF 班表", type="primary"):
            try:
                pdfmetrics.registerFont(TTFont('ChineseFont', FONT_FILE))
                buffer = io.BytesIO()
                # 縮小左右邊距，釋放更多水平印製空間給勤務人員
                doc = SimpleDocTemplate(buffer, pagesize=portrait(A4), rightMargin=20, leftMargin=20, topMargin=40, bottomMargin=40)
                elements = []
                styles = getSampleStyleSheet()
                title_style = ParagraphStyle(name='TitleStyle', fontName='ChineseFont', fontSize=15, spaceAfter=20, leading=20)
                title_text = f"<b>{COMPANY_NAME}</b><br/>{sel_site} {sel_month:02d}月班表"
                
                if os.path.exists(LOGO_FILE):
                    im = RLImage(LOGO_FILE, width=120, height=50)
                    header_table = Table([[im, Paragraph(title_text, title_style)]], colWidths=[130, 400])
                    header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
                    elements.append(header_table)
                else: elements.append(Paragraph(title_text, title_style))
                
                elements.append(Spacer(1, 10))
                cell_style = ParagraphStyle(name='CellStyle', fontName='ChineseFont', fontSize=9, leading=13, alignment=1)
                header_style = ParagraphStyle(name='HeaderStyle', fontName='ChineseFont', fontSize=10, alignment=1)
                
                data = [[Paragraph(f"<b>{c}</b>", header_style) for c in edited_df.columns]]
                for row in edited_df.values.tolist(): data.append([Paragraph(str(cell).replace('\n', '<br/>'), cell_style) for cell in row])
                
                # 💡 核心優化：調寬重要欄位（勤務人員放大到 270pt），縮小日期與星期，徹底防範擠壓
                t = Table(data, colWidths=[30, 110, 30, 270, 115], repeatRows=1)
                t.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))
                elements.append(t)
                elements.append(Spacer(1, 15))
                
                notes_style = ParagraphStyle(name='NoteStyle', fontName='ChineseFont', fontSize=9, leading=14)
                s_rows = st.session_state.sites_db[st.session_state.sites_db['案場名稱'] == sel_site]
                if not s_rows.empty and s_rows.iloc[0]['注意事項']:
                    for line in s_rows.iloc[0]['注意事項'].split('\n'): elements.append(Paragraph(line, notes_style))
                
                doc.build(elements)
                st.download_button(label="⬇️ 點擊下載正式 PDF 班表", data=buffer.getvalue(), file_name=f"{COMPANY_NAME}_{sel_site}_{sel_year}_{sel_month:02d}月班表.pdf", mime="application/pdf")
                st.success("✅ PDF 產生完畢！")
            except Exception as e: st.error(f"❌ PDF 產生失敗，請刷新重試：{str(e)}")

else:
    st.title("📱 員工個人出勤班表直式查詢")
    if st.session_state.schedule_db.empty or st.session_state.schedule_db['日期'].tolist()[0] == "":
        st.info("目前雲端資料庫內尚無發布的排班勤務數據。")
    else:
        c_emp1, c_emp2, c_emp3 = st.columns(3)
        with c_emp1:
            if is_admin:
                worker_names_list = st.session_state.workers_db['姓名'].tolist() if not st.session_state.workers_db.empty and st.session_state.workers_db['姓名'].tolist()[0] != "" else ["請先建立員工"]
                sel_worker_name = st.selectbox("請選取要查詢的姓名：", worker_names_list)
            else:
                st.info(f"🔒 隱私鎖定：您的專屬班表")
                sel_worker_name = st.session_state.current_user_name

        with c_emp2: sel_year = st.selectbox("查詢年份：", [2026, 2027], index=0)
        with c_emp3: sel_month = st.selectbox("查詢月份：", list(range(1, 13)), index=6)
            
        try:
            start_date = datetime.date(sel_year, sel_month, 1)
            next_m = sel_month + 1 if sel_month < 12 else 1
            next_y = sel_year if sel_month < 12 else sel_year + 1
            end_date = datetime.date(next_y, next_m, 1) - datetime.timedelta(days=1)
            days_count = end_date.day
        except: days_count = 31
        
        week_mapping = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}
        personal_rows = []
        for d in range(1, days_count + 1):
            loop_date = datetime.date(sel_year, sel_month, d)
            d_str = loop_date.strftime('%Y-%m-%d')
            w_name = week_mapping[loop_date.weekday()]
            
            s_db = st.session_state.schedule_db
            w_day_data = s_db[(s_db['日期'] == d_str) & (s_db['員工姓名'] == sel_worker_name)]
            duty_text = " / ".join([f"{r['案場名稱']} ({r['時段區間']})" for _, r in w_day_data.iterrows()]) if not w_day_data.empty else "（無排班）"
            
            l_db = st.session_state.leave_requests_db
            my_leave_text = ""
            if not l_db.empty and l_db['日期'].tolist()[0] != "":
                my_leave = l_db[(l_db['日期'] == d_str) & (l_db['員工姓名'] == sel_worker_name)]
                if not my_leave.empty: my_leave_text = "、".join([f"排休({r['請假時段']})" for _, r in my_leave.iterrows()])
            
            date_key = f"Personal_{sel_worker_name}_{sel_year}-{sel_month:02d}-{d:02d}"
            remark_text = remarks_db.get(date_key, "")
            personal_rows.append({"日期": f"{d}", "休假": my_leave_text, "星期": w_name, "值班勤務 / 班別": duty_text, "備註": remark_text})
            
        personal_df = pd.DataFrame(personal_rows)
        
        st.markdown("---")
        st.subheader("📝 第一步：編輯個人班表備註")
        edited_p_df = st.data_editor(personal_df, use_container_width=True, disabled=["日期", "休假", "星期", "值班勤務 / 班別"], hide_index=True)
        
        if st.button("💾 儲存個人備註資料", type="secondary"):
            for idx, row in edited_p_df.iterrows():
                date_key = f"Personal_{sel_worker_name}_{sel_year}-{sel_month:02d}-{int(row['日期']):02d}"
                remarks_db[date_key] = str(row['備註'])
            save_remarks(remarks_db)
            st.success("✅ 個人備註資料已成功儲存！")
            
        st.markdown("---")
        st.subheader("🖨️ 第二步：匯出個人正式 PDF 班表")
        
        if st.button("📥 一鍵產生並下載個人 PDF 班表", type="primary"):
            try:
                pdfmetrics.registerFont(TTFont('ChineseFont', FONT_FILE))
                buffer = io.BytesIO()
                doc = SimpleDocTemplate(buffer, pagesize=portrait(A4), rightMargin=20, leftMargin=20, topMargin=40, bottomMargin=40)
                elements = []
                styles = getSampleStyleSheet()
                title_style = ParagraphStyle(name='TitleStyle', fontName='ChineseFont', fontSize=15, spaceAfter=20, leading=20)
                title_text = f"<b>{COMPANY_NAME}</b><br/>【{sel_worker_name}】— {sel_year}年{sel_month:02d}月 班表"
                
                if os.path.exists(LOGO_FILE):
                    im = RLImage(LOGO_FILE, width=120, height=50)
                    header_table = Table([[im, Paragraph(title_text, title_style)]], colWidths=[130, 400])
                    header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
                    elements.append(header_table)
                else: elements.append(Paragraph(title_text, title_style))
                
                elements.append(Spacer(1, 10))
                cell_style = ParagraphStyle(name='CellStyle', fontName='ChineseFont', fontSize=9, leading=13, alignment=1)
                header_style = ParagraphStyle(name='HeaderStyle', fontName='ChineseFont', fontSize=10, alignment=1)
                
                data = [[Paragraph(f"<b>{c}</b>", header_style) for c in edited_p_df.columns]]
                for row in edited_p_df.values.tolist(): data.append([Paragraph(str(cell).replace('\n', '<br/>'), cell_style) for cell in row])
                
                t = Table(data, colWidths=[30, 110, 30, 270, 115], repeatRows=1)
                t.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))
                elements.append(t)
                
                notes_style = ParagraphStyle(name='NoteStyle', fontName='ChineseFont', fontSize=9, leading=14)
                elements.append(Spacer(1, 15))
                s_db_month = st.session_state.schedule_db
                worker_month_data = s_db_month[(s_db_month['員工姓名'] == sel_worker_name) & (s_db_month['日期'].str.startswith(f"{sel_year}-{sel_month:02d}"))]
                unique_sites = worker_month_data['案場名稱'].unique()
                
                if len(unique_sites) > 0:
                    elements.append(Paragraph("<b>【本月派駐案場資訊與注意事項】</b>", notes_style))
                    note_idx = 1
                    for site in unique_sites:
                        s_info = st.session_state.sites_db[st.session_state.sites_db['案場名稱'] == site]
                        if not s_info.empty: elements.append(Paragraph(f"{note_idx}、<b>{site}</b>：{s_info.iloc[0].get('案場地址', '')}", notes_style))
                        note_idx += 1
                    elements.append(Paragraph(f"{note_idx}、排班負責及聯絡人:(副總)張明倫 0931-110-721。", notes_style))
                    elements.append(Paragraph(f"{note_idx+1}、如有調班動作，請告知本公司負責人員，嚴禁擅自調班。", notes_style))

                doc.build(elements)
                st.download_button(label="⬇️ 點擊下載個人正式 PDF 班表", data=buffer.getvalue(), file_name=f"{COMPANY_NAME}_{sel_worker_name}_{sel_year}_{sel_month:02d}月_個人班表.pdf", mime="application/pdf")
                st.success("✅ 個人專屬 PDF 產生完畢！")
            except Exception as e: st.error(f"❌ PDF 產生失敗，請重試：{str(e)}")
