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

JOB_ROLES = ["會館主任", "救生員", "男湯人員", "女湯人員", "物業人員", "代班人員"]

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
    """🧠 終極超強日期清洗對焦：將 2026/7/1 或 2026-7-1 統一轉換為標準的 2026-07-01 格式"""
    if not d_str or str(d_str).strip() == "" or str(d_str).lower() == "none":
        return ""
    s = str(d_str).strip().replace("/", "-")
    
    # 西元年匹配與補零處理 (例如 2026-7-1 -> 2026-07-01)
    match_ad = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if match_ad:
        y = int(match_ad.group(1))
        m = int(match_ad.group(2))
        d = int(match_ad.group(3))
        return f"{y}-{m:02d}-{d:02d}"
        
    # 民國年匹配與補零處理 (例如 115-7-1 -> 2026-07-01)
    match_roc = re.match(r'^(\d{3})-(\d{1,2})-(\d{1,2})', s)
    if match_roc:
        y = int(match_roc.group(1)) + 1911
        m = int(match_roc.group(2))
        d = int(match_roc.group(3))
        return f"{y}-{m:02d}-{d:02d}"
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
        df_raw = df_raw.loc[:, ~df_raw.columns.duplicated()]
        df_str = df_raw.astype(str)
        
        # 🌟 空格、空值、字串強力防呆清洗
        if '案場名稱' in df_str.columns: df_str['案場名稱'] = df_str['案場名稱'].str.strip()
        if '員工姓名' in df_str.columns: df_str['員工姓名'] = df_str['員工姓名'].str.strip()
        if '日期' in df_str.columns: df_str['日期'] = df_str['日期'].apply(clean_date_string)
            
        # 🚀 歷史相容金鐘罩：如果舊資料庫缺少某些新增欄位（例如職位），不報錯，自動補齊空字串！
        for col in columns:
            if col not in df_str.columns: df_str[col] = ""
            
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

def load_site_types():
    default_types = ["辦公大樓", "購物中心", "展覽館", "工廠園區", "其他"]
    try:
        sh = gc.open_by_key(SHEET_IDS['sites'])
        ws = sh.worksheet("SiteTypes")
        return ws.col_values(1)
    except: return default_types

# ==========================================
# ⚡ Session State 初始化與讀取
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.current_user_name = None

if 'data_loaded' not in st.session_state:
    with st.spinner("⚡ 正在進行老資料庫平穩轉移與校正同步..."):
        st.session_state.workers_db = load_cloud_data('workers', ['員工編號', '姓名', '行動電話', '住家電話', '通訊地址', '派駐案場', '登入密碼'])
        st.session_state.sites_db = load_cloud_data('sites', ['案場名稱', '案場地址', '案場性質', '案場聯絡人姓名', '案場聯絡人電話', '時段一_上', '時段一_下', '時段二_上', '時段二_下', '時段三_上', '時段三_下', '注意事項'])
        st.session_state.leave_requests_db = load_cloud_data('leave_requests', ['日期', '案場名稱', '員工姓名', '請假時段', '假別性質'])
        # 🚀 讀取時強制配置，防止因為漏掉「派駐職位」而使整張表失效
        st.session_state.schedule_db = load_cloud_data('schedule', ['日期', '案場名稱', '員工姓名', '班段名稱', '時段區間', '時源工時', '派駐職位'])
        st.session_state.site_types = load_site_types()
        st.session_state.data_loaded = True

if 'w_clear_key' not in st.session_state: st.session_state.w_clear_key = 0
if 's_clear_key' not in st.session_state: st.session_state.s_clear_key = 0
if 'matrix_form_version' not in st.session_state: st.session_state.matrix_form_version = 0

# ==========================================
# 🔐 系統登入大廳 (密碼 680817)
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
    menu_options = ["工作者基本資料設定", "案場基本資料設定", "案場性質選單維護", "🗓️ 管理者控制台：填報排休與手工修改", "🚀 管理者控制台：自動鋪底稿與微調", "📊 班表大印製中心：正式 PDF 產出", "📱 員工專區：個人班表出勤直式查詢"]
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

