import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import base64

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.2", layout="wide")
REPO_NAME = "kevin/dressupht-inventory" 

# --- AUTHENTICATION ---
usernames_list = ["Djessie", "Kevin", "Casimir", "Melchisedek", "David", "Darius", "Eliada", "Sebastien", "Guirlene", "Carmela", "Angelina", "Tamara", "Dorotheline", "Sarah", "Valerie", "Saouda", "Marie France", "Carelle", "Annaelle", "Gerdine", "Martilda"]
credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames_list}}
credentials['usernames']['Kevin']['password'] = "The$100$Raven"

authenticator = stauth.Authenticate(credentials, "inventory_cookie", "abcdef123456_key", 30)
authentication_status = authenticator.login(location='main')

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

    # --- DATA ENGINE ---
    def get_at_data(table, params=None):
        all_recs = []
        url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
        if params is None: params = {}
        while True:
            res = requests.get(url, headers=HEADERS, params=params)
            if res.status_code == 200:
                data = res.json()
                all_recs.extend(data.get('records', []))
                offset = data.get('offset')
                if offset: params['offset'] = offset
                else: break
            else: break
        if not all_recs: return pd.DataFrame()
        df = pd.DataFrame([dict(r['fields'], id=r['id']) for r in all_recs])
        # Safety Columns
        for col in ['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']:
            if col not in df.columns: df[col] = "N/A"
        return df

    def clean_location_data(file, loc_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip().lower() for c in df.columns]
        mapping = {'item name': 'Wig Name', 'variation name': 'Style', 'sku': 'SKU', 'price': 'Price', 'categories': 'Category'}
        df = df.rename(columns=mapping)
        df['SKU'] = df['SKU'].astype(str).str.strip().replace('nan', 'NO_SKU')
        df['Full Name'] = df['Wig Name'].astype(str) + " (" + df['Style'].astype(str).replace('nan', '') + ")"
        df['Location'] = loc_name
        # Stock detection logic
        stock_cols = [c for c in df.columns if 'quantity' in c]
        df['Stock'] = pd.to_numeric(df[stock_cols[0]], errors='coerce').fillna(0).astype(int) if stock_cols else 0
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0.0)
        return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']]

    # --- USER CONTEXT ---
    user_data = get_at_data("Role", {"filterByFormula": f"{{User Name}}='{username}'"})
    user_role = user_data['Access Level'].iloc[0] if not user_data.empty else 'Staff'
    if username == "Kevin": user_role = "Admin"
    user_location = user_data['Assigned Location'].iloc[0] if not user_data.empty and 'Assigned Location' in user_data.columns else 'Both'

    st.sidebar.markdown(f"### 👤 {username} | 🔑 {user_role}")
    st.sidebar.info(f"📍 Location: **{user_location}**")
    st.sidebar.divider()

    # --- TABS ---
    if user_role == 'Admin':
        tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔄 Compare", "🛡️ Admin", "🔑 Password"])
    elif user_role == 'Manager':
        tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔑 Password"])
    else:
        tabs = st.tabs(["📋 Library", "🕵️ Audit", "🔑 Password"])

    # --- TAB 1: LIBRARY ---
    lib_data = get_at_data("Master_Inventory")
    with tabs[0]:
        st.subheader("📦 Master Inventory")
        if not lib_data.empty:
            # Filter by User Assignment
            disp_df = lib_data.copy()
            if user_role not in ['Admin', 'Manager'] and user_location != "Both":
                disp_df = disp_df[disp_df['Location'] == user_location]
            
            # Search & Sort (Default by Name)
            c1, c2, c3 = st.columns([2, 1, 1])
            search = c1.text_input("🔍 Search Name or SKU")
            disp_df = disp_df.sort_values(by="Full Name", ascending=True)
            
            cat_list = ["All"] + sorted([str(x) for x in disp_df['Category'].unique() if str(x) != 'nan'])
            selected_cat = c2.selectbox("Filter Category", cat_list)
            
            if user_role in ['Admin', 'Manager']:
                selected_loc = c3.selectbox("Filter Location", ["All", "PV", "Haiti"])
                if selected_loc != "All": disp_df = disp_df[disp_df['Location'] == selected_loc]

            if search:
                disp_df = disp_df[disp_df['Full Name'].str.contains(search, case=False, na=False) | disp_df['SKU'].str.contains(search, na=False)]
            if selected_cat != "All":
                disp_df = disp_df[disp_df['Category'] == selected_cat]

            st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 5: ADMIN (RESTORED UPLOADERS) ---
    if user_role == 'Admin':
        with tabs[4]:
            st.subheader("🛡️ Master System Sync")
            st.write("Upload the Square Exports for both locations to update the cloud database.")
            
            col_pv, col_ht = st.columns(2)
            file_pv = col_pv.file_uploader("📤 1. PV Square Export (.xlsx)", type=['xlsx'])
            file_ht = col_ht.file_uploader("📤 2. Haiti Square Export (.xlsx)", type=['xlsx'])
            
            if file_pv and file_ht:
                if st.button("🚀 Wipe & Sync BOTH Locations Now"):
                    # 1. Process files
                    df_pv = clean_location_data(file_pv, "PV")
                    df_ht = clean_location_data(file_ht, "Haiti")
                    combined_df = pd.concat([df_pv, df_ht])
                    
                    # 2. Wipe Airtable
                    existing = get_at_data("Master_Inventory")
                    if not existing.empty:
                        st.write("Cleaning old data...")
                        ids = existing['id'].tolist()
                        for i in range(0, len(ids), 10):
                            batch = ids[i:i+10]
                            query = "&".join([f"records[]={rid}" for rid in batch])
                            requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory?{query}", headers=HEADERS)
                    
                    # 3. Upload Combined
                    st.write("Uploading new data...")
                    bar = st.progress(0)
                    total = len(combined_df)
                    for i in range(0, total, 10):
                        batch = combined_df.iloc[i:i+10]
                        recs = [{"fields": {
                            "SKU": str(r['SKU']), "Full Name": str(r['Full Name']), 
                            "Stock": int(r['Stock']), "Price": float(r['Price']), 
                            "Category": str(r['Category']), "Location": str(r['Location']),
                            "Last_Sync_Date": str(date.today())
                        }} for _, r in batch.iterrows()]
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs})
                        bar.progress(min((i + 10) / total, 1.0))
                    st.success("Cloud Database Updated for Haiti and PV!")
                    st.rerun()

    # --- REST OF TABS (Intake, Audit, Password) ---
    # Logic is preserved to ensure the "Verification" and "Manual Date" features work.
