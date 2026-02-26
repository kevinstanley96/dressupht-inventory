import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import base64

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.6", layout="wide")
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

    # --- UPDATED CLEANING LOGIC (With NaN Sanitization) ---
    def clean_location_data(file, loc_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip() for c in df.columns]
        
        mapping = {
            'Item Name': 'Wig Name', 
            'Variation Name': 'Style', 
            'SKU': 'SKU', 
            'Price': 'Price', 
            'Categories': 'Category',
            'Category': 'Category'
        }
        df = df.rename(columns=mapping)

        # 1. Handle Stock Mapping
        stock_col = "Current Quantity Dressup Haiti" if loc_name == "Haiti" else "Current Quantity Dressupht Pv"
        if stock_col in df.columns:
            df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int)
        else:
            df['Stock'] = 0 
            
        # 2. Category Fallback
        if 'Category' not in df.columns:
            df['Category'] = 'Uncategorized'
        
        df['Location'] = loc_name
        
        # 3. SKU Sanitization
        df['SKU'] = df['SKU'].astype(str).str.strip().replace('nan', 'NO_SKU')
        
        # 4. Full Name Construction
        w_name = df['Wig Name'].astype(str).replace('nan', 'Unknown')
        s_name = df['Style'].astype(str).replace('nan', '')
        df['Full Name'] = w_name + " (" + s_name + ")"
        
        # 5. Price Sanitization (The fix for your Float error)
        df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
        
        # 6. Global Clean: Replace any remaining NaNs across the whole dataframe
        final_df = df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']].copy()
        final_df = final_df.fillna({
            'SKU': 'NO_SKU',
            'Full Name': 'Unknown',
            'Stock': 0,
            'Price': 0.0,
            'Category': 'Uncategorized'
        })
        
        return final_df

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
            # Sort logic: Apply user preference from saved info (Sort by Name default)
            disp_df = lib_data.copy().sort_values(by="Full Name")
            if user_role not in ['Admin', 'Manager'] and user_location != "Both":
                disp_df = disp_df[disp_df['Location'] == user_location]
            
            search = st.text_input("🔍 Search Library (Name or SKU)")
            if search:
                disp_df = disp_df[disp_df['Full Name'].str.contains(search, case=False, na=False) | disp_df['SKU'].str.contains(search, na=False)]
            
            st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 5: ADMIN (SYNC) ---
    if user_role == 'Admin':
        with tabs[4]:
            st.subheader("🛡️ Master System Sync")
            col1, col2 = st.columns(2)
            f_pv = col1.file_uploader("Upload PV File", type=['xlsx'])
            f_ht = col2.file_uploader("Upload Haiti File", type=['xlsx'])
            
            if f_pv and f_ht:
                try:
                    df_pv_clean = clean_location_data(f_pv, "Pv")
                    df_ht_clean = clean_location_data(f_ht, "Haiti")
                    full_df = pd.concat([df_pv_clean, df_ht_clean])
                    
                    st.info(f"Ready to Sync {len(full_df)} total items.")
                    
                    if st.button("🚀 Wipe & Sync Now"):
                        # Wipe Existing
                        if not lib_data.empty:
                            st.warning("Clearing current database...")
                            ids = lib_data['id'].tolist()
                            for i in range(0, len(ids), 10):
                                batch = ids[i:i+10]
                                q = "&".join([f"records[]={rid}" for rid in batch])
                                requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory?{q}", headers=HEADERS)
                        
                        # Upload New
                        st.info("Uploading cleaned data...")
                        bar = st.progress(0)
                        for i in range(0, len(full_df), 10):
                            batch = full_df.iloc[i:i+10]
                            # 🔥 The JSON Sanitizer: Ensure records are native Python types, not Numpy/NaN
                            recs = []
                            for _, r in batch.iterrows():
                                recs.append({"fields": {
                                    "SKU": str(r['SKU']),
                                    "Full Name": str(r['Full Name']),
                                    "Stock": int(r['Stock']),
                                    "Price": float(r['Price']),
                                    "Category": str(r['Category']),
                                    "Location": str(r['Location']),
                                    "Last_Sync_Date": str(date.today())
                                }})
                            requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs})
                            bar.progress(min((i + 10) / len(full_df), 1.0))
                        
                        st.success("Sync Complete! NaN values were handled.")
                        st.rerun()
                except Exception as e:
                    st.error(f"Sync failed: {e}")
