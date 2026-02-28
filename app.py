import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import plotly.express as px
import smtplib
from email.message import EmailMessage

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.13.0", layout="wide")

# --- AUTHENTICATION ---
usernames_list = ["Djessie", "Kevin", "Casimir", "Melchisedek", "David", "Darius", "Eliada", "Sebastien", "Guirlene", "Carmela", "Angelina", "Tamara", "Dorotheline", "Sarah", "Valerie", "Saouda", "Marie France", "Carelle", "Annaelle", "Gerdine", "Martilda"]
credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames_list}}
credentials['usernames']['Kevin']['password'] = "The$100$Raven"

authenticator = stauth.Authenticate(credentials, "inventory_cookie", "abcdef123456_key", 30)
name, authentication_status, username = authenticator.login(location='main')

# --- EMAIL NOTIFICATION FUNCTION ---
def send_email(subject, body, recipients):
    if not recipients:
        st.warning("No recipients provided.")
        return False
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = st.secrets["EMAIL_ADDRESS"]
    msg['To'] = ", ".join(recipients) 
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(st.secrets["EMAIL_ADDRESS"], st.secrets["EMAIL_PASSWORD"])
            smtp.send_message(msg)
            return True
    except Exception as e:
        st.error(f"Email failed: {e}")
        return False

