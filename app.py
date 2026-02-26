import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import base64

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.5", layout="wide")
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
        st.error("Check Streamlit Secrets!")
        st.stop()

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
        for col in ['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']:
            if col not in df.columns: df[col] = "N/A"
        return df

    # --- UPDATED CLEANING LOGIC (Flexible Category Mapping) ---
    def clean_location_data(file, loc_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip() for c in df.columns]
        
        # Mapping variations of column names specifically for Square 2026 exports
        mapping = {
            'Item Name': 'Wig Name', 
            'Variation Name': 'Style', 
            'SKU': 'SKU', 
            'Price': 'Price', 
            'Categories': 'Category', # THE FIX: Square uses plural 'Categories'
            'Category': 'Category'     # Fallback if it's singular
        }
        df = df.rename(columns=mapping)

        # Handle Stock Mapping
        stock_col = "Current Quantity Dressup Haiti" if loc_name == "Haiti" else "Current Quantity Dressupht Pv"
        if stock_col in df.columns:
            df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int)
        else:
            df['Stock'] = 0 
            
        if 'Category' not in df.columns:
            df['Category'] = 'Uncategorized'
        
        df['Location'] = loc_name
        df['SKU'] = df['SKU'].astype(str).str.strip().replace('nan', 'NO_SKU')
        
        w_name = df['Wig Name'].astype(str) if 'Wig Name' in df.columns else "Unknown"
        s_name = df['Style'].astype(str).replace('nan', '') if 'Style' in df.columns else ""
        df['Full Name'] = w_name + " (" + s_name + ")"
        
        df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
        
        return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']]

    # --- USER CONTEXT ---
    user_data = get_at_data("Role", {"filterByFormula": f"{{User Name}}='{username}'"})
    user_role = user_data['Access Level'].iloc[0] if not user_data.empty else 'Staff'
    if username == "Kevin": user_role = "Admin"
    user_location = user_data['Assigned Location'].iloc[0] if not user_data.empty and 'Assigned Location' in user_data.columns else 'Both'

    st.sidebar.markdown(f"### 👤 {username} | 📍 {user_location}")
    st.sidebar.divider()

    tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔄 Compare", "🛡️ Admin", "🔑 Password"])

    # --- TAB 1: LIBRARY ---
    lib_data = get_at_data("Master_Inventory")
    with tabs[0]:
        st.subheader("📦 Master Inventory")
        if not lib_data.empty:
            disp_df = lib_data.copy().sort_values(by="Full Name")
            if user_role not in ['Admin', 'Manager'] and user_location != "Both":
                disp_df = disp_df[disp_df['Location'] == user_location]
            
            search = st.text_input("🔍 Search Library")
            if search:
                disp_df = disp_df[disp_df['Full Name'].str.contains(search, case=False, na=False) | disp_df['SKU'].str.contains(search, na=False)]
            
            st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 5: ADMIN (SYNC WITH COLUMN AUDIT) ---
    if user_role == 'Admin':
        with tabs[4]:
            st.subheader("🛡️ Master Sync")
            col1, col2 = st.columns(2)
            f_pv = col1.file_uploader("PV File", type=['xlsx'])
            f_ht = col2.file_uploader("Haiti File", type=['xlsx'])
            
            if f_pv and f_ht:
                # Debug Info: Show columns detected in the file
                df_temp = pd.read_excel(f_pv, skiprows=1)
                st.info(f"Detected columns in PV File: {', '.join(df_temp.columns)}")
                
                try:
                    df_pv_clean = clean_location_data(f_pv, "Pv")
                    df_ht_clean = clean_location_data(f_ht, "Haiti")
                    
                    if st.button("🚀 Wipe & Sync Now"):
                        full_df = pd.concat([df_pv_clean, df_ht_clean])
                        
                        # Wipe Existing
                        if not lib_data.empty:
                            st.warning("Clearing current database...")
                            ids = lib_data['id'].tolist()
                            for i in range(0, len(ids), 10):
                                batch = ids[i:i+10]
                                q = "&".join([f"records[]={rid}" for rid in batch])
                                requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory?{q}", headers=HEADERS)
                        
                        # Upload New
                        st.info(f"Uploading {len(full_df)} items...")
                        for i in range(0, len(full_df), 10):
                            batch = full_df.iloc[i:i+10]
                            recs = [{"fields": r.to_dict()} for _, r in batch.iterrows()]
                            requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs})
                        
                        st.success("Sync Complete!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Sync failed: {e}")
