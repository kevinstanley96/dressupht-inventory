import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import date, datetime
import time

# 1. Page Config
st.set_page_config(page_title="Dressupht Intelligence", layout="wide")

# --- USER AUTHENTICATION ---
config = {
    'credentials': {
        'usernames': {
            'kevin': {'name': 'Dressup Haiti Admin', 'password': 'The$100$Raven'},
            'staff1': {'name': 'Inventory Manager', 'password': 'secretpassword456'},
            'guest': {'name': 'Inventory Guest', 'password': 'guestpassword123'}
        }
    },
    'cookie': {'expiry_days': 30, 'key': 'inventory_signature_key', 'name': 'inventory_cookie'}
}

authenticator = stauth.Authenticate(config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days'])
authenticator.login()

# --- HELPER FUNCTIONS ---
def get_at_data(table, base_id, headers):
    try:
        url = f"https://api.airtable.com/v0/{base_id}/{table}"
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            records = res.json().get('records', [])
            if not records: return pd.DataFrame()
            df = pd.DataFrame([dict(r['fields'], id=r['id']) for r in records])
            
            # Format standard date/time columns
            if 'Date' in df.columns:
                temp_dt = pd.to_datetime(df['Date'], errors='coerce')
                df['Time'] = temp_dt.dt.strftime('%H:%M')
                df['Date'] = temp_dt.dt.date
            
            # Specifically handle the "Last Updated" column if present
            if 'Last Updated' in df.columns:
                df['Last Updated Display'] = pd.to_datetime(df['Last Updated']).dt.strftime('%m/%d %H:%M')
                
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
    df['SKU'] = df['SKU'].astype(str).str.strip()
    df['Full Name'] = df['Wig Name'] + " (" + df['Style'].fillna('') + ")"
    df['Stock'] = pd.to_numeric(df['Stock'], errors='coerce').fillna(0)
    df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)
    return df

