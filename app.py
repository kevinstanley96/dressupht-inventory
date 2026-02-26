import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
from fpdf import FPDF # New Library for PDF Control

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.9.1", layout="wide")

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

    # --- REINFORCED PAGINATION (GETS ALL 755+) ---
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
        cols = ['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']
        for c in cols:
            if c not in df.columns: df[c] = "N/A"
        return df

    # --- PDF GENERATOR FUNCTION ---
    def create_pdf(df, title_text):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(190, 10, title_text, ln=True, align='C')
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(190, 10, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align='C')
        pdf.ln(5)

        # Table Header
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(200, 220, 255)
        pdf.cell(25, 8, "Location", 1, 0, 'C', True)
        pdf.cell(95, 8, "Wig Name", 1, 0, 'C', True)
        pdf.cell(40, 8, "SKU", 1, 0, 'C', True)
        pdf.cell(15, 8, "Qty", 1, 0, 'C', True)
        pdf.cell(15, 8, "Price", 1, 1, 'C', True)

        # Table Rows
        pdf.set_font("Arial", '', 8)
        for _, row in df.iterrows():
            pdf.cell(25, 7, str(row['Location']), 1)
            # Truncate long names to fit
            name_txt = (str(row['Full Name'])[:50] + '..') if len(str(row['Full Name'])) > 50 else str(row['Full Name'])
            pdf.cell(95, 7, name_txt, 1)
            pdf.cell(40, 7, str(row['SKU']), 1)
            pdf.cell(15, 7, str(row['Stock']), 1, 0, 'C')
            pdf.cell(15, 7, f"{row['Price']}", 1, 1, 'C')
            
        return pdf.output(dest='S').encode('latin-1')

    # --- ROLES & CONTEXT ---
    roles_df = get_at_data("Role")
    user_row = roles_df[roles_df['User Name'] == username] if not roles_df.empty else pd.DataFrame()
    user_role = "Admin" if username == "Kevin" else (user_row['Access Level'].iloc[0] if not user_row.empty else "Staff")
    user_location = user_row['Assigned Location'].iloc[0] if not user_row.empty and 'Assigned Location' in user_row.columns else "Both"

    tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🛡️ Admin", "🔑 Password"])

    # --- TAB 1: LIBRARY (WITH PDF CONTROL) ---
    with tabs[0]:
        lib_data = get_at_data("Master_Inventory")
        if not lib_data.empty:
            st.subheader(f"📦 Inventory List ({len(lib_data)} items total)")
            
            # --- PDF CONTROL PANEL ---
            with st.expander("📄 PDF Export Controls"):
                c_pdf1, c_pdf2 = st.columns(2)
                export_loc = c_pdf1.selectbox("Filter PDF by Location", ["All Locations", "Pv", "Haiti"])
                pdf_title = c_pdf2.text_input("PDF Report Title", "Dressupht Master Inventory")
                
                # Filter data for PDF based on control
                pdf_df = lib_data.copy().sort_values(by="Full Name")
                if export_loc != "All Locations":
                    pdf_df = pdf_df[pdf_df['Location'] == export_loc]
                
                if st.button("🛠️ Generate PDF Report"):
                    pdf_bytes = create_pdf(pdf_df, pdf_title)
                    st.download_button(
                        label="⬇️ Download PDF Now",
                        data=pdf_bytes,
                        file_name=f"Inventory_{export_loc}_{date.today()}.pdf",
                        mime="application/pdf"
                    )

            st.divider()
            
            # --- REGULAR SEARCH & SORT ---
            c1, c2, c3 = st.columns([2, 1, 1])
            search = c1.text_input("🔍 Search Name or SKU")
            sort_choice = c2.selectbox("Sort By", ["Name", "Category", "Location"])
            
            disp_df = lib_data.copy()
            # Restrict view if Staff
            if user_role not in ['Admin', 'Manager'] and user_location != "Both":
                disp_df = disp_df[disp_df['Location'] == user_location]
            
            if sort_choice == "Name": disp_df = disp_df.sort_values(by="Full Name")
            elif sort_choice == "Location": disp_df = disp_df.sort_values(by=["Location", "Full Name"])
            
            if search:
                disp_df = disp_df[disp_df['Full Name'].str.contains(search, case=False, na=False) | disp_df['SKU'].str.contains(search, na=False)]
            
            st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 4: ADMIN (SYNC) ---
    # [Wipe and Batch Upload logic from v4.8 remains identical to handle all 755 items]
