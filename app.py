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
    TABLE_NAME = "Shipments"
    AIRTABLE_URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}

    def get_airtable_data():
        try:
            params = {"sort[0][field]": "Date", "sort[0][direction]": "desc"}
            response = requests.get(AIRTABLE_URL, headers=HEADERS, params=params)
            if response.status_code == 200:
                records = response.json().get('records', [])
                if not records: return pd.DataFrame(columns=["Date", "SKU", "Name", "Quantity", "User"])
                df = pd.DataFrame([r['fields'] for r in records])
                df['Date'] = pd.to_datetime(df['Date']).dt.date
                return df
            return pd.DataFrame(columns=["Date", "SKU", "Name", "Quantity", "User"])
        except:
            return pd.DataFrame(columns=["Date", "SKU", "Name", "Quantity", "User"])

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
    airtable_df = get_airtable_data()
    haiti_active = False

    if file_pv:
        df_pv = clean_data(file_pv, "current quantity dressupht pv")
        sku_to_name = dict(zip(df_pv['SKU'], df_pv['Full Name']))
        if file_pv_prev:
            df_prev = clean_data(file_pv_prev, "current quantity dressupht pv")
            df_pv = pd.merge(df_pv, df_prev[['SKU', 'Stock']], on='SKU', how='left', suffixes=('', '_prev'))
            df_pv['Sold'] = (df_pv['Stock_prev'].fillna(0) - df_pv['Stock']).clip(lower=0)
        else:
            df_pv['Sold'] = 0
        if file_haiti:
            df_haiti = clean_data(file_haiti, "current quantity dressup haiti")
            haiti_active = True

    # --- 4. MAIN INTERFACE ---
    st.title("🦱 Dressupht Pv: Intelligence Center")
    search = st.text_input("🔍 Search Name or SKU")
    
    def get_view(df_to_filter):
        if df_to_filter.empty: return df_to_filter
        if search:
            return df_to_filter[df_to_filter['Full Name'].astype(str).str.contains(search, case=False) | 
                                df_to_filter['SKU'].astype(str).str.contains(search, case=False)]
        return df_to_filter

    t1, t2, t3, t4, t5, t6, t7, t8, t9 = st.tabs([
        "➕ Intake", "🔄 Comparison", "🚚 Transfers", "🔥 Fast/Slow", "❌ OOS", "⚠️ Low Stock", "💰 Financials", "📋 Library", "📈 Logistics Insights"
    ])

    # TAB 1: INTAKE
    with t1:
        st.subheader("Cloud Shipment Record")
        input_sku = st.text_input("Scan/Enter SKU").strip()
        det_name = sku_to_name.get(input_sku, "New Item/Unknown")
        if input_sku: st.success(f"Item: {det_name}")
        with st.form("intake", clear_on_submit=True):
            d_in = st.date_input("Date", value=date.today())
            q_in = st.number_input("Qty", min_value=1)
            if st.form_submit_button("Sync to Cloud"):
                payload = {"records": [{"fields": {"Date": str(d_in), "SKU": input_sku, "Name": det_name, "Quantity": q_in, "User": st.session_state['username']}}]}
                requests.post(AIRTABLE_URL, headers=HEADERS, json=payload)
                st.rerun()
        st.dataframe(airtable_df, use_container_width=True)

    # RESTORED TABS 2-8
    if not df_pv.empty:
        with t2:
            if haiti_active:
                compare_all = pd.merge(df_haiti[['SKU', 'Stock']], df_pv, on='SKU', suffixes=('_haiti', '_pv')).drop_duplicates(subset=['SKU'])
                comparison_view = compare_all[((compare_all['Stock_haiti'] > 75) & (compare_all['Stock_pv'] <= 35)) | (compare_all['Stock_pv'] < 5)].copy()
                def color_comparison(row):
                    if row['Stock_pv'] < 5 and row['Stock_haiti'] > 25: return ['background-color: #2ecc71; color: white']*len(row)
                    if row['Stock_pv'] < 5 and row['Stock_haiti'] < 5: return ['background-color: #e74c3c; color: white']*len(row)
                    return ['']*len(row)
                st.dataframe(get_view(comparison_view[['Full Name', 'SKU', 'Stock_pv', 'Stock_haiti']]).style.apply(color_comparison, axis=1), use_container_width=True)
        
        with t3:
            if haiti_active:
                def calculate_request(row):
                    if row['Stock_pv'] == 0 and row['Stock_haiti'] > 20: return 10
                    if row['Sold'] >= 10 and row['Stock_pv'] <= 20 and row['Stock_haiti'] > 20: return 25
                    if row['Stock_haiti'] > 75 and row['Stock_pv'] <= 35: return 15
                    return 0
                compare_all['Request Qty'] = compare_all.apply(calculate_request, axis=1)
                st.dataframe(get_view(compare_all[compare_all['Request Qty'] > 0][['Full Name', 'SKU', 'Stock_haiti', 'Stock_pv', 'Sold', 'Request Qty']]), use_container_width=True)

        with t4:
            cw1, cw2 = st.columns(2)
            cw1.write("✅ **Top 10 Sellers**")
            cw1.table(df_pv.nlargest(10, 'Sold')[['Full Name', 'Sold']])
            cw2.write("📉 **Worst 10**")
            cw2.table(df_pv[df_pv['Stock'] > 0].nsmallest(10, 'Sold')[['Full Name', 'Sold']])

        with t5: st.dataframe(get_view(df_pv[df_pv['Stock'] == 0]), use_container_width=True)
        with t6: st.dataframe(get_view(df_pv[(df_pv['Stock'] > 0) & (df_pv['Stock'] <= 5)]), use_container_width=True)
        with t7:
            df_pv['Value'] = df_pv['Stock'] * df_pv['Price']
            st.dataframe(get_view(df_pv[['Full Name', 'SKU', 'Stock', 'Price', 'Value']].sort_values('Value', ascending=False)), use_container_width=True)
        with t8: st.dataframe(get_view(df_pv), use_container_width=True)

    # TAB 9: NEW LOGISTICS INSIGHTS
    with t9:
        st.header("📊 Logistics & Performance Analytics")
        if not airtable_df.empty:
            c1, c2 = st.columns(2)
            s_date = c1.date_input("Filter Analytics From:", value=airtable_df['Date'].min())
            filtered_at = airtable_df[airtable_df['Date'] >= s_date]
            c2.metric("Total Wigs Received", int(filtered_at['Quantity'].sum()))

            st.divider()
            sel_sku = st.selectbox("Analyze Specific SKU", options=airtable_df['SKU'].unique())
            sku_h = airtable_df[airtable_df['SKU'] == sel_sku]
            
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Lifetime Received", int(sku_h['Quantity'].sum()))
            sc2.metric("First Arrival", str(sku_h['Date'].min()))
            
            if not df_pv.empty and sel_sku in df_pv['SKU'].values:
                curr_s = df_pv[df_pv['SKU'] == sel_sku]['Stock'].iloc[0]
                sold_l = sku_h['Quantity'].sum() - curr_s
                sc3.metric("Lifetime Sold", int(max(0, sold_l)))
                
                days_act = (date.today() - sku_h['Date'].min()).days
                if days_act > 0:
                    st.info(f"🚀 **Velocity:** You sell **{(sold_l/days_act):.2f}** units/day of this item.")

            st.write("Shipment History for this SKU:")
            st.table(sku_h[['Date', 'Quantity', 'User']])
