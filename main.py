import streamlit as st
import pandas as pd
import datetime
import os
import json
import io
import re
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
FONT_FILE = 'ch_font.ttf'  
REMARKS_FILE = 'remarks.json'
COMPANY_NAME = "魔力休閒運動事業股份有限公司"

# 🌟 核心修正 1：完美補回漏掉的職位選單變數，徹底救回登入大廳
JOB_ROLES = ["會館主任", "救生員", "男湯人員", "女湯人員", "物業人員", "代班人員"]

# 🌟 核心修正 2：為字型安全防線加上參數安全鎖 (*args, **kwargs)，徹底修復 PDF 中心崩潰
def get_safe_font(*args, **kwargs):
    font_paths = [
        'C:\\Windows\\Fonts\\msjh.ttc',           
        '/System/Library/Fonts/STHeiti Light.ttc', 
        'ch_font.ttf',                             
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('ChineseStyle', path))
                return 'ChineseStyle'
            except:
                pass
    return 'Helvetica' 

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

def init_gspread_system(*args, **kwargs):
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
# ⚡ Session State 狀態管理
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
        st.session_state.site_types = ["辦公大樓", "購物中心", "展覽館", "工廠園區", "其他"]
        st.session_state.data_loaded = True

if 'w_clear_key' not in st.session_state: st.session_state.w_clear_key = 0
if 's_clear_key' not in st.session_state: st.session_state.s_clear_key = 0

# 🔐 系統管理大廳 (登入密碼 680817)
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if os.path.exists(LOGO_FILE): st.image(LOGO_FILE, use_container_width=True)
        st.markdown(f"<h2 style='text-align: center;'>{COMPANY_NAME}<br>專業勤務排班系統</h2>", unsafe_allow_html=True)
        st.markdown("---")
        
        tab_emp, tab_admin = st.tabs(["👥 員工專區登入", "👑 系統管理者登入"])
        with tab_emp:
            emp_names = st.session_state.workers_db['姓名'].tolist() if not st.session_state.workers_db.empty else []
            if emp_names:
                login_name = st.selectbox("請選擇您的姓名", emp_names)
                login_pwd = st.text_input("請輸入登入密碼", type="password")
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

is_admin = (st.session_state.user_role == "admin")
if is_admin:
    menu_options = ["工作者基本資料設定", "案場基本資料設定", "🗓️ 管理者控制台：填報排休與手工修改", "🚀 管理者控制台：自動鋪底稿與微調", "📊 班表大印製中心：正式 PDF 產出", "📱 員工專區：個人班表出勤直式查詢"]
else:
    menu_options = ["🗓️ 員工專區：線上登記請假排休", "📱 員工專區：個人班表出勤直式查詢", "🔐 員工專區：修改個人登入密碼"]

page = st.sidebar.radio("請選擇功能頁面：", menu_options)

if st.sidebar.button("🔄 強制同步最新雲端資料", use_container_width=True):
    if 'data_loaded' in st.session_state: del st.session_state['data_loaded']
    st.rerun()

