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
            # Note: We use a larger page size or handle pagination if history gets very long
            res = requests.get(url, headers=HEADERS, params=params)
            if res.status_code == 200:
                records = res.json().get('records', [])
                if not records: return pd.DataFrame()
                df = pd.DataFrame([r['fields'] for r in records])
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

    # DATA PROCESSING
    df_pv = pd.DataFrame()
    sku_to_name = {}
    sku_to_stock = {}
    haiti_active = False

    if file_pv:
        df_pv = clean_data(file_pv, "current quantity dressupht pv")
        sku_to_name = dict(zip(df_pv['SKU'], df_pv['Full Name']))
        sku_to_stock = dict(zip(df_pv['SKU'], df_pv['Stock']))
        if file_pv_prev:
            df_prev = clean_data(file_pv_prev, "current quantity dressupht pv")
            df_pv = pd.merge(df_pv, df_prev[['SKU', 'Stock']], on='SKU', how='left', suffixes=('', '_prev'))
            df_pv['Sold'] = (df_pv['Stock_prev'].fillna(0) - df_pv['Stock']).clip(lower=0)
        else: df_pv['Sold'] = 0
        if file_haiti:
            df_haiti = clean_data(file_haiti, "current quantity dressup haiti")
            haiti_active = True

    # SEARCH
    st.title("🦱 Dressupht Pv: Intelligence Center")
    search = st.text_input("🔍 Search Name or SKU")
    def get_view(df_to_filter):
        if df_to_filter.empty: return df_to_filter
        if search: return df_to_filter[df_to_filter['Full Name'].astype(str).str.contains(search, case=False) | df_to_filter['SKU'].astype(str).str.contains(search, case=False)]
        return df_to_filter

    # --- 4. TABS ---
    tabs = st.tabs(["➕ Intake", "🕵️ Audit", "🔄 Compare", "🚚 Transfers", "🔥 Fast/Slow", "❌ OOS", "⚠️ Low", "💰 Finance", "📋 Library", "📈 Analytics"])
    
    with tabs[0]: # INTAKE
        st.subheader("Cloud Shipment Record")
        i_sku = st.text_input("Scan SKU for Intake", key="intake_scan").strip()
        det_n = sku_to_name.get(i_sku, "Unknown Item")
        if i_sku: st.success(f"Item: {det_n}")
        with st.form("in_form", clear_on_submit=True):
            d_i = st.date_input("Date", value=date.today())
            q_i = st.number_input("Qty Received", min_value=1)
            if st.form_submit_button("Sync Intake"):
                p = {"records": [{"fields": {"Date": str(d_i), "SKU": i_sku, "Name": det_n, "Quantity": q_i, "User": st.session_state['username']}}]}
                requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=p)
                st.rerun()
        st.dataframe(get_at_data("Shipments"), use_container_width=True)

    with tabs[1]: # AUDIT
        st.subheader("🕵️ Physical Inventory Audit")
        
        # Staff List for Inventory Day
        staff_members = ["Select Counter...", "Angelina", "Gerdine", "Annaelle", "David", "Kevin"]
        selected_staff = st.selectbox("Who is counting?", options=staff_members)
        
        a_sku = st.text_input("Scan SKU for Audit", key="audit_scan").strip()
        s_qty = sku_to_stock.get(a_sku, 0)
        a_name = sku_to_name.get(a_sku, "Unknown Item")
        
        if a_sku:
            c1, c2 = st.columns(2)
            c1.metric("Wig Name", a_name)
            c2.metric("System Qty", int(s_qty))
            
        with st.form("aud_form", clear_on_submit=True):
            m_qty = st.number_input("Manual Qty (On Shelf)", min_value=0, step=1)
            if st.form_submit_button("Log Audit"):
                if a_sku and selected_staff != "Select Counter...":
                    p = {"records": [{"fields": {
                        "Date": str(date.today()), 
                        "SKU": a_sku, 
                        "Name": a_name, 
                        "System_Qty": int(s_qty), 
                        "Manual_Qty": int(m_qty), 
                        "User": selected_staff
                    }}]}
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json=p)
                    st.success(f"Audit saved for {selected_staff}")
                    st.rerun()
                elif selected_staff == "Select Counter...":
                    st.error("Please select who did the count.")
                else:
                    st.error("Scan a SKU first.")
                    
        aud_hist = get_at_data("Inventory_Audit")
        if not aud_hist.empty:
            aud_hist['Diff'] = aud_hist['Manual_Qty'] - aud_hist['System_Qty']
            st.dataframe(aud_hist[['Date', 'SKU', 'Name', 'System_Qty', 'Manual_Qty', 'Diff', 'User']], use_container_width=True)

    if not df_pv.empty:
        with tabs[2]: # COMPARE
            if haiti_active:
                comp = pd.merge(df_haiti[['SKU', 'Stock']], df_pv, on='SKU', suffixes=('_haiti', '_pv')).drop_duplicates(subset=['SKU'])
                view = comp[((comp['Stock_haiti'] > 75) & (comp['Stock_pv'] <= 35)) | (comp['Stock_pv'] < 5)].copy()
                st.dataframe(get_view(view[['Full Name', 'SKU', 'Stock_pv', 'Stock_haiti']]), use_container_width=True)
        with tabs[3]: # TRANSFERS
            if haiti_active:
                def req(r):
                    if r['Stock_pv'] == 0 and r['Stock_haiti'] > 20: return 10
                    if r['Sold'] >= 10 and r['Stock_pv'] <= 20 and r['Stock_haiti'] > 20: return 25
                    return 0
                comp['Request'] = comp.apply(req, axis=1)
                st.dataframe(get_view(comp[comp['Request'] > 0][['Full Name', 'SKU', 'Stock_haiti', 'Stock_pv', 'Sold', 'Request']]), use_container_width=True)
        with tabs[4]: # FAST/SLOW
            cw1, cw2 = st.columns(2)
            cw1.write("Top 10 Sellers")
            cw1.table(df_pv.nlargest(10, 'Sold')[['Full Name', 'Sold']])
            cw2.write("Bottom 10 (Dead Stock)")
            cw2.table(df_pv[df_pv['Stock'] > 0].nsmallest(10, 'Sold')[['Full Name', 'Sold']])
        with tabs[5]: st.dataframe(get_view(df_pv[df_pv['Stock'] == 0]), use_container_width=True) # OOS
        with tabs[6]: st.dataframe(get_view(df_pv[(df_pv['Stock'] > 0) & (df_pv['Stock'] <= 5)]), use_container_width=True) # LOW
        with tabs[7]: # FINANCIALS
            df_pv['Value'] = df_pv['Stock'] * df_pv['Price']
            st.dataframe(get_view(df_pv[['Full Name', 'SKU', 'Stock', 'Price', 'Value']].sort_values('Value', ascending=False)), use_container_width=True)
        with tabs[8]: st.dataframe(get_view(df_pv), use_container_width=True) # LIBRARY
        with tabs[9]: # ANALYTICS
            st.subheader("📈 Shipment Velocity")
            at_df = get_at_data("Shipments")
            if not at_df.empty:
                sel_s = st.selectbox("Pick SKU to view history", at_df['SKU'].unique())
                sh = at_df[at_df['SKU'] == sel_s]
                st.metric("Total Units Received", int(sh['Quantity'].sum()))
                st.table(sh[['Date', 'Quantity', 'User']])
    else: st.info("Upload PV file in sidebar to see full performance data.")
