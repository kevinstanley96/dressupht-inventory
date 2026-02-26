import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import base64

# --- CONFIG & INITIALIZATION ---
st.set_page_config(page_title="Dressupht ERP v2.2", layout="wide")

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
            return pd.DataFrame([dict(r['fields'], id=r['id']) for r in recs])
        return pd.DataFrame()

    def get_user_role(user):
        df = get_at_data("Role", {"filterByFormula": f"{{User Name}}='{user}'"})
        return df['Access Level'].iloc[0] if not df.empty else 'Staff'

    def clean_data(file, loc_col_name="current quantity dressupht pv"):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip().lower() for c in df.columns]
        mapping = {'item name': 'Wig Name', 'variation name': 'Style', 'sku': 'SKU', 'price': 'Price'}
        df = df.rename(columns=mapping)
        df['SKU'] = df['SKU'].astype(str).str.strip()
        df['Full Name'] = df['Wig Name'] + " (" + df['Style'].fillna('') + ")"
        if loc_col_name in df.columns:
            df['Stock'] = pd.to_numeric(df[loc_col_name], errors='coerce').fillna(0)
        else:
            # Fallback for Haiti file or others
            possible_stock_cols = [c for c in df.columns if 'quantity' in c]
            if possible_stock_cols:
                df['Stock'] = pd.to_numeric(df[possible_stock_cols[0]], errors='coerce').fillna(0)
        return df

    user_role = get_user_role(username)
    st.sidebar.info(f"User: {username} | Role: {user_role}")

    # --- DYNAMIC TABS ---
    if user_role == 'Admin':
        tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔄 Compare", "📊 Sales", "💰 Finance", "🛡️ Admin", "🔑 Password"])
    elif user_role == 'Manager':
        tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔑 Password"])
    else:
        tabs = st.tabs(["📋 Library", "🔑 Password"])

    # --- SIDEBAR: DATA SYNC (Admin Only) ---
    if user_role == 'Admin':
        st.sidebar.divider()
        st.sidebar.subheader("☁️ Sync Square Data")
        f_pv = st.sidebar.file_uploader("Upload PV Square Export", type=['xlsx'])
        sync_date = st.sidebar.date_input("Sync Date", date.today())
        if f_pv and st.sidebar.button("🚀 Sync to Cloud"):
            df_new = clean_data(f_pv)
            with st.spinner("Updating Master Inventory..."):
                for i in range(0, len(df_new), 10):
                    batch = df_new.iloc[i:i+10]
                    recs = [{"fields": {"SKU": str(r['SKU']), "Full Name": str(r['Full Name']), "Stock": int(r['Stock']), "Price": float(r['Price']), "Last_Sync_Date": str(sync_date)}} for _, r in batch.iterrows()]
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs})
            st.sidebar.success("Database Updated!")

    # --- TAB 1: LIBRARY ---
    with tabs[0]:
        st.subheader("📦 Master Inventory")
        lib_data = get_at_data("Master_Inventory")
        search = st.text_input("🔍 Search Name or SKU")
        if not lib_data.empty:
            if search: lib_data = lib_data[lib_data['Full Name'].str.contains(search, case=False) | lib_data['SKU'].str.contains(search)]
            st.dataframe(lib_data[['Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 2: INTAKE ---
    if user_role in ['Admin', 'Manager']:
        with tabs[1]:
            st.subheader("➕ New Stock Shipment")
            with st.form("intake_form"):
                i_sku = st.text_input("Scan/Enter SKU").strip()
                i_qty = st.number_input("Quantity Received", min_value=1)
                if st.form_submit_button("Log Shipment"):
                    ship_payload = {"records": [{"fields": {"Date": datetime.now().isoformat(), "SKU": i_sku, "Quantity": i_qty, "User": username}}]}
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=ship_payload)
                    st.success("Shipment Logged!")

    # --- TAB 3: AUDIT ---
    if user_role in ['Admin', 'Manager']:
        with tabs[2]:
            st.subheader("🕵️ Physical Inventory Audit")
            a_sku = st.text_input("Scan SKU to Audit", key="aud_sku").strip()
            if a_sku and not lib_data.empty:
                match = lib_data[lib_data['SKU'] == a_sku]
                if not match.empty: st.success(f"Wig Identified: {match.iloc[0]['Full Name']}")

            with st.form("audit_v2_2"):
                c1, c2 = st.columns(2)
                m_q = c1.number_input("Shelf/Box (Max 50)", min_value=0)
                b_q = c2.number_input("Big Depot Storage", min_value=0)
                e_q = c1.number_input("Exposed (Outside)", min_value=0)
                r_q = c2.number_input("Returns", min_value=0)
                reason = st.selectbox("Return Reason", ["N/A", "Damaged", "Exchange", "Credit Refund"])
                
                if st.form_submit_button("Submit Audit"):
                    total = m_q + b_q + e_q + r_q
                    sys_s = lib_data[lib_data['SKU'] == a_sku]['Stock'].iloc[0] if a_sku in lib_data['SKU'].values else 0
                    
                    audit_fields = {
                        "Date": datetime.now().isoformat(), "SKU": a_sku, "Counter_Name": username,
                        "Manual_Qty": m_q, "Big_Depot_Qty": b_q, "Exposed_Qty": e_q, "Returns_Qty": r_q,
                        "Total_Physical": total, "System_Stock": int(sys_s), "Discrepancy": int(total-sys_s)
                    }
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json={"records": [{"fields": audit_fields}]})
                    
                    if reason == "Damaged" and r_q > 0:
                        dmg_fields = {"Date": datetime.now().isoformat(), "SKU": a_sku, "Quantity": r_q, "Reason": "Damaged", "User": username}
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Damaged_Stock", headers=HEADERS, json={"records": [{"fields": dmg_fields}]})
                    st.success(f"Log Saved! Discrepancy: {int(total-sys_s)}")

    # --- TAB 4: COMPARE (RESTORED) ---
    if user_role == 'Admin':
        with tabs[3]:
            st.subheader("🔄 Haiti vs. PV Comparison")
            f_haiti = st.file_uploader("Upload Dressup Haiti Export", type=['xlsx'])
            if f_haiti and not lib_data.empty:
                df_h = clean_data(f_haiti, "current quantity dressup haiti")
                comp = pd.merge(lib_data[['SKU', 'Full Name', 'Stock']], df_h[['SKU', 'Stock']], on='SKU', suffixes=('_PV', '_Haiti'))
                comp['Transfer_Note'] = comp.apply(lambda x: "🚀 Send to PV" if (x['Stock_Haiti'] > 2 and x['Stock_PV'] <= 1) else "OK", axis=1)
                st.dataframe(comp, use_container_width=True, hide_index=True)

    # --- TAB 7: ADMIN ---
    if user_role == 'Admin':
        with tabs[6]:
            st.subheader("🛡️ Roles & Backups")
            roles_df = get_at_data("Role")
            if not roles_df.empty:
                st.write("### Manage User Access")
                st.dataframe(roles_df[['User Name', 'Access Level']], hide_index=True)
                with st.expander("Change Role"):
                    u_target = st.selectbox("User", roles_df['User Name'])
                    u_role = st.selectbox("New Level", ["Admin", "Manager", "Staff"])
                    if st.button("Apply"):
                        rid = roles_df[roles_df['User Name'] == u_target]['id'].iloc[0]
                        requests.patch(f"https://api.airtable.com/v0/{BASE_ID}/Role", headers=HEADERS, json={"records": [{"id": rid, "fields": {"Access Level": u_role}}]})
                        st.rerun()
            
            st.divider()
            if st.button("📤 Backup to GitHub"):
                csv_b = lib_data.to_csv(index=False)
                b64 = base64.b64encode(csv_b.encode()).decode()
                url = f"https://api.github.com/repos/{REPO_NAME}/contents/backups/erp_backup_{date.today()}.csv"
                gh_h = {"Authorization": f"token {st.secrets['GITHUB_TOKEN']}", "Accept": "application/vnd.github.v3+json"}
                res = requests.put(url, headers=gh_h, json={"message": f"Backup {date.today()}", "content": b64})
                if res.status_code in [200, 201]: st.success("Cloud Data Backed up to GitHub!")

    # --- TAB 8: PASSWORD ---
    with tabs[-1]:
        st.subheader("🔑 Change Password")
        try:
            if authenticator.reset_password(username, 'Update'):
                st.success('Password updated!')
        except Exception as e: st.error(e)

elif st.session_state["authentication_status"] is False:
    st.error('Incorrect Password')
elif st.session_state["authentication_status"] is None:
    st.warning('Enter login credentials')
