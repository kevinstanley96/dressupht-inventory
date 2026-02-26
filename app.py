import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.8", layout="wide")

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

    # --- DATA ENGINE (REINFORCED PAGINATION) ---
    def get_at_data(table):
        all_records = []
        offset = None
        url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
        
        while True:
            params = {"offset": offset} if offset else {}
            response = requests.get(url, headers=HEADERS, params=params)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('records', [])
                for r in records:
                    row = r['fields']
                    row['id'] = r['id']
                    all_records.append(row)
                
                offset = data.get('offset')
                if not offset:
                    break
            else:
                break
        
        df = pd.DataFrame(all_records)
        if df.empty:
            return pd.DataFrame(columns=['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price'])
        
        # Ensure mandatory columns
        for col in ['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']:
            if col not in df.columns: df[col] = "N/A"
        return df

    # --- CLEANING LOGIC ---
    def clean_location_data(file, loc_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip() for c in df.columns]
        mapping = {'Item Name': 'Wig Name', 'Variation Name': 'Style', 'SKU': 'SKU', 'Price': 'Price', 'Categories': 'Category'}
        df = df.rename(columns=mapping)

        stock_col = "Current Quantity Dressup Haiti" if loc_name == "Haiti" else "Current Quantity Dressupht Pv"
        df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int) if stock_col in df.columns else 0
        df['Category'] = df['Category'].fillna("Uncategorized")
        df['Location'] = loc_name
        df['SKU'] = df['SKU'].astype(str).str.strip().replace('nan', 'NO_SKU')
        
        w_name = df['Wig Name'].astype(str).replace('nan', 'Unknown')
        s_name = df['Style'].astype(str).replace('nan', '')
        df['Full Name'] = w_name + " (" + s_name + ")"
        df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
        
        return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']]

    # --- ROLES ---
    roles_df = get_at_data("Role")
    user_row = roles_df[roles_df['User Name'] == username] if not roles_df.empty else pd.DataFrame()
    user_role = "Admin" if username == "Kevin" else (user_row['Access Level'].iloc[0] if not user_row.empty else "Staff")
    user_location = user_row['Assigned Location'].iloc[0] if not user_row.empty and 'Assigned Location' in user_row.columns else "Both"

    st.sidebar.info(f"👤 {username} | 📍 {user_location}")

    tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔄 Compare", "🛡️ Admin", "🔑 Password"])

    # --- TAB 1: LIBRARY ---
    with tabs[0]:
        lib_data = get_at_data("Master_Inventory")
        st.subheader(f"📦 Master Inventory ({len(lib_data)} items found)")
        
        if not lib_data.empty:
            disp_df = lib_data.copy().sort_values(by="Full Name", ascending=True)
            
            if user_role not in ['Admin', 'Manager'] and user_location != "Both":
                disp_df = disp_df[disp_df['Location'] == user_location]
            
            c1, c2, c3 = st.columns([2, 1, 1])
            search = c1.text_input("🔍 Search")
            sort_choice = c2.selectbox("Sort By", ["Name", "Category", "Date Entered"])
            
            if sort_choice == "Category": disp_df = disp_df.sort_values(by="Category")
            if search:
                disp_df = disp_df[disp_df['Full Name'].str.contains(search, case=False, na=False) | disp_df['SKU'].str.contains(search, na=False)]
            
            st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 5: ADMIN (SYNC) ---
    if user_role == 'Admin':
        with tabs[4]:
            st.subheader("🛡️ Master Sync")
            f_pv = st.file_uploader("Upload PV", type=['xlsx'])
            f_ht = st.file_uploader("Upload Haiti", type=['xlsx'])
            
            if f_pv and f_ht:
                if st.button("🚀 Wipe & Full Sync (755 Items)"):
                    df_pv = clean_location_data(f_pv, "Pv")
                    df_ht = clean_location_data(f_ht, "Haiti")
                    full_df = pd.concat([df_pv, df_ht]).reset_index(drop=True)
                    
                    # Wipe
                    old_data = get_at_data("Master_Inventory")
                    if not old_data.empty:
                        st.write("🗑️ Deleting old records...")
                        ids = old_data['id'].tolist()
                        for i in range(0, len(ids), 10):
                            batch = ids[i:i+10]
                            q = "&".join([f"records[]={rid}" for rid in batch])
                            requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory?{q}", headers=HEADERS)
                    
                    # Upload
                    st.write(f"🚀 Uploading {len(full_df)} records...")
                    prog = st.progress(0)
                    for i in range(0, len(full_df), 10):
                        chunk = full_df.iloc[i:i+10]
                        recs = [{"fields": {
                            "SKU": str(r['SKU']), "Full Name": str(r['Full Name']),
                            "Stock": int(r['Stock']), "Price": float(r['Price']),
                            "Category": str(r['Category']), "Location": str(r['Location'])
                        }} for _, r in chunk.iterrows()]
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs})
                        prog.progress(min((i + 10) / len(full_df), 1.0))
                        time.sleep(0.2)
                    st.success("Sync Complete!")
                    st.rerun()

elif authentication_status is False: st.error("Wrong Login")
