import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
import os
from datetime import date

# 1. ALWAYS FIRST: Set page to wide mode and configure title
st.set_page_config(page_title="Dressupht Intelligence", layout="wide")

# --- USER AUTHENTICATION SETUP ---
config = {
    'credentials': {
        'usernames': {
            'kevin': {
                'name': 'Dressup Haiti Admin',
                'password': 'The$100$Raven' 
            },
            'staff1': {
                'name': 'Inventory Manager',
                'password': 'secretpassword456'
            }
        }
    },
    'cookie': {
        'expiry_days': 30,
        'key': 'inventory_signature_key',
        'name': 'inventory_cookie'
    }
}

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

login_data = authenticator.login()

if st.session_state["authentication_status"] == False:
    st.error("Username/password is incorrect")
elif st.session_state["authentication_status"] == None:
    st.warning("Please enter your username and password")
elif st.session_state["authentication_status"]:
    
    authenticator.logout('Logout', 'sidebar')
    st.sidebar.title(f"Welcome {st.session_state['name']}")

    # --- 2. AIRTABLE CONFIGURATION ---
    AIR_TOKEN = "pat1SYxIQWWcgkwy5.35f38c5bdc516561cbacc01116d09eeac8e861f3c442af68fcf19ee58e9dc72a"
    BASE_ID = "app5eJFgtbCaJHGhc"
    TABLE_NAME = "Shipments"
    AIRTABLE_URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    HEADERS = {
        "Authorization": f"Bearer {AIR_TOKEN}",
        "Content-Type": "application/json"
    }

    def get_airtable_data():
        try:
            response = requests.get(AIRTABLE_URL, headers=HEADERS)
            if response.status_code == 200:
                records = response.json().get('records', [])
                if not records:
                    return pd.DataFrame(columns=["Date", "SKU", "Name", "Quantity", "User"])
                df = pd.DataFrame([r['fields'] for r in records])
                for col in ["Date", "SKU", "Name", "Quantity", "User"]:
                    if col not in df.columns: df[col] = None
                return df[["Date", "SKU", "Name", "Quantity", "User"]]
            return pd.DataFrame(columns=["Date", "SKU", "Name", "Quantity", "User"])
        except Exception as e:
            return pd.DataFrame(columns=["Date", "SKU", "Name", "Quantity", "User"])

    def clean_data(file, location_col_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip().lower() for c in df.columns]
        needed = {
            'item name': 'Wig Name', 'variation name': 'Style', 
            'sku': 'SKU', 'price': 'Price', 'categories': 'Category',
            location_col_name.lower(): 'Stock'
        }
        existing = [c for c in list(df.columns) if c in needed.keys()]
        df = df[existing].copy()
        df.columns = [needed[c] for c in existing]
        if 'Category' not in df.columns: df['Category'] = 'Uncategorized'
        df = df.dropna(subset=['SKU'])
        df['SKU'] = df['SKU'].astype(str).str.strip()
        df['Full Name'] = df['Wig Name'] + " (" + df['Style'].fillna('') + ")"
        df['Stock'] = pd.to_numeric(df['Stock'], errors='coerce').fillna(0)
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)
        return df

    # --- 3. SIDEBAR UPLOADS ---
    st.sidebar.divider()
    st.sidebar.subheader("📁 Data Upload Center")
    file_pv = st.sidebar.file_uploader("📍 THIS Saturday (PV)", type=['xlsx'])
    file_pv_prev = st.sidebar.file_uploader("🕒 LAST Saturday (PV)", type=['xlsx'])
    file_haiti = st.sidebar.file_uploader("🌐 Dressup Haiti", type=['xlsx'])

    # --- 4. DATA PROCESSING ---
    df_pv = pd.DataFrame()
    sku_to_name = {}
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

    # --- 5. MAIN INTERFACE ---
    st.title("🦱 Dressupht Pv: Intelligence Center")
    
    search = st.text_input("🔍 Search Name or SKU")
    
    def get_view(df_to_filter):
        if df_to_filter.empty: return df_to_filter
        if search:
            return df_to_filter[df_to_filter['Full Name'].astype(str).str.contains(search, case=False) | 
                                df_to_filter['SKU'].astype(str).str.contains(search, case=False)]
        return df_to_filter

    t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([
        "➕ Shipment Intake", "🔄 Comparison", "🚚 Smart Transfers", "🔥 Fast/Slow", 
        "❌ OOS", "⚠️ Low Stock", "💰 Financials", "📋 Full Library"
    ])

    with t1:
        st.subheader("Cloud Shipment Record")
        input_sku = st.text_input("Enter SKU to receive").strip()
        
        # Automatically detect name if PV file is uploaded
        detected_name = sku_to_name.get(input_sku, None)
        if input_sku:
            if detected_name:
                st.success(f"Verified: {detected_name}")
            else:
                st.warning("SKU not recognized in Excel. Will be saved as 'New/Unknown'")
                detected_name = "New Item / Unknown"

        existing_data = get_airtable_data()

        with st.form("intake_form", clear_on_submit=True):
            col_f1, col_f2 = st.columns(2)
            input_date = col_f1.date_input("Date Received", value=date.today())
            qty = col_f2.number_input("Quantity Received", min_value=1)
            
            if st.form_submit_button("✅ Sync to Cloud"):
                if input_sku:
                    payload = {"records": [{"fields": {
                        "Date": str(input_date),
                        "SKU": str(input_sku),
                        "Name": str(detected_name),
                        "Quantity": int(qty),
                        "User": str(st.session_state['username'])
                    }}]}
                    res = requests.post(AIRTABLE_URL, headers=HEADERS, json=payload)
                    if res.status_code == 200:
                        st.success(f"Saved: {detected_name}")
                        st.rerun()
                    else:
                        st.error(f"Sync Failed: {res.text}")
                else:
                    st.error("Please enter a SKU.")

        st.divider()
        st.dataframe(existing_data.iloc[::-1], use_container_width=True)

    with t2:
        if not df_pv.empty and haiti_active:
            compare_all = pd.merge(df_haiti[['SKU', 'Stock']], df_pv, on='SKU', suffixes=('_haiti', '_pv')).drop_duplicates(subset=['SKU'])
            comparison_view = compare_all[((compare_all['Stock_haiti'] > 75) & (compare_all['Stock_pv'] <= 35)) | (compare_all['Stock_pv'] < 5)].copy()
            def color_comparison(row):
                if row['Stock_pv'] < 5 and row['Stock_haiti'] > 25: return ['background-color: #2ecc71; color: white']*len(row)
                if row['Stock_pv'] < 5 and row['Stock_haiti'] < 5: return ['background-color: #e74c3c; color: white']*len(row)
                return ['']*len(row)
            st.dataframe(get_view(comparison_view[['Full Name', 'SKU', 'Stock_pv', 'Stock_haiti']]).style.apply(color_comparison, axis=1), use_container_width=True)
        else:
            st.info("Upload PV and Haiti files in the sidebar to view comparisons.")

    with t3:
        if not df_pv.empty and haiti_active:
            def calculate_request(row):
                if row['Stock_pv'] == 0 and row['Stock_haiti'] > 20: return 10
                if row['Sold'] >= 10 and row['Stock_pv'] <= 20 and row['Stock_haiti'] > 20: return 25
                if row['Stock_haiti'] > 75 and row['Stock_pv'] <= 35: return 15
                return 0
            compare_all['Request Qty'] = compare_all.apply(calculate_request, axis=1)
            st.dataframe(get_view(compare_all[compare_all['Request Qty'] > 0][['Full Name', 'SKU', 'Stock_haiti', 'Stock_pv', 'Sold', 'Request Qty']]), use_container_width=True)
        else:
            st.info("Upload PV and Haiti files to see transfer recommendations.")

    with t4:
        if not df_pv.empty:
            cw1, cw2 = st.columns(2)
            cw1.write("✅ **Top 10 Sellers**")
            cw1.table(df_pv.nlargest(10, 'Sold')[['Full Name', 'Sold']])
            cw2.write("📉 **Worst 10 (Dead Stock)**")
            cw2.table(df_pv[df_pv['Stock'] > 0].nsmallest(10, 'Sold')[['Full Name', 'Sold']])
        else:
            st.info("Upload PV file to see sales performance.")

    with t5: 
        if not df_pv.empty: st.dataframe(get_view(df_pv[df_pv['Stock'] == 0]), use_container_width=True)
    with t6: 
        if not df_pv.empty: st.dataframe(get_view(df_pv[(df_pv['Stock'] > 0) & (df_pv['Stock'] <= 5)]), use_container_width=True)
    with t7:
        if not df_pv.empty:
            df_pv['Value'] = df_pv['Stock'] * df_pv['Price']
            st.dataframe(get_view(df_pv[['Full Name', 'SKU', 'Stock', 'Price', 'Value']].sort_values('Value', ascending=False)), use_container_width=True)
    with t8:
        if not df_pv.empty: st.dataframe(get_view(df_pv), use_container_width=True)
