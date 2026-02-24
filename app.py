import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import date, datetime
import io

# 1. Page Config
st.set_page_config(page_title="Dressupht Intelligence", layout="wide")

# --- USER AUTHENTICATION (Keep your existing config) ---
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

    def get_at_data(table):
        try:
            url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
            params = {"sort[0][field]": "Date", "sort[0][direction]": "desc"}
            res = requests.get(url, headers=HEADERS, params=params)
            if res.status_code == 200:
                records = res.json().get('records', [])
                if not records: return pd.DataFrame()
                df = pd.DataFrame([r['fields'] for r in records])
                if 'Date' in df.columns: df['Date'] = pd.to_datetime(df['Date']).dt.date
                return df
            return pd.DataFrame()
        except: return pd.DataFrame()

    # --- 3. UPDATED DATA CLEANER FOR YOUR FILES ---
    def process_inventaire_file(uploaded_file):
        """Processes the 'INVENTAIRE NORMAL' style files you uploaded."""
        # Use sheet name or file name as category
        cat_label = uploaded_file.name.split('-')[-1].replace('.xlsx', '').replace('.csv', '').strip()
        
        # Read the file, skipping the first title row
        df = pd.read_csv(uploaded_file, skiprows=1) 
        
        # Standardize columns
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        if 'POUCES' in df.columns and 'TEXTURES' in df.columns:
            # Drop empty rows where Pouces/Textures are missing
            df = df.dropna(subset=['POUCES', 'TEXTURES'])
            
            # Build the "Full Name" and "SKU" (Since these files don't have unique IDs, we create one)
            df['Full Name'] = df['POUCES'].astype(str) + " " + df['TEXTURES'].astype(str)
            df['SKU'] = (cat_label + "-" + df['Full Name']).str.replace('"', '').str.replace(' ', '')
            df['Category'] = cat_label
            
            # Use 'TOTAL' or 'SYSTEME' as the stock count
            df['Stock'] = pd.to_numeric(df['TOTAL'], errors='coerce').fillna(0)
            df['Price'] = 0 # These files don't have prices, set to 0
            
            return df[['Full Name', 'SKU', 'Category', 'Stock', 'Price']]
        return pd.DataFrame()

    # --- 4. SIDEBAR UPLOADS ---
    st.sidebar.subheader("📁 Data Upload Center")
    # Accept multiple files now to handle your different sheets
    uploaded_inventaire = st.sidebar.file_uploader("📂 Upload ALL Inventaire Sheets", type=['csv', 'xlsx'], accept_multiple_files=True)
    file_haiti = st.sidebar.file_uploader("🌐 Dressup Haiti (Square Export)", type=['xlsx'])

    # DATA PROCESSING
    df_pv = pd.DataFrame()
    sku_to_name = {}
    sku_to_stock = {}
    sku_to_cat = {}
    haiti_active = False

    if uploaded_inventaire:
        list_dfs = []
        for f in uploaded_inventaire:
            processed = process_inventaire_file(f)
            if not processed.empty:
                list_dfs.append(processed)
        
        if list_dfs:
            df_pv = pd.concat(list_dfs).drop_duplicates(subset=['SKU'])
            sku_to_name = dict(zip(df_pv['SKU'], df_pv['Full Name']))
            sku_to_stock = dict(zip(df_pv['SKU'], df_pv['Stock']))
            sku_to_cat = dict(zip(df_pv['SKU'], df_pv['Category']))
            df_pv['Sold'] = 0 # Placeholder since we aren't comparing to 'Last Saturday' yet

    # --- 5. TABS ---
    st.title("🦱 Dressupht Pv: Intelligence Center")
    search = st.text_input("🔍 Search Name, SKU, or Category (e.g. 'Pixie')")
    
    def get_view(df_to_filter):
        if df_to_filter.empty: return df_to_filter
        if search: 
            return df_to_filter[
                df_to_filter['Full Name'].astype(str).str.contains(search, case=False) | 
                df_to_filter['SKU'].astype(str).str.contains(search, case=False) |
                df_to_filter['Category'].astype(str).str.contains(search, case=False)
            ]
        return df_to_filter

    tabs = st.tabs(["🕵️ Audit", "📋 Library", "➕ Intake", "🔥 Analytics", "💰 Finance"])

    with tabs[0]: # AUDIT
        st.subheader("🕵️ Physical Inventory Audit")
        
        col_a, col_b = st.columns([1, 2])
        
        with col_a:
            staff_members = ["Select Counter...", "Angelina", "Gerdine", "Annaelle", "David", "Kevin"]
            selected_staff = st.selectbox("Who is counting?", options=staff_members)
            a_sku = st.text_input("Scan SKU for Audit", key="audit_scan").strip()
            
            s_qty = sku_to_stock.get(a_sku, 0)
            a_name = sku_to_name.get(a_sku, "Unknown Item")
            a_cat = sku_to_cat.get(a_sku, "General")

            if a_sku:
                st.metric("Item", a_name)
                st.info(f"Category: {a_cat} | System Qty: {int(s_qty)}")
            
            with st.form("aud_form", clear_on_submit=True):
                m_qty = st.number_input("Manual Qty (On Shelf)", min_value=0, step=1)
                if st.form_submit_button("Log Audit"):
                    if a_sku and selected_staff != "Select Counter...":
                        p = {"records": [{"fields": {
                            "Date": str(date.today()), 
                            "SKU": a_sku, 
                            "Name": a_name, 
                            "Category": a_cat,
                            "System_Qty": int(s_qty), 
                            "Manual_Qty": int(m_qty), 
                            "User": selected_staff
                        }}]}
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json=p)
                        st.success(f"Saved: {a_name}")
                        st.rerun()

        with col_b:
            st.write("### Recent Logs")
            aud_hist = get_at_data("Inventory_Audit")
            if not aud_hist.empty:
                aud_hist['Diff'] = aud_hist['Manual_Qty'] - aud_hist['System_Qty']
                
                # Category Grouping View
                st.write("#### Grouped by Category Today")
                summary = aud_hist[aud_hist['Date'] == date.today()].groupby('Category').agg({'Manual_Qty':'sum', 'SKU':'count'})
                st.dataframe(summary, use_container_width=True)
                
                st.write("#### Detailed History")
                st.dataframe(aud_hist[['Date', 'Category', 'Name', 'Manual_Qty', 'Diff', 'User']], use_container_width=True)

    with tabs[1]: # LIBRARY
        st.subheader("📦 Master Inventory List")
        if not df_pv.empty:
            st.dataframe(get_view(df_pv), use_container_width=True)
        else:
            st.info("Upload your Excel sheets in the sidebar to populate the library.")

    # (Intake, Finance tabs remain largely the same, using df_pv)
