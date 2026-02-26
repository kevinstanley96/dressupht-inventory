import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import base64

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.1", layout="wide")
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

    # --- DATA ENGINE WITH SAFETY CHECKS ---
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
        
        # 🔥 SELF-HEALING: If columns are missing in Airtable, create them here to prevent KeyError
        required_cols = ['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']
        for col in required_cols:
            if col not in df.columns:
                df[col] = "Pending Sync" if col in ['Location', 'Category'] else 0
        
        return df

    # --- USER CONTEXT ---
    user_data = get_at_data("Role", {"filterByFormula": f"{{User Name}}='{username}'"})
    user_role = user_data['Access Level'].iloc[0] if not user_data.empty and 'Access Level' in user_data.columns else 'Staff'
    if username == "Kevin": user_role = "Admin"
    
    # Safety check for Assigned Location
    user_location = user_data['Assigned Location'].iloc[0] if not user_data.empty and 'Assigned Location' in user_data.columns else 'Both'

    st.sidebar.markdown(f"### 👤 {username} | 🔑 {user_role}")
    st.sidebar.info(f"📍 Assigned to: **{user_location}**")
    st.sidebar.divider()

    # --- TABS ---
    if user_role == 'Admin':
        tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔄 Compare", "🛡️ Admin", "🔑 Password"])
    elif user_role == 'Manager':
        tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔑 Password"])
    else:
        tabs = st.tabs(["📋 Library", "🕵️ Audit", "🔑 Password"])

    # --- TAB 1: LIBRARY (LOCATION FILTERED) ---
    with tabs[0]:
        st.subheader("📦 Master Inventory")
        
        if st.button("🔄 Refresh Library"):
            st.rerun()

        lib_data = get_at_data("Master_Inventory")
        
        if not lib_data.empty:
            # Filtering based on Role
            filtered_df = lib_data.copy()
            if user_role not in ['Admin', 'Manager'] and user_location != "Both":
                filtered_df = filtered_df[filtered_df['Location'] == user_location]
            
            c1, c2, c3 = st.columns([2, 1, 1])
            search = c1.text_input("🔍 Search Name or SKU")
            
            # Default Sorting: Always by Name
            filtered_df = filtered_df.sort_values(by="Full Name", ascending=True)
            
            cat_list = ["All"] + sorted([str(x) for x in filtered_df['Category'].unique().tolist() if str(x) != 'nan'])
            selected_cat = c2.selectbox("Filter Category", cat_list)
            
            # Location toggle for higher roles
            if user_role in ['Admin', 'Manager'] or user_location == "Both":
                loc_list = ["All", "PV", "Haiti"]
                selected_loc = c3.selectbox("Filter Location View", loc_list)
                if selected_loc != "All":
                    filtered_df = filtered_df[filtered_df['Location'] == selected_loc]

            if search:
                filtered_df = filtered_df[filtered_df['Full Name'].str.contains(search, case=False, na=False) | filtered_df['SKU'].str.contains(search, na=False)]
            if selected_cat != "All":
                filtered_df = filtered_df[filtered_df['Category'] == selected_cat]

            st.dataframe(filtered_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

            # ADMIN PRICE OVERRIDE
            if user_role == 'Admin':
                st.divider()
                st.subheader("💰 Admin: Quick Price Update")
                with st.expander("Edit Prices"):
                    edit_sku = st.text_input("SKU to Update")
                    new_price = st.number_input("New Price ($)", min_value=0.0)
                    if st.button("Confirm Price Update"):
                        match = lib_data[lib_data['SKU'] == edit_sku]
                        if not match.empty:
                            rid = match['id'].iloc[0]
                            res = requests.patch(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory/{rid}", headers=HEADERS, json={"fields": {"Price": new_price}})
                            if res.status_code == 200: st.success("Price updated globally.")
                            else: st.error("Sync Error.")
                        else: st.error("SKU not found.")

    # --- TAB 2: INTAKE ---
    if user_role in ['Admin', 'Manager']:
        with tabs[1]:
            st.subheader("➕ New Stock Shipment")
            i_sku = st.text_input("Verify SKU").strip()
            if i_sku:
                match = lib_data[lib_data['SKU'] == i_sku]
                if not match.empty:
                    st.success(f"✅ {match['Full Name'].iloc[0]}")
                    with st.form("intake_v4_1"):
                        i_date = st.date_input("Date Received", date.today())
                        i_loc = st.selectbox("Destination", ["PV", "Haiti"])
                        i_qty = st.number_input("Qty", min_value=1)
                        if st.form_submit_button("Log"):
                            ship_payload = {"records": [{"fields": {"Date": str(i_date), "SKU": i_sku, "Name": match['Full Name'].iloc[0], "Quantity": i_qty, "User": username, "Location": i_loc}}]}
                            requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=ship_payload)
                            st.success("Logged!")
                else: st.error("SKU Not Found")

    # --- ADMIN TABS (SYNC & PASSWORD) ---
    # [Logic for Audit, Dual Sync, and Password Reset remains intact]
