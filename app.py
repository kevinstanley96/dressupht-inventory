import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
import os
from datetime import date, datetime

# 1. Page Config
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
    AIR_TOKEN = os.getenv("AIRTABLE_TOKEN")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")

HEADERS = {
    "Authorization": f"Bearer {AIR_TOKEN}",
    "Content-Type": "application/json"
}

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
        if 'Category' not in df.columns: df['Category'] = "Uncategorized"
        else: df['Category'] = df['Category'].fillna("Uncategorized")
        df['SKU'] = df['SKU'].astype(str).str.strip()
        df['Full Name'] = df['Wig Name'] + " (" + df['Style'].fillna('') + ")"
        df['Stock'] = pd.to_numeric(df['Stock'], errors='coerce').fillna(0)
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)
        return df

    # --- 3. SIDEBAR & DATA LOADING ---
    st.sidebar.subheader("📁 Data Upload Center")
    file_pv = st.sidebar.file_uploader("📍 THIS Saturday (PV)", type=['xlsx'])
    file_pv_prev = st.sidebar.file_uploader("🕒 LAST Saturday (PV)", type=['xlsx'])
    file_haiti = st.sidebar.file_uploader("🌐 Dressup Haiti", type=['xlsx'])

    df_pv = pd.DataFrame()
    haiti_active = False
    sales_ready = False
    sku_to_name, sku_to_stock, sku_to_cat = {}, {}, {}

    if file_pv:
        df_pv = clean_data(file_pv, "current quantity dressupht pv")
        sku_to_name = dict(zip(df_pv['SKU'], df_pv['Full Name']))
        sku_to_stock = dict(zip(df_pv['SKU'], df_pv['Stock']))
        sku_to_cat = dict(zip(df_pv['SKU'], df_pv['Category']))
        
        if file_pv_prev:
            df_prev = clean_data(file_pv_prev, "current quantity dressupht pv")
            df_pv = pd.merge(df_pv, df_prev[['SKU', 'Stock']], on='SKU', how='left', suffixes=('', '_prev'))
            df_pv['Sold'] = (df_pv['Stock_prev'].fillna(0) - df_pv['Stock']).clip(lower=0)
            sales_ready = True
        else: 
            df_pv['Sold'] = 0
        
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
    # ADDED "📊 Sales" Tab here
    tabs = st.tabs(["➕ Intake", "🕵️ Audit", "📊 Sales", "🔄 Compare", "🚚 Transfers", "🔥 Fast/Slow", "❌ OOS", "💰 Finance", "📋 Library", "📈 Analytics"])
    
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
        staff_members = ["Select Counter...", "Angelina", "Gerdine", "Annaelle", "David", "Kevin"]
        selected_staff = st.selectbox("Who is counting?", options=staff_members)
        a_sku = st.text_input("Scan SKU for Audit", key="audit_scan").strip()
        
        if a_sku:
            s_qty = sku_to_stock.get(a_sku, 0)
            a_name = sku_to_name.get(a_sku, "Unknown Item")
            a_cat = sku_to_cat.get(a_sku, "Uncategorized")
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
                    if selected_staff != "Select Counter...":
                        fields = {"Date": str(date.today()), "SKU": a_sku, "Name": a_name, "Category": a_cat, "System_Qty": int(s_qty), "Manual_Qty": int(m_qty), "Mannequin": int(e_qty), "Returns": int(r_qty), "Diff": diff_value, "User": selected_staff}
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json={"records": [{"fields": fields}]})
                        st.success("Audit saved!")
                        st.rerun()

        aud_hist = get_at_data("Inventory_Audit")
        if not aud_hist.empty:
            for col in ['Mannequin', 'Manual_Qty', 'Returns', 'System_Qty']:
                if col not in aud_hist.columns: aud_hist[col] = 0
                else: aud_hist[col] = pd.to_numeric(aud_hist[col], errors='coerce').fillna(0)
            
            aud_hist['Diff'] = (aud_hist['Manual_Qty'] + aud_hist['Mannequin'] + aud_hist['Returns']) - aud_hist['System_Qty']
            
            st.write("---")
            st.write("#### 🗑️ Manage Today's Entries")
            today_logs = aud_hist[aud_hist['Date'] == date.today()].copy()
            if not today_logs.empty:
                del_sku = st.selectbox("Select SKU to delete", options=today_logs['SKU'].unique())
                if st.button("🗑️ Delete Selected Row"):
                    rid = today_logs[today_logs['SKU'] == del_sku].iloc[0]['id']
                    requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit/{rid}", headers=HEADERS)
                    st.rerun()
            
            st.write("#### Detailed History")
            st.dataframe(aud_hist, use_container_width=True)

    with tabs[2]: # NEW SALES TAB
        st.subheader("📊 Sales Tracking (Weekly)")
        if sales_ready:
            sales_df = df_pv[df_pv['Sold'] > 0].copy()
            sales_df['Revenue'] = sales_df['Sold'] * sales_df['Price']
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Units Sold", int(sales_df['Sold'].sum()))
            m2.metric("Total Revenue", f"${sales_df['Revenue'].sum():,.2f}")
            m3.metric("Unique Items Sold", len(sales_df))
            
            st.write("#### Sales Breakdown")
            st.dataframe(get_view(sales_df[['Full Name', 'SKU', 'Stock_prev', 'Stock', 'Sold', 'Price', 'Revenue']].sort_values('Sold', ascending=False)), use_container_width=True)
        else:
            st.warning("⚠️ Please upload both **THIS Saturday** and **LAST Saturday** files in the sidebar to calculate sales.")

    if not df_pv.empty:
        with tabs[3]: # COMPARE
            st.subheader("🔄 PV vs Haiti Stock")
            if haiti_active:
                comp = pd.merge(df_haiti[['SKU', 'Stock']], df_pv, on='SKU', suffixes=('_haiti', '_pv')).drop_duplicates(subset=['SKU'])
                view = comp[((comp['Stock_haiti'] > 75) & (comp['Stock_pv'] <= 35)) | (comp['Stock_pv'] < 5)].copy()
                st.dataframe(get_view(view[['Full Name', 'SKU', 'Stock_pv', 'Stock_haiti']]), use_container_width=True)
            else: st.warning("Upload Haiti file to compare.")

        with tabs[4]: # TRANSFERS
            st.subheader("🚚 Transfer Recommendations")
            if haiti_active:
                def req(r):
                    if r['Stock_pv'] == 0 and r['Stock_haiti'] > 20: return 10
                    if r['Sold'] >= 10 and r['Stock_pv'] <= 20 and r['Stock_haiti'] > 20: return 25
                    return 0
                comp['Request'] = comp.apply(req, axis=1)
                st.dataframe(get_view(comp[comp['Request'] > 0][['Full Name', 'SKU', 'Stock_haiti', 'Stock_pv', 'Sold', 'Request']]), use_container_width=True)
            else: st.warning("Upload Haiti file to see transfer needs.")

        with tabs[5]: # FAST/SLOW
            st.subheader("🔥 Performance Analysis")
            cw1, cw2 = st.columns(2)
            cw1.write("**Top 10 Sellers**")
            cw1.table(df_pv.nlargest(10, 'Sold')[['Full Name', 'Sold']])
            cw2.write("**Bottom 10 (Dead Stock)**")
            cw2.table(df_pv[df_pv['Stock'] > 0].nsmallest(10, 'Sold')[['Full Name', 'Sold']])

        with tabs[6]: # OOS
            st.subheader("❌ Out of Stock")
            st.dataframe(get_view(df_pv[df_pv['Stock'] == 0]), use_container_width=True)

        with tabs[7]: # FINANCE
            st.subheader("💰 Inventory Valuation")
            df_pv['Value'] = df_pv['Stock'] * df_pv['Price']
            st.dataframe(get_view(df_pv[['Full Name', 'SKU', 'Stock', 'Price', 'Value']].sort_values('Value', ascending=False)), use_container_width=True)

        with tabs[8]: # LIBRARY
            st.subheader("📋 Full Item Library")
            st.dataframe(get_view(df_pv), use_container_width=True)

        with tabs[9]: # ANALYTICS
            st.subheader("📈 Shipment Velocity")
            at_ship = get_at_data("Shipments")
            if not at_ship.empty:
                sel_s = st.selectbox("Pick SKU for history", at_ship['SKU'].unique())
                sh = at_ship[at_ship['SKU'] == sel_s]
                st.metric("Total Units Received", int(sh['Quantity'].sum()))
                st.table(sh[['Date', 'Quantity', 'User']])
    else:
        st.info("Upload PV Inventory file in the sidebar to unlock performance tabs.")

