import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time

# 1. Page Config
st.set_page_config(page_title="Dressupht ERP", layout="wide")

# --- AUTHENTICATION CONFIG ---
# Note: In a production app, you would store these hashes in Airtable.
# For now, we use a basic config. Passwords will be 'temp123' until they change them.
usernames = [
    "Djessie", "Kevin", "Casimir", "Melchisedek", "David", "Darius", "Eliada",
    "Sebastien", "Guirlene", "Carmela", "Angelina", "Tamara", "Dorotheline", 
    "Sarah", "Valerie", "Saouda", "Marie France", "Carelle", "Annaelle", 
    "Gerdine", "Martilda"
]

credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames}}
# Manual override for Admin
credentials['usernames']['Kevin']['password'] = "The$100$Raven" 

authenticator = stauth.Authenticate(
    credentials, "inventory_cookie", "signature_key", 30
)

name, authentication_status, username = authenticator.login("Login", "main")

# --- MAIN LOGIC ---
if authentication_status:
    authenticator.logout('Logout', 'sidebar')
    
    # 2. API SETUP
    try:
        AIR_TOKEN = st.secrets["AIRTABLE_TOKEN"]
        BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
        HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}
    except:
        st.error("Missing Airtable Secrets!")
        st.stop()

    # 3. GET USER ROLE FROM AIRTABLE
    def get_user_role(user):
        res = requests.get(f"https://api.airtable.com/v0/{BASE_ID}/Role?filterByFormula={{User Name}}='{user}'", headers=HEADERS)
        if res.status_code == 200:
            recs = res.json().get('records', [])
            return recs[0]['fields'].get('Access Level', 'Staff') if recs else 'Staff'
        return 'Staff'

    user_role = get_user_role(username)
    st.sidebar.info(f"Logged in as: {username} | Role: {user_role}")

    # --- SIDEBAR DATE & SYNC ---
    if user_role in ['Admin', 'Manager']:
        st.sidebar.subheader("📅 Data Update")
        sync_date = st.sidebar.date_input("Data effective date", date.today())
        f_pv = st.sidebar.file_uploader("Upload Square Export", type=['xlsx'])
        
        if f_pv and st.sidebar.button("🚀 Update Master Inventory"):
            # (Logic for cleaning and pushing to Master_Inventory table)
            st.sidebar.success(f"Database updated for {sync_date}")

    # --- TABS BASED ON ROLES ---
    if user_role == 'Admin':
        tabs = st.tabs(["📋 Library", "🕵️ Audit", "➕ Intake", "📊 Sales", "💰 Finance", "🛠️ Admin", "🔄 Reset Password"])
    elif user_role == 'Manager':
        tabs = st.tabs(["📋 Library", "🕵️ Audit", "➕ Intake", "🔄 Reset Password"])
    else:
        tabs = st.tabs(["📋 Library", "🔄 Reset Password"])

    # --- AUDIT TAB (WITH BIG DEPOT) ---
    if user_role in ['Admin', 'Manager']:
        with tabs[1]:
            st.subheader("🕵️ Physical Inventory Audit")
            # 1. Verification Section
            a_sku = st.text_input("Scan SKU to Audit").strip()
            
            with st.form("audit_form_2.0", clear_on_submit=True):
                col1, col2 = st.columns(2)
                m_qty = col1.number_input("In Box/Shelf (Max 50)", min_value=0)
                b_qty = col2.number_input("Big Depot Storage", min_value=0)
                e_qty = col1.number_input("Exposed (Outside)", min_value=0)
                r_qty = col2.number_input("Returns", min_value=0)
                
                reason = st.selectbox("If Return, what is the reason?", ["N/A", "Damaged", "Exchange", "Credit Refund"])
                
                if st.form_submit_button("Log Audit"):
                    total_phys = m_qty + b_qty + e_qty + r_qty
                    
                    # Logic to push to Inventory_Audit
                    audit_payload = {
                        "records": [{"fields": {
                            "Date": datetime.now().isoformat(),
                            "SKU": a_sku,
                            "Counter_Name": username,
                            "Manual_Qty": m_qty,
                            "Big_Depot_Qty": b_qty,
                            "Exposed_Qty": e_qty,
                            "Returns_Qty": r_qty,
                            "Total_Physical": total_phys,
                            "User": username
                        }}]
                    }
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json=audit_payload)
                    
                    # 2. Damaged Stock Logic
                    if reason == "Damaged":
                        damage_payload = {
                            "records": [{"fields": {
                                "Date": datetime.now().isoformat(),
                                "SKU": a_sku,
                                "Quantity": r_qty,
                                "Reason": "Damaged",
                                "User": username
                            }}]
                        }
                        requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Damaged_Stock", headers=HEADERS, json=damage_payload)
                        st.warning("Item logged in Damaged Table.")

                    st.success(f"Audit Complete. Total Found: {total_phys}")

    # --- PASSWORD RESET TAB ---
    with tabs[-1]:
        st.subheader("🔑 Security Settings")
        try:
            if authenticator.reset_password(username, 'Reset Password'):
                st.success('Password modified successfully')
        except Exception as e:
            st.error(e)

elif authentication_status is False:
    st.error('Username/password is incorrect')
elif authentication_status is None:
    st.warning('Please enter your username and password')
