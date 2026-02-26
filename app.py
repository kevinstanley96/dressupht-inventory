import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import base64

# --- CONFIG & INITIALIZATION ---
st.set_page_config(page_title="Dressupht ERP v3.1", layout="wide")

REPO_NAME = "kevin/dressupht-inventory" 

# --- AUTHENTICATION ---
usernames_list = [
    "Djessie", "Kevin", "Casimir", "Melchisedek", "David", "Darius", "Eliada",
    "Sebastien", "Guirlene", "Carmela", "Angelina", "Tamara", "Dorotheline", 
    "Sarah", "Valerie", "Saouda", "Marie France", "Carelle", "Annaelle", 
    "Gerdine", "Martilda"
]
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

    # --- UPDATED HELPER FUNCTION: PAGINATION FIX ---
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
                if offset:
                    params['offset'] = offset  # Ask for the next 100
                else:
                    break  # No more records left
            else:
                break
                
        if not all_recs: return pd.DataFrame()
        return pd.DataFrame([dict(r['fields'], id=r['id']) for r in all_recs])

    def get_user_role(user):
        df = get_at_data("Role", {"filterByFormula": f"{{User Name}}='{user}'"})
        if not df.empty and 'Access Level' in df.columns:
            return df['Access Level'].iloc[0]
        return 'Staff'

    def delete_at_records(table, df):
        if df.empty: return
        ids = df['id'].tolist()
        st.info(f"Clearing {len(ids)} old records...")
        for i in range(0, len(ids), 10):
            batch = ids[i:i+10]
            query = "&".join([f"records[]={rid}" for rid in batch])
            requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/{table}?{query}", headers=HEADERS)
            time.sleep(0.1)

    def clean_data(file, loc_col_name="current quantity dressupht pv"):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip().lower() for c in df.columns]
        mapping = {'item name': 'Wig Name', 'variation name': 'Style', 'sku': 'SKU', 'price': 'Price', 'categories': 'Category'}
        df = df.rename(columns=mapping)
        df['SKU'] = df['SKU'].astype(str).str.strip().replace('nan', 'NO_SKU')
        df['Full Name'] = df['Wig Name'].astype(str) + " (" + df['Style'].astype(str).replace('nan', '') + ")"
        if 'Category' not in df.columns: df['Category'] = 'Uncategorized'
        df['Category'] = df['Category'].astype(str).str.strip().replace('nan', 'Uncategorized')
        
        if loc_col_name in df.columns:
            df['Stock'] = pd.to_numeric(df[loc_col_name], errors='coerce').fillna(0).astype(int)
        else:
            stock_cols = [c for c in df.columns if 'quantity' in c]
            df['Stock'] = pd.to_numeric(df[stock_cols[0]], errors='coerce').fillna(0).astype(int) if stock_cols else 0
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0.0)
        return df

    user_role = get_user_role(username)
    if username == "Kevin": user_role = "Admin"
    st.sidebar.info(f"User: {username} | Role: {user_role}")

    # --- TABS ---
    if user_role == 'Admin':
        tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔄 Compare", "📊 Sales", "🛡️ Admin", "🔑 Password"])
    elif user_role == 'Manager':
        tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔑 Password"])
    else:
        tabs = st.tabs(["📋 Library", "🕵️ Audit", "🔑 Password"])

    # --- SIDEBAR: SYNC ---
    if user_role == 'Admin':
        st.sidebar.divider()
        f_pv = st.sidebar.file_uploader("Upload PV Square Export", type=['xlsx'])
        sync_date = st.sidebar.date_input("Sync Date", date.today())
        
        if f_pv and st.sidebar.button("🚀 Wipe & Sync to Cloud"):
            df_new = clean_data(f_pv)
            existing_df = get_at_data("Master_Inventory")
            delete_at_records("Master_Inventory", existing_df)
            
            total = len(df_new)
            bar = st.sidebar.progress(0)
            with st.spinner(f"Syncing {total} items..."):
                for i in range(0, total, 10):
                    batch = df_new.iloc[i:i+10]
                    recs = [{"fields": {
                        "SKU": str(r['SKU']), "Full Name": str(r['Full Name']), 
                        "Stock": int(r['Stock']), "Price": float(r['Price']), 
                        "Category": str(r['Category']), "Last_Sync_Date": str(sync_date)
                    }} for _, r in batch.iterrows()]
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs})
                    bar.progress(min((i + 10) / total, 1.0))
                    time.sleep(0.2)
            st.sidebar.success("Database Updated!")
            st.rerun()

    # --- TAB 1: LIBRARY (Alphabetical Default + Sorting) ---
    with tabs[0]:
        st.subheader("📦 Master Inventory")
        lib_data = get_at_data("Master_Inventory")
        
        if not lib_data.empty:
            c1, c2, c3 = st.columns([2, 1, 1])
            search = c1.text_input("🔍 Search Name or SKU")
            
            cat_list = ["All"] + sorted(lib_data['Category'].dropna().unique().tolist()) if 'Category' in lib_data.columns else ["All"]
            selected_cat = c2.selectbox("Filter Category", cat_list)
            sort_option = c3.selectbox("Sort By", ["Name (A-Z)", "Category", "Date Sync"])

            filtered_df = lib_data.copy()
            if search:
                filtered_df = filtered_df[filtered_df['Full Name'].str.contains(search, case=False) | filtered_df['SKU'].str.contains(search)]
            if selected_cat != "All":
                filtered_df = filtered_df[filtered_df['Category'] == selected_cat]

            # SORTING
            if sort_option == "Name (A-Z)":
                filtered_df = filtered_df.sort_values(by="Full Name", ascending=True)
            elif sort_option == "Category":
                filtered_df = filtered_df.sort_values(by=["Category", "Full Name"], ascending=True)
            elif sort_option == "Date Sync":
                filtered_df = filtered_df.sort_values(by="Last_Sync_Date", ascending=False)

            display_cols = ['Category', 'Full Name', 'SKU', 'Stock', 'Price']
            actual_cols = [c for c in display_cols if c in filtered_df.columns]
            st.dataframe(filtered_df[actual_cols], use_container_width=True, hide_index=True)
        else:
            st.warning("Cloud is empty. Please Sync in sidebar.")

    # --- TAB 2: INTAKE ---
    intake_idx = 1 if user_role in ['Admin', 'Manager'] else None
    if intake_idx:
        with tabs[intake_idx]:
            st.subheader("➕ New Stock Shipment")
            with st.form("intake_form"):
                i_sku = st.text_input("Scan/Enter SKU").strip()
                i_qty = st.number_input("Quantity Received", min_value=1)
                if st.form_submit_button("Log Shipment"):
                    ship_payload = {"records": [{"fields": {"Date": datetime.now().isoformat(), "SKU": i_sku, "Quantity": i_qty, "User": username}}]}
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=ship_payload)
                    st.success("Shipment Logged!")

    # --- TAB 3: AUDIT ---
    audit_idx = 2 if user_role in ['Admin', 'Manager'] else 1
    with tabs[audit_idx]:
        st.subheader("🕵️ Physical Inventory Audit")
        a_sku = st.text_input("Scan SKU to Audit", key="aud_sku").strip()
        with st.form("audit_form_v3"):
            c1, c2 = st.columns(2)
            m_q = c1.number_input("Shelf", min_value=0)
            b_q = c2.number_input("Big Depot", min_value=0)
            e_q = c1.number_input("Exposed", min_value=0)
            r_q = c2.number_input("Returns", min_value=0)
            reason = st.selectbox("Reason", ["N/A", "Damaged", "Exchange", "Credit Refund"])
            
            if st.form_submit_button("Submit Audit"):
                total_phys = m_q + b_q + e_q + r_q
                sys_s = lib_data[lib_data['SKU'] == a_sku]['Stock'].iloc[0] if not lib_data.empty and a_sku in lib_data['SKU'].values else 0
                
                audit_payload = {"records": [{"fields": {
                    "Date": datetime.now().isoformat(), "SKU": a_sku, "Counter_Name": username,
                    "Manual_Qty": m_q, "Big_Depot_Qty": b_q, "Exposed_Qty": e_q, "Returns_Qty": r_q,
                    "Total_Physical": total_phys, "System_Stock": int(sys_s), "Discrepancy": int(total_phys - sys_s)
                }}]}
                requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json=audit_payload)
                
                if reason == "Damaged" and r_q > 0:
                    dmg_payload = {"records": [{"fields": {"Date": datetime.now().isoformat(), "SKU": a_sku, "Quantity": r_q, "Reason": "Damaged", "User": username}}]}
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Damaged_Stock", headers=HEADERS, json=dmg_payload)
                st.success(f"Audit Logged. Total: {total_phys}")

    # --- TAB 4: COMPARE ---
    if user_role == 'Admin':
        with tabs[3]:
            st.subheader("🔄 Comparison")
            f_haiti = st.file_uploader("Upload Haiti Export", type=['xlsx'], key="h_up")
            if f_haiti and not lib_data.empty:
                df_h = clean_data(f_haiti, "current quantity dressup haiti")
                comp = pd.merge(lib_data[['SKU', 'Full Name', 'Stock', 'Category']], df_h[['SKU', 'Stock']], on='SKU', suffixes=('_PV', '_Haiti'))
                st.dataframe(comp, use_container_width=True, hide_index=True)

    # --- TAB 5: ADMIN ---
    if user_role == 'Admin':
        with tabs[4]:
            st.subheader("🛡️ Admin")
            if st.button("📤 Backup to GitHub"):
                if not lib_data.empty:
                    csv_b = lib_data.to_csv(index=False)
                    b64 = base64.b64encode(csv_b.encode()).decode()
                    url = f"https://api.github.com/repos/{REPO_NAME}/contents/backups/erp_{date.today()}.csv"
                    gh_h = {"Authorization": f"token {st.secrets['GITHUB_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
                    res = requests.put(url, headers=gh_h, json={"message": f"Backup {date.today()}", "content": b64})
                    if res.status_code in [200, 201]: st.success("Backup Saved!")

    # --- TAB 6: PASSWORD ---
    with tabs[-1]:
        st.subheader("🔑 Password")
        try:
            if authenticator.reset_password(username, 'Update'):
                st.success('Password updated!')
        except Exception as e: st.error(e)

elif st.session_state["authentication_status"] is False:
    st.error('Incorrect Password')
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your login details.')
