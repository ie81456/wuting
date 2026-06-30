# ... (其他程式碼保持不變，僅需更新下方這段 HTML 樣式區塊) ...

    # 🌟 修正：將橫向轉為直向 A4 列印，並優化直式滿版排版
    full_html_document = f"""
    <style>
        @media print {{
            body {{ background: #fff; color: #000; padding: 0; margin: 0; }}
            .no-print {{ display: none !important; }}
            #printArea {{ width: 100%; padding: 0 !important; }}
            /* 🌟 強制設定為 A4 直向列印 */
            @page {{ size: A4 portrait; margin: 1cm; }}
        }}
    </style>
    <div id='printArea' style='font-family:"Microsoft JhengHei", "Arial", sans-serif; padding:10px; background:#fff; color:#000; width:100%; box-sizing:border-box;'>
        <div style='width:100%; overflow:hidden; margin-bottom:15px;'>
            {logo_tag}
            <div style='float:left; padding-top:2px;'>
                <h2 style='margin:0; font-size:22px; font-weight:bold;'>{COMPANY_NAME}</h2>
                <h3 style='margin:2px 0 0 0; font-size:16px; color:#222;'>{sel_site} {sel_year}年{sel_month:02d}月份 勤務班表</h3>
            </div>
        </div>
        <table style='width:100%; border-collapse:collapse; background:#fff; font-size:14px; clear:both;'>
            <thead>
                <tr style='background-color:#f2f2f2; height:35px;'>
                    <th style='width:8%; border:1px solid #000; padding:6px;'>日期</th>
                    <th style='width:20%; border:1px solid #000; padding:6px;'>休假</th>
                    <th style='width:8%; border:1px solid #000; padding:6px;'>星期</th>
                    <th style='width:44%; border:1px solid #000; padding:6px;'>班別 / 勤務人員</th>
                    <th style='width:20%; border:1px solid #000; padding:6px;'>備註</th>
                </tr>
            </thead>
            <tbody>
                {html_table_rows}
            </tbody>
        </table>
        {site_notes_html}
    </div>
    <div class='no-print' style='text-align:center; margin-top:20px;'>
        <button onclick='window.print();' style='padding:12px 35px; font-size:16px; font-weight:bold; background-color:#1E88E5; color:white; border:none; border-radius:5px; cursor:pointer;'>🖨️ 啟動 A4 直式班表放大列印中心</button>
    </div>
    """
# ... (其餘程式碼保持不變)
