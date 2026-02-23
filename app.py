import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
import os
from datetime import date

# --- 1. USER AUTHENTICATION SETUP ---
# You can add more users here
names = ["Dressup Haiti User"]
usernames = ["admin"]
passwords = ["wigmaster123"] # Change this to your preferred password

# Hash the password (standard security)
hashed_passwords = stauth.Hasher(passwords).generate()

authenticator = stauth.Authenticate(
    names, usernames, hashed_passwords,
    "inventory_cookie", "signature_key", cookie_expiry_days=30
)

name, authentication_status, username = authenticator.login("Login", "main")

if authentication_status == False:
    st.error("Username/password is incorrect")
elif authentication_status == None:
    st.warning("Please enter your username and password")
elif authentication_status:
    # --- EVERYTHING BELOW RUNS ONLY AFTER LOGIN ---
    authenticator.logout("Logout", "sidebar")
    st.sidebar.title(f"Welcome {name}")

    # --- FILE SETUP ---
    LOG_FILE = "wig_intake_log.csv"
    EXPECTED_COLS = ["Date", "SKU", "Name", "Quantity", "User"] # Added 'User' column

    if not os.path.exists(LOG_FILE):
        pd.DataFrame(columns=EXPECTED_COLS).to_csv(LOG_FILE, index=False)

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

    # --- APP LOGIC ---
    st.title("🦱 Dressupht Pv: Secure Inventory")

    # [UPLOADS SECTION - Same as before]
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

            with st.form("intake_form", clear_on_submit=True):
                qty = st.number_input("Quantity", min_value=1)
                if st.form_submit_button("✅ Save Entry"):
                    if detected_name:
                        # We save the 'username' so we know who entered it
                        new_entry = pd.DataFrame([[str(date.today()), input_sku, detected_name, qty, username]], columns=EXPECTED_COLS)
                        new_entry.to_csv(LOG_FILE, mode='a', header=False, index=False)
                        st.rerun()

            st.divider()
            st.subheader("History")
            log_df = pd.read_csv(LOG_FILE)
            # Filter history so a user only sees their own entries (or show all for admin)
            st.dataframe(log_df.iloc[::-1], use_container_width=True)

    else:
        st.info("Upload PV file to begin.")
