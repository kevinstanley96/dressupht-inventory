import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import date, datetime

# 1. Page Config - FORCE WIDE MODE
st.set_page_config(page_title="Dressupht Intelligence", layout="wide")

# --- USER AUTHENTICATION ---
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
                data = res.json().get('records', [])
                if not data: return pd.DataFrame()
                df = pd.DataFrame([dict(r['fields'], id=r['id']) for r in data])
                if 'Date' in df.columns: df['Date'] = pd.to_datetime(df['Date']).dt.date
                return df
            return pd.DataFrame()
        except: return pd.DataFrame()

    def clean_data(file, loc_col):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip().lower() for c in df.columns]
        needed = {'item name': 'Wig Name', 'variation name': 'Style', 'sku': 'SKU', 'price': 'Price', 'categories': 'Category', loc_col.lower(): 'Stock'}
        existing = [c for c in list(df.columns) if c in needed.keys()]
        df = df[existing].copy()
        df.columns = [needed[c] for c in existing]
        
        if 'Category' not in df.columns:
            df['Category'] = "Uncategorized"
        else:
            df['Category'] = df['Category'].fillna("Uncategorized")
            
        df['SKU'] = df['SKU'].astype(str).str.strip()
        df['Full Name'] = df['Wig Name'] + " (" + df['Style'].fillna('') + ")"
        df['Stock'] = pd.to_numeric(df['Stock'], errors='coerce').fillna(0)
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)
        return df

    # --- 3. SIDEBAR UPLOADS ---
    st.sidebar.subheader("📁 Data Upload Center")
    file_pv = st.sidebar.file_uploader("📍 THIS Saturday (PV)", type=['xlsx'])
    file_pv_prev = st.sidebar.file_uploader("🕒 LAST Saturday (PV)", type=['xlsx'])
    file_haiti = st.sidebar.file_uploader("🌐 Dressup Haiti", type=['xlsx'])

    df_pv = pd.DataFrame()
    sku_to_name = {}
    sku_to_stock = {}
    sku_to_cat = {} 

    if file_pv:
        df_pv = clean_data(file_pv, "current quantity dressupht pv")
        sku_to_name = dict(zip(df_pv['SKU'], df_pv['Full Name']))
        sku_to_stock = dict(zip(df_pv['SKU'], df_pv['Stock']))
        sku_to_cat = dict(zip(df_pv['SKU'], df_pv['Category'])) 
        
        if file_pv_prev:
            df_prev = clean_data(file_pv_prev, "current quantity dressupht pv")
            df_pv = pd.merge(df_pv, df_prev[['SKU', 'Stock']], on='SKU', how='left', suffixes=('', '_prev'))
            df_pv['Sold'] = (df_pv['Stock_prev'].fillna(0) - df_pv['Stock']).clip(lower=0)
        else: df_pv['Sold'] = 0
        haiti_active = False
        if file_haiti:
            df_haiti = clean_data(file_haiti, "current quantity dressup haiti")
            haiti_active = True

    st.title("🦱 Dressupht Pv: Intelligence Center")
    search = st.text_input("🔍 Search Name or SKU")
    def get_view(df_to_filter):
        if df_to_filter.empty: return df_to_filter
        if search: return df_to_filter[df_to_filter['Full Name'].astype(str).str.contains(search, case=False) | df_to_filter['SKU'].astype(str).str.contains(search, case=False)]
        return df_to_filter

    # --- 4. TABS ---
    tabs = st.tabs(["➕ Intake", "🕵️ Audit", "🔄 Compare", "🚚 Transfers", "🔥 Fast/Slow", "❌ OOS", "⚠️ Low", "💰 Finance", "📋 Library", "📈 Analytics"])
    
    with tabs[1]: # AUDIT
        st.subheader("🕵️ Physical Inventory Audit")
        
        staff_members = ["Select Counter...", "Angelina", "Gerdine", "Annaelle", "David", "Kevin"]
        selected_staff = st.selectbox("Who is counting?", options=staff_members)
        
        a_sku = st.text_input("Scan SKU for Audit", key="audit_scan").strip()
        s_qty = sku_to_stock.get(a_sku, 0)
        a_name = sku_to_name.get(a_sku, "Unknown Item")
        a_cat = sku_to_cat.get(a_sku, "Uncategorized") 
        
        if a_sku:
            c1, c2, c3 = st.columns(3)
            c1.metric("Wig Name", a_name)
            c2.metric("Category", a_cat)
            c3.metric("System Qty", int(s_qty))
            
        with st.form("aud_form", clear_on_submit=True):
            col_m1, col_m2, col_m3 = st.columns(3)
            m_qty = col_m1.number_input("Depot Qty", min_value=0, step=1)
            e_qty = col_m2.number_input("Mannequin Qty", min_value=0, step=1)
            r_qty = col_m3.number_input("Returns (Not in System)", min_value=0, step=1)
            
            total_physical = m_qty + e_qty + r_qty
            diff_value = int(total_physical - s_qty)
            
            st.info(f"Total Physical Count: **{total_physical}** | Difference: **{diff_value}**")

            if st.form_submit_button("Log Audit"):
                if a_sku and selected_staff != "Select Counter...":
                    existing_data = get_at_data("Inventory_Audit")
                    match_id = None
                    if not existing_data.empty:
                        match = existing_data[(existing_data['SKU'] == a_sku) & (existing_data['Date'] == date.today())]
                        if not match.empty:
                            match_id = match.iloc[0]['id']

                    fields = {
                        "Date": str(date.today()), 
                        "SKU": a_sku, 
                        "Name": a_name, 
                        "Category": a_cat,
                        "System_Qty": int(s_qty), 
                        "Manual_Qty": int(m_qty),
                        "Mannequin": int(e_qty),
                        "Returns": int(r_qty),
                        "Diff": diff_value,
                        "User": selected_staff
                    }

                    if match_id:
                        requests.patch(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit/{match_id}", headers=HEADERS, json={"fields": fields})
                        st.success(f"Updated existing entry for {a_sku}")
                    else:
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json={"records": [{"fields": fields}]})
                        st.success(f"Audit saved for {selected_staff}")
                    st.rerun()
                else:
                    st.error("Select staff and scan SKU.")
                        
        aud_hist = get_at_data("Inventory_Audit")
        if not aud_hist.empty:
            # FIX FOR AttributeError & Missing Columns
            for col in ['Mannequin', 'Manual_Qty', 'Returns', 'System_Qty']:
                if col not in aud_hist.columns:
                    aud_hist[col] = 0
                else:
                    aud_hist[col] = pd.to_numeric(aud_hist[col], errors='coerce').fillna(0)

            aud_hist['Diff'] = (aud_hist['Manual_Qty'] + aud_hist['Mannequin'] + aud_hist['Returns']) - aud_hist['System_Qty']
            
            st.write("#### Detailed History")
            display_cols = ['Date', 'Category', 'SKU', 'Name', 'System_Qty', 'Manual_Qty', 'Mannequin', 'Returns', 'Diff', 'User']
            existing_cols = [c for c in display_cols if c in aud_hist.columns]
            st.dataframe(aud_hist[existing_cols], use_container_width=True)

    # --- REMAINING TABS (Simplified for this version) ---
    if not df_pv.empty:
        with tabs[8]: st.dataframe(get_view(df_pv), use_container_width=True)
    else:
        st.info("Please upload data files to enable comparison and library views.")
