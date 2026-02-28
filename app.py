import streamlit as st
import pandas as pd
from supabase import create_client, Client
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import plotly.express as px
import smtplib
from email.message import EmailMessage

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v5.0", layout="wide")

# --- SUPABASE SETUP ---
# Pre-requisite: Install supabase (pip install supabase)
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- AUTHENTICATION ---
# Note: In a production app, credentials should be moved to a secure database/file,
# not hardcoded in the script.
usernames_list = ["Djessie", "Kevin", "Casimir", "Melchisedek", "David", "Darius", "Eliada", "Sebastien", "Guirlene", "Carmela", "Angelina", "Tamara", "Dorotheline", "Sarah", "Valerie", "Saouda", "Marie France", "Carelle", "Annaelle", "Gerdine", "Martilda"]
credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames_list}}
credentials['usernames']['Kevin']['password'] = "The$100$Raven"

authenticator = stauth.Authenticate(credentials, "inventory_cookie", "abcdef123456_key", 30)
name, authentication_status, username = authenticator.login(location='main')

# --- EMAIL NOTIFICATION FUNCTION ---
def send_email(subject, body, recipients):
    """Sends an email to a list of recipients."""
    if not recipients:
        st.warning("No recipients provided.")
        return False
        
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
    except Exception as e:
        st.error(f"Email failed: {e}")
        return False