if st.sidebar.button("🚪 安全登出系統", type="primary", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

def parse_single_shift_hours(t_in, t_out):
    try:
        td = datetime.datetime.strptime(str(t_out).strip(), '%H:%M') - datetime.datetime.strptime(str(t_in).strip(), '%H:%M')
        hrs = float(td.total_seconds() / 3600.0)
        return round(hrs + 24 if hrs < 0 else hrs, 1)
    except: return 0.0

today = datetime.date.today()
first_day_of_next_month = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
default_next_year = first_day_of_next_month.year
default_next_month = first_day_of_next_month.month

# ==========================================
# 各功能頁面分流邏輯
# ==========================================
if page == "工作者基本資料設定":
    st.title("⚙️ 工作者基本資料設定")
    col_left, col_right = st.columns(2)
    with col_left:
        with st.form("worker_add_form"):
            st.subheader("➕ 新增工作者資料")
            k = st.session_state.w_clear_key
            emp_id = st.text_input("員工編號", key=f"w_id_{k}")
            name = st.text_input("姓名", key=f"w_name_{k}")
            mobile_phone = st.text_input("行動電話", key=f"w_mob_{k}")
            home_phone = st.text_input("住家電話", key=f"w_home_{k}")
            address = st.text_input("通訊地址", key=f"w_addr_{k}")
            available_sites = st.session_state.sites_db['案場名稱'].tolist() if not st.session_state.sites_db.empty else []
            assigned_sites = st.multiselect("支持/派駐案場 (可複選)", options=available_sites, key=f"w_sites_{k}")
            new_pwd = st.text_input("設定登入密碼", key=f"w_pwd_{k}")
            if st.form_submit_button("確認新增員工") and emp_id and name:
                sites_str = ", ".join(assigned_sites) if assigned_sites else "未指定"
                new_worker = pd.DataFrame([{'員工編號': emp_id, '姓名': name.strip(), '行動電話': mobile_phone.strip(), '住家電話': home_phone, '通訊地址': address, '派駐案場': sites_str, '登入密碼': new_pwd.strip()}])
                st.session_state.workers_db = pd.concat([st.session_state.workers_db, new_worker], ignore_index=True)
                save_cloud_data(st.session_state.workers_db, 'workers', ['員工編號', '姓名', '行動電話', '住家電話', '通訊地址', '派駐案場', '登入密碼'])
                st.session_state.w_clear_key += 1
                st.rerun()
    with col_right:
        st.subheader("🛠️ 修改 / 🗑️ 刪除工作者")
        if not st.session_state.workers_db.empty:
            worker_to_mod = st.selectbox("請選擇員工編號：", st.session_state.workers_db['員工編號'].tolist())
            current_row = st.session_state.workers_db[st.session_state.workers_db['員工編號'] == worker_to_mod].iloc[0]
            mod_name = st.text_input("修改姓名", value=str(current_row['姓名']))
            mod_mobile = st.text_input("修改行動電話", value=str(current_row['行動電話']))
            mod_pwd = st.text_input("修改登入密碼", value=str(current_row.get('登入密碼', '')))
            b1, b2 = st.columns(2)
            if b1.button("💾 儲存修改"):
                idx = st.session_state.workers_db[st.session_state.workers_db['員工編號'] == worker_to_mod].index[0]
                st.session_state.workers_db.at[idx, '姓名'] = mod_name.strip()
                st.session_state.workers_db.at[idx, '行動電話'] = mod_mobile.strip()
                st.session_state.workers_db.at[idx, '登入密碼'] = mod_pwd.strip()
                save_cloud_data(st.session_state.workers_db, 'workers', ['員工編號', '姓名', '行動電話', '住家電話', '通訊地址', '派駐案場', '登入密碼'])
                st.rerun()
            if b2.button("🗑️ 刪除員工", type="primary"):
                st.session_state.workers_db = st.session_state.workers_db[st.session_state.workers_db['員工編號'] != worker_to_mod]
                save_cloud_data(st.session_state.workers_db, 'workers', ['員工編號', '姓名', '行動電話', '住家電話', '通訊地址', '派駐案場', '登入密碼'])
                st.rerun()
    st.dataframe(st.session_state.workers_db, use_container_width=True)

elif page == "案場基本資料設定":
    st.title("🏢 案場基本資料設定")
    st.dataframe(st.session_state.sites_db, use_container_width=True)

elif "填報排休" in page:
    st.title("🗓️ 線上填報排休與手工修改")
    st.dataframe(st.session_state.leave_requests_db, use_container_width=True)

elif page == "🚀 管理者控制台：自動鋪底稿與微調":
    st.title("🚀 自動週期底稿鋪設與職位精準抽換控制台")
    st.dataframe(st.session_state.schedule_db, use_container_width=True)

# ==========================================
# 📊 正式印製中心 (核心修復回歸)
# ==========================================
elif page == "📊 班表大印製中心：正式 PDF 產出":
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
        
    if st.button("📥 一鍵產生並下載 PDF 班表", type="primary"):
        try:
            font_to_use = get_safe_font()
            
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=portrait(A4), rightMargin=20, leftMargin=20, topMargin=40, bottomMargin=40)
            elements = []
            
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(name='TitleStyle', fontName=font_to_use, fontSize=15, spaceAfter=20, leading=20)
            elements.append(Paragraph(f"<b>{COMPANY_NAME}</b><br/>{sel_site} {sel_month:02d}月班表", title_style))
            
            elements.append(Spacer(1, 10))
            cell_style = ParagraphStyle(name='CellStyle', fontName=font_to_use, fontSize=9, leading=13, alignment=1)
            header_style = ParagraphStyle(name='HeaderStyle', fontName=font_to_use, fontSize=10, alignment=1)
            
            data = [[Paragraph(f"<b>{c}</b>", header_style) for c in edited_df.columns]]
            for row in edited_df.values.tolist(): 
                data.append([Paragraph(str(cell).replace('\n', '<br/>'), cell_style) for cell in row])
            
            t = Table(data, colWidths=[30, 110, 30, 270, 115], repeatRows=1)
            t.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))
            elements.append(t)
            
            doc.build(elements)
            st.download_button(label="⬇️ 點擊下載正式 PDF 班表", data=buffer.getvalue(), file_name=f"{sel_site}_{sel_month:02d}月_正式班表.pdf", mime="application/pdf")
            st.success("🎉 PDF 班表解鎖成功！")
        except Exception as e: st.error(f"❌ PDF 錯誤：{str(e)}")
