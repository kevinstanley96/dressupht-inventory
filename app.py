import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import base64

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.3", layout="wide")
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
        st.error("Missing Secrets in Streamlit Cloud!")
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
        # Ensure mandatory columns exist in the DataFrame to prevent KeyError
        for col in ['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']:
            if col not in df.columns: df[col] = "N/A"
        return df

    # --- SPECIFIC LOCATION CLEANING LOGIC ---
    def clean_location_data(file, loc_name):
        df = pd.read_excel(file, skiprows=1)
        # Normalize column names for mapping but keep search strict
        df.columns = [str(c).strip() for c in df.columns]
        
        # 1. Map Core Columns
        mapping = {
            'Item Name': 'Wig Name', 
            'Variation Name': 'Style', 
            'SKU': 'SKU', 
            'Price': 'Price', 
            'Category': 'Category'
        }
        df = df.rename(columns=mapping)

        # 2. Specific Stock Column Mapping (As per user's Square Report)
        if loc_name == "Haiti":
            stock_col = "Current Quantity Dressup Haiti"
        else: # PV
            stock_col = "Current Quantity Dressupht Pv"
        
        if stock_col in df.columns:
            df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int)
        else:
            # Error handling if the column name changes again
            st.error(f"Could not find column '{stock_col}' in the {loc_name} file.")
            df['Stock'] = 0
            
        df['Location'] = loc_name
        df['SKU'] = df['SKU'].astype(str).str.strip().replace('nan', 'NO_SKU')
        df['Full Name'] = df['Wig Name'].astype(str) + " (" + df['Style'].astype(str).replace('nan', '') + ")"
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0.0)
        
        return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']]

    # --- USER CONTEXT ---
    user_data = get_at_data("Role", {"filterByFormula": f"{{User Name}}='{username}'"})
    user_role = user_data['Access Level'].iloc[0] if not user_data.empty else 'Staff'
    if username == "Kevin": user_role = "Admin"
    
    # Match Role table single-select options (Both, Pv, Haiti)
    user_location = user_data['Assigned Location'].iloc[0] if not user_data.empty and 'Assigned Location' in user_data.columns else 'Both'

    st.sidebar.markdown(f"### 👤 {username}")
    st.sidebar.markdown(f"### 🔑 {user_role} | 📍 {user_location}")
    st.sidebar.divider()

    # --- TABS ---
    if user_role == 'Admin':
        tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔄 Compare", "🛡️ Admin", "🔑 Password"])
    elif user_role == 'Manager':
        tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔑 Password"])
    else:
        tabs = st.tabs(["📋 Library", "🕵️ Audit", "🔑 Password"])

    # --- TAB 1: LIBRARY (LOCATION FILTERING) ---
    lib_data = get_at_data("Master_Inventory")
    with tabs[0]:
        st.subheader("📦 Master Inventory")
        if not lib_data.empty:
            disp_df = lib_data.copy()
            
            # Filter based on Assigned Location
            if user_role not in ['Admin', 'Manager'] and user_location != "Both":
                disp_df = disp_df[disp_df['Location'] == user_location]
            
            c1, c2, c3 = st.columns([2, 1, 1])
            search = c1.text_input("🔍 Search Name or SKU")
            
            # Default sort by Name
            disp_df = disp_df.sort_values(by="Full Name", ascending=True)
            
            cat_list = ["All"] + sorted([str(x) for x in disp_df['Category'].unique() if str(x) != 'nan'])
            selected_cat = c2.selectbox("Filter Category", cat_list)
            
            if user_role in ['Admin', 'Manager']:
                selected_loc = c3.selectbox("Filter View by Location", ["All", "Pv", "Haiti"])
                if selected_loc != "All": disp_df = disp_df[disp_df['Location'] == selected_loc]

            if search:
                disp_df = disp_df[disp_df['Full Name'].str.contains(search, case=False, na=False) | disp_df['SKU'].str.contains(search, na=False)]
            if selected_cat != "All":
                disp_df = disp_df[disp_df['Category'] == selected_cat]

            st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 5: ADMIN (DUAL SYNC LOGIC) ---
    if user_role == 'Admin':
        with tabs[4]:
            st.subheader("🛡️ Master System Sync")
            col_pv, col_ht = st.columns(2)
            f_pv = col_pv.file_uploader("Upload Pétion-Ville Export", type=['xlsx'])
            f_ht = col_ht.file_uploader("Upload Haiti (Canapé-Vert) Export", type=['xlsx'])
            
            if f_pv and f_ht:
                df_pv_clean = clean_location_data(f_pv, "Pv")
                df_ht_clean = clean_location_data(f_ht, "Haiti")
                
                st.write("### 🔍 Pre-Sync Preview")
                st.write(f"PV Items: {len(df_pv_clean)} | Haiti Items: {len(df_ht_clean)}")
                
                if st.button("🚀 Wipe & Sync BOTH Locations"):
                    full_df = pd.concat([df_pv_clean, df_ht_clean])
                    
                    # Wipe Airtable
                    if not lib_data.empty:
                        st.info("Deleting old records...")
                        ids = lib_data['id'].tolist()
                        for i in range(0, len(ids), 10):
                            batch = ids[i:i+10]
                            query = "&".join([f"records[]={rid}" for rid in batch])
                            requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory?{query}", headers=HEADERS)
                    
                    # Batch Upload
                    st.info("Uploading combined inventory...")
                    bar = st.progress(0)
                    for i in range(0, len(full_df), 10):
                        batch = full_df.iloc[i:i+10]
                        recs = [{"fields": {
                            "SKU": str(r['SKU']), "Full Name": str(r['Full Name']), 
                            "Stock": int(r['Stock']), "Price": float(r['Price']), 
                            "Category": str(r['Category']), "Location": str(r['Location']),
                            "Last_Sync_Date": str(date.today())
                        }} for _, r in batch.iterrows()]
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs})
                        bar.progress(min((i + 10) / len(full_df), 1.0))
                    st.success("Master Inventory Sync Successful!")
                    st.rerun()

    # --- OTHER TABS (Intake, Audit, Password) ---
    # [Verification logic remains the same as v4.2]
