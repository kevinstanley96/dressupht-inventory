import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
from fpdf import FPDF 

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.9.6", layout="wide")

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

    # --- 1. DATA ENGINE (PAGINATION) ---
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

    # --- 2. USER PROFILE & SIDEBAR ---
    roles_df = get_at_data("Role")
    user_row = roles_df[roles_df['User Name'] == username] if not roles_df.empty else pd.DataFrame()
    user_role = "Admin" if username == "Kevin" else (user_row['Access Level'].iloc[0] if not user_row.empty else "Staff")
    user_location = user_row['Assigned Location'].iloc[0] if not user_row.empty and 'Assigned Location' in user_row.columns else "Both"

    st.sidebar.markdown(f"### 👤 {username}")
    st.sidebar.markdown(f"**📍 Location:** {user_location}")
    st.sidebar.markdown(f"**🛡️ Role:** {user_role}")
    st.sidebar.divider()
    authenticator.logout('Logout', 'sidebar')

    # --- 3. CLEANING LOGIC ---
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
        w_name, s_name = df['Wig Name'].astype(str).replace('nan', 'Unknown'), df['Style'].astype(str).replace('nan', '')
        df['Full Name'] = w_name + " (" + s_name + ")"
        df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
        return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']].copy()

    # --- 4. TABS ---
    tab_list = ["📋 Library", "➕ Intake", "🛡️ Admin Sync", "🔑 Password"] if user_role in ["Admin", "Manager"] else ["📋 Library", "🔑 Password"]
    tabs = st.tabs(tab_list)

    # --- TAB 1: LIBRARY ---
    with tabs[0]:
        lib_data = get_at_data("Master_Inventory")
        st.subheader(f"📦 Inventory ({len(lib_data)} Items)")
        c1, c2 = st.columns([2, 1])
        search = c1.text_input("🔍 Search Name/SKU")
        sort_choice = c2.selectbox("Sort By", ["Name", "Location", "Category"])
        disp_df = lib_data.copy()
        if user_role == "Staff" and user_location != "Both":
            disp_df = disp_df[disp_df['Location'] == user_location]
        if sort_choice == "Location": disp_df = disp_df.sort_values(by=["Location", "Full Name"])
        elif sort_choice == "Category": disp_df = disp_df.sort_values(by=["Category", "Full Name"])
        else: disp_df = disp_df.sort_values(by="Full Name")
        if search:
            disp_df = disp_df[disp_df['Full Name'].str.contains(search, case=False, na=False) | disp_df['SKU'].str.contains(search, na=False)]
        st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 2: INTAKE (DYNAMIC VERIFICATION) ---
    if user_role in ["Admin", "Manager"]:
        with tabs[1]:
            st.subheader("➕ Stock Intake (PV Tracking)")
            col_left, col_right = st.columns([1, 1])
            master_data = get_at_data("Master_Inventory")

            with col_left:
                st.markdown("### 📥 1. Verify Item")
                # We use a standalone input for SKU to trigger verification before the form
                input_sku = st.text_input("Scan or Enter SKU", key="sku_input").strip()
                
                v_name, v_cat = None, None
                if input_sku:
                    match = master_data[(master_data['SKU'] == input_sku) & (master_data['Location'] == "Pv")]
                    if not match.empty:
                        v_name = match['Full Name'].iloc[0]
                        v_cat = match['Category'].iloc[0]
                        st.success(f"✅ **Item Found:** {v_name}")
                        st.info(f"📁 **Category:** {v_cat}")
                    else:
                        st.error("❌ SKU not found in PV Inventory. Check the SKU or sync the database.")

                st.divider()
                st.markdown("### 📥 2. Record Quantity")
                with st.form("record_form", clear_on_submit=True):
                    in_date = st.date_input("Date Received", date.today())
                    in_qty = st.number_input("Quantity Received", min_value=1, step=1)
                    
                    # Disabled button if no item is verified
                    submit_btn = st.form_submit_button("Record Intake", disabled=(v_name is None))
                    
                    if submit_btn:
                        payload = {"records": [{"fields": {
                            "Date": str(in_date), "SKU": input_sku, "Wig Name": v_name,
                            "Category": v_cat, "Quantity": in_qty, "User": username, "Location": "Pv"
                        }}]}
                        res = requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=payload)
                        if res.status_code == 200:
                            st.toast(f"Logged {in_qty} units of {v_name}", icon='✅')
                            st.cache_data.clear()
                            time.sleep(1)
                            st.rerun()

            with col_right:
                st.markdown("### 🔎 Receiving History")
                ship_data = get_at_data("Shipments")
                if not ship_data.empty:
                    dates = sorted(ship_data['Date'].unique(), reverse=True)
                    f_date = st.selectbox("Filter History by Date", ["Show All"] + dates)
                    f_sku = st.text_input("🔍 Search History by SKU")
                    hist_df = ship_data.copy()
                    if f_date != "Show All": hist_df = hist_df[hist_df['Date'] == f_date]
                    if f_sku: hist_df = hist_df[hist_df['SKU'].str.contains(f_sku, na=False)]
                    st.dataframe(hist_df[['Date', 'SKU', 'Wig Name', 'Quantity', 'User']], use_container_width=True, hide_index=True)

    # --- TAB 3: ADMIN SYNC ---
    if user_role == "Admin":
        with tabs[2]:
            st.subheader("🛡️ Master Data Sync")
            f_pv, f_ht = st.file_uploader("PV Square File", type=['xlsx']), st.file_uploader("Haiti Square File", type=['xlsx'])
            if f_pv and f_ht:
                if st.button("🚀 Run Wipe & Sync"):
                    d1, d2 = clean_location_data(f_pv, "Pv"), clean_location_data(f_ht, "Haiti")
                    full_sync = pd.concat([d1, d2]).reset_index(drop=True)
                    lib_old = get_at_data("Master_Inventory")
                    if not lib_old.empty:
                        for i in range(0, len(lib_old), 10):
                            batch = lib_old['id'].tolist()[i:i+10]
                            q = "&".join([f"records[]={rid}" for rid in batch])
                            requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory?{q}", headers=HEADERS)
                    prog = st.progress(0)
                    for i in range(0, len(full_sync), 10):
                        chunk = full_sync.iloc[i:i+10]
                        recs = [{"fields": r.to_dict()} for _, r in chunk.iterrows()]
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs})
                        prog.progress(min((i+10)/len(full_sync), 1.0))
                        time.sleep(0.2)
                    st.success("Sync Finished!")
                    st.cache_data.clear()
                    st.rerun()

    with tabs[-1]:
        st.subheader("🔑 Change Password")
        if authenticator.reset_password(username=username, fields={'form_name': 'Update'}):
            st.success('Password updated!')

elif authentication_status is False: st.error('Wrong Login')
elif authentication_status is None: st.warning('Please login.')
