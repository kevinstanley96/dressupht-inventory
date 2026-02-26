import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
from fpdf import FPDF 

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.9.2", layout="wide")

# --- AUTHENTICATION (Standard) ---
usernames_list = ["Djessie", "Kevin", "Casimir", "Melchisedek", "David", "Darius", "Eliada", "Sebastien", "Guirlene", "Carmela", "Angelina", "Tamara", "Dorotheline", "Sarah", "Valerie", "Saouda", "Marie France", "Carelle", "Annaelle", "Gerdine", "Martilda"]
credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames_list}}
credentials['usernames']['Kevin']['password'] = "The$100$Raven"

authenticator = stauth.Authenticate(credentials, "inventory_cookie", "abcdef123456_key", 30)
name, authentication_status, username = authenticator.login(location='main')

if st.session_state["authentication_status"]:
    username = st.session_state["username"]
    
    try:
        AIR_TOKEN = st.secrets["AIRTABLE_TOKEN"]
        BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
        HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}
    except:
        st.error("Missing Secrets!")
        st.stop()

    # --- PAGINATION ENGINE ---
    @st.cache_data(ttl=60)
    def get_at_data(table):
        all_records = []
        offset = None
        base_url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
        while True:
            params = {"offset": offset} if offset else {}
            res = requests.get(base_url, headers=HEADERS, params=params)
            if res.status_code == 200:
                data = res.json()
                for r in data.get('records', []):
                    row = r['fields']
                    row['id'] = r['id']
                    all_records.append(row)
                offset = data.get('offset')
                if not offset: break
            else: break
        df = pd.DataFrame(all_records)
        for c in ['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']:
            if c not in df.columns: df[c] = "N/A"
        return df

    # --- ENHANCED PDF GENERATOR WITH TOTALS ---
    def create_pdf(df, title_text):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(190, 10, title_text, ln=True, align='C')
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(190, 7, f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align='C')
        pdf.ln(10)

        # Header
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(20, 8, "Loc", 1, 0, 'C', True)
        pdf.cell(90, 8, "Item Name", 1, 0, 'C', True)
        pdf.cell(40, 8, "SKU", 1, 0, 'C', True)
        pdf.cell(15, 8, "Qty", 1, 0, 'C', True)
        pdf.cell(25, 8, "Value", 1, 1, 'C', True)

        total_qty = 0
        total_value = 0.0

        # Rows
        pdf.set_font("Arial", '', 8)
        for _, row in df.iterrows():
            qty = int(row['Stock'])
            price = float(row['Price'])
            line_val = qty * price
            
            pdf.cell(20, 7, str(row['Location']), 1)
            pdf.cell(90, 7, str(row['Full Name'])[:55], 1)
            pdf.cell(40, 7, str(row['SKU']), 1)
            pdf.cell(15, 7, str(qty), 1, 0, 'C')
            pdf.cell(25, 7, f"${line_val:,.2f}", 1, 1, 'R')
            
            total_qty += qty
            total_value += line_val

        # Summary Footer
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(255, 255, 200) # Highlight yellow
        pdf.cell(150, 10, "GRAND TOTAL INVENTORY VALUE:", 1, 0, 'R', True)
        pdf.cell(40, 10, f"${total_value:,.2f}", 1, 1, 'C', True)
        pdf.cell(150, 10, "TOTAL UNIT COUNT:", 1, 0, 'R')
        pdf.cell(40, 10, str(total_qty), 1, 1, 'C')
            
        return pdf.output(dest='S').encode('latin-1')

    # --- APPLICATION TABS ---
    tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🛡️ Admin", "🔑 Password"])

    with tabs[0]:
        lib_data = get_at_data("Master_Inventory")
        if not lib_data.empty:
            st.subheader(f"📦 Inventory ({len(lib_data)} Wigs Found)")
            
            # PDF Options
            with st.expander("📄 PDF Control & Financial Export"):
                c_p1, c_p2 = st.columns(2)
                pdf_loc = c_p1.selectbox("Filter PDF Location", ["All", "Pv", "Haiti"])
                pdf_name = c_p2.text_input("Report Name", "Dressupht Stock Value Report")
                
                pdf_ready_df = lib_data.copy().sort_values(by="Full Name")
                if pdf_loc != "All":
                    pdf_ready_df = pdf_ready_df[pdf_ready_df['Location'] == pdf_loc]
                
                if st.button("Generate Financial PDF"):
                    bytes_data = create_pdf(pdf_ready_df, pdf_name)
                    st.download_button("Download Report", bytes_data, f"Inventory_Value_{pdf_loc}.pdf", "application/pdf")

            # Normal View
            st.divider()
            c_s1, c_s2 = st.columns([2,1])
            search = c_s1.text_input("Search")
            sort_by = c_s2.selectbox("Sort Order", ["Name", "Location", "Category"])
            
            disp_df = lib_data.copy()
            if sort_by == "Location": disp_df = disp_df.sort_values(by=["Location", "Full Name"])
            else: disp_df = disp_df.sort_values(by="Full Name")
            
            if search:
                disp_df = disp_df[disp_df['Full Name'].str.contains(search, case=False, na=False) | disp_df['SKU'].str.contains(search, na=False)]
            
            st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # Admin tab for Syncing 755 items remains the same...
