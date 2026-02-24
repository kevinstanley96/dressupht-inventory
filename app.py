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

authenticator = stauth.Authenticate(
    config['credentials'], 
    config['cookie']['name'], 
    config['cookie']['key'], 
    config['cookie']['expiry_days']
)

authenticator.login()

# --- HELPER FUNCTIONS ---
def get_at_data(table, base_id, headers):
    try:
        url = f"https://api.airtable.com/v0/{base_id}/{table}"
        # Sorting logic: Master_Inventory by Name, others by Date
        params = {"sort[0][field]": "Wig Name", "sort[0][direction]": "asc"} if table == "Master_Inventory" else {"sort[0][field]": "Date", "sort[0][direction]": "desc"}
        res = requests.get(url, headers=headers, params=params)
        
        if res.status_code == 200:
            data = res.json().get('records', [])
            if not data: return pd.DataFrame()
            df = pd.DataFrame([dict(r['fields'], id=r['id']) for r in data])
            
            if 'Date' in df.columns:
                temp_dt = pd.to_datetime(df['Date'])
                df['Time'] = temp_dt.dt.strftime('%H:%M')
                df['Date'] = temp_dt.dt.date
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

# --- MAIN APP ---
if st.session_state["authentication_status"]:
    authenticator.logout('Logout', 'sidebar')
    curr_user = st.session_state['username']
    st.sidebar.title(f"Welcome {st.session_state['name']}")

    try:
        AIR_TOKEN = st.secrets["AIRTABLE_TOKEN"]
        BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
        HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}
    except:
        st.error("Missing Airtable Secrets.")
        st.stop()

    # --- ADMIN SIDEBAR: LIVE SYNC LOGIC ---
    df_pv = pd.DataFrame()
    if curr_user != 'guest':
        st.sidebar.subheader("📅 Saturday Reports")
        file_pv = st.sidebar.file_uploader("THIS Saturday (PV)", type=['xlsx'])
        if file_pv: df_pv = clean_data(file_pv, "current quantity dressupht pv")

        st.sidebar.markdown("---")
        st.sidebar.subheader("⚡ Live Guest Sync")
        st.sidebar.caption("Update target: 08:10, 11:10, 14:10...")
        quick_file = st.sidebar.file_uploader("Upload Square Export", type=['xlsx'], key="quick")
        
        if quick_file:
            df_quick = clean_data(quick_file, "current quantity dressupht pv")
            if st.sidebar.button("🚀 Sync to Guest Library"):
                with st.spinner("🔄 Wiping old data and uploading new stock..."):
                    # 1. Get and Delete all existing records
                    old_data = get_at_data("Master_Inventory", BASE_ID, HEADERS)
                    if not old_data.empty:
                        old_ids = old_data['id'].tolist()
                        for i in range(0, len(old_ids), 10):
                            batch = old_ids[i:i+10]
                            requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, params={"records[]": batch})
                    
                    # 2. Upload New Records in batches of 10
                    new_recs = []
                    for _, row in df_quick.iterrows():
                        new_recs.append({"fields": {
                            "Full Name": str(row['Full Name']),
                            "SKU": str(row['SKU']),
                            "Stock": int(row['Stock']),
                            "Category": str(row['Category'])
                        }})
                    
                    for i in range(0, len(new_recs), 10):
                        batch = new_recs[i:i+10]
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": batch})
                    
                    st.sidebar.success(f"✅ Library Live! Updated at {datetime.now().strftime('%H:%M')}")

    st.title("🦱 Dressupht Intelligence")
    search = st.text_input("🔍 Search Name or SKU")

    # --- TABS ---
    if curr_user == 'guest':
        tabs = st.tabs(["📋 Library"])
        with tabs[0]:
            st.subheader("PV Depot Inventory")
            cloud_inv = get_at_data("Master_Inventory", BASE_ID, HEADERS)
            if not cloud_inv.empty:
                # Security: ensure Guest never sees Price or internal ID
                guest_view = cloud_inv.drop(columns=['Price', 'id'], errors='ignore')
                if search:
                    guest_view = guest_view[guest_view['Full Name'].str.contains(search, case=False) | guest_view['SKU'].str.contains(search, case=False)]
                st.dataframe(guest_view, use_container_width=True)
            else:
                st.info("Inventory update in progress. Please wait.")

    else:
        # ADMIN / STAFF VIEW
        tabs = st.tabs(["➕ Intake", "🕵️ Audit", "📊 Sales", "📋 Full Library", "📈 Analytics"])
        
        with tabs[0]: # Intake
            st.subheader("Cloud Shipment Record")
            i_sku = st.text_input("Scan SKU", key="i_scan").strip()
            with st.form("in_form", clear_on_submit=True):
                q_i = st.number_input("Qty Received", min_value=1)
                if st.form_submit_button("Sync to Cloud"):
                    p = {"records": [{"fields": {"Date": datetime.now().isoformat(), "SKU": i_sku, "Quantity": q_i, "User": curr_user}}]}
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=p)
                    st.success("Intake Recorded")
            ships = get_at_data("Shipments", BASE_ID, HEADERS)
            if not ships.empty: st.dataframe(ships.drop(columns=['id']), use_container_width=True)

        with tabs[3]: # Admin Library
            st.subheader("Internal Inventory (Full Data)")
            if not df_pv.empty:
                st.dataframe(df_pv, use_container_width=True)
            else:
                st.warning("Upload 'THIS Saturday' file in sidebar to see full details.")

# Footer auth handling
elif st.session_state["authentication_status"] is False:
    st.error("Username/password is incorrect")
elif st.session_state["authentication_status"] is None:
    st.warning("Please enter credentials")