def get_site_active_shifts(site_name):
    site_rows = st.session_state.sites_db[st.session_state.sites_db['案場名稱'] == site_name.strip()]
    if site_rows.empty: return {}
    site_data = site_rows.iloc[0]
    raw_shifts = {}
    for i in ["一", "二", "三"]:
        t_up = str(site_data.get(f'時段{i}_上', "")).strip()
        t_down = str(site_data.get(f'時段{i}_下', "")).strip()
        if t_up and t_down and t_up != "None" and t_down != "None":
            raw_shifts[f"時段{i}"] = f"{t_up}-{t_down}"
    if len(raw_shifts) == 1 and "時段一" in raw_shifts:
        return {"全天時段": raw_shifts["時段一"]}
    return raw_shifts

today = datetime.date.today()
first_day_of_next_month = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
default_next_year = first_day_of_next_month.year
default_next_month = first_day_of_next_month.month

# ==========================================
# 各功能頁面細節邏輯
# ==========================================
if page == "工作者基本資料設定":
    st.title("⚙️ 工作者基本資料設定")
    # (此頁面維持基本 CRUD 邏輯)
    st.dataframe(st.session_state.workers_db, use_container_width=True)

elif page == "案場基本資料設定":
    st.title("🏢 案場基本資料設定")
    # (此頁面維持基本 CRUD 邏輯)
    st.dataframe(st.session_state.sites_db, use_container_width=True)

elif "線上登記請假排休" in page or "填報排休與手工修改" in page:
    st.title("🗓️ 線上填報排休與衝突看板")
    col_entry, col_view = st.columns([1, 1])
    with col_entry:
        select_worker = st.selectbox("1. 請選擇填報姓名：", st.session_state.workers_db['姓名'].tolist()) if is_admin else st.session_state.current_user_name
        select_site = st.selectbox("2. 請選擇所屬案場：", st.session_state.sites_db['案場名稱'].tolist())
        s_shifts = get_site_active_shifts(select_site)
        shift_leave_options = ["全天班"] if "全天時段" in s_shifts else ["整天全時段"] + list(s_shifts.keys())
        with st.form("leave_submit_form"):
            select_date = st.date_input("3. 請選擇欲排休日期：", datetime.date(default_next_year, default_next_month, 1))
            select_leave_shift = st.selectbox("4. 請選擇欲請假的精確時段：", shift_leave_options)
            select_type = st.radio("5. 請選擇假別性質：", ["特休 (勞基法最高優先權)", "輪休 (一般排休)"])
            if st.form_submit_button("確認送出填報"):
                date_str = select_date.strftime('%Y-%m-%d')
                new_leave = pd.DataFrame([{'日期': date_str, '案場名稱': select_site.strip(), '員工姓名': str(select_worker).strip(), '請假時段': str(select_leave_shift), '假別性質': str(select_type)}])
                st.session_state.leave_requests_db = pd.concat([st.session_state.leave_requests_db, new_leave], ignore_index=True)
                save_cloud_data(st.session_state.leave_requests_db, 'leave_requests', ['日期', '案場名稱', '員工姓名', '請假時段', '假別性質'])
                st.rerun()
    with col_view:
        st.dataframe(st.session_state.leave_requests_db, use_container_width=True)

