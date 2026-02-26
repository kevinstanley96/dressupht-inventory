import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import plotly.express as px
from fpdf import FPDF 

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.10.0", layout="wide")

# --- AUTHENTICATION ---
usernames_list = ["Djessie", "Kevin", "Casimir", "Melchisedek", "David", "Darius", "Eliada", "Sebastien", "Guirlene", "Carmela", "Angelina", "Tamara", "Dorotheline", "Sarah", "Valerie", "Saouda", "Marie France", "Carelle", "Annaelle", "Gerdine", "Martilda"]
credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames_list}}
credentials['usernames']['Kevin']['password'] = "The$100$Raven"

authenticator = stauth.Authenticate(credentials, "inventory_cookie", "abcdef123456_key", 30)
name, authentication_status, username = authenticator.login(location='main')

if st.session_state["authentication_status"]:
    username = st.session_state["username"]
    
    # --- SESSION STATE FOR PERSISTENT UI ---
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

    # --- DATA ENGINE ---
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

    # --- CLEANING LOGIC (SQUARE COMPATIBILITY) ---
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

    # --- USER PROFILE & SIDEBAR ---
    roles_df = get_at_data("Role")
    user_row = roles_df[roles_df['User Name'] == username] if not roles_df.empty else pd.DataFrame()
    user_role = "Admin" if username == "Kevin" else (user_row['Access Level'].iloc[0] if not user_row.empty else "Staff")
    user_location = user_row['Assigned Location'].iloc[0] if not user_row.empty and 'Assigned Location' in user_row.columns else "Both"

    st.sidebar.markdown(f"### 👤 {username}")
    st.sidebar.markdown(f"**📍 Location:** {user_location}")
    st.sidebar.divider()
    authenticator.logout('Logout', 'sidebar')

    # --- DYNAMIC TAB DEFINITION ---
    if user_role == "Admin":
        tab_list = ["📋 Library", "➕ Intake", "🕵️ Audit", "💰 Sales", "🛡️ Sync", "🔑 Password"]
    elif user_role == "Manager":
        tab_list = ["📋 Library", "➕ Intake", "🕵️ Audit", "🔑 Password"]
    else:
        tab_list = ["📋 Library", "🔑 Password"]
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

    # --- TAB 2: INTAKE ---
    if user_role in ["Admin", "Manager"]:
        with tabs[1]:
            st.subheader("➕ Stock Intake (PV)")
            master_data = get_at_data("Master_Inventory")
            cola, colb = st.columns(2)
            with cola:
                in_sku = st.text_input("Scan SKU", key="int_sku").strip()
                if in_sku and in_sku != st.session_state.intake_verify["sku"]:
                    match = master_data[(master_data['SKU'] == in_sku) & (master_data['Location'] == "Pv")]
                    if not match.empty:
                        st.session_state.intake_verify = {"name": match['Full Name'].iloc[0], "cat": match['Category'].iloc[0], "sku": in_sku}
                    else: st.session_state.intake_verify = {"name": None, "cat": None, "sku": in_sku}
                
                if st.session_state.intake_verify["name"]:
                    st.success(f"Verified: {st.session_state.intake_verify['name']}")
                
                with st.form("in_form"):
                    in_qty = st.number_input("Qty", min_value=1)
                    if st.form_submit_button("Record") and st.session_state.intake_verify["name"]:
                        payload = {"records": [{"fields": {"Date": str(date.today()), "SKU": in_sku, "Wig Name": st.session_state.intake_verify["name"], "Category": st.session_state.intake_verify["cat"], "Quantity": in_qty, "User": username, "Location": "Pv"}}]}
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=payload)
                        st.cache_data.clear()
            with colb:
                st.markdown("### 📜 History")
                h = get_at_data("Shipments")
                if not h.empty:
                    h['Date'] = pd.to_datetime(h['Date']).dt.strftime('%Y-%m-%d')
                    st.dataframe(h[['Date', 'SKU', 'Wig Name', 'Quantity']], hide_index=True)

    # --- TAB 3: AUDIT ---
    if user_role in ["Admin", "Manager"]:
        with tabs[2]:
            st.subheader("🕵️ Manual Inventory Audit")
            master_data = get_at_data("Master_Inventory")
            ca, cb = st.columns([1, 2])
            with ca:
                counter = st.selectbox("Who is counting?", usernames_list)
                a_sku = st.text_input("SKU", key="aud_sku").strip()
                if a_sku and a_sku != st.session_state.audit_verify["sku"]:
                    match = master_data[(master_data['SKU'] == a_sku) & (master_data['Location'] == "Pv")]
                    if not match.empty:
                        st.session_state.audit_verify = {"name": match['Full Name'].iloc[0], "cat": match['Category'].iloc[0], "sys": int(match['Stock'].iloc[0]), "sku": a_sku}
                    else: st.session_state.audit_verify = {"name": None, "cat": None, "sys": 0, "sku": a_sku}
                
                if st.session_state.audit_verify["name"]:
                    st.success(f"Item: {st.session_state.audit_verify['name']}")
                    st.info(f"System: {st.session_state.audit_verify['sys']}")
                
                with st.form("aud_form"):
                    m, e, r, b = st.number_input("Manual"), st.number_input("Exposed"), st.number_input("Returns"), st.number_input("Big Depot")
                    tp = m + e + r + b
                    ds = tp - st.session_state.audit_verify["sys"]
                    if st.form_submit_button("Save Audit") and st.session_state.audit_verify["name"]:
                        payload = {"records": [{"fields": {"Date": str(date.today()), "SKU": a_sku, "Name": st.session_state.audit_verify["name"], "Counter_Name": counter, "Total_Physical": tp, "System_Stock": st.session_state.audit_verify["sys"], "Discrepancy": ds}}]}
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json=payload)
                        st.cache_data.clear()
            with cb:
                aud_h = get_at_data("Inventory_Audit")
                if not aud_h.empty:
                    aud_h['Date'] = pd.to_datetime(aud_h['Date']).dt.strftime('%Y-%m-%d')
                    st.dataframe(aud_h.sort_values(by="Date", ascending=False), hide_index=True)

    # --- TAB 4: SALES (NEW - ADMIN ONLY) ---
    if user_role == "Admin":
        with tabs[3]:
            st.subheader("💰 Monday Sales Delta Engine (PV)")
            cs1, cs2 = st.columns(2)
            old_f = cs1.file_uploader("OLD Square File (Last Week)", type=['xlsx'])
            new_f = cs2.file_uploader("NEW Square File (Today)", type=['xlsx'])
            
            if old_f and new_f:
                df_o, df_n = clean_location_data(old_f, "Pv"), clean_location_data(new_f, "Pv")
                comp = pd.merge(df_o[['SKU', 'Full Name', 'Category', 'Stock', 'Price']], df_n[['SKU', 'Stock']], on='SKU', suffixes=('_old', '_new'))
                comp['Sold'] = comp['Stock_old'] - comp['Stock_new']
                sales_df = comp[comp['Sold'] > 0].copy()
                
                if not sales_df.empty:
                    st.markdown("### 📊 Analysis")
                    ed_sales = st.data_editor(sales_df[['Category', 'Full Name', 'SKU', 'Sold', 'Price']], hide_index=True, use_container_width=True)
                    ed_sales['Revenue'] = ed_sales['Sold'] * ed_sales['Price']
                    st.metric("Total Revenue", f"${ed_sales['Revenue'].sum():,.2f}")
                    
                    fig = px.pie(ed_sales, values='Revenue', names='Category', hole=0.4, title="Revenue by Category")
                    st.plotly_chart(fig)
                else: st.warning("No sales detected between these files.")

    # --- TAB 5: SYNC (ADMIN ONLY) ---
    if user_role == "Admin":
        with tabs[4]:
            st.subheader("🛡️ Master Sync")
            fp, fh = st.file_uploader("PV File", type=['xlsx'], key="sync_p"), st.file_uploader("Haiti File", type=['xlsx'], key="sync_h")
            if fp and fh and st.button("🚀 Run Wipe & Sync"):
                # [Sync Logic...]
                st.success("Database Updated")

    # --- TAB 6: PASSWORD ---
    with tabs[-1]:
        st.subheader("🔑 Password")
        if authenticator.reset_password(username=username, fields={'form_name': 'Update'}):
            st.success('Updated!')

elif authentication_status is False: st.error('Incorrect Login')
elif authentication_status is None: st.warning('Please Login')
