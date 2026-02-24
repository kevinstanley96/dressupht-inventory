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
    .stButton>button {
        height: 3em;
        border-radius: 10px;
        font-weight: bold;
        width: 100%;
    }
    /* Hide the row numbers globally for a cleaner look */
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
    try:
        url = f"https://api.airtable.com/v0/{base_id}/{table}"
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            records = res.json().get('records', [])
            if not records: return pd.DataFrame()
            df = pd.DataFrame([dict(r['fields'], id=r['id']) for r in records])
            
            if 'Date' in df.columns:
                temp_dt = pd.to_datetime(df['Date'], errors='coerce')
                df['Time'] = temp_dt.dt.strftime('%H:%M')
                df['Date'] = temp_dt.dt.date
            
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

    if curr_user != 'guest':
        st.sidebar.subheader("📁 Saturday Center")
        f_pv = st.sidebar.file_uploader("THIS Saturday (PV)", type=['xlsx'])
        f_pv_prev = st.sidebar.file_uploader("LAST Saturday (PV)", type=['xlsx'])
        f_haiti = st.sidebar.file_uploader("Dressup Haiti", type=['xlsx'])
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("⚡ 3-Hour Sync")
        f_quick = st.sidebar.file_uploader("Daily Square Export", type=['xlsx'], key="quick")

        if f_pv:
            df_pv = clean_data(f_pv, "current quantity dressupht pv")
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

    # --- HEADER & SEARCH ---
    st.title("🦱 Dressupht Intelligence")
    search = st.text_input("🔍 Search Inventory", placeholder="Search style name...")

    # --- ROLE-BASED TABS ---
    if curr_user == 'guest':
        tabs = st.tabs(["📋 Library"])
    else:
        tabs = st.tabs(["➕ Intake", "🕵️ Audit", "📊 Sales", "🔄 Compare", "🚚 Transfers", "🔥 Fast/Slow", "❌ OOS", "💰 Finance", "📋 Library", "📈 Analytics"])

    # --- GUEST TAB LOGIC ---
    if curr_user == 'guest':
        with tabs[0]:
            data = get_at_data("Master_Inventory", BASE_ID, HEADERS)
            if not data.empty:
                # Optimized Column Selection for Guest
                cols = [c for c in ['Full Name', 'Stock', 'Last Updated Display'] if c in data.columns]
                display_df = data[cols].copy()
                
                if search:
                    display_df = display_df[display_df['Full Name'].str.contains(search, case=False)]
                
                # Mobile Optimized Dataframe
                st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Full Name": st.column_config.TextColumn("Wig Style", width="large"),
                        "Stock": st.column_config.NumberColumn("Available", format="%d 📦"),
                        "Last Updated Display": st.column_config.TextColumn("Synced", width="small")
                    }
                )
                
                # Download button for Excel/Mobile use
                csv = display_df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Inventory (Excel)", data=csv, file_name="inventory.csv", mime="text/csv")
            else:
                st.warning("Inventory update in progress. Please wait.")

    # --- ADMIN/STAFF TAB LOGIC ---
    else:
        with tabs[0]: # Intake
            i_sku = st.text_input("Scan for Intake").strip()
            with st.form("in_f"):
                q = st.number_input("Qty", 1)
                if st.form_submit_button("Sync Intake"):
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json={"records": [{"fields": {"Date": datetime.now().isoformat(), "SKU": i_sku, "Quantity": q, "User": curr_user}}]})
                    st.success("Synced")
            ships = get_at_data("Shipments", BASE_ID, HEADERS)
            if not ships.empty: st.dataframe(ships.drop(columns=['id']), use_container_width=True, hide_index=True)

        with tabs[1]: # Audit
            a_sku = st.text_input("Scan for Audit").strip()
            with st.form("aud"):
                m = st.number_input("Actual Qty Found", 0)
                if st.form_submit_button("Log Audit"):
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json={"records": [{"fields": {"Date": datetime.now().isoformat(), "SKU": a_sku, "Manual_Qty": m, "User": curr_user}}]})
                    st.rerun()
            aud = get_at_data("Inventory_Audit", BASE_ID, HEADERS)
            if not aud.empty: st.dataframe(aud.drop(columns=['id']), use_container_width=True, hide_index=True)

        with tabs[2]: # Sales
            if sales_ready:
                st.dataframe(df_pv[df_pv['Sold'] > 0], use_container_width=True, hide_index=True)
            else: st.info("Upload Saturday files to see sales.")

        with tabs[6]: # OOS
            if not df_pv.empty:
                st.dataframe(df_pv[df_pv['Stock'] == 0], use_container_width=True, hide_index=True)

        with tabs[8]: # Internal Library
            st.subheader("Cloud Master Library")
            lib_data = get_at_data("Master_Inventory", BASE_ID, HEADERS)
            if not lib_data.empty:
                st.dataframe(lib_data.drop(columns=['id'], errors='ignore'), use_container_width=True, hide_index=True)

elif st.session_state["authentication_status"] is False:
    st.error("Login failed.")

