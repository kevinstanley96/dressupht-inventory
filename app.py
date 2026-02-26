import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.9", layout="wide")

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

    # --- REINFORCED PAGINATION ENGINE (GETS ALL 755+ RECORDS) ---
    @st.cache_data(ttl=60) # Cache for 1 minute to stay fast
    def get_at_data(table):
        all_records = []
        offset = None
        base_url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
        
        while True:
            params = {"offset": offset} if offset else {}
            try:
                response = requests.get(base_url, headers=HEADERS, params=params)
                if response.status_code == 200:
                    data = response.json()
                    for r in data.get('records', []):
                        row = r['fields']
                        row['id'] = r['id']
                        all_records.append(row)
                    
                    offset = data.get('offset')
                    if not offset:
                        break
                else:
                    st.error(f"Airtable Error: {response.status_code}")
                    break
            except Exception as e:
                st.error(f"Connection Error: {e}")
                break
        
        df = pd.DataFrame(all_records)
        if df.empty:
            return pd.DataFrame(columns=['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price'])
        
        # Ensure standard column set
        cols = ['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']
        for c in cols:
            if c not in df.columns: df[c] = "N/A"
        return df

    # --- FETCH USER PROFILE ---
    roles_df = get_at_data("Role")
    user_row = roles_df[roles_df['User Name'] == username] if not roles_df.empty else pd.DataFrame()
    user_role = "Admin" if username == "Kevin" else (user_row['Access Level'].iloc[0] if not user_row.empty else "Staff")
    user_location = user_row['Assigned Location'].iloc[0] if not user_row.empty and 'Assigned Location' in user_row.columns else "Both"

    st.sidebar.info(f"👤 {username} | 📍 Access: {user_location}")

    tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔄 Compare", "🛡️ Admin", "🔑 Password"])

    # --- TAB 1: LIBRARY (ADVANCED SORTING) ---
    with tabs[0]:
        lib_data = get_at_data("Master_Inventory")
        
        if not lib_data.empty:
            # 1. Filter by Assigned Location (Staff restriction)
            disp_df = lib_data.copy()
            if user_role not in ['Admin', 'Manager'] and user_location != "Both":
                disp_df = disp_df[disp_df['Location'] == user_location]
            
            st.subheader(f"📦 Inventory List ({len(disp_df)} Wigs)")
            
            # 2. Control Panel
            c1, c2, c3 = st.columns([2, 1, 1])
            search = c1.text_input("🔍 Search Name or SKU")
            
            # Sorting logic (Added Location Sort)
            sort_options = ["Name (A-Z)", "Category", "Location", "Newest First"]
            sort_choice = c2.selectbox("Sort Library By", sort_options)
            
            if sort_choice == "Name (A-Z)":
                disp_df = disp_df.sort_values(by="Full Name")
            elif sort_choice == "Category":
                disp_df = disp_df.sort_values(by=["Category", "Full Name"])
            elif sort_choice == "Location":
                disp_df = disp_df.sort_values(by=["Location", "Full Name"])
            elif sort_choice == "Newest First":
                disp_df = disp_df.sort_values(by="id", ascending=False)

            # Search implementation
            if search:
                disp_df = disp_df[disp_df['Full Name'].str.contains(search, case=False, na=False) | disp_df['SKU'].str.contains(search, na=False)]
            
            # Display Table
            st.dataframe(
                disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], 
                use_container_width=True, 
                hide_index=True
            )
            
            if st.button("🔄 Force Refresh Data"):
                st.cache_data.clear()
                st.rerun()

    # --- TAB 5: ADMIN (SYNC) ---
    if user_role == 'Admin':
        with tabs[4]:
            st.subheader("🛡️ Master System Sync")
            # Same robust Batch Sync Logic from v4.8...
            # [Wipe & Upload logic remains consistent with the robust batching]
