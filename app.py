import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import date, datetime

# 1. Page Config
st.set_page_config(page_title="Dressupht Intelligence", layout="wide")

# --- USER AUTHENTICATION SETUP ---
config = {
    'credentials': {
        'usernames': {
            'kevin': {'name': 'Dressup Haiti Admin', 'password': 'The$100$Raven'},
            'staff1': {'name': 'Inventory Manager', 'password': 'secretpassword456'}
        }
    },
    'cookie': {'expiry_days': 30, 'key': 'inventory_signature_key', 'name': 'inventory_cookie'}
}

authenticator = stauth.Authenticate(config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days'])
login_data = authenticator.login()

if st.session_state["authentication_status"]:
    authenticator.logout('Logout', 'sidebar')
    st.sidebar.title(f"Welcome {st.session_state['name']}")

    # --- 2. AIRTABLE CONFIG ---
    AIR_TOKEN = "pat1SYxIQWWcgkwy5.35f38c5bdc516561cbacc01116d09eeac8e861f3c442af68fcf19ee58e9dc72a"
    BASE_ID = "app5eJFgtbCaJHGhc"
    HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}

    # Helper function for Airtable GET
    def get_at_data(table):
        try:
            url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
            params = {"sort[0][field]": "Date", "sort[0][direction]": "desc"}
            res = requests.get(url, headers=HEADERS, params=params)
            if res.status_code == 200:
                records = res.json().get('records', [])
                if not records: return pd.DataFrame()
                return pd.DataFrame([r['fields'] for r in records])
            return pd.DataFrame()
        except:
            return pd.DataFrame()

    def clean_data(file, location_col_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip().lower() for c in df.columns]
        needed = {'item name': 'Wig Name', 'variation name': 'Style', 'sku': 'SKU', 'price': 'Price', 'categories': 'Category', location_col_name.lower(): 'Stock'}
        existing = [c for c in list(df.columns) if c in needed.keys()]
        df = df[existing].copy()
        df.columns = [needed[c] for c in existing]
        if 'Category' not in df.columns: df['Category'] = 'Uncategorized'
        df['SKU'] = df['SKU'].astype(str).str.strip()
        df['Full Name'] = df['Wig Name'] + " (" + df['Style'].fillna('') + ")"
        df['Stock'] = pd.to_numeric(df['Stock'], errors='coerce').fillna(0)
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)
        return df

    # --- 3. SIDEBAR & DATA ---
    st.sidebar.subheader("📁 Data Upload Center")
    file_pv = st.sidebar.file_uploader("📍 THIS Saturday (PV)", type=['xlsx'])
    file_pv_prev = st.sidebar.file_uploader("🕒 LAST Saturday (PV)", type=['xlsx'])
    file_haiti = st.sidebar.file_uploader("🌐 Dressup Haiti", type=['xlsx'])

    df_pv = pd.DataFrame()
    sku_to_name = {}
    sku_to_stock = {}
    
    if file_pv:
        df_pv = clean_data(file_pv, "current quantity dressupht pv")
        sku_to_name = dict(zip(df_pv['SKU'], df_pv['Full Name']))
        sku_to_stock = dict(zip(df_pv['SKU'], df_pv['Stock']))
        # ... rest of your existing logic for Sold / Haiti Active ...
        if file_pv_prev:
            df_prev = clean_data(file_pv_prev, "current quantity dressupht pv")
            df_pv = pd.merge(df_pv, df_prev[['SKU', 'Stock']], on='SKU', how='left', suffixes=('', '_prev'))
            df_pv['Sold'] = (df_pv['Stock_prev'].fillna(0) - df_pv['Stock']).clip(lower=0)
        else: df_pv['Sold'] = 0
        haiti_active = bool(file_haiti)
        if file_haiti: df_haiti = clean_data(file_haiti, "current quantity dressup haiti")

    # --- 4. MAIN INTERFACE ---
    st.title("🦱 Dressupht Pv: Intelligence Center")
    search = st.text_input("🔍 Search Name or SKU")
    
    t1, t2, t3, t4, t5, t6, t7, t8, t9, t10 = st.tabs([
        "➕ Intake", "🕵️ Stock Audit", "🔄 Comparison", "🚚 Transfers", "🔥 Fast/Slow", "❌ OOS", "⚠️ Low Stock", "💰 Financials", "📋 Library", "📈 Analytics"
    ])

    # --- TAB 1: INTAKE (Same as before) ---
    with t1:
        st.subheader("Cloud Shipment Record")
        input_sku = st.text_input("Scan SKU for Intake").strip()
        det_name = sku_to_name.get(input_sku, "Unknown")
        with st.form("intake_form", clear_on_submit=True):
            d_in = st.date_input("Date", value=date.today(), key="in_date")
            q_in = st.number_input("Qty Received", min_value=1)
            if st.form_submit_button("Sync Intake"):
                payload = {"records": [{"fields": {"Date": str(d_in), "SKU": input_sku, "Name": det_name, "Quantity": q_in, "User": st.session_state['username']}}]}
                requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=payload)
                st.rerun()
        st.dataframe(get_at_data("Shipments"), use_container_width=True)

    # --- NEW TAB 2: STOCK AUDIT ---
    with t2:
        st.subheader("🕵️ Physical Inventory Audit")
        st.info("Use this to manually count what is on the shelf and compare it to the System.")
        
        audit_sku = st.text_input("Scan SKU for Counting").strip()
        system_qty = sku_to_stock.get(audit_sku, 0)
        audit_name = sku_to_name.get(audit_sku, "Unknown Item")
        
        if audit_sku:
            c1, c2 = st.columns(2)
            c1.metric("Wig Name", audit_name)
            c2.metric("System Qty (Excel)", int(system_qty))

        with st.form("audit_form", clear_on_submit=True):
            manual_qty = st.number_input("Manual Qty (Physical Count)", min_value=0, step=1)
            if st.form_submit_button("📥 Log Physical Count"):
                if audit_sku:
                    payload = {"records": [{"fields": {
                        "Date": str(date.today()),
                        "SKU": audit_sku,
                        "Name": audit_name,
                        "System_Qty": int(system_qty),
                        "Manual_Qty": int(manual_qty),
                        "User": st.session_state['username']
                    }}]}
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json=payload)
                    st.success("Audit Logged!")
                    st.rerun()
                else: st.error("Please enter a SKU.")
        
        st.divider()
        st.write("### Recent Audit History")
        audit_history = get_at_data("Inventory_Audit")
        if not audit_history.empty:
            # Calculate discrepancy for display
            audit_history['Diff'] = audit_history['Manual_Qty'] - audit_history['System_Qty']
            st.dataframe(audit_history[['Date', 'SKU', 'Name', 'System_Qty', 'Manual_Qty', 'Diff', 'User']], use_container_width=True)

    # ... [Rest of your previous tabs t3-t9 code stays here] ...
