import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import base64

# --- CONFIG & INITIALIZATION ---
st.set_page_config(page_title="Dressupht ERP v2.5", layout="wide")

# ⚠️ UPDATE THIS TO YOUR REPO (Format: "username/repo-name")
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

    # API KEYS
    try:
        AIR_TOKEN = st.secrets["AIRTABLE_TOKEN"]
        BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
        HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}
    except:
        st.error("Missing Secrets!")
        st.stop()

    # --- HELPER FUNCTIONS ---
    def get_at_data(table, params=None):
        url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
        res = requests.get(url, headers=HEADERS, params=params)
        if res.status_code == 200:
            recs = res.json().get('records', [])
            if not recs: return pd.DataFrame()
            return pd.DataFrame([dict(r['fields'], id=r['id']) for r in recs])
        return pd.DataFrame()

    def get_user_role(user):
        df = get_at_data("Role", {"filterByFormula": f"{{User Name}}='{user}'"})
        return df['Access Level'].iloc[0] if not df.empty else 'Staff'

    def delete_at_records(table, df):
        if df.empty: return
        ids = df['id'].tolist()
        st.info(f"Clearing {len(ids)} old records to prevent duplicates...")
        for i in range(0, len(ids), 10):
            batch = ids[i:i+10]
            query = "&".join([f"records[]={rid}" for rid in batch])
            requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/{table}?{query}", headers=HEADERS)
            time.sleep(0.2) # Avoid Rate Limit

    def clean_data(file, loc_col_name="current quantity dressupht pv"):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip().lower() for c in df.columns]
        mapping = {'item name': 'Wig Name', 'variation name': 'Style', 'sku': 'SKU', 'price': 'Price'}
        df = df.rename(columns=mapping)
        df['SKU'] = df['SKU'].astype(str).str.strip().replace('nan', 'NO_SKU')
        df['Full Name'] = df['Wig Name'].astype(str) + " (" + df['Style'].astype(str).replace('nan', '') + ")"
        
        if loc_col_name in df.columns:
            df['Stock'] = pd.to_numeric(df[loc_col_name], errors='coerce').fillna(0).astype(int)
        else:
            stock_cols = [c for c in df.columns if 'quantity' in c]
            df['Stock'] = pd.to_numeric(df[stock_cols[0]], errors='coerce').fillna(0).astype(int) if stock_cols else 0
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0.0)
        return df

    user_role = get_user_role(username)
    # Admin Override for Setup
    if username == "Kevin": user_role = "Admin"
    st.sidebar.info(f"User: {username} | Role: {user_role}")

    # --- DYNAMIC TABS ---
    if user_role == 'Admin':
        tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔄 Compare", "📊 Sales", "🛡️ Admin", "🔑 Password"])
    elif user_role == 'Manager':
        tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔑 Password"])
    else:
        tabs = st.tabs(["📋 Library", "🔑 Password"])

    # --- SIDEBAR: SYNC (Wipe & Upload) ---
    if user_role == 'Admin':
        st.sidebar.divider()
        f_pv = st.sidebar.file_uploader("Upload PV Square Export", type=['xlsx'])
        sync_date = st.sidebar.date_input("Sync Date", date.today())
        
        if f_pv and st.sidebar.button("🚀 Wipe & Sync to Cloud"):
            df_new = clean_data(f_pv)
            # 1. Clear Old Data
            existing_df = get_at_data("Master_Inventory")
            delete_at_records("Master_Inventory", existing_df)
            
            # 2. Upload 400+ Rows in Batches
            total = len(df_new)
            bar = st.sidebar.progress(0)
            with st.spinner(f"Syncing {total} items..."):
                for i in range(0, total, 10):
                    batch = df_new.iloc[i:i+10]
                    recs = [{"fields": {
                        "SKU": str(r['SKU']), "Full Name": str(r['Full Name']), 
                        "Stock": int(r['Stock']), "Price": float(r['Price']), 
                        "Last_Sync_Date": str(sync_date)
                    }} for _, r in batch.iterrows()]
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs})
                    bar.progress(min((i + 10) / total, 1.0))
                    time.sleep(0.2)
            st.sidebar.success("Cloud Updated!")
            st.rerun()

    # --- TAB 1: LIBRARY ---
    with tabs[0]:
        st.subheader("📦 Master Inventory")
        lib_data = get_at_data("Master_Inventory")
        search = st.text_input("🔍 Search Name or SKU")
        if not lib_data.empty:
            if search: lib_data = lib_data[lib_data['Full Name'].str.contains(search, case=False) | lib_data['SKU'].str.contains(search)]
            st.dataframe(lib_data[['Full Name', 'SKU', 'Stock', 'Price', 'Last_Sync_Date']], use_container_width=True, hide_index=True)
        else: st.warning("Cloud is empty. Please Sync data in the sidebar.")

    # --- TAB: AUDIT (BIG DEPOT + DAMAGED) ---
    audit_tab_idx = 2 if user_role == 'Admin' else (2 if user_role == 'Manager' else None)
    if audit_tab_idx:
        with tabs[audit_tab_idx]:
            st.subheader("🕵️ Physical Inventory Audit")
            a_sku = st.text_input("Scan SKU to Audit", key="aud_sku").strip()
            with st.form("audit_v2_5"):
                c1, c2 = st.columns(2)
                m_q = c1.number_input("Shelf (Max 50)", min_value=0)
                b_q = c2.number_input("Big Depot Storage", min_value=0)
                e_q = c1.number_input("Exposed", min_value=0)
                r_q = c2.number_input("Returns", min_value=0)
                reason = st.selectbox("Reason for returns", ["N/A", "Damaged", "Exchange", "Credit Refund"])
                
                if st.form_submit_button("Submit Audit"):
                    total_phys = m_q + b_q + e_q + r_q
                    # Get system stock for discrepancy
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
                    st.success(f"Audit Logged. Discrepancy: {int(total_phys - sys_s)}")

    # --- TAB: COMPARE (HAITI VS PV) ---
    if user_role == 'Admin':
        with tabs[3]:
            st.subheader("🔄 Stock Comparison: Haiti vs. PV")
            f_haiti = st.file_uploader("Upload Haiti Export", type=['xlsx'], key="h_up")
            if f_haiti and not lib_data.empty:
                df_h = clean_data(f_haiti, "current quantity dressup haiti")
                comp = pd.merge(lib_data[['SKU', 'Full Name', 'Stock']], df_h[['SKU', 'Stock']], on='SKU', suffixes=('_PV', '_Haiti'))
                st.dataframe(comp, use_container_width=True, hide_index=True)

    # --- TAB: ADMIN (BACKUP) ---
    if user_role == 'Admin':
        with tabs[5]:
            st.subheader("🛡️ Admin Panel")
            if st.button("📤 GitHub Backup"):
                csv_b = lib_data.to_csv(index=False)
                b64 = base64.b64encode(csv_b.encode()).decode()
                url = f"https://api.github.com/repos/{REPO_NAME}/contents/backups/erp_{date.today()}.csv"
                gh_h = {"Authorization": f"token {st.secrets['GITHUB_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
                res = requests.put(url, headers=gh_h, json={"message": f"Backup {date.today()}", "content": b64})
                if res.status_code in [200, 201]: st.success("Backup Saved to GitHub!")

    # --- PASSWORD RESET ---
    with tabs[-1]:
        st.subheader("🔑 Change Password")
        try:
            if authenticator.reset_password(username, 'Update'):
                st.success('Password updated successfully!')
        except Exception as e: st.error(e)

elif st.session_state["authentication_status"] is False:
    st.error('Incorrect Password')
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your login details.')
