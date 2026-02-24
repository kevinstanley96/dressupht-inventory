import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import date, datetime

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

# Render Login Widget
authenticator.login()

# --- HELPER FUNCTIONS ---
def get_at_data(table, base_id, headers):
    try:
        url = f"https://api.airtable.com/v0/{base_id}/{table}"
        params = {"sort[0][field]": "Date", "sort[0][direction]": "desc"}
        res = requests.get(url, headers=headers, params=params)
        
        if res.status_code == 200:
            data = res.json().get('records', [])
            if not data: return pd.DataFrame()
            df = pd.DataFrame([dict(r['fields'], id=r['id']) for r in data])
            if 'Date' in df.columns:
                temp_date = pd.to_datetime(df['Date'])
                df['Time'] = temp_date.dt.strftime('%H:%M') # 24h format as requested
                df['Date'] = temp_date.dt.date
            return df
        return pd.DataFrame()
    except Exception: return pd.DataFrame()

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

# --- MAIN APP LOGIC ---
if st.session_state["authentication_status"]:
    authenticator.logout('Logout', 'sidebar')
    curr_user = st.session_state['username']
    st.sidebar.title(f"Welcome {st.session_state['name']}")

    # Airtable Config
    try:
        AIR_TOKEN = st.secrets["AIRTABLE_TOKEN"]
        BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
        HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}
    except:
        st.error("Secrets Error: Please check your configuration.")
        st.stop()

    # --- DATA LOADING ---
    # Hide uploaders for Guests to keep it clean
    if curr_user != 'guest':
        st.sidebar.subheader("📁 Data Upload Center")
        file_pv = st.sidebar.file_uploader("📍 THIS Saturday (PV)", type=['xlsx'])
        file_pv_prev = st.sidebar.file_uploader("🕒 LAST Saturday (PV)", type=['xlsx'])
        file_haiti = st.sidebar.file_uploader("🌐 Dressup Haiti", type=['xlsx'])
    else:
        file_pv = st.sidebar.file_uploader("📍 Load PV Inventory", type=['xlsx'])
        file_pv_prev, file_haiti = None, None

    df_pv = pd.DataFrame()
    haiti_active = sales_ready = False
    sku_to_name = sku_to_stock = sku_to_cat = {}

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
        else: df_pv['Sold'] = 0
        
        if file_haiti:
            df_haiti = clean_data(file_haiti, "current quantity dressup haiti")
            haiti_active = True

    st.title("🦱 Dressupht Pv: Intelligence Center")
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

    # --- TAB CONTENT LOGIC ---
    if curr_user != 'guest':
        with tabs[0]: # INTAKE
            st.subheader("Cloud Shipment Record")
            i_sku = st.text_input("Scan SKU for Intake", key="intake_scan").strip()
            det_n = sku_to_name.get(i_sku, "Unknown Item")
            if i_sku: st.success(f"Item: {det_n}")
            with st.form("in_form", clear_on_submit=True):
                d_i = st.date_input("Date", value=date.today())
                q_i = st.number_input("Qty Received", min_value=1)
                if st.form_submit_button("Sync Intake"):
                    p = {"records": [{"fields": {"Date": datetime.now().isoformat(), "SKU": i_sku, "Name": det_n, "Quantity": q_i, "User": st.session_state['name']}}]}
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=p)
                    st.rerun()
            ship_data = get_at_data("Shipments", BASE_ID, HEADERS)
            if not ship_data.empty: st.dataframe(ship_data.drop(columns=['id']), use_container_width=True)

        with tabs[1]: # AUDIT
            st.subheader("🕵️ Physical Inventory Audit")
            staff_list = ["Select Counter...", "Angelina", "Gerdine", "Annaelle", "David", "Kevin"]
            selected_staff = st.selectbox("Who is counting?", options=staff_list)
            a_sku = st.text_input("Scan SKU for Audit", key="audit_scan").strip()
            if a_sku:
                s_qty, a_name, a_cat = sku_to_stock.get(a_sku, 0), sku_to_name.get(a_sku, "Unknown"), sku_to_cat.get(a_sku, "Uncategorized")
                st.metric("Item", a_name)
                with st.form("aud_form", clear_on_submit=True):
                    c1, c2, c3 = st.columns(3)
                    m_qty = c1.number_input("Depot Qty", min_value=0, step=1)
                    e_qty = c2.number_input("Mannequin Qty", min_value=0, step=1)
                    r_qty = c3.number_input("Returns", min_value=0, step=1)
                    total_p = m_qty + e_qty + r_qty
                    if st.form_submit_button("Log Audit"):
                        if selected_staff != "Select Counter...":
                            fields = {"Date": datetime.now().isoformat(), "SKU": a_sku, "Name": a_name, "Category": a_cat, "System_Qty": int(s_qty), "Manual_Qty": int(m_qty), "Mannequin": int(e_qty), "Returns": int(r_qty), "Diff": int(total_p - s_qty), "User": selected_staff}
                            requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json={"records": [{"fields": fields}]})
                            st.rerun()
            aud_hist = get_at_data("Inventory_Audit", BASE_ID, HEADERS)
            if not aud_hist.empty: st.dataframe(aud_hist.drop(columns=['id']), use_container_width=True)

        # Tabs 2-7 follow similar patterns for staff (Sales, Compare, etc.)
        # [Remaining tabs 2-7 logic goes here - omitted for brevity but should be kept in your file]

    # --- THE LIBRARY TAB (Accessed by Guest and Staff/Admin) ---
    # Guest sees it at tabs[0], others at tabs[8]
    lib_idx = 0 if curr_user == 'guest' else 8
    with tabs[lib_idx]:
        st.subheader("📋 PV Depot Library")
        if not df_pv.empty:
            view_df = df_pv.copy()
            # 🛡️ SECURITY: Remove sensitive data for Guest
            if curr_user == 'guest':
                cols_to_drop = [c for c in ['Price', 'Value', 'Sold', 'Stock_prev'] if c in view_df.columns]
                view_df = view_df.drop(columns=cols_to_drop)
            
            st.dataframe(get_view(view_df), use_container_width=True)
        else:
            st.info("Please upload the PV Inventory file in the sidebar.")

    # --- ANALYTICS TAB (Staff/Admin Only) ---
    if curr_user != 'guest':
        with tabs[9]:
            st.subheader("📈 Shipment History")
            at_ship = get_at_data("Shipments", BASE_ID, HEADERS)
            if not at_ship.empty:
                sel_s = st.selectbox("Pick SKU", at_ship['SKU'].unique())
                sh = at_ship[at_ship['SKU'] == sel_s]
                st.table(sh[['Date', 'Time', 'Quantity', 'User']])

elif st.session_state["authentication_status"] is False:
    st.error("Invalid Credentials")
