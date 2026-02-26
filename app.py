import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import date, datetime, timedelta
import time

# 1. Page Config
st.set_page_config(page_title="Dressupht Intelligence", layout="wide")

# --- MOBILE OPTIMIZATION CSS ---
st.markdown("""
    <style>
    .stDataFrame { font-size: 12px; }
    .stButton>button { height: 3em; border-radius: 10px; font-weight: bold; width: 100%; }
    [data-testid="stElementToolbar"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

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
    all_records = []
    offset = None
    try:
        url = f"https://api.airtable.com/v0/{base_id}/{table}"
        while True:
            params = {}
            if offset: params['offset'] = offset
            if table in ["Shipments", "Inventory_Audit"]:
                params['sort[0][field]'] = "Date"; params['sort[0][direction]'] = "desc"
            else:
                params['sort[0][field]'] = "Full Name"; params['sort[0][direction]'] = "asc"

            res = requests.get(url, headers=headers, params=params)
            if res.status_code != 200: break
            data = res.json()
            all_records.extend(data.get('records', []))
            offset = data.get('offset')
            if not offset: break
        
        if not all_records: return pd.DataFrame()
        df = pd.DataFrame([dict(r['fields'], id=r['id']) for r in all_records])
        
        if 'Date' in df.columns:
            temp_dt = pd.to_datetime(df['Date'], errors='coerce') - timedelta(hours=5)
            df['Time'] = temp_dt.dt.strftime('%H:%M')
            df['Date'] = temp_dt.dt.date
        if 'Last Updated' in df.columns:
            updated_dt = pd.to_datetime(df['Last Updated']) - timedelta(hours=5)
            df['Last Updated Display'] = updated_dt.dt.strftime('%m/%d %H:%M')
        return df
    except: return pd.DataFrame()

def clean_data(file, loc_col):
    df = pd.read_excel(file, skiprows=1)
    df.columns = [str(c).strip().lower() for c in df.columns]
    needed = {'item name': 'Wig Name', 'variation name': 'Style', 'sku': 'SKU', 'price': 'Price', 'categories': 'Category', loc_col.lower(): 'Stock'}
    existing = [c for c in list(df.columns) if c in needed.keys()]
    df = df[existing].copy()
    df.columns = [needed[c] for c in existing]
    for col in ['Wig Name', 'Style']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace('â€', '”', regex=False).str.replace('â€™', "'", regex=False).str.replace('â€œ', '“', regex=False)
    df['SKU'] = df['SKU'].astype(str).str.strip()
    df['Full Name'] = df['Wig Name'] + " (" + df['Style'].fillna('') + ")"
    df['Stock'] = pd.to_numeric(df['Stock'], errors='coerce').fillna(0)
    df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)
    return df.sort_values('Full Name')

# --- MAIN APP ---
if st.session_state["authentication_status"]:
    authenticator.logout('Logout', 'sidebar')
    curr_user = st.session_state['username']
    
    try:
        AIR_TOKEN = st.secrets["AIRTABLE_TOKEN"]; BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
        HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}
    except:
        st.error("Secrets Error."); st.stop()

    df_pv = pd.DataFrame(); df_haiti = pd.DataFrame(); sales_ready = haiti_ready = False

    if curr_user != 'guest':
        st.sidebar.subheader("📁 Data Center")
        f_pv = st.sidebar.file_uploader("THIS Saturday (PV)", type=['xlsx'])
        f_pv_prev = st.sidebar.file_uploader("LAST Saturday (PV)", type=['xlsx'])
        f_haiti = st.sidebar.file_uploader("Dressup Haiti", type=['xlsx'])
        if f_pv:
            df_pv = clean_data(f_pv, "current quantity dressupht pv")
            if f_pv_prev:
                df_prev = clean_data(f_pv_prev, "current quantity dressupht pv")
                df_pv = pd.merge(df_pv, df_prev[['SKU', 'Stock']], on='SKU', how='left', suffixes=('', '_prev'))
                df_pv['Sold'] = (df_pv['Stock_prev'].fillna(0) - df_pv['Stock']).clip(lower=0); sales_ready = True
            if f_haiti:
                df_haiti = clean_data(f_haiti, "current quantity dressup haiti"); haiti_ready = True

        st.sidebar.markdown("---")
        f_quick = st.sidebar.file_uploader("Daily Export (Quick Sync)", type=['xlsx'])
        if f_quick and st.sidebar.button("🚀 Push to Guest Library"):
            df_q = clean_data(f_quick, "current quantity dressupht pv")
            old = get_at_data("Master_Inventory", BASE_ID, HEADERS)
            if not old.empty:
                ids = old['id'].tolist()
                for i in range(0, len(ids), 10): requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, params={"records[]": ids[i:i+10]})
            recs = [{"fields": {"Full Name": str(r['Full Name']), "SKU": str(r['SKU']), "Stock": int(r['Stock'])}} for _, r in df_q.iterrows()]
            for i in range(0, len(recs), 10): requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs[i:i+10]})
            st.rerun()

    st.title("🦱 Dressupht Intelligence")
    search = st.text_input("🔍 Search Inventory", placeholder="Try '10 bob' or '12 black'...")

    if curr_user == 'guest':
        tabs = st.tabs(["📋 Library"])
        with tabs[0]:
            data = get_at_data("Master_Inventory", BASE_ID, HEADERS)
            if not data.empty:
                view = data[['Full Name', 'Stock', 'Last Updated Display']].copy()
                if search:
                    for term in search.split(): view = view[view['Full Name'].str.contains(term, case=False, na=False)]
                st.dataframe(view, use_container_width=True, hide_index=True)
                st.caption(f"Showing {len(view)} wigs.")
    else:
        # ALL ADMIN TABS RESTORED
        tabs = st.tabs(["➕ Intake", "🕵️ Audit", "📊 Sales", "🔄 Compare", "🚚 Transfers", "🔥 Fast/Slow", "❌ OOS", "💰 Finance", "📋 Library"])
        
        with tabs[0]: # Intake
            with st.form("in_f", clear_on_submit=True):
                i_sku = st.text_input("Scan SKU").strip(); q = st.number_input("Qty", 1)
                if st.form_submit_button("Sync Intake"):
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json={"records": [{"fields": {"Date": datetime.utcnow().isoformat(), "SKU": i_sku, "Quantity": q, "User": curr_user}}]})
                    st.rerun()
            ships = get_at_data("Shipments", BASE_ID, HEADERS)
            if not ships.empty: st.dataframe(ships[['Date', 'Time', 'SKU', 'Quantity', 'User']], use_container_width=True, hide_index=True)

        with tabs[1]: # Audit
            with st.form("aud_f", clear_on_submit=True):
                a_sku = st.text_input("Scan SKU").strip(); m = st.number_input("Found Count", 0)
                if st.form_submit_button("Log Audit"):
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json={"records": [{"fields": {"Date": datetime.utcnow().isoformat(), "SKU": a_sku, "Manual_Qty": m, "User": curr_user}}]})
                    st.rerun()
            auds = get_at_data("Inventory_Audit", BASE_ID, HEADERS)
            if not auds.empty: st.dataframe(auds[['Date', 'Time', 'SKU', 'Manual_Qty', 'User']], use_container_width=True, hide_index=True)

        with tabs[2]: # Sales
            if sales_ready: st.dataframe(df_pv[df_pv['Sold'] > 0][['Full Name', 'SKU', 'Stock_prev', 'Stock', 'Sold']], use_container_width=True, hide_index=True)
            else: st.info("Upload 'THIS' and 'LAST' Saturday files.")

        with tabs[3]: # Compare
            if haiti_ready and not df_pv.empty:
                comp = pd.merge(df_haiti[['SKU', 'Stock']], df_pv[['SKU', 'Full Name', 'Stock']], on='SKU', suffixes=('_haiti', '_pv'))
                st.dataframe(comp, use_container_width=True, hide_index=True)
            else: st.info("Upload Haiti and PV files.")

        with tabs[4]: # Transfers
            if haiti_ready and not df_pv.empty:
                trans = pd.merge(df_haiti[['SKU', 'Stock']], df_pv[['SKU', 'Full Name', 'Stock']], on='SKU', suffixes=('_haiti', '_pv'))
                st.dataframe(trans[(trans['Stock_haiti'] > 2) & (trans['Stock_pv'] < 1)], use_container_width=True, hide_index=True)
            else: st.info("Upload files to see suggestions.")

        with tabs[5]: # Fast/Slow
            if sales_ready: st.table(df_pv.nlargest(10, 'Sold')[['Full Name', 'Sold']])
            else: st.info("Upload files to see top sellers.")

        with tabs[6]: # OOS
            if not df_pv.empty: st.dataframe(df_pv[df_pv['Stock'] == 0][['Full Name', 'SKU']], use_container_width=True, hide_index=True)
            else: st.info("Upload PV file.")

        with tabs[7]: # Finance
            if not df_pv.empty:
                df_pv['Value'] = df_pv['Stock'] * df_pv['Price']
                st.metric("Total Depot Value", f"${df_pv['Value'].sum():,.2f}")
                st.dataframe(df_pv[['Full Name', 'Stock', 'Price', 'Value']], use_container_width=True, hide_index=True)

        with tabs[8]: # Library
            lib = get_at_data("Master_Inventory", BASE_ID, HEADERS)
            if not lib.empty: st.dataframe(lib.drop(columns=['id'], errors='ignore'), use_container_width=True, hide_index=True)

elif st.session_state["authentication_status"] is False:
    st.error("Login failed.")
