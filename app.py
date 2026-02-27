import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import plotly.express as px
from fpdf import FPDF 

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.11.1", layout="wide")

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

    # --- CLEANING LOGIC ---
    def clean_location_data(file, loc_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip() for c in df.columns]
        mapping = {'Item Name': 'Wig Name', 'Variation Name': 'Style', 'SKU': 'SKU', 'Price': 'Price', 'Categories': 'Category'}
        df = df.rename(columns=mapping)
        stock_col = "Current Quantity Dressup Haiti" if loc_name == "Canape-Vert" else "Current Quantity Dressupht Pv"
        df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int) if stock_col in df.columns else 0
        df['Category'] = df['Category'].fillna("Uncategorized")
        df['Location'] = loc_name
        df['SKU'] = df['SKU'].astype(str).str.strip().replace('nan', 'NO_SKU')
        w_name, s_name = df['Wig Name'].astype(str).replace('nan', 'Unknown'), df['Style'].astype(str).replace('nan', '')
        df['Full Name'] = w_name + " (" + s_name + ")"
        df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
        return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']].copy()

    # --- USER PROFILE ---
    roles_df = get_at_data("Role")
    user_row = roles_df[roles_df['User Name'] == username] if not roles_df.empty else pd.DataFrame()
    user_role = "Admin" if username == "Kevin" else (user_row['Access Level'].iloc[0] if not user_row.empty else "Staff")
    user_location = user_row['Assigned Location'].iloc[0] if not user_row.empty and 'Assigned Location' in user_row.columns else "Both"

    st.sidebar.markdown(f"### 👤 {username}")
    st.sidebar.markdown(f"**📍 Location:** {user_location}")
    st.sidebar.divider()
    authenticator.logout('Logout', 'sidebar')

    # --- DYNAMIC TABS SETUP ---
    if user_role == "Admin":
        tab_list = ["📋 Library", "➕ Intake", "🕵️ Audit", "💰 Sales", "🔄 Comparison", "🛡️ Sync", "🔑 Password"]
    elif user_role == "Manager":
        tab_list = ["📋 Library", "➕ Intake", "🕵️ Audit", "🔄 Comparison", "🔑 Password"]
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

    # --- TAB 2: INTAKE (PERSISTENT) ---
    if user_role in ["Admin", "Manager"]:
        with tabs[1]:
            st.subheader("➕ Stock Intake (PV Tracking)")
            master_data = get_at_data("Master_Inventory")
            col1, col2 = st.columns(2)
            with col1:
                in_sku = st.text_input("Scan SKU", key="int_sku").strip()
                if in_sku and in_sku != st.session_state.intake_verify["sku"]:
                    match = master_data[(master_data['SKU'] == in_sku) & (master_data['Location'] == "Pv")]
                    if not match.empty:
                        st.session_state.intake_verify = {"name": match['Full Name'].iloc[0], "cat": match['Category'].iloc[0], "sku": in_sku}
                    else:
                        st.session_state.intake_verify = {"name": None, "cat": None, "sku": in_sku}
                        st.error("SKU Not Found")

                if st.session_state.intake_verify["name"]:
                    st.success(f"**Item:** {st.session_state.intake_verify['name']}")
                
                with st.form("int_form", clear_on_submit=True):
                    in_qty = st.number_input("Qty Received", min_value=1)
                    if st.form_submit_button("Record Intake") and st.session_state.intake_verify["name"]:
                        payload = {"records": [{"fields": {"Date": str(date.today()), "SKU": in_sku, "Wig Name": st.session_state.intake_verify["name"], "Category": st.session_state.intake_verify["cat"], "Quantity": in_qty, "User": username, "Location": "Pv"}}]}
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=payload)
                        st.toast("Intake Saved!")
                        st.cache_data.clear()
            with col2:
                st.markdown("### 📜 History")
                h = get_at_data("Shipments")
                if not h.empty:
                    h['Date'] = pd.to_datetime(h['Date']).dt.strftime('%Y-%m-%d')
                    st.dataframe(h[['Date', 'SKU', 'Wig Name', 'Quantity']], hide_index=True)

    # --- TAB 3: AUDIT (PERSISTENT) ---
    if user_role in ["Admin", "Manager"]:
        with tabs[2]:
            st.subheader("🕵️ Manual Inventory Audit")
            master_data = get_at_data("Master_Inventory")
            ca, cb = st.columns([1, 2])
            with ca:
                counter = st.selectbox("Counter Name", usernames_list)
                a_sku = st.text_input("SKU to Audit", key="aud_sku").strip()
                if a_sku and a_sku != st.session_state.audit_verify["sku"]:
                    match = master_data[(master_data['SKU'] == a_sku) & (master_data['Location'] == "Pv")]
                    if not match.empty:
                        st.session_state.audit_verify = {"name": match['Full Name'].iloc[0], "cat": match['Category'].iloc[0], "sys": int(match['Stock'].iloc[0]), "sku": a_sku}
                    else:
                        st.session_state.audit_verify = {"name": None, "cat": None, "sys": 0, "sku": a_sku}
                        st.error("SKU Not Found")
                
                if st.session_state.audit_verify["name"]:
                    st.success(f"Item: {st.session_state.audit_verify['name']}")
                    st.info(f"System Stock: {st.session_state.audit_verify['sys']}")
                
                with st.form("aud_form"):
                    m, e, r, b = st.number_input("Manual", min_value=0), st.number_input("Exposed", min_value=0), st.number_input("Returns", min_value=0), st.number_input("Big Depot", min_value=0)
                    tp = m + e + r + b
                    ds = tp - st.session_state.audit_verify["sys"]
                    if st.form_submit_button("Save Audit") and st.session_state.audit_verify["name"]:
                        payload = {"records": [{"fields": {"Date": str(date.today()), "SKU": a_sku, "Name": st.session_state.audit_verify["name"], "Category": st.session_state.audit_verify["cat"], "Counter_Name": counter, "Total_Physical": tp, "System_Stock": st.session_state.audit_verify["sys"], "Discrepancy": ds}}]}
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json=payload)
                        st.cache_data.clear()
                        st.success("Audit Recorded")
            with cb:
                aud_h = get_at_data("Inventory_Audit")
                if not aud_h.empty:
                    aud_h['Date'] = pd.to_datetime(aud_h['Date']).dt.strftime('%Y-%m-%d')
                    st.dataframe(aud_h.sort_values(by="Date", ascending=False), hide_index=True)

    # --- TAB 4: SALES (DELTA ENGINE) ---
    if user_role == "Admin":
        with tabs[3]:
            st.subheader("💰 Monday Sales Delta Engine (PV)")
            cs1, cs2 = st.columns(2)
            old_f = cs1.file_uploader("OLD Square File", type=['xlsx'], key="old_s")
            new_f = cs2.file_uploader("NEW Square File", type=['xlsx'], key="new_s")
            
            if old_f and new_f:
                df_o, df_n = clean_location_data(old_f, "Pv"), clean_location_data(new_f, "Pv")
                comp = pd.merge(df_o[['SKU', 'Full Name', 'Category', 'Stock', 'Price']], df_n[['SKU', 'Stock']], on='SKU', suffixes=('_old', '_new'))
                comp['Sold'] = comp['Stock_old'] - comp['Stock_new']
                sales_df = comp[comp['Sold'] > 0].copy()
                
                if not sales_df.empty:
                    st.markdown("### 📈 Analysis")
                    ed_sales = st.data_editor(sales_df[['Category', 'Full Name', 'SKU', 'Sold', 'Price']], hide_index=True)
                    ed_sales['Revenue'] = ed_sales['Sold'] * ed_sales['Price']
                    st.metric("Total Revenue", f"${ed_sales['Revenue'].sum():,.2f}")
                    st.plotly_chart(px.pie(ed_sales, values='Revenue', names='Category', hole=0.4, title="Revenue by Category"))
                else: st.warning("No sales detected.")

    # --- TAB 5: COMPARISON (NAME MATCH ENGINE) ---
    if user_role in ["Admin", "Manager"]:
        with tabs[4 if user_role == "Admin" else 3]:
            st.subheader("🔄 Stock Comparison: Canape-Vert vs PV")
            st.info("Compare stock levels by Wig Name to plan internal transfers.")
            
            c_comp1, c_comp2 = st.columns(2)
            f_cv = c_comp1.file_uploader("Upload Canape-Vert File", type=['xlsx'], key="comp_cv")
            f_pv = c_comp2.file_uploader("Upload PV File", type=['xlsx'], key="comp_pv")
            
            if f_cv and f_pv:
                df_cv = clean_location_data(f_cv, "Canape-Vert")
                df_pv = clean_location_data(f_pv, "Pv")
                
                # Merge on "Full Name" because SKUs might not match
                merged_comp = pd.merge(
                    df_cv[['Full Name', 'Category', 'Stock', 'SKU']], 
                    df_pv[['Full Name', 'Stock', 'SKU']], 
                    on='Full Name', 
                    how='outer', 
                    suffixes=('_CV', '_PV')
                ).fillna(0)
                
                # FIX: Correctly handle category sorting to prevent TypeError
                unique_cats = merged_comp['Category'].astype(str).unique().tolist()
                if "nan" in unique_cats: unique_cats.remove("nan")
                cats = ["All"] + sorted(unique_cats)
                
                selected_cat = st.selectbox("Filter by Category", cats)
                if selected_cat != "All":
                    merged_comp = merged_comp[merged_comp['Category'] == selected_cat]

                # Visual Column logic: What to request?
                merged_comp['Status'] = merged_comp.apply(lambda x: "Request Needed" if x['Stock_PV'] == 0 and x['Stock_CV'] > 0 else "Balanced", axis=1)

                st.dataframe(
                    merged_comp[['Category', 'Full Name', 'Stock_CV', 'SKU_CV', 'Stock_PV', 'SKU_PV', 'Status']],
                    column_config={
                        "Stock_CV": "Stock (Canape-Vert)",
                        "Stock_PV": "Stock (PV)",
                        "SKU_CV": "SKU (CV)",
                        "SKU_PV": "SKU (PV)"
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                # Summary Metric
                low_pv = len(merged_comp[(merged_comp['Stock_PV'] <= 1) & (merged_comp['Stock_CV'] > 2)])
                st.metric("Potential Transfer Requests", low_pv)

    # --- TAB 6: SYNC ---
    if user_role == "Admin":
        with tabs[5]:
            st.subheader("🛡️ Master Data Sync")
            fp, fh = st.file_uploader("PV File", type=['xlsx'], key="sync_p"), st.file_uploader("Haiti File", type=['xlsx'], key="sync_h")
            if fp and fh and st.button("🚀 Run Wipe & Sync"):
                d1, d2 = clean_location_data(fp, "Pv"), clean_location_data(fh, "Canape-Vert")
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
                st.success("Database Updated")
                st.cache_data.clear()

    # --- TAB 7: PASSWORD ---
    with tabs[-1]:
        st.subheader("🔑 Password")
        if authenticator.reset_password(username=username, fields={'form_name': 'Update'}):
            st.success('Updated!')

elif authentication_status is False: st.error('Incorrect Login')
elif authentication_status is None: st.warning('Please Login')
