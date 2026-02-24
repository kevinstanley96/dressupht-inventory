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

# --- BULLETPROOF HELPER FUNCTION ---
def get_at_data(table, base_id, headers):
    try:
        url = f"https://api.airtable.com/v0/{base_id}/{table}"
        res = requests.get(url, headers=headers)
        
        if res.status_code == 200:
            records = res.json().get('records', [])
            if not records:
                return pd.DataFrame()
            
            # Flatten Airtable response
            df = pd.DataFrame([dict(r['fields'], id=r['id']) for r in records])
            
            # Formatting Date/Time if they exist (for Shipments/Audit tables)
            if 'Date' in df.columns:
                temp_dt = pd.to_datetime(df['Date'], errors='coerce')
                df['Time'] = temp_dt.dt.strftime('%H:%M')
                df['Date'] = temp_dt.dt.date
            
            # Handling "Last Updated" formatting if it exists
            if 'Last Updated' in df.columns:
                df['Last Updated'] = pd.to_datetime(df['Last Updated']).dt.strftime('%m/%d %H:%M')
                
            return df
        else:
            st.error(f"Airtable Error {res.status_code}: {res.text}")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"App Error: {e}")
        return pd.DataFrame()

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
    return df

# --- MAIN APP ---
if st.session_state["authentication_status"]:
    authenticator.logout('Logout', 'sidebar')
    curr_user = st.session_state['username']
    
    try:
        AIR_TOKEN = st.secrets["AIRTABLE_TOKEN"]
        BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
        HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}
    except:
        st.error("Missing Secrets!")
        st.stop()

    # --- ADMIN SIDEBAR ---
    if curr_user != 'guest':
        st.sidebar.subheader("⚡ Live Guest Sync")
        quick_file = st.sidebar.file_uploader("Upload Square Export", type=['xlsx'])
        if quick_file:
            df_quick = clean_data(quick_file, "current quantity dressupht pv")
            if st.sidebar.button("🚀 Sync Now"):
                with st.spinner("Updating Cloud..."):
                    # 1. Clear old
                    old_data = get_at_data("Master_Inventory", BASE_ID, HEADERS)
                    if not old_data.empty:
                        old_ids = old_data['id'].tolist()
                        for i in range(0, len(old_ids), 10):
                            requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, params={"records[]": old_ids[i:i+10]})
                    
                    # 2. Upload New
                    new_recs = [{"fields": {"Full Name": str(r['Full Name']), "SKU": str(r['SKU']), "Stock": int(r['Stock']), "Category": str(r['Category'])}} for _, r in df_quick.iterrows()]
                    for i in range(0, len(new_recs), 10):
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": new_recs[i:i+10]})
                    st.sidebar.success("Done!")
                    time.sleep(1)
                    st.rerun()

    st.title("🦱 Dressupht Intelligence")
    search = st.text_input("🔍 Search Inventory")

    # --- TABS ---
    if curr_user == 'guest':
        tabs = st.tabs(["📋 Library"])
        with tabs[0]:
            st.subheader("PV Depot Inventory")
            # We fetch the data directly here
            data = get_at_data("Master_Inventory", BASE_ID, HEADERS)
            
            if not data.empty:
                # Remove internal IDs and sensitive columns if they exist
                to_hide = ['id', 'Price', 'Value']
                display_df = data.drop(columns=[c for c in to_hide if c in data.columns])
                
                # Apply Search
                if search:
                    display_df = display_df[display_df.apply(lambda row: search.lower() in row.astype(str).str.lower().values, axis=1)]
                
                st.dataframe(display_df, use_container_width=True)
            else:
                st.warning("No data found in Master_Inventory. Admin needs to Sync.")
    else:
        # Admin Tabs
        tabs = st.tabs(["➕ Intake", "🕵️ Audit", "📋 Admin Library"])
        with tabs[2]:
            st.subheader("Cloud Library (Internal)")
            admin_data = get_at_data("Master_Inventory", BASE_ID, HEADERS)
            st.dataframe(admin_data, use_container_width=True)

elif st.session_state["authentication_status"] is False:
    st.error("Login Failed")
