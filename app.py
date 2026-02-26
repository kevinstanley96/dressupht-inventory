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
            # Always sort audits by newest first
            if table == "Inventory_Audit":
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
            df['Date_Only'] = temp_dt.dt.date
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
        st.error("Secrets Error. Check AIRTABLE_TOKEN and AIRTABLE_BASE_ID.")
        st.stop()

    df_pv = pd.DataFrame()
    df_haiti = pd.DataFrame()
    sales_ready = False

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

    st.title("🦱 Dressupht Intelligence")

    if curr_user == 'guest':
        tabs = st.tabs(["📋 Library"])
        # Guest logic omitted for brevity, same as before
    else:
        tabs = st.tabs(["➕ Intake", "🕵️ Audit", "📊 Sales", "🔄 Compare", "🚚 Transfers", "🔥 Fast/Slow", "❌ OOS", "💰 Finance", "📋 Library"])

        with tabs[1]: # --- AUDIT TAB WITH NAME LOOKUP ---
            st.subheader("🕵️ Physical Count Audit")
            
            # SKU CHECKER
            a_sku = st.text_input("Scan SKU to Audit").strip()
            wig_name_found = "Unknown SKU"
            
            if a_sku and not df_pv.empty:
                match = df_pv[df_pv['SKU'] == a_sku]
                if not match.empty:
                    wig_name_found = match.iloc[0]['Full Name']
                    st.markdown(f"<div class='sku-match'>✅ Found: {wig_name_found}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='sku-miss'>⚠️ SKU not in PV Square Export</div>", unsafe_allow_html=True)

            with st.form("aud_f", clear_on_submit=True):
                counter = st.selectbox("Who is counting?", ["Angelina", "David", "Annaelle", "Gerdine", "Kevin", "Darius", "Martilda", "Sebastien"])
                col_a, col_b, col_c = st.columns(3)
                m_qty = col_a.number_input("In Box/Stock", min_value=0, step=1)
                e_qty = col_b.number_input("Exposed (Outside)", min_value=0, step=1)
                r_qty = col_c.number_input("Returns", min_value=0, step=1)
                
                if st.form_submit_button("Log Audit Count", use_container_width=True):
                    if a_sku:
                        total_phys = m_qty + e_qty + r_qty
                        sys_stock = 0
                        discrepancy = 0
                        if not df_pv.empty:
                            match = df_pv[df_pv['SKU'] == a_sku]
                            if not match.empty:
                                sys_stock = match.iloc[0]['Stock']
                                discrepancy = total_phys - sys_stock

                        payload = {"records": [{"fields": {
                            "Date": datetime.now().isoformat(), 
                            "SKU": a_sku, 
                            "Counter_Name": counter,
                            "Manual_Qty": m_qty, 
                            "Exposed_Qty": e_qty, 
                            "Returns_Qty": r_qty,
                            "Total_Physical": total_phys, 
                            "System_Stock": int(sys_stock), 
                            "Discrepancy": int(discrepancy), 
                            "User": curr_user
                        }}]}
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json=payload)
                        st.success(f"Recorded {wig_name_found}!")
                        time.sleep(1)
                        st.rerun()

            st.write("### 📝 Recent Audit History")
            auds = get_at_data("Inventory_Audit", BASE_ID, HEADERS)
            if not auds.empty:
                # Merge with df_pv to get names in the history table
                if not df_pv.empty:
                    auds = pd.merge(auds, df_pv[['SKU', 'Full Name']], on='SKU', how='left')
                
                # Column check to prevent errors if Airtable is missing fields
                display_cols = ['Time', 'Full Name', 'SKU', 'Counter_Name', 'System_Stock', 'Total_Physical', 'Discrepancy']
                existing = [c for c in display_cols if c in auds.columns]
                st.dataframe(auds[existing], use_container_width=True, hide_index=True)

        # Rest of the tabs (Sales, Finance, etc.) remain as per the previous full version
        with tabs[7]: # Finance
            if not df_pv.empty:
                df_pv['Value'] = df_pv['Stock'] * df_pv['Price']
                st.metric("Total Depot Value", f"${df_pv['Value'].sum():,.2f}")
                st.dataframe(df_pv[['Full Name', 'Stock', 'Price', 'Value']], use_container_width=True, hide_index=True)

elif st.session_state["authentication_status"] is False:
    st.error("Login failed.")