if st.session_state["authentication_status"]:
    username = st.session_state["username"]
    
    # --- SESSION STATE ---
    if 'audit_verify' not in st.session_state: st.session_state.audit_verify = {"name": None, "cat": None, "sys": 0, "sku": ""}
    if 'intake_verify' not in st.session_state: st.session_state.intake_verify = {"name": None, "cat": None, "sku": ""}
    if 'depot_verify' not in st.session_state: st.session_state.depot_verify = {"name": None, "sku": ""}

    try:
        AIR_TOKEN = st.secrets["AIRTABLE_TOKEN"]
        BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
        HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}
    except:
        st.error("Missing Secrets!")
        st.stop()

    @st.cache_data(ttl=300)
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

    def clean_location_data(file, loc_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip() for c in df.columns]
        mapping = {'Item Name': 'Wig Name', 'Variation Name': 'Style', 'SKU': 'SKU', 'Price': 'Price', 'Categories': 'Category'}
        df = df.rename(columns=mapping)
        stock_col = "Current Quantity Dressup Haiti" if loc_name == "Canape-Vert" else "Current Quantity Dressupht Pv"
        if stock_col in df.columns:
            df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int)
        else:
            df['Stock'] = 0 
        df['Category'] = df['Category'].fillna("Uncategorized")
        df['Location'] = loc_name
        df['SKU'] = df['SKU'].astype(str).str.strip().replace('nan', 'NO_SKU')
        w_name, s_name = df['Wig Name'].astype(str).replace('nan', 'Unknown'), df['Style'].astype(str).replace('nan', '')
        df['Full Name'] = w_name + " (" + s_name + ")"
        df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
        return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']].copy()

    # --- NEW: AUTO-FETCH LOGIC FOR AUDIT ---
    def get_stock_from_subtables(sku):
        """Checks Big_Depot and Exposed_Wigs for current levels"""
        depot_df = get_at_data("Big_Depot")
        exposed_df = get_at_data("Exposed_Wigs")
        dep_val, exp_val = 0, 0
        
        if not depot_df.empty and 'SKU' in depot_df.columns:
            item_depot = depot_df[depot_df['SKU'].str.lower() == sku.lower()]
            adds = item_depot[item_depot['Type'] == "Addition"]['Quantity'].sum()
            subs = item_depot[item_depot['Type'] == "Subtraction"]['Quantity'].sum()
            dep_val = adds - subs
            
        if not exposed_df.empty and 'SKU' in exposed_df.columns:
            item_exp = exposed_df[exposed_df['SKU'].str.lower() == sku.lower()]
            exp_val = item_exp['Quantity'].sum()
            
        return dep_val, exp_val

    # --- USER PROFILE ---
    roles_df = get_at_data("Role")
    user_row = roles_df[roles_df['User Name'] == username] if not roles_df.empty else pd.DataFrame()
    user_role = "Admin" if username == "Kevin" else (user_row['Access Level'].iloc[0] if not user_row.empty else "Staff")
    user_location = user_row['Assigned Location'].iloc[0] if not user_row.empty and 'Assigned Location' in user_row.columns else "Both"
    
    # Authorized Staff for Exposure
    exposed_staff = ["Kevin", "Djessie", "Casimir"]

    st.sidebar.markdown(f"### 👤 {username}")
    st.sidebar.markdown(f"**📍 Location:** {user_location}")
    st.sidebar.divider()
    authenticator.logout('Logout', 'sidebar')

    st.title("DRESSUP HAITI STOCK SYSTEM")

    # --- ADMIN DATA SYNC ---
    if user_role == "Admin":
        with st.expander("🛡️ Master Data Sync (Admin Only)", expanded=False):
            c_u1, c_u2 = st.columns(2)
            fp = c_u1.file_uploader("PV Square File", type=['xlsx'], key="sync_p")
            fh = c_u2.file_uploader("Canape-Vert Square File", type=['xlsx'], key="sync_h")
            if fp and fh and st.button("🚀 Run Wipe & Sync"):
                with st.spinner("Syncing..."):
                    d1 = clean_location_data(fp, "Pv")
                    d2 = clean_location_data(fh, "Canape-Vert")
                    full = pd.concat([d1, d2], ignore_index=True)
                    old = get_at_data("Master_Inventory")
                    for i in range(0, len(old), 10):
                        batch = old['id'].tolist()[i:i+10]
                        q = "&".join([f"records[]={rid}" for rid in batch])
                        requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory?{q}", headers=HEADERS)
                    for i in range(0, len(full), 10):
                        chunk = full.iloc[i:i+10]
                        recs = [{"fields": r.to_dict()} for _, r in chunk.iterrows()]
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs})
                    st.success("Database Updated"); st.cache_data.clear(); st.rerun()

    # --- TABS SETUP ---
    tab_list = ["Library", "Intake", "Audit", "Sales", "Comparison", "Fast/Slow", "Big Depot", "Password"]
    if username in exposed_staff or user_role == "Admin":
        tab_list.insert(7, "Exposed")
    
    if user_role == "Staff":
        tab_list = ["Library", "Password"]
        
    tabs = st.tabs(tab_list)

    # --- TAB 1: LIBRARY ---
    with tabs[0]:
        lib_data = get_at_data("Master_Inventory")
        st.subheader(f"Inventory ({len(lib_data)} Items)")
        c1, c2 = st.columns([2, 1])
        search = c1.text_input("🔍 Search Name/SKU")
        sort_choice = c2.selectbox("Sort By", ["Name", "Location", "Category"])
        disp_df = lib_data.copy()
        if user_role == "Staff" and user_location != "Both":
            disp_df = disp_df[disp_df['Location'] == user_location]
        
        if not disp_df.empty:
            if sort_choice == "Location": disp_df = disp_df.sort_values(by=["Location", "Full Name"])
            elif sort_choice == "Category": disp_df = disp_df.sort_values(by=["Category", "Full Name"])
            else: disp_df = disp_df.sort_values(by="Full Name")

        if search:
            tokens = search.strip().lower().split()
            disp_df = disp_df[disp_df.apply(lambda r: all(t in str(r['Full Name']).lower() or t in str(r['SKU']).lower() for t in tokens), axis=1)]
        st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 2: INTAKE ---
    if "Intake" in tab_list:
        with tabs[tab_list.index("Intake")]:
            st.subheader("Stock Intake (PV Tracking)")
            master_data = get_at_data("Master_Inventory")
            in_sku = st.text_input("Scan SKU", key="int_sku").strip()
            if in_sku and in_sku != st.session_state.intake_verify["sku"]:
                match = master_data[(master_data['SKU'].str.lower() == in_sku.lower()) & (master_data['Location'] == "Pv")]
                if not match.empty:
                    st.session_state.intake_verify = {"name": match['Full Name'].iloc[0], "cat": match['Category'].iloc[0], "sku": in_sku}
                else:
                    st.session_state.intake_verify = {"name": None, "cat": None, "sku": in_sku}
            
            if st.session_state.intake_verify["name"]:
                st.success(f"**Item:** {st.session_state.intake_verify['name']}")
                with st.form("int_form", clear_on_submit=True):
                    in_qty = st.number_input("Qty Received", min_value=1)
                    if st.form_submit_button("Record Intake"):
                        payload = {"records": [{"fields": {"Date": str(date.today()), "SKU": in_sku, "Wig Name": st.session_state.intake_verify["name"], "Quantity": in_qty, "User": username, "Location": "Pv"}}]}
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=payload)
                        st.toast("Intake Saved!"); st.cache_data.clear()

    # --- TAB 3: AUDIT (INTEGRATED AUTO-FETCH/UPDATE) ---
    if "Audit" in tab_list:
        with tabs[tab_list.index("Audit")]:
            st.subheader("Manual Inventory Audit")
            master_data = get_at_data("Master_Inventory")
            ca, cb = st.columns([1, 2])
            with ca:
                counter = st.selectbox("Counter Name", usernames_list)
                a_sku = st.text_input("SKU to Audit", key="aud_sku").strip()
                if a_sku and a_sku != st.session_state.audit_verify["sku"]:
                    match = master_data[(master_data['SKU'].str.lower() == a_sku.lower()) & (master_data['Location'] == "Pv")]
                    if not match.empty:
                        # AUTO-FETCH FROM SUB-TABLES
                        dep_val, exp_val = get_stock_from_subtables(a_sku)
                        st.session_state.audit_verify = {
                            "name": match['Full Name'].iloc[0], 
                            "cat": match['Category'].iloc[0], 
                            "sys": int(match['Stock'].iloc[0]), 
                            "sku": a_sku,
                            "auto_depot": dep_val,
                            "auto_exposed": exp_val
                        }
                    else:
                        st.session_state.audit_verify = {"name": None, "sku": a_sku}

                if st.session_state.audit_verify.get("name"):
                    st.success(f"Item: {st.session_state.audit_verify['name']}")
                    with st.form("aud_form"):
                        m = st.number_input("Manual (Floor)", min_value=0)
                        e = st.number_input("Exposed (Fetched)", value=int(st.session_state.audit_verify.get("auto_exposed", 0)))
                        r = st.number_input("Returns", min_value=0)
                        b = st.number_input("Big Depot (Fetched)", value=int(st.session_state.audit_verify.get("auto_depot", 0)))
                        
                        tp = m + e + r + b
                        ds = tp - st.session_state.audit_verify["sys"]
                        
                        if st.form_submit_button("Save Audit"):
                            # 1. Update Audit Log
                            payload_audit = {"records": [{"fields": {"Date": str(date.today()), "SKU": a_sku, "Name": st.session_state.audit_verify["name"], "Counter_Name": counter, "Total_Physical": tp, "System_Stock": st.session_state.audit_verify["sys"], "Discrepancy": ds}}]}
                            requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json=payload_audit)
                            
                            # 2. Update/Sync Exposed Table with new value entered during audit
                            payload_exp = {"records": [{"fields": {"SKU": a_sku, "Full Name": st.session_state.audit_verify["name"], "Quantity": e, "Last_Updated": str(date.today())}}]}
                            requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Exposed_Wigs", headers=HEADERS, json=payload_exp)
                            
                            st.cache_data.clear()
                            st.success("Audit & Exposed records synced!")

    # --- TAB 4: SALES ---
    if "Sales" in tab_list:
        with tabs[tab_list.index("Sales")]:
            st.subheader("Monday Sales Delta Engine (PV)")
            cs1, cs2 = st.columns(2)
            old_f = cs1.file_uploader("OLD Square File", type=['xlsx'], key="old_s")
            new_f = cs2.file_uploader("NEW Square File", type=['xlsx'], key="new_s")
            if old_f and new_f:
                df_o, df_n = clean_location_data(old_f, "Pv"), clean_location_data(new_f, "Pv")
                comp = pd.merge(df_o[['SKU', 'Full Name', 'Category', 'Stock', 'Price']], df_n[['SKU', 'Stock']], on='SKU', suffixes=('_old', '_new'))
                comp['Sold'] = comp['Stock_old'] - comp['Stock_new']
                sales_df = comp[comp['Sold'] > 0].copy()
                if not sales_df.empty:
                    st.markdown("### Analysis")
                    ed_sales = st.data_editor(sales_df[['Category', 'Full Name', 'SKU', 'Sold', 'Price']], hide_index=True)
                    ed_sales['Revenue'] = ed_sales['Sold'] * ed_sales['Price']
                    st.metric("Total Revenue", f"${ed_sales['Revenue'].sum():,.2f}")
                    st.plotly_chart(px.pie(ed_sales, values='Revenue', names='Category', hole=0.4, title="Revenue by Category"))
                else: st.warning("No sales detected.")

    # --- TAB 5: COMPARISON ---
    if "Comparison" in tab_list:
        with tabs[tab_list.index("Comparison")]:
            st.subheader("Stock Comparison: Canape-Vert vs PV")
            c_comp1, c_comp2 = st.columns(2)
            f_cv = c_comp1.file_uploader("Upload Canape-Vert File", type=['xlsx'], key="comp_cv")
            f_pv = c_comp2.file_uploader("Upload PV File", type=['xlsx'], key="comp_pv")
            if f_cv and f_pv:
                df_cv = clean_location_data(f_cv, "Canape-Vert")
                df_pv = clean_location_data(f_pv, "Pv")
                merged_comp = pd.merge(df_cv[['Full Name', 'Category', 'Stock', 'SKU']], df_pv[['Full Name', 'Stock', 'SKU']], on='Full Name', how='outer', suffixes=('_CV', '_PV')).fillna(0)
                st.dataframe(merged_comp, use_container_width=True)

    # --- TAB 6: FAST/SLOW ---
    if "Fast/Slow" in tab_list:
        with tabs[tab_list.index("Fast/Slow")]:
            st.subheader("Fast & Slow Moving Wigs")
            cs1, cs2 = st.columns(2)
            old_fs = cs1.file_uploader("OLD Square File", type=['xlsx'], key="fs_old")
            new_fs = cs2.file_uploader("NEW Square File", type=['xlsx'], key="fs_new")
            if old_fs and new_fs:
                df_o = clean_location_data(old_fs, "Pv")
                df_n = clean_location_data(new_fs, "Pv")
                comp = pd.merge(df_o, df_n[['SKU', 'Stock']], on='SKU', suffixes=('_old', '_new'))
                comp['Sold'] = comp['Stock_old'] - comp['Stock_new']
                st.dataframe(comp, use_container_width=True)

    # --- TAB 7: BIG DEPOT ---
    if "Big Depot" in tab_list:
        with tabs[tab_list.index("Big Depot")]:
            st.subheader("Depot Inventory Tracking")
            d_sku = st.text_input("Scan SKU for Depot", key="dep_sku_input").strip()
            if d_sku and d_sku != st.session_state.depot_verify["sku"]:
                match = master_data[master_data['SKU'].str.lower() == d_sku.lower()]
                if not match.empty:
                    st.session_state.depot_verify = {"name": match['Full Name'].iloc[0], "sku": d_sku}
            
            if st.session_state.depot_verify["name"]:
                st.success(f"**Item:** {st.session_state.depot_verify['name']}")
                with st.form("depot_form", clear_on_submit=True):
                    d_type = st.selectbox("Action", ["Addition", "Subtraction"])
                    d_qty = st.number_input("Quantity", min_value=1)
                    if st.form_submit_button("Save Depot Movement"):
                        payload = {"records": [{"fields": {"Date": str(date.today()), "SKU": d_sku, "Wig Name": st.session_state.depot_verify["name"], "Type": d_type, "Quantity": d_qty, "User": username}}]}
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Big_Depot", headers=HEADERS, json=payload)
                        st.cache_data.clear(); st.toast("Depot Movement Saved")

    # --- NEW TAB: EXPOSED (TOKENIZED SEARCH) ---
    if "Exposed" in tab_list:
        with tabs[tab_list.index("Exposed")]:
            st.subheader("📍 Exposed Wigs Management")
            master_inv = get_at_data("Master_Inventory")
            
            e_search = st.text_input("🔍 Search Wig to Update Exposure (e.g., 'Loose Wave 24')")
            if e_search:
                e_tokens = e_search.lower().split()
                matches = master_inv[master_inv.apply(lambda r: all(t in str(r['Full Name']).lower() or t in str(r['SKU']).lower() for t in e_tokens), axis=1)]
                
                if not matches.empty:
                    choice = st.selectbox("Select Wig", matches['Full Name'].unique())
                    sel_sku = matches[matches['Full Name'] == choice]['SKU'].values[0]
                    
                    with st.form("exposed_form_update"):
                        new_qty = st.number_input("Current Exposed Count", min_value=0)
                        if st.form_submit_button("Update Exposed Level"):
                            payload = {"records": [{"fields": {"SKU": sel_sku, "Full Name": choice, "Quantity": new_qty, "Last_Updated": str(date.today())}}]}
                            requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Exposed_Wigs", headers=HEADERS, json=payload)
                            st.success(f"Updated {choice}")
                            st.cache_data.clear()

    # --- TAB 8: PASSWORD ---
    with tabs[-1]:
        st.subheader("Security Settings")
        if authenticator.reset_password(username=username, fields={'form_name': 'Update'}):
            st.success('Password Updated!')

elif authentication_status is False: st.error('Incorrect Login')
elif authentication_status is None: st.warning('Please Login')
