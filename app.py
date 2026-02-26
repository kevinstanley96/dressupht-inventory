import streamlit as st
import pd as pd
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.7", layout="wide")

# --- AUTHENTICATION ---
usernames_list = ["Djessie", "Kevin", "Casimir", "Melchisedek", "David", "Darius", "Eliada", "Sebastien", "Guirlene", "Carmela", "Angelina", "Tamara", "Dorotheline", "Sarah", "Valerie", "Saouda", "Marie France", "Carelle", "Annaelle", "Gerdine", "Martilda"]
credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames_list}}
credentials['usernames']['Kevin']['password'] = "The$100$Raven"

authenticator = stauth.Authenticate(credentials, "inventory_cookie", "abcdef123456_key", 30)
authentication_status = authenticator.login(location='main')

if st.session_state["authentication_status"]:
    username = st.session_state["username"]
    authenticator.logout('Logout', 'sidebar')

    try:
        AIR_TOKEN = st.secrets["AIRTABLE_TOKEN"]
        BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
        HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}
    except:
        st.error("Missing Secrets in Streamlit Cloud!")
        st.stop()

    # --- DATA ENGINE ---
    def get_at_data(table, params=None):
        all_recs = []
        url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
        if params is None: params = {}
        while True:
            res = requests.get(url, headers=HEADERS, params=params)
            if res.status_code == 200:
                data = res.json()
                all_recs.extend(data.get('records', []))
                offset = data.get('offset')
                if offset: params['offset'] = offset
                else: break
            else: break
        if not all_recs: return pd.DataFrame()
        df = pd.DataFrame([dict(r['fields'], id=r['id']) for r in all_recs])
        for col in ['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']:
            if col not in df.columns: df[col] = "N/A"
        return df

    def clean_location_data(file, loc_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip() for c in df.columns]
        mapping = {'Item Name': 'Wig Name', 'Variation Name': 'Style', 'SKU': 'SKU', 'Price': 'Price', 'Categories': 'Category'}
        df = df.rename(columns=mapping)

        stock_col = "Current Quantity Dressup Haiti" if loc_name == "Haiti" else "Current Quantity Dressupht Pv"
        df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int) if stock_col in df.columns else 0
        df['Category'] = df['Category'].fillna("Uncategorized")
        df['Location'] = loc_name
        df['SKU'] = df['SKU'].astype(str).str.strip().replace('nan', 'NO_SKU')
        
        w_name = df['Wig Name'].astype(str).replace('nan', 'Unknown')
        s_name = df['Style'].astype(str).replace('nan', '')
        df['Full Name'] = w_name + " (" + s_name + ")"
        df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
        
        return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']].copy()

    # --- USER CONTEXT ---
    user_data = get_at_data("Role", {"filterByFormula": f"{{User Name}}='{username}'"})
    user_role = "Admin" if username == "Kevin" else (user_data['Access Level'].iloc[0] if not user_data.empty else 'Staff')
    user_location = user_data['Assigned Location'].iloc[0] if not user_data.empty and 'Assigned Location' in user_data.columns else 'Both'

    st.sidebar.markdown(f"### 👤 {username} | 📍 {user_location}")
    st.sidebar.divider()

    tabs = st.tabs(["📋 Library", "➕ Intake", "🕵️ Audit", "🔄 Compare", "🛡️ Admin", "🔑 Password"])

    # --- TAB 1: LIBRARY ---
    lib_data = get_at_data("Master_Inventory")
    with tabs[0]:
        st.subheader("📦 Master Inventory")
        if not lib_data.empty:
            disp_df = lib_data.copy().sort_values(by="Full Name")
            if user_role not in ['Admin', 'Manager'] and user_location != "Both":
                disp_df = disp_df[disp_df['Location'] == user_location]
            
            search = st.text_input("🔍 Search Library (Name or SKU)")
            if search:
                disp_df = disp_df[disp_df['Full Name'].str.contains(search, case=False, na=False) | disp_df['SKU'].str.contains(search, na=False)]
            
            st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 5: ADMIN (THE FULL SYNC LOGIC) ---
    if user_role == 'Admin':
        with tabs[4]:
            st.subheader("🛡️ Master System Sync")
            c1, c2 = st.columns(2)
            f_pv = c1.file_uploader("Upload PV File", type=['xlsx'])
            f_ht = c2.file_uploader("Upload Haiti File", type=['xlsx'])
            
            if f_pv and f_ht:
                df_pv = clean_location_data(f_pv, "Pv")
                df_ht = clean_location_data(f_ht, "Haiti")
                full_df = pd.concat([df_pv, df_ht]).reset_index(drop=True)
                
                st.info(f"Detected {len(full_df)} total items across both locations.")
                
                if st.button("🚀 Wipe & Sync ALL Items"):
                    # 1. BATCH DELETE
                    if not lib_data.empty:
                        status = st.empty()
                        ids = lib_data['id'].tolist()
                        for i in range(0, len(ids), 10):
                            batch_ids = ids[i:i+10]
                            query = "&".join([f"records[]={rid}" for rid in batch_ids])
                            requests.delete(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory?{query}", headers=HEADERS)
                            status.text(f"🗑️ Deleting: {i}/{len(ids)}")
                    
                    # 2. BATCH UPLOAD (THE FIX)
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i in range(0, len(full_df), 10):
                        chunk = full_df.iloc[i : i + 10]
                        recs = []
                        for _, r in chunk.iterrows():
                            recs.append({"fields": {
                                "SKU": str(r['SKU']), "Full Name": str(r['Full Name']),
                                "Stock": int(r['Stock']), "Price": float(r['Price']),
                                "Category": str(r['Category']), "Location": str(r['Location']),
                                "Last_Sync_Date": str(date.today())
                            }})
                        
                        res = requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Master_Inventory", headers=HEADERS, json={"records": recs})
                        
                        if res.status_code != 200:
                            st.error(f"Error: {res.text}")
                            break
                            
                        progress_bar.progress(min((i + 10) / len(full_df), 1.0))
                        status_text.text(f"🚀 Uploading: {min(i+10, len(full_df))} / {len(full_df)} items...")
                        time.sleep(0.2) # Avoid rate limits
                    
                    st.success("✅ Sync Finished! All items are in Airtable.")
                    st.rerun()

    # --- TAB 2: INTAKE (WITH SKU VERIFICATION) ---
    if user_role in ['Admin', 'Manager']:
        with tabs[1]:
            st.subheader("➕ New Stock Shipment")
            v_sku = st.text_input("Enter SKU to verify").strip()
            if v_sku:
                match = lib_data[lib_data['SKU'] == v_sku]
                if not match.empty:
                    st.success(f"✅ Verified: {match['Full Name'].iloc[0]} | Stock: {match['Stock'].iloc[0]}")
                    with st.form("ship_form"):
                        s_date = st.date_input("Date", date.today())
                        s_loc = st.selectbox("Location", ["Pv", "Haiti"])
                        s_qty = st.number_input("Quantity", min_value=1)
                        if st.form_submit_button("Log Shipment"):
                            payload = {"records": [{"fields": {"Date": str(s_date), "SKU": v_sku, "Name": match['Full Name'].iloc[0], "Quantity": s_qty, "User": username, "Location": s_loc}}]}
                            requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=payload)
                            st.success("Shipment Logged!")
                else: st.error("SKU Not Found.")

    # --- TAB 6: PASSWORD ---
    with tabs[-1]:
        st.subheader("🔑 Change Password")
        if authenticator.reset_password(username=username, fields={'form_name': 'Update'}):
            st.success('Password updated!')

elif st.session_status is False: st.error('Incorrect Password')
elif st.session_status is None: st.warning('Please login.')
