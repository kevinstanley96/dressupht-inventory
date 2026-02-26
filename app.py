import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import base64

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.0", layout="wide")
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
        return df

    # --- USER CONTEXT (LOCATION AWARENESS) ---
    user_data = get_at_data("Role", {"filterByFormula": f"{{User Name}}='{username}'"})
    user_role = user_data['Access Level'].iloc[0] if not user_data.empty else 'Staff'
    if username == "Kevin": user_role = "Admin"
    
    # Get assigned location (PV, Haiti, or Both)
    user_location = user_data['Assigned Location'].iloc[0] if not user_data.empty and 'Assigned Location' in user_data.columns else 'PV'

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

    # --- TAB 1: LIBRARY (LOCATION FILTERED + ADMIN PRICE EDIT) ---
    with tabs[0]:
        st.subheader("📦 Master Inventory")
        
        # Manual Refresh Button
        if st.button("🔄 Refresh Library"):
            st.cache_data.clear()
            st.rerun()

        lib_data = get_at_data("Master_Inventory")
        
        if not lib_data.empty:
            # 1. Location Filtering Logic
            if user_role not in ['Admin', 'Manager'] and user_location != "Both":
                lib_data = lib_data[lib_data['Location'] == user_location]
            
            # 2. Search and Sort (Sorted by Name by default)
            c1, c2, c3 = st.columns([2, 1, 1])
            search = c1.text_input("🔍 Search Name or SKU")
            
            # Default sorting by Name
            lib_data = lib_data.sort_values(by="Full Name", ascending=True)
            
            cat_list = ["All"] + sorted([str(x) for x in lib_data['Category'].unique().tolist() if str(x) != 'nan'])
            selected_cat = c2.selectbox("Filter Category", cat_list)
            
            # Location toggle for Admins/Managers
            if user_role in ['Admin', 'Manager'] or user_location == "Both":
                loc_list = ["All", "PV", "Haiti"]
                selected_loc = c3.selectbox("Filter Location", loc_list)
                if selected_loc != "All":
                    lib_data = lib_data[lib_data['Location'] == selected_loc]

            if search:
                lib_data = lib_data[lib_data['Full Name'].str.contains(search, case=False, na=False) | lib_data['SKU'].str.contains(search, na=False)]
            if selected_cat != "All":
                lib_data = lib_data[lib_data['Category'] == selected_cat]

            st.dataframe(lib_data[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

            # 3. ADMIN PRICE OVERRIDE TOOL
            if user_role == 'Admin':
                st.divider()
                st.subheader("💰 Admin: Quick Price Update")
                with st.expander("Click to Edit Prices"):
                    edit_sku = st.text_input("Enter SKU to Update Price")
                    new_price = st.number_input("New Price ($)", min_value=0.0)
                    if st.button("Update Price for All Staff"):
                        match = lib_data[lib_data['SKU'] == edit_sku]
                        if not match.empty:
                            record_id = match['id'].iloc[0]
                            patch_url = f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory/{record_id}"
                            res = requests.patch(patch_url, headers=HEADERS, json={"fields": {"Price": new_price}})
                            if res.status_code == 200:
                                st.success(f"Price for {edit_sku} updated to ${new_price}. Staff must click 'Refresh' to see.")
                            else: st.error("Failed to update Airtable.")
                        else: st.error("SKU not found.")

    # --- TAB 2: INTAKE (VERIFICATION) ---
    if user_role in ['Admin', 'Manager']:
        with tabs[1]:
            st.subheader("➕ New Stock Shipment")
            i_sku = st.text_input("1. Verify SKU").strip()
            if i_sku:
                match = lib_data[lib_data['SKU'] == i_sku]
                if not match.empty:
                    st.success(f"✅ Verified: {match['Full Name'].iloc[0]} (Stock: {match['Stock'].iloc[0]})")
                    with st.form("intake_v4"):
                        i_date = st.date_input("Date Received", date.today())
                        # Multi-location intake
                        i_loc = st.selectbox("Destination Location", ["PV", "Haiti"])
                        i_qty = st.number_input("Quantity Received", min_value=1)
                        if st.form_submit_button("Log Shipment"):
                            ship_payload = {"records": [{"fields": {
                                "Date": str(i_date), "SKU": i_sku, "Name": match['Full Name'].iloc[0], 
                                "Quantity": i_qty, "User": username, "Location": i_loc
                            }}]}
                            requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=ship_payload)
                            st.success("Shipment Logged!")
                else: st.error("SKU not found.")

    # --- TAB 5: ADMIN (DUAL SYNC LOGIC) ---
    if user_role == 'Admin':
        with tabs[4]:
            st.subheader("🛡️ Multi-Location Sync")
            col1, col2 = st.columns(2)
            f_pv = col1.file_uploader("Upload PV Square Export", type=['xlsx'])
            f_ht = col2.file_uploader("Upload Haiti Square Export", type=['xlsx'])
            
            if st.button("🚀 Wipe & Full Sync Both Locations"):
                # (Logic would loop through both files, tagging location='PV' and location='Haiti')
                st.info("Syncing process initiated for both locations...")
                # Detailed sync logic would go here...

    # --- PASSWORD ---
    with tabs[-1]:
        st.subheader("🔑 Change Password")
        if authenticator.reset_password(username=username, fields={'form_name': 'Update'}):
            st.success('Password updated!')

elif st.session_state["authentication_status"] is False:
    st.error('Incorrect Password')
elif st.session_state["authentication_status"] is None:
    st.warning('Please login.')
