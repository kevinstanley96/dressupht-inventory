import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
from fpdf import FPDF 

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.9.3", layout="wide")

# --- AUTHENTICATION ---
usernames_list = ["Djessie", "Kevin", "Casimir", "Melchisedek", "David", "Darius", "Eliada", "Sebastien", "Guirlene", "Carmela", "Angelina", "Tamara", "Dorotheline", "Sarah", "Valerie", "Saouda", "Marie France", "Carelle", "Annaelle", "Gerdine", "Martilda"]
credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames_list}}
credentials['usernames']['Kevin']['password'] = "The$100$Raven"

authenticator = stauth.Authenticate(credentials, "inventory_cookie", "abcdef123456_key", 30)
name, authentication_status, username = authenticator.login(location='main')

if st.session_state["authentication_status"]:
    username = st.session_state["username"]
    authenticator.logout('Logout', 'sidebar')

    try:
        AIR_TOKEN = st.secrets["AIRTABLE_TOKEN"]
        BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
        HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}
    except:
        st.error("Missing Secrets!")
        st.stop()

    # --- 1. REINFORCED PAGINATION (GETS ALL 755+ RECORDS) ---
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
        # Ensure standard column set for display
        for c in ['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']:
            if c not in df.columns: df[c] = "N/A"
        return df

    # --- 2. CLEANING LOGIC (SQUARE MAPPING & NaN FIX) ---
    def clean_location_data(file, loc_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip() for c in df.columns]
        
        # Mapping Square 'Categories' to Airtable 'Category'
        mapping = {'Item Name': 'Wig Name', 'Variation Name': 'Style', 'SKU': 'SKU', 'Price': 'Price', 'Categories': 'Category'}
        df = df.rename(columns=mapping)

        # Handle Location-Specific Stock Columns
        stock_col = "Current Quantity Dressup Haiti" if loc_name == "Haiti" else "Current Quantity Dressupht Pv"
        if stock_col in df.columns:
            df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int)
        else:
            df['Stock'] = 0 
            
        df['Category'] = df['Category'].fillna("Uncategorized")
        df['Location'] = loc_name
        df['SKU'] = df['SKU'].astype(str).str.strip().replace('nan', 'NO_SKU')
        
        # Build Full Name
        w_name = df['Wig Name'].astype(str).replace('nan', 'Unknown')
        s_name = df['Style'].astype(str).replace('nan', '')
        df['Full Name'] = w_name + " (" + s_name + ")"
        
        # Price Sanitization
        df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
        
        return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']].copy()

    # --- 3. PDF GENERATOR WITH CONTROL & TOTALS ---
    def create_pdf(df, title_text):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(190, 10, title_text, ln=True, align='C')
        pdf.ln(10)
        
        # Table Header
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(230, 230, 230)
        cols = [("Loc", 20), ("Item Name", 90), ("SKU", 40), ("Qty", 15), ("Value", 25)]
        for label, width in cols:
            pdf.cell(width, 8, label, 1, 0, 'C', True)
        pdf.ln()

        total_qty = 0
        total_val = 0.0
        pdf.set_font("Arial", '', 8)
        for _, row in df.iterrows():
            q = int(row['Stock'])
            p = float(row['Price'])
            val = q * p
            pdf.cell(20, 7, str(row['Location']), 1)
            pdf.cell(90, 7, str(row['Full Name'])[:55], 1)
            pdf.cell(40, 7, str(row['SKU']), 1)
            pdf.cell(15, 7, str(q), 1, 0, 'C')
            pdf.cell(25, 7, f"${val:,.2f}", 1, 1, 'R')
            total_qty += q
            total_val += val

        pdf.ln(5)
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(255, 255, 200)
        pdf.cell(150, 10, "GRAND TOTAL VALUE:", 1, 0, 'R', True)
        pdf.cell(40, 10, f"${total_val:,.2f}", 1, 1, 'C', True)
        return pdf.output(dest='S').encode('latin-1')

    # --- DATA CONTEXT ---
    roles_df = get_at_data("Role")
    user_row = roles_df[roles_df['User Name'] == username] if not roles_df.empty else pd.DataFrame()
    user_role = "Admin" if username == "Kevin" else (user_row['Access Level'].iloc[0] if not user_row.empty else "Staff")
    user_location = user_row['Assigned Location'].iloc[0] if not user_row.empty and 'Assigned Location' in user_row.columns else "Both"

    tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🛡️ Admin", "🔑 Password"])

    # --- TAB 1: LIBRARY (SORTING PRESERVED) ---
    with tabs[0]:
        lib_data = get_at_data("Master_Inventory")
        st.subheader(f"📦 Inventory List ({len(lib_data)} Wigs)")
        
        with st.expander("📄 PDF Export Controls"):
            c_p1, c_p2 = st.columns(2)
            p_loc = c_p1.selectbox("Filter PDF by Location", ["All", "Pv", "Haiti"])
            p_title = c_p2.text_input("PDF Report Title", "Inventory Audit")
            p_df = lib_data.copy().sort_values(by="Full Name")
            if p_loc != "All": p_df = p_df[p_df['Location'] == p_loc]
            if st.button("Generate PDF"):
                st.download_button("Download", create_pdf(p_df, p_title), "Report.pdf", "application/pdf")

        c1, c2, c3 = st.columns([2, 1, 1])
        search = c1.text_input("🔍 Search Name/SKU")
        sort_choice = c2.selectbox("Sort By", ["Name", "Location", "Category", "Newest"])
        
        disp_df = lib_data.copy()
        if user_role not in ['Admin', 'Manager'] and user_location != "Both":
            disp_df = disp_df[disp_df['Location'] == user_location]
            
        if sort_choice == "Location": disp_df = disp_df.sort_values(by=["Location", "Full Name"])
        elif sort_choice == "Category": disp_df = disp_df.sort_values(by=["Category", "Full Name"])
        elif sort_choice == "Newest": disp_df = disp_df.sort_values(by="id", ascending=False)
        else: disp_df = disp_df.sort_values(by="Full Name")

        if search:
            disp_df = disp_df[disp_df['Full Name'].str.contains(search, case=False, na=False) | disp_df['SKU'].str.contains(search, na=False)]
        
        st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 4: ADMIN (WIPE & SYNC PRESERVED) ---
    if user_role == 'Admin':
        with tabs[3]:
            st.subheader("🛡️ System Sync (Wipe & Reload)")
            f1 = st.file_uploader("PV File", type=['xlsx'])
            f2 = st.file_uploader("Haiti File", type=['xlsx'])
            if f1 and f2:
                if st.button("🚀 Run Full Sync (755+ Items)"):
                    d1 = clean_location_data(f1, "Pv")
                    d2 = clean_location_data(f2, "Haiti")
                    full = pd.concat([d1, d2]).reset_index(drop=True)
                    
                    # Wipe
                    old = get_at_data("Master_Inventory")
                    if not old.empty:
                        for i in range(0, len(old), 10):
                            batch = old['id'].tolist()[i:i+10]
                            q = "&".join([f"records[]={rid}" for rid in batch])
                            requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory?{q}", headers=HEADERS)
                    
                    # Batch Upload
                    prog = st.progress(0)
                    for i in range(0, len(full), 10):
                        chunk = full.iloc[i:i+10]
                        recs = [{"fields": r.to_dict()} for _, r in chunk.iterrows()]
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs})
                        prog.progress(min((i+10)/len(full), 1.0))
                        time.sleep(0.2)
                    st.success("Sync Finished!")
                    st.rerun()

elif authentication_status is False: st.error("Login Failed")