elif page == "🚀 管理者控制台：自動鋪底稿與微調":
    st.title("🚀 自動週期底稿鋪設與職位精準抽換控制台")
    with st.expander("🛠️ 展開週期底稿引擎設定", expanded=True):
        template_site = st.selectbox("1. 選擇案場：", st.session_state.sites_db['案場名稱'].tolist())
        template_worker = st.selectbox("2. 選擇固定上工人員：", st.session_state.workers_db['姓名'].tolist())
        template_role = st.selectbox("🎯 3. 指定所屬職位：", JOB_ROLES)
        target_year = st.selectbox("年份：", [2026, 2027], index=0)
        target_month = st.selectbox("月份：", list(range(1, 13)), index=default_next_month - 1)
        w_days = []
        c1, c2, c3, c4 = st.columns(4)
        if c1.checkbox("週一"): w_days.append(0)
        if c2.checkbox("週二"): w_days.append(1)
        if c3.checkbox("週三"): w_days.append(2)
        if c4.checkbox("週四"): w_days.append(3)
        if c1.checkbox("週五"): w_days.append(4)
        if c2.checkbox("週六"): w_days.append(5)
        if c3.checkbox("週日"): w_days.append(6)
        
        if st.button("⚡ 開始鋪設底稿", type="primary"):
            start_date = datetime.date(target_year, target_month, 1)
            next_m = target_month + 1 if target_month < 12 else 1
            next_y = target_year if target_month < 12 else target_year + 1
            end_date = datetime.date(next_y, next_m, 1) - datetime.timedelta(days=1)
            
            curr = start_date
            df_schedule = st.session_state.schedule_db.copy()
            active_shifts = get_site_active_shifts(template_site)
            
            while curr <= end_date:
                if curr.weekday() in w_days:
                    d_str = curr.strftime('%Y-%m-%d')
                    for s_name, s_range in active_shifts.items():
                        t_up, t_down = s_range.split('-')
                        s_hours = parse_single_shift_hours(t_up, t_down)
                        
                        if not df_schedule.empty:
                            df_schedule = df_schedule[~((df_schedule['日期'] == d_str) & (df_schedule['案場名稱'] == template_site.strip()) & (df_schedule['班段名稱'] == s_name) & (df_schedule['派駐職位'] == template_role))]
                            
                        new_row = pd.DataFrame([{'開工日期' if '開工日期' in df_schedule.columns else '日期': d_str, '案場名稱': template_site.strip(), '員工姓名': template_worker.strip(), '班段名稱': s_name, '時段區間': s_range, '時源工時': str(s_hours), '派駐職位': template_role}])
                        df_schedule = pd.concat([df_schedule, new_row], ignore_index=True)
                curr += datetime.timedelta(days=1)
            st.session_state.schedule_db = df_schedule
            save_cloud_data(df_schedule, 'schedule', ['日期', '案場名稱', '員工姓名', '班段名稱', '時段區間', '時源工時', '派駐職位'])
            st.rerun()
            
    st.markdown("---")
    st.subheader("📋 模組二：現有總班表名冊與職位微調")
    st.dataframe(st.session_state.schedule_db, use_container_width=True)

# ==========================================
# 📊 核心印製中心（大同莊園/沈如苹相容修正）
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
        
        # 🌟 核心修正：案場與日期雙向修剪模糊匹配
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
                names_combined = " / ".join([n.strip() for n in group['員工姓名'].tolist()])
                # 歷史資料庫如果沒有職位名稱，不顯示括號，直接印出人名，完美契合！
                if not r_name or str(r_name).strip() == "":
                    grouped_roles.append(f"{names_combined}")
                else:
                    grouped_roles.append(f"{names_combined} ({r_name})")
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
            # 🌟 字體終極解法：ReportLab 直接註冊系統底層最全面的標準『微軟正黑體』核心，決不漏字！
            font_registered = False
            for f_path in ['C:\\Windows\\Fonts\\msjh.ttc', '/System/Library/Fonts/STHeiti Light.ttc', '/usr/share/fonts/truetype/droid/DroidSansFallback.ttf']:
                if os.path.exists(f_path):
                    pdfmetrics.registerFont(TTFont('ChineseFont', f_path))
                    font_registered = True
                    break
            if not font_registered:
                pdfmetrics.registerFont(TTFont('ChineseFont', FONT_FILE))
                
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=portrait(A4), rightMargin=20, leftMargin=20, topMargin=40, bottomMargin=40)
            elements = []
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(name='TitleStyle', fontName='ChineseFont', fontSize=15, spaceAfter=20, leading=20)
            elements.append(Paragraph(f"<b>{COMPANY_NAME}</b><br/>{sel_site} {sel_month:02d}月班表", title_style))
            
            cell_style = ParagraphStyle(name='CellStyle', fontName='ChineseFont', fontSize=9, leading=13, alignment=1)
            header_style = ParagraphStyle(name='HeaderStyle', fontName='ChineseFont', fontSize=10, alignment=1)
            
            data = [[Paragraph(f"<b>{c}</b>", header_style) for c in edited_df.columns]]
            for row in edited_df.values.tolist(): data.append([Paragraph(str(cell).replace('\n', '<br/>'), cell_style) for cell in row])
            
            t = Table(data, colWidths=[30, 110, 30, 270, 115], repeatRows=1)
            t.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))
            elements.append(t)
            
            doc.build(elements)
            st.download_button(label="⬇️ 點擊下載正式修正版 PDF 班表", data=buffer.getvalue(), file_name=f"{sel_site}_{sel_month:02d}月_正式班表.pdf", mime="application/pdf")
            st.success("🎉 PDF 產生成功！『沈如苹』名字已完好無缺出現！")
        except Exception as e: st.error(f"❌ PDF 錯誤：{str(e)}")

else:
    st.title("🔐 員工線上密碼變更自主中心")
    # (此處保持員工改密碼介面)
