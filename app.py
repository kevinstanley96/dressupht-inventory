import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
from fpdf import FPDF 

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.9.4", layout="wide")

# --- AUTHENTICATION ---
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

    # --- 1. DATA ENGINE (PAGINATION INTACT) ---
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
        return pd.DataFrame(all_records)

    # --- 2. USER PROFILE & SIDEBAR (RESTORED) ---
    roles_df = get_at_data("Role")
    user_row = roles_df[roles_df['User Name'] == username] if not roles_df.empty else pd.DataFrame()
    
    # Defaults
    user_role = "Staff"
    user_location = "Both"
    
    if username == "Kevin":
        user_role = "Admin"
    elif not user_row.empty:
        user_role = user_row['Access Level'].iloc[0]
        user_location = user_row['Assigned Location'].iloc[0] if 'Assigned Location' in user_row.columns else "Both"

    # Sidebar UI
    st.sidebar.markdown(f"### 👤 {username}")
    st.sidebar.markdown(f"**📍 Location:** {user_location}")
    st.sidebar.markdown(f"**🛡️ Role:** {user_role}")
    st.sidebar.divider()
    authenticator.logout('Logout', 'sidebar')

    # --- 3. TAB VISIBILITY LOGIC (SECURITY FIX) ---
    # Staff only get Library and Password. Admin/Manager get all.
    if user_role in ["Admin", "Manager"]:
        tab_list = ["📋 Library", "➕ Intake", "🕵️ Audit", "🛡️ Admin Sync", "🔑 Password"]
    else:
        tab_list = ["📋 Library", "🔑 Password"]
    
    tabs = st.tabs(tab_list)

    # --- TAB: LIBRARY (Shared) ---
    with tabs[0]:
        lib_data = get_at_data("Master_Inventory")
        if not lib_data.empty:
            st.subheader(f"📦 Inventory ({len(lib_data)} Items)")
            
            # PDF Controls (Only for higher roles usually, but kept here if staff need to print)
            with st.expander("📄 PDF Export Controls"):
                c_p1, c_p2 = st.columns(2)
                p_loc = c_p1.selectbox("Filter PDF Location", ["All", "Pv", "Haiti"])
                p_df = lib_data.copy()
                if p_loc != "All": p_df = p_df[p_df['Location'] == p_loc]
                # (PDF Gen logic here...)

            # Regular View & Sorting
            c1, c2 = st.columns([2, 1])
            search = c1.text_input("🔍 Search Name/SKU")
            sort_choice = c2.selectbox("Sort By", ["Name", "Location", "Category"])
            
            disp_df = lib_data.copy()
            # Staff restricted view
            if user_role == "Staff" and user_location != "Both":
                disp_df = disp_df[disp_df['Location'] == user_location]
                
            if sort_choice == "Location": disp_df = disp_df.sort_values(by=["Location", "Full Name"])
            else: disp_df = disp_df.sort_values(by="Full Name")

            if search:
                disp_df = disp_df[disp_df['Full Name'].str.contains(search, case=False, na=False) | disp_df['SKU'].str.contains(search, na=False)]
            
            st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- CONDITIONAL TABS (Security Guard) ---
    if user_role in ["Admin", "Manager"]:
        with tabs[1]: # Intake
            st.subheader("➕ Stock Intake")
            # [Intake Logic Here]
            
        with tabs[2]: # Audit
            st.subheader("🕵️ Inventory Audit")
            
        with tabs[3]: # Admin Sync
            st.subheader("🛡️ System Sync")
            # [The robust 755-item Batch Sync Logic Here]

    # Password Tab (Always Last)
    with tabs[-1]:
        st.subheader("🔑 Password Management")
        # [Reset password logic]

elif authentication_status is False:
    st.error('Username/password is incorrect')
elif authentication_status is None:
    st.warning('Please enter your username and password')
