import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time

# 1. Page Config
st.set_page_config(page_title="Dressupht ERP", layout="wide")

# --- AUTHENTICATION CONFIG ---
usernames_list = [
    "Djessie", "Kevin", "Casimir", "Melchisedek", "David", "Darius", "Eliada",
    "Sebastien", "Guirlene", "Carmela", "Angelina", "Tamara", "Dorotheline", 
    "Sarah", "Valerie", "Saouda", "Marie France", "Carelle", "Annaelle", 
    "Gerdine", "Martilda"
]

# Initialize credentials with temporary passwords
credentials = {
    "usernames": {
        u: {"name": u, "password": "temppassword123"} for u in usernames_list
    }
}
# Admin Override
credentials['usernames']['Kevin']['password'] = "The$100$Raven"

# Correct 0.3.1 Initialization
authenticator = stauth.Authenticate(
    credentials, 
    "inventory_cookie", 
    "abcdef123456_key", # Secure signature key
    30
)

# --- LOGIN INTERFACE ---
# Fix for ValueError/TypeError: location must be a keyword argument
authentication_status = authenticator.login(location='main')

if st.session_state["authentication_status"]:
    username = st.session_state["username"]
    authenticator.logout('Logout', 'sidebar')

    # 2. API SETUP
    try:
        AIR_TOKEN = st.secrets["AIRTABLE_TOKEN"]
        BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
        HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}
    except:
        st.error("Missing Airtable Secrets in Streamlit Cloud!")
        st.stop()

    # --- HELPER: GET USER ROLE ---
    def get_user_role(user):
        try:
            url = f"https://api.airtable.com/v0/{BASE_ID}/Role"
            params = {"filterByFormula": f"{{User Name}}='{user}'"}
            res = requests.get(url, headers=HEADERS, params=params)
            if res.status_code == 200:
                recs = res.json().get('records', [])
                if recs:
                    return recs[0]['fields'].get('Access Level', 'Staff')
            return 'Staff'
        except: return 'Staff'

    user_role = get_user_role(username)
    st.sidebar.success(f"Welcome, {username}")
    st.sidebar.info(f"Role: {user_role}")

    # --- DATA LOADING HELPERS ---
    def clean_data(file):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip().lower() for c in df.columns]
        # Mapping for Square Export
        mapping = {'item name': 'Wig Name', 'variation name': 'Style', 'sku': 'SKU', 'price': 'Price'}
        df = df.rename(columns=mapping)
        df['SKU'] = df['SKU'].astype(str).str.strip()
        df['Full Name'] = df['Wig Name'] + " (" + df['Style'].fillna('') + ")"
        return df

    # --- DYNAMIC TABS BASED ON ROLE ---
    if user_role == 'Admin':
        tabs = st.tabs(["📋 Library", "🕵️ Audit", "➕ Intake", "📊 Sales", "💰 Finance", "🛡️ Roles", "🔑 Password"])
    elif user_role == 'Manager':
        tabs = st.tabs(["📋 Library", "🕵️ Audit", "➕ Intake", "🔑 Password"])
    else:
        tabs = st.tabs(["📋 Library", "🔑 Password"])

    # --- TAB 1: LIBRARY (Visible to All) ---
    with tabs[0]:
        st.subheader("📦 Master Inventory")
        # Global Search
        search = st.text_input("🔍 Search Wig or SKU")
        # Note: In production, fetch from Airtable Master_Inventory table here
        st.info("Upload current data in the sidebar to populate this view.")

    # --- TAB 2: AUDIT (Admin & Manager Only) ---
    if user_role in ['Admin', 'Manager']:
        with tabs[1]:
            st.subheader("🕵️ Physical Inventory Audit")
            a_sku = st.text_input("Scan SKU to Audit", placeholder="Enter or scan SKU...").strip()
            
            with st.form("audit_form"):
                col1, col2 = st.columns(2)
                with col1:
                    m_qty = st.number_input("In Box/Shelf (Max 50)", min_value=0, step=1)
                    e_qty = st.number_input("Exposed (Outside)", min_value=0, step=1)
                with col2:
                    b_qty = st.number_input("Big Depot Storage", min_value=0, step=1)
                    r_qty = st.number_input("Returns", min_value=0, step=1)
                
                reason = st.selectbox("Return Reason (if any)", ["N/A", "Damaged", "Exchange", "Credit Refund"])
                
                if st.form_submit_button("Submit Audit"):
                    total_phys = m_qty + e_qty + b_qty + r_qty
                    
                    # 1. Log to Audit Table
                    audit_data = {
                        "records": [{"fields": {
                            "Date": datetime.now().isoformat(),
                            "SKU": a_sku,
                            "Counter_Name": username,
                            "Manual_Qty": m_qty,
                            "Exposed_Qty": e_qty,
                            "Big_Depot_Qty": b_qty,
                            "Returns_Qty": r_qty,
                            "Total_Physical": total_phys,
                            "User": username
                        }}]
                    }
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json=audit_data)
                    
                    # 2. Log Damaged separately if needed
                    if reason == "Damaged" and r_qty > 0:
                        dmg_data = {
                            "records": [{"fields": {
                                "Date": datetime.now().isoformat(),
                                "SKU": a_sku,
                                "Quantity": r_qty,
                                "Reason": "Damaged",
                                "User": username
                            }}]
                        }
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Damaged_Stock", headers=HEADERS, json=dmg_data)
                        st.warning(f"Logged {r_qty} units as DAMAGED.")

                    st.success(f"Audit Saved! Total Physical Count: {total_phys}")

    # --- LAST TAB: PASSWORD RESET ---
    with tabs[-1]:
        st.subheader("🔑 Change Your Password")
        try:
            if authenticator.reset_password(username, 'Reset Password'):
                st.success('Password changed successfully!')
        except Exception as e:
            st.error(f"Error: {e}")

# --- LOGIN HANDLING ---
elif st.session_state["authentication_status"] is False:
    st.error('Username/password is incorrect')
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your username and password')
