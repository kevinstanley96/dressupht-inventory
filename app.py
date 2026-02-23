import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection  # Added for cloud sync
import streamlit_authenticator as stauth
import os
from datetime import date
import yaml
from yaml.loader import SafeLoader

# --- 1. USER AUTHENTICATION SETUP ---
config = {
    'credentials': {
        'usernames': {
            'kevin': {
                'name': 'Dressup Haiti Admin',
                'password': 'The$100$Raven' 
            },
            'staff1': {
                'name': 'Inventory Manager',
                'password': 'secretpassword456'
            }
        }
    },
    'cookie': {
        'expiry_days': 30,
        'key': 'inventory_signature_key',
        'name': 'inventory_cookie'
    }
}

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

login_data = authenticator.login()

if st.session_state["authentication_status"] == False:
    st.error("Username/password is incorrect")
elif st.session_state["authentication_status"] == None:
    st.warning("Please enter your username and password")
elif st.session_state["authentication_status"]:
    
    authenticator.logout('Logout', 'sidebar')
    st.sidebar.title(f"Welcome {st.session_state['name']}")

    # --- 2. GOOGLE SHEETS CONNECTION ---
    # This replaces the LOG_FILE for cross-device syncing
    conn = st.connection("gsheets", type=GSheetsConnection)

    def clean_data(file, location_col_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip().lower() for c in df.columns]
        needed = {
            'item name': 'Wig Name', 'variation name': 'Style', 
            'sku': 'SKU', 'price': 'Price', 'categories': 'Category',
            location_col_name.lower(): 'Stock'
        }
        existing = [c for c in needed.keys() if c in df.columns]
        df = df[existing].copy()
        df.columns = [needed[c] for c in existing]
        if 'Category' not in df.columns: df['Category'] = 'Uncategorized'
        df = df.dropna(subset=['SKU'])
        df['SKU'] = df['SKU'].astype(str).str.strip()
        df['Full Name'] = df['Wig Name'] + " (" + df['Style'].fillna('') + ")"
        return df

    # --- 3. MAIN APP LOGIC ---
    st.title("🦱 Dressupht Pv: Secure Inventory")

    col_u1, col_u2, col_u3 = st.columns(3)
    file_pv = col_u1.file_uploader("📍 THIS Saturday (PV)", type=['xlsx'])
    file_pv_prev = col_u2.file_uploader("🕒 LAST Saturday (PV)", type=['xlsx'])
    file_haiti = col_u3.file_uploader("🌐 Dressup Haiti", type=['xlsx'])

    if file_pv:
        df_pv = clean_data(file_pv, "current quantity dressupht pv")
        sku_to_name = dict(zip(df_pv['SKU'], df_pv['Full Name']))

        t1, t2 = st.tabs(["➕ Shipment Intake", "📋 View All Stock"])

        with t1:
            st.subheader("Record New Shipment")
            input_sku = st.text_input("SKU Number").strip()
            detected_name = sku_to_name.get(input_sku, None)
            
            if input_sku and detected_name:
                st.success(f"Item: {detected_name}")

            # Pull existing data from Google Sheets
            try:
                existing_data = conn.read(ttl=0) # ttl=0 ensures it pulls the latest info
            except:
                existing_data = pd.DataFrame(columns=["Date", "SKU", "Name", "Quantity", "User"])

            with st.form("intake_form", clear_on_submit=True):
                qty = st.number_input("Quantity", min_value=1)
                if st.form_submit_button("✅ Save Entry"):
                    if detected_name:
                        # Prepare new row
                        new_row = pd.DataFrame([{
                            "Date": str(date.today()), 
                            "SKU": input_sku, 
                            "Name": detected_name, 
                            "Quantity": qty, 
                            "User": st.session_state['username']
                        }])
                        
                        # Sync to Google Sheets
                        updated_df = pd.concat([existing_data, new_row], ignore_index=True)
                        conn.update(data=updated_df)
                        
                        st.success("Entry saved and synced to cloud!")
                        st.rerun()

            st.divider()
            st.subheader("Cloud History (Visible on Computer & Phone)")
            st.dataframe(existing_data.iloc[::-1], use_container_width=True)
    else:
        st.info("Please upload the PV file to start.")
