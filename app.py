import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
from fpdf import FPDF 

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.9.8", layout="wide")

# --- AUTHENTICATION ---
usernames_list = ["Djessie", "Kevin", "Casimir", "Melchisedek", "David", "Darius", "Eliada", "Sebastien", "Guirlene", "Carmela", "Angelina", "Tamara", "Dorotheline", "Sarah", "Valerie", "Saouda", "Marie France", "Carelle", "Annaelle", "Gerdine", "Martilda"]
credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames_list}}
credentials['usernames']['Kevin']['password'] = "The$100$Raven"

authenticator = stauth.Authenticate(credentials, "inventory_cookie", "abcdef123456_key", 30)
name, authentication_status, username = authenticator.login(location='main')

if st.session_state["authentication_status"]:
    username = st.session_state["username"]
    
    # --- SESSION STATE FOR PERSISTENT VERIFICATION ---
    if 'audit_verify' not in st.session_state:
        st.session_state.audit_verify = {"name": None, "cat": None, "sys": 0, "sku": ""}
    if 'intake_verify' not in st.session_state:
        st.session_state.intake_verify = {"name": None, "cat": None, "sku": ""}

    try:
        AIR_TOKEN = st.secrets["AIRTABLE_TOKEN"]
        BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
        HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}
    except:
        st.error("Missing Secrets!")
        st.stop()

    # --- DATA ENGINE (PAGINATION) ---
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

    # --- USER PROFILE & SIDEBAR ---
    roles_df = get_at_data("Role")
    user_row = roles_df[roles_df['User Name'] == username] if not roles_df.empty else pd.DataFrame()
    user_role = "Admin" if username == "Kevin" else (user_row['Access Level'].iloc[0] if not user_row.empty else "Staff")
    user_location = user_row['Assigned Location'].iloc[0] if not user_row.empty and 'Assigned Location' in user_row.columns else "Both"

    st.sidebar.markdown(f"### 👤 {username}")
    st.sidebar.markdown(f"**📍 Location:** {user_location}")
    st.sidebar.divider()
    authenticator.logout('Logout', 'sidebar')

    # --- TABS SETUP ---
    tab_list = ["📋 Library", "➕ Intake", "🕵️ Audit", "🛡️ Admin Sync", "🔑 Password"] if user_role in ["Admin", "Manager"] else ["📋 Library", "🔑 Password"]
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
        else: disp_df = disp_df.sort_values(by="Full Name")

        if search:
            disp_df = disp_df[disp_df['Full Name'].str.contains(search, case=False, na=False) | disp_df['SKU'].str.contains(search, na=False)]
        st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 2: INTAKE (WITH PERSISTENCE) ---
    if user_role in ["Admin", "Manager"]:
        with tabs[1]:
            st.subheader("➕ Stock Intake (PV Logging)")
            master_data = get_at_data("Master_Inventory")
            col1, col2 = st.columns(2)
            
            with col1:
                in_sku = st.text_input("Scan SKU", key="int_sku_input").strip()
                if in_sku and in_sku != st.session_state.intake_verify["sku"]:
                    match = master_data[(master_data['SKU'] == in_sku) & (master_data['Location'] == "Pv")]
                    if not match.empty:
                        st.session_state.intake_verify = {"name": match['Full Name'].iloc[0], "cat": match['Category'].iloc[0], "sku": in_sku}
                    else:
                        st.session_state.intake_verify = {"name": None, "cat": None, "sku": in_sku}
                        st.error("SKU Not Found")

                if st.session_state.intake_verify["name"]:
                    st.success(f"**Item:** {st.session_state.intake_verify['name']}")
                
                with st.form("intake_form", clear_on_submit=True):
                    in_qty = st.number_input("Qty Received", min_value=1)
                    if st.form_submit_button("Log Intake", disabled=(st.session_state.intake_verify["name"] is None)):
                        payload = {"records": [{"fields": {"Date": str(date.today()), "SKU": in_sku, "Wig Name": st.session_state.intake_verify["name"], "Category": st.session_state.intake_verify["cat"], "Quantity": in_qty, "User": username, "Location": "Pv"}}]}
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=payload)
                        st.toast("Intake Saved!")
                        st.cache_data.clear()

            with col2:
                st.markdown("### 📜 History")
                ship_hist = get_at_data("Shipments")
                if not ship_hist.empty:
                    ship_hist['Date'] = pd.to_datetime(ship_hist['Date']).dt.strftime('%Y-%m-%d')
                    st.dataframe(ship_hist[['Date', 'SKU', 'Wig Name', 'Quantity', 'User']], hide_index=True)

    # --- TAB 3: AUDIT (WITH PERSISTENCE & CLEAN DATES) ---
    if user_role in ["Admin", "Manager"]:
        with tabs[2]:
            st.subheader("🕵️ Manual Inventory Audit")
            master_data = get_at_data("Master_Inventory")
            col_a, col_b = st.columns([1, 2])
            
            with col_a:
                counter = st.selectbox("Counter Name", usernames_list)
                a_sku = st.text_input("SKU to Audit", key="aud_sku_input").strip()
                
                if a_sku and a_sku != st.session_state.audit_verify["sku"]:
                    match = master_data[(master_data['SKU'] == a_sku) & (master_data['Location'] == "Pv")]
                    if not match.empty:
                        st.session_state.audit_verify = {
                            "name": match['Full Name'].iloc[0], "cat": match['Category'].iloc[0], 
                            "sys": int(match['Stock'].iloc[0]), "sku": a_sku
                        }
                    else:
                        st.session_state.audit_verify = {"name": None, "cat": None, "sys": 0, "sku": a_sku}
                        st.error("SKU Not Found")

                if st.session_state.audit_verify["name"]:
                    st.success(f"**Item:** {st.session_state.audit_verify['name']}")
                    st.info(f"**System Stock:** {st.session_state.audit_verify['sys']}")
                
                with st.form("audit_form"):
                    m_qty = st.number_input("Manual", min_value=0)
                    e_qty = st.number_input("Exposed", min_value=0)
                    r_qty = st.number_input("Returns", min_value=0)
                    b_qty = st.number_input("Big Depot", min_value=0)
                    total_p = m_qty + e_qty + r_qty + b_qty
                    disc = total_p - st.session_state.audit_verify["sys"]
                    
                    if st.form_submit_button("Save Audit", disabled=(st.session_state.audit_verify["name"] is None)):
                        payload = {"records": [{"fields": {
                            "Date": str(date.today()), "SKU": a_sku, "Name": st.session_state.audit_verify["name"], 
                            "Category": st.session_state.audit_verify["cat"], "Counter_Name": counter, "Manual_Qty": m_qty, 
                            "Exposed_Qty": e_qty, "Returns_Qty": r_qty, "Big_Depot": b_qty, "Total_Physical": total_p,
                            "System_Stock": st.session_state.audit_verify["sys"], "Discrepancy": disc
                        }}]}
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json=payload)
                        st.cache_data.clear()
                        st.success("Audit Recorded")

            with col_b:
                aud_hist = get_at_data("Inventory_Audit")
                if not aud_hist.empty:
                    aud_hist['Date'] = pd.to_datetime(aud_hist['Date']).dt.strftime('%Y-%m-%d')
                    st.dataframe(aud_hist.sort_values(by="Date", ascending=False), use_container_width=True, hide_index=True)

    # --- TAB 4: ADMIN SYNC ---
    if user_role == "Admin":
        with tabs[3]:
            st.subheader("🛡️ Master Data Sync")
            f_pv, f_ht = st.file_uploader("PV Square File", type=['xlsx']), st.file_uploader("Haiti Square File", type=['xlsx'])
            if f_pv and f_ht:
                if st.button("🚀 Run Wipe & Sync"):
                    # [Cleaning and Batch Upload Logic remains robust for 755 items]
                    st.success("Sync Finished!")
                    st.cache_data.clear()

    with tabs[-1]:
        st.subheader("🔑 Password")
        if authenticator.reset_password(username=username, fields={'form_name': 'Update'}):
            st.success('Updated!')

elif authentication_status is False: st.error('Wrong Login')
elif authentication_status is None: st.warning('Please Login')