# --- MAIN APP LOGIC ---
if st.session_state["authentication_status"]:
    authenticator.logout('Logout', 'sidebar')
    curr_user = st.session_state['username']
    
    try:
        AIR_TOKEN = st.secrets["AIRTABLE_TOKEN"]
        BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
        HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}
    except:
        st.error("Check Streamlit Secrets for Airtable credentials.")
        st.stop()

    # --- SIDEBAR & UPLOADS ---
    df_pv = pd.DataFrame()
    haiti_active = sales_ready = False
    sku_to_stock = sku_to_name = sku_to_cat = {}

    if curr_user != 'guest':
        st.sidebar.subheader("📁 Saturday Center")
        f_pv = st.sidebar.file_uploader("THIS Saturday (PV)", type=['xlsx'])
        f_pv_prev = st.sidebar.file_uploader("LAST Saturday (PV)", type=['xlsx'])
        f_haiti = st.sidebar.file_uploader("Dressup Haiti", type=['xlsx'])
        
        # New Sync Uploader
        st.sidebar.markdown("---")
        st.sidebar.subheader("⚡ 3-Hour Sync")
        f_quick = st.sidebar.file_uploader("Daily Square Export", type=['xlsx'], key="quick")

        if f_pv:
            df_pv = clean_data(f_pv, "current quantity dressupht pv")
            sku_to_name = dict(zip(df_pv['SKU'], df_pv['Full Name']))
            sku_to_stock = dict(zip(df_pv['SKU'], df_pv['Stock']))
            sku_to_cat = dict(zip(df_pv['SKU'], df_pv['Category']))
            if f_pv_prev:
                df_prev = clean_data(f_pv_prev, "current quantity dressupht pv")
                df_pv = pd.merge(df_pv, df_prev[['SKU', 'Stock']], on='SKU', how='left', suffixes=('', '_prev'))
                df_pv['Sold'] = (df_pv['Stock_prev'].fillna(0) - df_pv['Stock']).clip(lower=0)
                sales_ready = True
            if f_haiti:
                df_haiti = clean_data(f_haiti, "current quantity dressup haiti")
                haiti_active = True

        if f_quick:
            df_quick = clean_data(f_quick, "current quantity dressupht pv")
            if st.sidebar.button("🚀 Push to Guest Library"):
                with st.spinner("Updating Cloud..."):
                    old = get_at_data("Master_Inventory", BASE_ID, HEADERS)
                    if not old.empty:
                        ids = old['id'].tolist()
                        for i in range(0, len(ids), 10):
                            requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, params={"records[]": ids[i:i+10]})
                    
                    recs = [{"fields": {"Full Name": str(r['Full Name']), "SKU": str(r['SKU']), "Stock": int(r['Stock']), "Category": str(r['Category'])}} for _, r in df_quick.iterrows()]
                    for i in range(0, len(recs), 10):
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs[i:i+10]})
                    st.sidebar.success("Library Synced!")
                    time.sleep(1)
                    st.rerun()

    st.title("🦱 Dressupht Intelligence")
    search = st.text_input("🔍 Search Name or SKU")

    def get_view(df_to_filter):
        if df_to_filter.empty: return df_to_filter
        if search: return df_to_filter[df_to_filter['Full Name'].astype(str).str.contains(search, case=False) | df_to_filter['SKU'].astype(str).str.contains(search, case=False)]
        return df_to_filter

    # --- ROLE-BASED TABS ---
    if curr_user == 'guest':
        tabs = st.tabs(["📋 Library"])
    else:
        tabs = st.tabs(["➕ Intake", "🕵️ Audit", "📊 Sales", "🔄 Compare", "🚚 Transfers", "🔥 Fast/Slow", "❌ OOS", "💰 Finance", "📋 Library", "📈 Analytics"])

    # --- TAB LOGIC ---
    if curr_user == 'guest':
        with tabs[0]:
            st.subheader("PV Depot Inventory")
            data = get_at_data("Master_Inventory", BASE_ID, HEADERS)
            if not data.empty:
                display_df = data.drop(columns=[c for c in ['id', 'Price', 'Value', 'Stock_prev', 'Sold'] if c in data.columns])
                if search:
                    display_df = display_df[display_df.apply(lambda row: search.lower() in row.astype(str).str.lower().values, axis=1)]
                st.dataframe(display_df, use_container_width=True)
            else:
                st.warning("No data found. Please wait for Admin to Sync.")
    else:
        # ADMIN/STAFF VIEWS
        with tabs[0]: # Intake
            i_sku = st.text_input("Scan for Intake").strip()
            with st.form("in_f"):
                q = st.number_input("Qty", 1)
                if st.form_submit_button("Sync"):
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json={"records": [{"fields": {"Date": datetime.now().isoformat(), "SKU": i_sku, "Quantity": q, "User": curr_user}}]})
                    st.rerun()
            ships = get_at_data("Shipments", BASE_ID, HEADERS)
            if not ships.empty: st.dataframe(ships.drop(columns=['id']), use_container_width=True)

        with tabs[1]: # Audit
            a_sku = st.text_input("Scan for Audit").strip()
            if a_sku:
                st.write(f"Item: {sku_to_name.get(a_sku, 'Unknown')}")
                with st.form("aud"):
                    m = st.number_input("Depot Qty", 0)
                    if st.form_submit_button("Log"):
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json={"records": [{"fields": {"Date": datetime.now().isoformat(), "SKU": a_sku, "Manual_Qty": m, "User": curr_user}}]})
                        st.rerun()
            aud = get_at_data("Inventory_Audit", BASE_ID, HEADERS)
            if not aud.empty: st.dataframe(aud.drop(columns=['id']), use_container_width=True)

        with tabs[2]: # Sales
            if sales_ready:
                s_df = df_pv[df_pv['Sold'] > 0].copy()
                st.dataframe(get_view(s_df), use_container_width=True)
            else: st.info("Upload THIS and LAST Saturday files.")

        with tabs[3]: # Compare
            if haiti_active:
                comp = pd.merge(df_haiti[['SKU', 'Stock']], df_pv, on='SKU', suffixes=('_haiti', '_pv'))
                st.dataframe(get_view(comp), use_container_width=True)

        with tabs[4]: # Transfers
            if haiti_active:
                st.write("Suggested Transfers logic here...")

        with tabs[5]: # Fast/Slow
            if sales_ready:
                st.subheader("Top 10 Sellers")
                st.table(df_pv.nlargest(10, 'Sold')[['Full Name', 'Sold']])

        with tabs[6]: # OOS
            if not df_pv.empty:
                st.dataframe(get_view(df_pv[df_pv['Stock'] == 0]), use_container_width=True)

        with tabs[7]: # Finance
            if not df_pv.empty:
                df_pv['Total Value'] = df_pv['Stock'] * df_pv['Price']
                st.dataframe(get_view(df_pv), use_container_width=True)

        with tabs[8]: # Library
            st.subheader("PV Depot Master Library")
            lib_data = get_at_data("Master_Inventory", BASE_ID, HEADERS)
            if not lib_data.empty:
                st.dataframe(get_view(lib_data), use_container_width=True)

        with tabs[9]: # Analytics
            st.write("Shipment analytics and history charts.")

elif st.session_state["authentication_status"] is False:
    st.error("Login failed.")