if st.session_state["authentication_status"]:
    username = st.session_state["username"]
    
    # --- SESSION STATE ---
    if 'audit_verify' not in st.session_state: st.session_state.audit_verify = {"name": None, "cat": None, "sys": 0, "sku": ""}
    if 'intake_verify' not in st.session_state: st.session_state.intake_verify = {"name": None, "cat": None, "sku": ""}
    if 'depot_verify' not in st.session_state: st.session_state.depot_verify = {"name": None, "sku": ""}

    # --- SUPABASE DATA FETCHING ---
    @st.cache_data(ttl=60) # Reduced TTL, Supabase is fast
    def get_sb_data(table_name):
        response = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(response.data)

    def clean_location_data(file, loc_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip() for c in df.columns]
        mapping = {'Item Name': 'Wig Name', 'Variation Name': 'Style', 'SKU': 'SKU', 'Price': 'Price', 'Categories': 'Category'}
        df = df.rename(columns=mapping)
        
        stock_col = "Current Quantity Dressup Haiti" if loc_name == "Canape-Vert" else "Current Quantity Dressupht Pv"
        if stock_col in df.columns:
            df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int)
        else:
            df['Stock'] = 0 
            
        df['Category'] = df['Category'].fillna("Uncategorized")
        df['Location'] = loc_name
        df['SKU'] = df['SKU'].astype(str).str.strip().replace('nan', 'NO_SKU')
        w_name, s_name = df['Wig Name'].astype(str).replace('nan', 'Unknown'), df['Style'].astype(str).replace('nan', '')
        df['Full Name'] = w_name + " (" + s_name + ")"
        df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
        # Reorder to match DB columns
        return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']].copy()

    # --- USER PROFILE ---
    roles_df = get_sb_data("Role")
    user_row = roles_df[roles_df['User Name'] == username] if not roles_df.empty else pd.DataFrame()
    user_role = "Admin" if username == "Kevin" else (user_row['Access Level'].iloc[0] if not user_row.empty else "Staff")
    user_location = user_row['Assigned Location'].iloc[0] if not user_row.empty and 'Assigned Location' in user_row.columns else "Both"

    st.sidebar.markdown(f"### 👤 {username}")
    st.sidebar.markdown(f"**📍 Location:** {user_location}")
    st.sidebar.divider()
    authenticator.logout('Logout', 'sidebar')

    # --- APP TITLE ---
    st.title("DRESSUP HAITI STOCK SYSTEM - SUPABASE")

    # --- DASHBOARD HEADER (ADMIN ONLY) ---
    if user_role == "Admin":
        with st.expander("🛡️ Master Data Sync (Admin Only)", expanded=False):
            st.info("Upload files here to sync both locations to Supabase.")
            c_u1, c_u2 = st.columns(2)
            fp = c_u1.file_uploader("PV Square File", type=['xlsx'], key="sync_p")
            fh = c_u2.file_uploader("Canape-Vert Square File", type=['xlsx'], key="sync_h")
            
            if st.button("🧪 Test Email to All Staff"):
                if 'Email' in roles_df.columns:
                    email_list = roles_df['Email'].dropna().unique().tolist()
                    if email_list:
                        st.info(f"Sending test email to: {', '.join(email_list)}")
                        if send_email("Test Subject - Team Notification", "This is a test email sent to all staff members.", email_list):
                            st.success("Test emails sent successfully!")
                        else:
                            st.error("Failed to send test emails.")
                    else:
                        st.warning("No emails found in the Role table.")
                else:
                    st.error("No 'Email' column found in Role table.")

            if fp and fh and st.button("🚀 Run Wipe & Sync"):
                with st.spinner("Processing files and updating database..."):
                    d1 = clean_location_data(fp, "Pv")
                    d2 = clean_location_data(fh, "Canape-Vert")
                    full = pd.concat([d1, d2], ignore_index=True)
                    old = get_sb_data("Master_Inventory")
                    email_list = roles_df['Email'].dropna().unique().tolist()

                    if not old.empty:
                        # Email Notifications for Changes
                        merged = pd.merge(full, old, on='SKU', suffixes=('_new', '_old'))
                        price_changes = merged[merged['Price_new'] != merged['Price_old']]
                        
                        if not price_changes.empty:
                            msg = "Price Changes:\n"
                            for _, r in price_changes.iterrows():
                                msg += f"- {r['Full Name_new']}: ${r['Price_old']} -> ${r['Price_new']}\n"
                            send_email("🚨 Price Update Notification", msg, email_list)
                        
                        new_stock = merged[(merged['Stock_old'] == 0) & (merged['Stock_new'] > 0)]
                        if not new_stock.empty:
                            msg = "Items Now Back in Stock:\n"
                            for _, r in new_stock.iterrows():
                                msg += f"- {r['Full Name_new']} ({r['Location_new']})\n"
                            send_email("✅ New Stock Arrival", msg, email_list)

                    # --- SUPABASE WIPE & SYNC ---
                    # 1. Delete all existing data
                    supabase.table("Master_Inventory").delete().neq("SKU", "NON_EXISTENT_SKU").execute()                
                    
                    # 2. Insert new data in batches
                    for i in range(0, len(full), 100): # Supabase handles larger batches better
                        chunk = full.iloc[i:i+100]
                        recs = chunk.to_dict('records')
                        supabase.table("Master_Inventory").insert(recs).execute()
                    
                    st.success("Database Updated Successfully")
                    st.cache_data.clear()
                    st.rerun()

    # --- TABS SETUP ---
    tab_list = ["Library", "Intake", "Audit", "Sales", "Comparison", "Fast/Slow", "Big Depot", "Exposed", "Password"]
    if user_role == "Manager":
        tab_list = ["Library", "Intake", "Audit", "Comparison", "Fast/Slow", "Big Depot", "Exposed", "Password"]
    elif user_role == "Staff":
        tab_list = ["Library", "Exposed", "Password"]
    tabs = st.tabs(tab_list)

    # --- TAB 1: LIBRARY ---
    with tabs[0]:
        lib_data = get_sb_data("Master_Inventory")
        
        # --- DEBUGGING BLOCK ---
        st.write("Columns in Database:", lib_data.columns.tolist())
        # -----------------------
        
        st.subheader(f"Inventory ({len(lib_data)} Items)")
        c1, c2 = st.columns([2, 1])
        search = c1.text_input("🔍 Search Name/SKU")
        sort_choice = c2.selectbox("Sort By", ["Name", "Location", "Category"])
        
        disp_df = lib_data.copy()
        if user_role == "Staff" and user_location != "Both":
            disp_df = disp_df[disp_df['Location'] == user_location]
            
        if not disp_df.empty:
            if sort_choice == "Location" and "Location" in disp_df.columns: 
                disp_df = disp_df.sort_values(by=["Location", "Full Name"])
            elif sort_choice == "Category" and "Category" in disp_df.columns: 
                disp_df = disp_df.sort_values(by=["Category", "Full Name"])
            elif "Full Name" in disp_df.columns: 
                disp_df = disp_df.sort_values(by="Full Name")

        if search:
            search_clean = search.strip().lower()
            search_tokens = search_clean.split()
            disp_df = disp_df[
                disp_df.apply(lambda row: all(
                    token in str(row['Full Name']).lower() or 
                    token in str(row['SKU']).lower() 
                    for token in search_tokens
                ), axis=1)
            ]
          # ... inside Tab 1: LIBRARY ...
    st.write("DEBUG - Columns found in Pandas:", disp_df.columns.tolist()) 
    st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)
    
        st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB 2: INTAKE ---
    if user_role in ["Admin", "Manager"]:
        with tabs[1]:
            st.subheader("Stock Intake (PV Tracking)")
            master_data = get_sb_data("Master_Inventory")
            col1, col2 = st.columns(2)
            with col1:
                in_sku = st.text_input("Scan SKU", key="int_sku").strip()
                if in_sku and in_sku != st.session_state.intake_verify["sku"]:
                    match = master_data[master_data['SKU'].str.strip().str.lower() == in_sku.strip().lower()]
                    match = match[match['Location'] == "Pv"]
                    if not match.empty:
                        st.session_state.intake_verify = {"name": match['Full Name'].iloc[0], "cat": match['Category'].iloc[0], "sku": in_sku}
                    else:
                        st.session_state.intake_verify = {"name": None, "cat": None, "sku": in_sku}
                        st.error("SKU Not Found in Pv")
                if st.session_state.intake_verify["name"]:
                    st.success(f"**Item:** {st.session_state.intake_verify['name']}")
                with st.form("int_form", clear_on_submit=True):
                    in_qty = st.number_input("Qty Received", min_value=1)
                    selected_date = st.date_input("Select Date Received", value=date.today())
                    
                    if st.form_submit_button("Record Intake") and st.session_state.intake_verify["name"]:
                        payload = {
                            "Date": str(selected_date),
                            "SKU": in_sku,
                            "Wig Name": st.session_state.intake_verify["name"],
                            "Category": st.session_state.intake_verify["cat"],
                            "Quantity": in_qty,
                            "User": username,
                            "Location": "Pv"
                        }
                        supabase.table("Shipments").insert(payload).execute()
                        st.toast(f"Intake Saved for {selected_date}!")
                        st.cache_data.clear()
            with col2:
                st.markdown("### History")
                h = get_sb_data("Shipments")
                if not h.empty:
                    h['Date'] = pd.to_datetime(h['Date']).dt.strftime('%Y-%m-%d')
                    st.dataframe(h[['Date', 'SKU', 'Wig Name', 'Quantity']].sort_values(by="Date", ascending=False), hide_index=True)

    # --- TAB 3: AUDIT ---
    if user_role in ["Admin", "Manager"]:
        with tabs[2]:
            st.subheader("Manual Inventory Audit")
            master_data = get_sb_data("Master_Inventory")
            ca, cb = st.columns([1, 2])
            with ca:
                counter = st.selectbox("Counter Name", usernames_list)
                a_sku = st.text_input("SKU to Audit", key="aud_sku").strip()
                if a_sku and a_sku != st.session_state.audit_verify["sku"]:
                    match = master_data[master_data['SKU'].str.strip().str.lower() == a_sku.strip().lower()]
                    match = match[match['Location'] == "Pv"]
                    
                    if not match.empty:
                        st.session_state.audit_verify = {"name": match['Full Name'].iloc[0], "cat": match['Category'].iloc[0], "sys": int(match['Stock'].iloc[0]), "sku": a_sku}
                    else:
                        st.session_state.audit_verify = {"name": None, "cat": None, "sys": 0, "sku": a_sku}
                        st.error("SKU Not Found in Pv")
                if st.session_state.audit_verify["name"]:
                    st.success(f"Item: {st.session_state.audit_verify['name']}")
                    st.info(f"System Stock: {st.session_state.audit_verify['sys']}")
                with st.form("aud_form"):
                    m, e, r, b = st.number_input("Manual", min_value=0), st.number_input("Exposed", min_value=0), st.number_input("Returns", min_value=0), st.number_input("Big Depot", min_value=0)
                    tp = m + e + r + b
                    ds = tp - st.session_state.audit_verify["sys"]
                    if st.form_submit_button("Save Audit") and st.session_state.audit_verify["name"]:
                        payload = {
                            "Date": str(date.today()),
                            "SKU": a_sku,
                            "Name": st.session_state.audit_verify["name"],
                            "Category": st.session_state.audit_verify["cat"],
                            "Counter_Name": counter,
                            "Total_Physical": tp,
                            "System_Stock": st.session_state.audit_verify["sys"],
                            "Discrepancy": ds
                        }
                        supabase.table("Inventory_Audit").insert(payload).execute()
                        st.cache_data.clear()
                        st.success("Audit Recorded")
            with cb:
                aud_h = get_sb_data("Inventory_Audit")
                if not aud_h.empty:
                    aud_h['Date'] = pd.to_datetime(aud_h['Date']).dt.strftime('%Y-%m-%d')
                    st.dataframe(aud_h.sort_values(by="Date", ascending=False), hide_index=True)

    # --- TAB 4: SALES ---
    if user_role == "Admin":
        with tabs[3]:
            st.subheader("Monday Sales Delta Engine (PV)")
            cs1, cs2 = st.columns(2)
            old_f = cs1.file_uploader("OLD Square File", type=['xlsx'], key="old_s")
            new_f = cs2.file_uploader("NEW Square File", type=['xlsx'], key="new_s")
            if old_f and new_f:
                df_o, df_n = clean_location_data(old_f, "Pv"), clean_location_data(new_f, "Pv")
                comp = pd.merge(df_o[['SKU', 'Full Name', 'Category', 'Stock', 'Price']], df_n[['SKU', 'Stock']], on='SKU', suffixes=('_old', '_new'))
                comp['Sold'] = comp['Stock_old'] - comp['Stock_new']
                sales_df = comp[comp['Sold'] > 0].copy()
                if not sales_df.empty:
                    st.markdown("### Analysis")
                    ed_sales = st.data_editor(sales_df[['Category', 'Full Name', 'SKU', 'Sold', 'Price']], hide_index=True)
                    ed_sales['Revenue'] = ed_sales['Sold'] * ed_sales['Price']
                    st.metric("Total Revenue", f"${ed_sales['Revenue'].sum():,.2f}")
                    st.plotly_chart(px.pie(ed_sales, values='Revenue', names='Category', hole=0.4, title="Revenue by Category"))
                else: st.warning("No sales detected.")

    # --- TAB 5: COMPARISON ---
    if user_role in ["Admin", "Manager"]:
        with tabs[4]:
            st.subheader("Stock Comparison: Canape-Vert vs PV")
            c_comp1, c_comp2 = st.columns(2)
            f_cv = c_comp1.file_uploader("Upload Canape-Vert File", type=['xlsx'], key="comp_cv")
            f_pv = c_comp2.file_uploader("Upload PV File", type=['xlsx'], key="comp_pv")
            if f_cv and f_pv:
                df_cv = clean_location_data(f_cv, "Canape-Vert")
                df_pv = clean_location_data(f_pv, "Pv")
                merged_comp = pd.merge(df_cv[['Full Name', 'Category', 'Stock', 'SKU']], df_pv[['Full Name', 'Stock', 'SKU']], on='Full Name', how='outer', suffixes=('_CV', '_PV')).fillna(0)
                unique_cats = merged_comp['Category'].astype(str).unique().tolist()
                if "nan" in unique_cats: unique_cats.remove("nan")
                cats = ["All"] + sorted(unique_cats)
                selected_cat = st.selectbox("Filter by Category", cats)
                if selected_cat != "All": merged_comp = merged_comp[merged_comp['Category'] == selected_cat]
                merged_comp['Status'] = merged_comp.apply(lambda x: "Request Needed" if x['Stock_PV'] == 0 and x['Stock_CV'] > 0 else "Balanced", axis=1)
                st.dataframe(merged_comp[['Category', 'Full Name', 'Stock_CV', 'SKU_CV', 'Stock_PV', 'SKU_PV', 'Status']], column_config={"Stock_CV": "Stock (CV)", "Stock_PV": "Stock (PV)", "SKU_CV": "SKU (CV)", "SKU_PV": "SKU (PV)"}, use_container_width=True, hide_index=True)
                low_pv = len(merged_comp[(merged_comp['Stock_PV'] <= 1) & (merged_comp['Stock_CV'] > 2)])
                st.metric("Potential Transfer Requests", low_pv)

    # --- TAB 6: FAST/SLOW ---
    if user_role in ["Admin", "Manager"]:
        with tabs[5]:
            st.subheader("Fast & Slow Moving Wigs")
            cs1, cs2 = st.columns(2)
            old_fs = cs1.file_uploader("OLD Square File", type=['xlsx'], key="fs_old")
            new_fs = cs2.file_uploader("NEW Square File", type=['xlsx'], key="fs_new")
            
            if old_fs and new_fs:
                df_o = clean_location_data(old_fs, "Pv")
                df_n = clean_location_data(new_fs, "Pv")
                
                comp = pd.merge(df_o, df_n[['SKU', 'Stock']], on='SKU', suffixes=('_old', '_new'))
                comp['Sold'] = comp['Stock_old'] - comp['Stock_new']
                
                st.markdown("### 🚀 Top Selling Items")
                fast_df = comp.sort_values(by="Sold", ascending=False)
                c_f1, c_f2 = st.columns(2)
                c_f1.dataframe(fast_df.head(5)[['Full Name', 'Sold']], hide_index=True, use_container_width=True)
                c_f2.dataframe(fast_df.head(10)[['Full Name', 'Sold']], hide_index=True, use_container_width=True)
                
                st.markdown("### 🐢 Slow Moving Items")
                slow_df = comp[(comp['Sold'] <= 0) & (comp['Stock_old'] > 0)].sort_values(by="Stock_old", ascending=False)
                c_s1, c_s2 = st.columns(2)
                c_s1.dataframe(slow_df.head(5)[['Full Name', 'Stock_old']], hide_index=True, use_container_width=True)
                c_s2.dataframe(slow_df.head(10)[['Full Name', 'Stock_old']], hide_index=True, use_container_width=True)

    # --- TAB 7: BIG DEPOT ---
    if user_role in ["Admin", "Manager"]:
        with tabs[6]:
            st.subheader("Depot Inventory Tracking")
            master_data = get_sb_data("Master_Inventory")
            
            depot_data = get_sb_data("Big_Depot")
            
            c_d1, c_d2 = st.columns([1, 2])
            with c_d1:
                d_sku = st.text_input("Scan SKU for Depot", key="dep_sku_input").strip()
                if d_sku and d_sku != st.session_state.depot_verify["sku"]:
                    match = master_data[master_data['SKU'].str.strip().str.lower() == d_sku.strip().lower()]
                    if not match.empty:
                        st.session_state.depot_verify = {"name": match['Full Name'].iloc[0], "sku": d_sku}
                    else:
                        st.session_state.depot_verify = {"name": None, "sku": d_sku}
                        st.error("SKU Not Found in Master Inventory")
                
                if st.session_state.depot_verify["name"]:
                    st.success(f"**Item:** {st.session_state.depot_verify['name']}")
                
                with st.form("depot_form", clear_on_submit=True):
                    d_type = st.selectbox("Action", ["Addition", "Subtraction"])
                    d_qty = st.number_input("Quantity", min_value=1)
                    d_date = st.date_input("Date", value=date.today())
                    
                    if st.form_submit_button("Save Depot Movement") and st.session_state.depot_verify["name"]:
                        payload = {
                            "Date": str(d_date),
                            "SKU": d_sku,
                            "Wig Name": st.session_state.depot_verify["name"],
                            "Type": d_type,
                            "Quantity": d_qty,
                            "User": username
                        }
                        
                        try:
                            supabase.table("Big_Depot").insert(payload).execute()
                            st.toast(f"✅ {d_type} Saved to Depot!")
                            st.cache_data.clear() # Refresh data
                        except Exception as e:
                            st.error(f"❌ Failed to save to Supabase: {e}")

            with c_d2:
                st.markdown("### Depot Log")
                if not depot_data.empty:
                    depot_data['Date'] = pd.to_datetime(depot_data['Date']).dt.strftime('%Y-%m-%d')
                    st.dataframe(depot_data.sort_values(by="Date", ascending=False), hide_index=True)

   # --- TAB 8: EXPOSED WIGS (Supabase) ---
    with tabs[7]:
        st.subheader("📋 Exposed Wigs Registry")
        
        # Fetch current exposed wigs
        exposed_data = get_sb_data("Exposed_Wigs")
        
        # Define required columns based on DB setup
        req_cols = ['SKU', 'Full Name', 'Quantity', 'Location', 'Last_Updated']
        
        # Check if DataFrame is empty
        if not exposed_data.empty:
            # Filter for current user's location if Staff
            if user_role == "Staff" and user_location != "Both":
                exposed_display = exposed_data[exposed_data['Location'] == user_location]
            else:
                exposed_display = exposed_data
            
            # Ensure columns exist in DB output
            existing_cols = [c for c in req_cols if c in exposed_display.columns]
            st.dataframe(exposed_display[existing_cols], use_container_width=True)
        else:
            st.warning("No exposed wigs data found.")

        st.divider()
        st.markdown("### ✍️ Log/Update Exposed Wig")
        
        with st.form("exposed_form", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            e_sku = col_a.text_input("SKU").strip()
            e_qty = col_b.number_input("Quantity", min_value=0)
            
            # Auto-fill name based on Master Inventory
            master_data = get_sb_data("Master_Inventory")
            match = master_data[master_data['SKU'].str.strip().str.lower() == e_sku.lower()]
            e_name = match['Full Name'].iloc[0] if not match.empty else "Unknown"
            
            st.write(f"**Item Name:** {e_name}")
            
            e_loc = st.selectbox("Location", ["Pv", "Canape-Vert"])
            
            submit = st.form_submit_button("Update Exposed Record")
            
            if submit and e_sku:
                # Logic to Add/Update in Supabase
                existing = exposed_data[
                    (exposed_data['SKU'].str.strip() == e_sku) & 
                    (exposed_data['Location'] == e_loc)
                ]
                
                payload = {
                    "SKU": e_sku,
                    "Full Name": e_name,
                    "Quantity": e_qty,
                    "Location": e_loc,
                    "Last_Updated": str(datetime.now())
                }
                
                if not existing.empty:
                    # Update existing record using ID
                    record_id = existing['id'].iloc[0]
                    supabase.table("Exposed_Wigs").update(payload).eq("id", record_id).execute()
                    st.success(f"Updated {e_name} in {e_loc}")
                else:
                    # Create new record
                    supabase.table("Exposed_Wigs").insert(payload).execute()
                    st.success(f"Added {e_name} to {e_loc}")
                
                st.cache_data.clear()
                st.rerun()

    # --- TAB 9: PASSWORD ---
    with tabs[-1]:
        st.subheader("Password")
        if authenticator.reset_password(username=username, fields={'form_name': 'Update'}):
            st.success('Updated!')

elif authentication_status is False: st.error('Incorrect Login')
elif authentication_status is None: st.warning('Please Login')


