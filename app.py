import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import date, datetime
import time

# 1. Page Config
st.set_page_config(page_title="Dressupht Intelligence", layout="wide")

# --- MOBILE OPTIMIZATION CSS ---
st.markdown("""
    <style>
    .stDataFrame { font-size: 12px; }
    .stButton>button { height: 3em; border-radius: 10px; font-weight: bold; width: 100%; }
    [data-testid="stElementToolbar"] { display: none; }
    .sku-match { color: #28a745; font-weight: bold; margin-bottom: 10px; }
    .sku-miss { color: #dc3545; font-weight: bold; margin-bottom: 10px; }
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
                params['sort[0][field]'] = "Date"
                params['sort[0][direction]'] = "desc"
            res = requests.get(url, headers=headers, params=params)
            if res.status_code != 200: break
            data = res.json()
            records = data.get('records', [])
            all_records.extend(records)
            offset = data.get('offset')
            if not offset: break
        if not all_records: return pd.DataFrame()
        df = pd.DataFrame([dict(r['fields'], id=r['id']) for r in all_records])
        if 'Date' in df.columns:
            temp_dt = pd.to_datetime(df['Date'], errors='coerce')
            df['Time'] = temp_dt.dt.strftime('%H:%M')
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
        st.error("Secrets Error.")
        st.stop()

    df_pv = pd.DataFrame()
    df_haiti = pd.DataFrame()
    sales_ready = haiti_ready = False

    # --- SIDEBAR & UPLOADS ---
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
                df_pv['Sold'] = (df_pv['Stock_prev'].fillna(0) - df_pv['Stock']).clip(lower=0)
                sales_ready = True
            if f_haiti:
                df_haiti = clean_data(f_haiti, "current quantity dressup haiti")
                haiti_ready = True

        st.sidebar.markdown("---")
        st.sidebar.subheader("⚡ Guest Sync")
        f_quick = st.sidebar.file_uploader("Daily Square Export", type=['xlsx'], key="quick")
        if f_quick and st.sidebar.button("🚀 Push to Guest Library"):
            with st.spinner("Syncing..."):
                df_q = clean_data(f_quick, "current quantity dressupht pv")
                old = get_at_data("Master_Inventory", BASE_ID, HEADERS)
                if not old.empty:
                    ids = old['id'].tolist()
                    for i in range(0, len(ids), 10): requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, params={"records[]": ids[i:i+10]})
                recs = [{"fields": {"Full Name": str(r['Full Name']), "SKU": str(r['SKU']), "Stock": int(r['Stock']), "Category": str(r['Category'])}} for _, r in df_q.iterrows()]
                for i in range(0, len(recs), 10): requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs[i:i+10]})
                st.sidebar.success("Updated!")
                time.sleep(1)
                st.rerun()

    st.title("🦱 Dressupht Intelligence")
    search = st.text_input("🔍 Global Search", placeholder="Wig name or SKU...")

    if curr_user == 'guest':
        tabs = st.tabs(["📋 Library"])
        with tabs[0]:
            data = get_at_data("Master_Inventory", BASE_ID, HEADERS)
            if not data.empty:
                view = data[['Full Name', 'Stock']]
                if search: view = view[view['Full Name'].str.contains(search, case=False)]
                st.dataframe(view, use_container_width=True, hide_index=True)
    else:
        # ALL TABS RESTORED
        tabs = st.tabs(["➕ Intake", "🕵️ Audit", "📊 Sales", "🔄 Compare", "🚚 Transfers", "🔥 Fast/Slow", "❌ OOS", "💰 Finance", "📋 Library"])

        with tabs[0]: # Intake
            with st.form("in_f", clear_on_submit=True):
                i_sku = st.text_input("Scan SKU").strip()
                q = st.number_input("Quantity Received", min_value=1, step=1)
                if st.form_submit_button("Sync Intake"):
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json={"records": [{"fields": {"Date": datetime.now().isoformat(), "SKU": i_sku, "Quantity": q, "User": curr_user}}]})
                    st.success("Logged!")
            ships = get_at_data("Shipments", BASE_ID, HEADERS)
            if not ships.empty: st.dataframe(ships, use_container_width=True, hide_index=True)

        with tabs[1]: # Audit (Improved)
            a_sku = st.text_input("Scan SKU to Audit", key="aud_sku").strip()
            if a_sku and not df_pv.empty:
                match = df_pv[df_pv['SKU'] == a_sku]
                if not match.empty: st.markdown(f"<div class='sku-match'>✅ Found: {match.iloc[0]['Full Name']}</div>", unsafe_allow_html=True)
            
            with st.form("aud_f", clear_on_submit=True):
                counter = st.selectbox("Who is counting?", ["Angelina", "David", "Annaelle", "Gerdine", "Kevin", "Darius", "Martilda", "Sebastien"])
                c1, c2, c3 = st.columns(3)
                m_q = c1.number_input("In Box", min_value=0, step=1)
                e_q = c2.number_input("Exposed", min_value=0, step=1)
                r_q = c3.number_input("Returns", min_value=0, step=1)
                if st.form_submit_button("Save Audit"):
                    total = m_q + e_q + r_q
                    sys = 0
                    if not df_pv.empty:
                        m = df_pv[df_pv['SKU'] == a_sku]
                        if not m.empty: sys = m.iloc[0]['Stock']
                    payload = {"records": [{"fields": {"Date": datetime.now().isoformat(), "SKU": a_sku, "Counter_Name": counter, "Manual_Qty": m_q, "Exposed_Qty": e_q, "Returns_Qty": r_q, "Total_Physical": total, "System_Stock": int(sys), "Discrepancy": int(total-sys), "User": curr_user}}]}
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json=payload)
                    st.success("Audit Recorded!")
            
            auds = get_at_data("Inventory_Audit", BASE_ID, HEADERS)
            if not auds.empty:
                if not df_pv.empty: auds = pd.merge(auds, df_pv[['SKU', 'Full Name']], on='SKU', how='left')
                st.dataframe(auds, use_container_width=True, hide_index=True)

        with tabs[2]: # Sales (Restored)
            if sales_ready: st.dataframe(df_pv[df_pv['Sold'] > 0][['Full Name', 'SKU', 'Stock_prev', 'Stock', 'Sold']], use_container_width=True, hide_index=True)
            else: st.info("Upload Saturday files.")

        with tabs[3]: # Compare (Restored)
            if haiti_ready and not df_pv.empty:
                comp = pd.merge(df_haiti[['SKU', 'Stock']], df_pv[['SKU', 'Full Name', 'Stock']], on='SKU', suffixes=('_haiti', '_pv'))
                st.dataframe(comp, use_container_width=True, hide_index=True)

        with tabs[4]: # Transfers (Restored)
            if haiti_ready and not df_pv.empty:
                trans = pd.merge(df_haiti[['SKU', 'Stock']], df_pv[['SKU', 'Full Name', 'Stock']], on='SKU', suffixes=('_haiti', '_pv'))
                st.dataframe(trans[(trans['Stock_haiti'] > 2) & (trans['Stock_pv'] < 1)], use_container_width=True, hide_index=True)

        with tabs[5]: # Fast/Slow (Restored)
            if sales_ready: st.table(df_pv.nlargest(10, 'Sold')[['Full Name', 'Sold']])

        with tabs[6]: # OOS (Restored)
            if not df_pv.empty: st.dataframe(df_pv[df_pv['Stock'] == 0][['Full Name', 'SKU']], use_container_width=True, hide_index=True)

        with tabs[7]: # Finance (Restored)
            if not df_pv.empty:
                df_pv['Value'] = df_pv['Stock'] * df_pv['Price']
                st.metric("Total Depot Value", f"${df_pv['Value'].sum():,.2f}")
                st.dataframe(df_pv[['Full Name', 'Stock', 'Price', 'Value']], use_container_width=True, hide_index=True)

        with tabs[8]: # Library
            lib = get_at_data("Master_Inventory", BASE_ID, HEADERS)
            if not lib.empty: st.dataframe(lib, use_container_width=True, hide_index=True)

elif st.session_state["authentication_status"] is False:
    st.error("Login failed.")
