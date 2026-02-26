import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
from fpdf import FPDF 

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.9.7", layout="wide")

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
        st.error("Missing Secrets! Check Streamlit Cloud.")
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

    # --- 4. TABS SETUP ---
    if user_role in ["Admin", "Manager"]:
        tab_list = ["📋 Library", "➕ Intake", "🕵️ Audit", "🛡️ Admin Sync", "🔑 Password"]
    else:
        tab_list = ["📋 Library", "🔑 Password"]
    tabs = st.tabs(tab_list)

    # --- TAB 1: LIBRARY ---
    with tabs[0]:
        lib_data = get_at_data("Master_Inventory")
        st.subheader(f"📦 Inventory ({len(lib_data)} Items)")
        c1, c2 = st.columns([2, 1])
        search = c1.text_input("🔍 Search Name/SKU")
        sort_choice = c2.selectbox("Sort By", ["Name", "Location", "Category", "Newest"])
        
        disp_df = lib_data.copy()
        if user_role == "Staff" and user_location != "Both":
            disp_df = disp_df[disp_df['Location'] == user_location]
            
        if sort_choice == "Location": disp_df = disp_df.sort_values(by=["Location", "Full Name"])
        elif sort_choice == "Category": disp_df = disp_df.sort_values(by=["Category", "Full Name"])
        elif sort_choice == "Newest": disp_df = disp_df.sort_values(by="id", ascending=False)
        else: disp_df = disp_df.sort_values(by="Full Name") # Default Alpha Sort

        if search:
            disp_df = disp_df[disp_df['Full Name'].str.contains(search, case=False, na=False) | disp_df['SKU'].str.contains(search, na=False)]
        st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 2: INTAKE ---
    if user_role in ["Admin", "Manager"]:
        with tabs[1]:
            st.subheader("➕ Stock Intake (Shipment Logging)")
            master_data = get_at_data("Master_Inventory")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### 📥 1. Verify & Record")
                in_sku = st.text_input("Scan SKU", key="intake_sku").strip()
                v_name, v_cat = None, None
                if in_sku:
                    match = master_data[(master_data['SKU'] == in_sku) & (master_data['Location'] == "Pv")]
                    if not match.empty:
                        v_name, v_cat = match['Full Name'].iloc[0], match['Category'].iloc[0]
                        st.success(f"Verified: {v_name}")
                    else: st.error("SKU not in PV system.")
                
                with st.form("intake_form"):
                    in_qty = st.number_input("Qty Received", min_value=1)
                    if st.form_submit_button("Log Intake", disabled=(v_name is None)):
                        payload = {"records": [{"fields": {"Date": str(date.today()), "SKU": in_sku, "Wig Name": v_name, "Category": v_cat, "Quantity": in_qty, "User": username, "Location": "Pv"}}]}
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=payload)
                        st.cache_data.clear()
                        st.rerun()
            with col2:
                st.markdown("### 📜 History")
                ship_hist = get_at_data("Shipments")
                if not ship_hist.empty:
                    st.dataframe(ship_hist[['Date', 'SKU', 'Wig Name', 'Quantity', 'User']], hide_index=True)

    # --- TAB 3: AUDIT (NEW) ---
    if user_role in ["Admin", "Manager"]:
        with tabs[2]:
            st.subheader("🕵️ Manual Inventory Audit")
            master_data = get_at_data("Master_Inventory")
            col_a, col_b = st.columns([1, 2])
            
            with col_a:
                st.markdown("### 📝 New Count")
                counter = st.selectbox("Counter Name", usernames_list)
                a_sku = st.text_input("SKU to Audit", key="a_sku").strip()
                a_item, a_cat, a_sys = None, None, 0
                if a_sku:
                    match = master_data[(master_data['SKU'] == a_sku) & (master_data['Location'] == "Pv")]
                    if not match.empty:
                        a_item, a_cat, a_sys = match['Full Name'].iloc[0], match['Category'].iloc[0], int(match['Stock'].iloc[0])
                        st.info(f"System Stock: {a_sys}")
                    else: st.error("SKU not found.")
                
                with st.form("audit_form"):
                    m_qty = st.number_input("Manual", min_value=0)
                    e_qty = st.number_input("Exposed", min_value=0)
                    r_qty = st.number_input("Returns", min_value=0)
                    b_qty = st.number_input("Big Depot", min_value=0)
                    total_p = m_qty + e_qty + r_qty + b_qty
                    disc = total_p - a_sys
                    if st.form_submit_button("Save Audit", disabled=(a_item is None)):
                        payload = {"records": [{"fields": {
                            "Date": str(date.today()), "SKU": a_sku, "Name": a_item, "Category": a_cat,
                            "Counter_Name": counter, "Manual_Qty": m_qty, "Exposed_Qty": e_qty,
                            "Returns_Qty": r_qty, "Big_Depot": b_qty, "Total_Physical": total_p,
                            "System_Stock": a_sys, "Discrepancy": disc
                        }}]}
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json=payload)
                        st.cache_data.clear()
                        st.rerun()
            with col_b:
                st.markdown("### 📜 Audit History")
                aud_hist = get_at_data("Inventory_Audit")
                if not aud_hist.empty:
                    st.dataframe(aud_hist.sort_values(by="Date", ascending=False), hide_index=True)

    # --- TAB 4: ADMIN SYNC ---
    if user_role == "Admin":
        with tabs[3]:
            st.subheader("🛡️ Master Data Sync")
            f_pv, f_ht = st.file_uploader("PV Square File", type=['xlsx']), st.file_uploader("Haiti Square File", type=['xlsx'])
            if f_pv and f_ht:
                if st.button("🚀 Run Wipe & Sync"):
                    d1, d2 = clean_location_data(f_pv, "Pv"), clean_location_data(f_ht, "Haiti")
                    full = pd.concat([d1, d2]).reset_index(drop=True)
                    old = get_at_data("Master_Inventory")
                    if not old.empty:
                        for i in range(0, len(old), 10):
                            batch = old['id'].tolist()[i:i+10]
                            q = "&".join([f"records[]={rid}" for rid in batch])
                            requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory?{q}", headers=HEADERS)
                    prog = st.progress(0)
                    for i in range(0, len(full), 10):
                        chunk = full.iloc[i:i+10]
                        recs = [{"fields": r.to_dict()} for _, r in chunk.iterrows()]
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs})
                        prog.progress(min((i+10)/len(full), 1.0))
                        time.sleep(0.2)
                    st.success("Sync Finished!")
                    st.cache_data.clear()
                    st.rerun()

    with tabs[-1]:
        st.subheader("🔑 Password")
        if authenticator.reset_password(username=username, fields={'form_name': 'Update'}):
            st.success('Updated!')

elif authentication_status is False: st.error('Wrong Login')
elif authentication_status is None: st.warning('Please Login')
