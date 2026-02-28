import streamlit as st
import pandas as pd
import requests
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import plotly.express as px
import smtplib
from email.message import EmailMessage

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v4.13.0", layout="wide")

# --- AUTHENTICATION ---
usernames_list = ["Djessie", "Kevin", "Casimir", "Melchisedek", "David", "Darius", "Eliada", "Sebastien", "Guirlene", "Carmela", "Angelina", "Tamara", "Dorotheline", "Sarah", "Valerie", "Saouda", "Marie France", "Carelle", "Annaelle", "Gerdine", "Martilda"]
credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames_list}}
credentials['usernames']['Kevin']['password'] = "The$100$Raven"

authenticator = stauth.Authenticate(credentials, "inventory_cookie", "abcdef123456_key", 30)
name, authentication_status, username = authenticator.login(location='main')

# --- HELPERS ---
def send_email(subject, body, recipients):
    if not recipients: return False
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = st.secrets["EMAIL_ADDRESS"]
    msg['To'] = ", ".join(recipients) 
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(st.secrets["EMAIL_ADDRESS"], st.secrets["EMAIL_PASSWORD"])
            smtp.send_message(msg)
            return True
    except: return False

if st.session_state["authentication_status"]:
    # --- SESSION STATE ---
    if 'audit_verify' not in st.session_state: st.session_state.audit_verify = {"name": None, "cat": None, "sys": 0, "sku": ""}
    if 'intake_verify' not in st.session_state: st.session_state.intake_verify = {"name": None, "cat": None, "sku": ""}
    if 'depot_verify' not in st.session_state: st.session_state.depot_verify = {"name": None, "sku": ""}
    if 'cart' not in st.session_state: st.session_state.cart = []

    try:
        AIR_TOKEN = st.secrets["AIRTABLE_TOKEN"]
        BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
        HEADERS = {"Authorization": f"Bearer {AIR_TOKEN}", "Content-Type": "application/json"}
    except:
        st.error("Missing Secrets!")
        st.stop()

    @st.cache_data(ttl=60)
    def get_at_data(table):
        all_records = []
        offset = None
        base_url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
        while True:
            params = {"offset": offset} if offset else {}
            res = requests.get(base_url, headers=HEADERS, params=params)
            if res.status_code == 200:
                data = res.json()
                for r in data.get('records', []):
                    row = r['fields']; row['id'] = r['id']
                    all_records.append(row)
                offset = data.get('offset')
                if not offset: break
            else: break
        return pd.DataFrame(all_records)

    def clean_location_data(file, loc_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip() for c in df.columns]
        mapping = {'Item Name': 'Wig Name', 'Variation Name': 'Style', 'SKU': 'SKU', 'Price': 'Price', 'Categories': 'Category'}
        df = df.rename(columns=mapping)
        stock_col = "Current Quantity Dressup Haiti" if loc_name == "Canape-Vert" else "Current Quantity Dressupht Pv"
        df['Stock'] = pd.to_numeric(df.get(stock_col, 0), errors='coerce').fillna(0).astype(int)
        df['Category'] = df['Category'].fillna("Uncategorized")
        df['Location'] = loc_name
        df['SKU'] = df['SKU'].astype(str).str.strip().replace('nan', 'NO_SKU')
        df['Full Name'] = df['Wig Name'].astype(str) + " (" + df['Style'].astype(str) + ")"
        df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
        return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']].copy()

    # --- AUTO-FETCH LOGIC FOR AUDIT ---
    def get_stock_from_subtables(sku):
        depot_df = get_at_data("Big_Depot")
        exposed_df = get_at_data("Exposed_Wigs")
        dep_val, exp_val = 0, 0
        if not depot_df.empty and 'SKU' in depot_df.columns:
            item_depot = depot_df[depot_df['SKU'].str.lower() == sku.lower()]
            adds = item_depot[item_depot['Type'] == "Addition"]['Quantity'].sum()
            subs = item_depot[item_depot['Type'] == "Subtraction"]['Quantity'].sum()
            dep_val = adds - subs
        if not exposed_df.empty and 'SKU' in exposed_df.columns:
            item_exp = exposed_df[exposed_df['SKU'].str.lower() == sku.lower()]
            exp_val = item_exp['Quantity'].sum()
        return dep_val, exp_val

    # --- USER PROFILE & PERMISSIONS ---
    roles_df = get_at_data("Role")
    user_row = roles_df[roles_df['User Name'] == username] if not roles_df.empty else pd.DataFrame()
    user_role = "Admin" if username == "Kevin" else (user_row['Access Level'].iloc[0] if not user_row.empty else "Staff")
    user_location = user_row['Assigned Location'].iloc[0] if not user_row.empty else "Both"
    exposed_auth = ["Kevin", "Djessie", "Casimir"]

    # --- TABS SETUP ---
    tab_list = ["Library", "Intake", "Audit", "PoS", "Big Depot", "Comparison", "Fast/Slow", "Sales History", "Password"]
    if username in exposed_auth: tab_list.insert(7, "Exposed")
    tabs = st.tabs(tab_list)

    # --- TAB 1: LIBRARY ---
    with tabs[0]:
        lib_data = get_at_data("Master_Inventory")
        st.subheader(f"Inventory ({len(lib_data)} Items)")
        c1, c2 = st.columns([2, 1])
        search = c1.text_input("🔍 Search Name/SKU")
        sort_choice = c2.selectbox("Sort By", ["Name", "Category", "Location"])
        
        disp_df = lib_data.copy()
        if user_role == "Staff" and user_location != "Both":
            disp_df = disp_df[disp_df['Location'] == user_location]

        if sort_choice == "Name": disp_df = disp_df.sort_values(by="Full Name")
        elif sort_choice == "Category": disp_df = disp_df.sort_values(by=["Category", "Full Name"])
        elif sort_choice == "Location": disp_df = disp_df.sort_values(by=["Location", "Full Name"])

        if search:
            tokens = search.lower().split()
            disp_df = disp_df[disp_df.apply(lambda r: all(t in str(r['Full Name']).lower() or t in str(r['SKU']).lower() for t in tokens), axis=1)]
        st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 2: INTAKE ---
    with tabs[1]:
        st.subheader("Stock Intake (PV Tracking)")
        col1, col2 = st.columns(2)
        with col1:
            in_sku = st.text_input("Scan SKU for Intake").strip()
            if in_sku:
                match = lib_data[(lib_data['SKU'].str.lower() == in_sku.lower()) & (lib_data['Location'] == "Pv")]
                if not match.empty:
                    st.success(f"Item: {match.iloc[0]['Full Name']}")
                    with st.form("int_form", clear_on_submit=True):
                        in_qty = st.number_input("Qty Received", min_value=1)
                        in_date = st.date_input("Date Received", value=date.today())
                        if st.form_submit_button("Record Intake"):
                            payload = {"records": [{"fields": {"Date": str(in_date), "SKU": in_sku, "Wig Name": match.iloc[0]['Full Name'], "Quantity": in_qty, "User": username, "Location": "Pv"}}]}
                            requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Shipments", headers=HEADERS, json=payload)
                            st.toast("Intake Saved!"); st.cache_data.clear()
        with col2:
            st.markdown("### History")
            h = get_at_data("Shipments")
            if not h.empty:
                st.dataframe(h[['Date', 'SKU', 'Wig Name', 'Quantity']].sort_values(by="Date", ascending=False), hide_index=True)

    # --- TAB 3: AUDIT (THE NEW AUTO-FETCH ENGINE) ---
    with tabs[2]:
        st.subheader("Inventory Audit (Floor + Exposed + Depot)")
        ca, cb = st.columns([1, 2])
        with ca:
            a_sku = st.text_input("Scan SKU to Audit", key="aud_sku_main").strip()
            if a_sku:
                match = lib_data[(lib_data['SKU'].str.lower() == a_sku.lower()) & (lib_data['Location'] == "Pv")]
                if not match.empty:
                    item = match.iloc[0]
                    auto_depot, auto_exposed = get_stock_from_subtables(a_sku)
                    st.success(f"Found: {item['Full Name']}")
                    with st.form("audit_form_integrated"):
                        f_floor = st.number_input("Floor Count (Manual)", min_value=0)
                        f_exp = st.number_input("Exposed (Fetched)", value=int(auto_exposed))
                        f_depot = st.number_input("Big Depot (Fetched)", value=int(auto_depot))
                        f_returns = st.number_input("Returns", min_value=0)
                        
                        total_phys = f_floor + f_exp + f_depot + f_returns
                        sys_stock = int(item['Stock'])
                        
                        if st.form_submit_button("Log Full Audit"):
                            payload = {"records": [{"fields": {
                                "Date": str(date.today()), "SKU": a_sku, "Name": item['Full Name'],
                                "Total_Physical": total_phys, "System_Stock": sys_stock, "Discrepancy": total_phys - sys_stock
                            }}]}
                            requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Inventory_Audit", headers=HEADERS, json=payload)
                            st.success("Audit Logged!"); st.cache_data.clear()
        with cb:
            aud_h = get_at_data("Inventory_Audit")
            if not aud_h.empty:
                st.dataframe(aud_h.sort_values(by="Date", ascending=False), hide_index=True)

    # --- TAB 4: PoS ---
    with tabs[3]:
        st.subheader("Point of Sale")
        c_p1, c_p2 = st.columns(2)
        with c_p1:
            psku = st.text_input("Scan SKU to Sell").strip()
            if psku:
                item_match = lib_data[lib_data['SKU'].str.lower() == psku.lower()]
                if not item_match.empty:
                    item = item_match.iloc[0]
                    st.write(f"**Item:** {item['Full Name']} - ${item['Price']}")
                    if st.button("Add to Cart"):
                        st.session_state.cart.append({"SKU": item['SKU'], "Name": item['Full Name'], "Price": item['Price'], "Qty": 1})
                        st.rerun()
        with c_p2:
            if st.session_state.cart:
                cart_df = pd.DataFrame(st.session_state.cart)
                st.table(cart_df[['Name', 'Price']])
                total = sum(i['Price'] for i in st.session_state.cart)
                st.metric("Total", f"${total:,.2f}")
                pay_mode = st.selectbox("Payment", ["Cash", "MonCash", "Card", "Transfer"])
                if st.button("Complete Checkout"):
                    receipt = f"REC-{int(time.time())}"
                    recs = [{"fields": {"Date": str(date.today()), "Receipt_ID": receipt, "SKU": i['SKU'], "Item_Name": i['Name'], "Quantity": 1, "Price_Sold": i['Price'], "Payment_Method": pay_mode, "Seller": username}} for i in st.session_state.cart]
                    requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Sales_Transactions", headers=HEADERS, json={"records": recs})
                    st.balloons(); st.session_state.cart = []; st.rerun()

    # --- TAB 5: BIG DEPOT ---
    with tabs[4]:
        st.subheader("Big Depot Management")
        with st.form("dep_form"):
            dsku = st.text_input("SKU").strip()
            dtype = st.selectbox("Action", ["Addition", "Subtraction"])
            dqty = st.number_input("Quantity", min_value=1)
            if st.form_submit_button("Update Depot"):
                payload = {"records": [{"fields": {"Date": str(date.today()), "SKU": dsku, "Type": dtype, "Quantity": dqty, "User": username}}]}
                requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Big_Depot", headers=HEADERS, json=payload)
                st.success("Depot Updated"); st.cache_data.clear()

    # --- EXPOSED TAB (DYNAMIC) ---
    if "Exposed" in tab_list:
        with tabs[tab_list.index("Exposed")]:
            st.subheader("Exposed Wigs Tracker")
            e_search = st.text_input("Search Wig for Exposure")
            if e_search:
                e_tokens = e_search.lower().split()
                e_matches = lib_data[lib_data.apply(lambda r: all(t in str(r['Full Name']).lower() for t in e_tokens), axis=1)]
                if not e_matches.empty:
                    e_choice = st.selectbox("Select Item", e_matches['Full Name'].tolist())
                    e_sku = e_matches[e_matches['Full Name'] == e_choice]['SKU'].values[0]
                    with st.form("exp_form_submit"):
                        e_qty = st.number_input("Quantity currently exposed", min_value=0)
                        if st.form_submit_button("Update Exposure"):
                            payload = {"records": [{"fields": {"SKU": e_sku, "Full Name": e_choice, "Quantity": e_qty, "Last_Updated": str(date.today())}}]}
                            requests.post(f"https://api.airtable.com/v0/{BASE_ID}/Exposed_Wigs", headers=HEADERS, json=payload)
                            st.success("Exposed Level Updated"); st.cache_data.clear()

    # --- OTHER TABS (COMPARISON, SALES HISTORY, ETC) ---
    # These sections would follow the same pattern as built in v4.11/v4.12
    with tabs[-1]:
        st.subheader("User Settings")
        authenticator.logout('Logout', 'main')

elif authentication_status is False: st.error('Incorrect Login')
elif authentication_status is None: st.warning('Please Login')
