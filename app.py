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
st.set_page_config(page_title="Dressupht ERP v5.2.0", layout="wide")

# --- SUPABASE SETUP ---
@st.cache_resource
def init_connection():
    # Using cache_resource to prevent leaking file descriptors/connections
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

# --- AUTHENTICATION SETUP ---
usernames_list = [u.lower() for u in ["Djessie", "Kevin", "Casimir", "Melchisedek", "David", "Darius", "Eliada", "Sebastien", "Guirlene", "Carmela", "Angelina", "Tamara", "Dorotheline", "Sarah", "Valerie", "Saouda", "Marie France", "Carelle", "Annaelle", "Gerdine", "Martilda"]]
credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames_list}}
credentials['usernames']['kevin']['password'] = "The$100$Raven"

authenticator = stauth.Authenticate(credentials, "inventory_cookie", "abcdef123456_key", 30)
name, authentication_status, username = authenticator.login(location='main')

# --- SHARED FUNCTIONS ---
@st.cache_data(ttl=60)
def get_sb_data(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(response.data)
    except Exception:
        return pd.DataFrame()

def send_email(subject, body, recipients):
    if not recipients: return False
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'], msg['From'], msg['To'] = subject, st.secrets["EMAIL_ADDRESS"], ", ".join(recipients)
    try:
        # Using standard SMTP with STARTTLS for port 587 or SSL for 465 based on provider
        with smtplib.SMTP(st.secrets["SMTP_SERVER"], st.secrets["SMTP_PORT"]) as smtp:
            smtp.starttls()
            smtp.login(st.secrets["EMAIL_ADDRESS"], st.secrets["EMAIL_PASSWORD"])
            smtp.send_message(msg)
            return True
    except Exception as e:
        st.error(f"Email failed: {e}")
        return False

def clean_location_data(file, loc_name):
    df = pd.read_excel(file, skiprows=1)
    df.columns = [str(c).strip() for c in df.columns]
    
    # 🛡️ THE FIX: Sanitize "Smart Quotes" to prevent encoding errors (â€)
    if 'Item Name' in df.columns:
        df['Item Name'] = (df['Item Name'].astype(str)
                           .str.replace('”', '"')
                           .str.replace('“', '"')
                           .str.replace('’', "'")
                           .str.replace('‘', "'"))
        
    mapping = {'Item Name': 'Full Name', 'SKU': 'SKU', 'Categories': 'Category', 'Price': 'Price'}
    df = df.rename(columns=mapping)
    stock_col = "Current Quantity Dressup Haiti" if loc_name == "Canape-Vert" else "Current Quantity Dressupht Pv"
    df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int) if stock_col in df.columns else 0
    df['Category'] = df['Category'].fillna("Uncategorized")
    df['Location'] = loc_name
    df['SKU'] = df['SKU'].astype(str).str.strip().replace(['nan', ''], 'NO_SKU')
    df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
    return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']].copy()

# --- MAIN APP ---
if st.session_state["authentication_status"]:
    for key in ['audit_verify', 'intake_verify', 'depot_verify']:
        if key not in st.session_state:
            st.session_state[key] = {"name": None, "cat": None, "sys": 0, "sku": "", "auto_exp": 0, "auto_depot": 0}

    roles_df = get_sb_data("Role")
    master_inventory = get_sb_data("Master_Inventory")

    if username == "kevin":
        user_role, user_location = "Admin", "Both"
    else:
        user_row = roles_df[roles_df['User Name'] == username] if not roles_df.empty else pd.DataFrame()
        user_role = user_row['Roles'].iloc[0] if not user_row.empty else "Staff"
        user_location = user_row['Assigned Location'].iloc[0] if not user_row.empty else "Both"

    st.sidebar.markdown(f"### 👤 {username.title()}\n**📍 Location:** {user_location}\n**🛡️ Role:** {user_role}")
    st.sidebar.divider()
    authenticator.logout('Logout', 'sidebar')

    st.title("DRESSUP HAITI STOCK SYSTEM")

    if user_role == "Admin":
        with st.expander("🛡️ Master Data Sync", expanded=False):
            c_u1, c_u2 = st.columns(2)
            fp, fh = c_u1.file_uploader("PV Square File", type=['xlsx']), c_u2.file_uploader("CV Square File", type=['xlsx'])
            if fp and fh and st.button("🚀 Run Wipe & Sync"):
                with st.spinner("Syncing and cleaning characters..."):
                    full = pd.concat([clean_location_data(fp, "Pv"), clean_location_data(fh, "Canape-Vert")], ignore_index=True)
                    supabase.table("Master_Inventory").delete().neq("SKU", "NON_EXISTENT").execute()
                    
                    # 🛡️ Errno 24 Fix: Process in smaller chunks with sleep to allow file descriptor cleanup
                    for i in range(0, len(full), 100):
                        supabase.table("Master_Inventory").insert(full.iloc[i:i+100].to_dict('records')).execute()
                        time.sleep(0.1) 
                        
                    st.cache_data.clear()
                    st.success("Sync Complete!")
                    st.rerun()

    all_tabs = ["Library", "Intake", "Audit", "Sales", "Comparison", "Fast/Slow", "Big Depot", "Exposed", "Password", "Admin", "Cleanup"]
    if user_role == "Manager":
        tab_list = ["Library", "Intake", "Audit", "Comparison", "Fast/Slow", "Big Depot", "Exposed", "Password"]
    elif user_role == "Staff":
        tab_list = ["Library", "Exposed", "Password"]
    else:
        tab_list = all_tabs
    
    tabs = st.tabs(tab_list)

    # --- TAB: LIBRARY ---
    if "Library" in tab_list:
        with tabs[tab_list.index("Library")]:
            st.subheader(f"Inventory ({len(master_inventory)} Items)")
            c1, c2 = st.columns([2, 1])
            search = c1.text_input("🔍 Search Name/SKU")
            sort_choice = c2.selectbox("Sort By", ["Name", "Category", "Location"])
            
            disp_df = master_inventory.copy()
            if user_role == "Staff" and user_location != "Both":
                disp_df = disp_df[disp_df['Location'] == user_location]
            
            if not disp_df.empty:
                sort_map = {"Name": "Full Name", "Category": ["Category", "Full Name"], "Location": ["Location", "Full Name"]}
                disp_df = disp_df.sort_values(by=sort_map[sort_choice])
                if search:
                    tokens = search.lower().split()
                    disp_df = disp_df[disp_df.apply(lambda r: all(t in str(r['Full Name']).lower() or t in str(r['SKU']).lower() for t in tokens), axis=1)]
                st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)
                
                # 📥 Clean Export
                csv = disp_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                st.download_button("📥 Download Excel-Safe CSV", data=csv, file_name=f"inventory_{date.today()}.csv", mime='text/csv')

    # --- TAB: INTAKE ---
    if "Intake" in tab_list:
        with tabs[tab_list.index("Intake")]:
            col1, col2 = st.columns(2)
            with col1:
                in_sku = st.text_input("Scan SKU", key="int_sku_input").strip()
                if in_sku and in_sku != st.session_state.intake_verify["sku"]:
                    match = master_inventory[(master_inventory['SKU'].str.lower() == in_sku.lower()) & (master_inventory['Location'] == "Pv")]
                    if not match.empty:
                        st.session_state.intake_verify = {"name": match['Full Name'].iloc[0], "cat": match['Category'].iloc[0], "sku": in_sku}
                    else:
                        st.session_state.intake_verify = {"name": None, "cat": None, "sku": in_sku}
                        st.error("SKU Not Found in Pv")
                
                if st.session_state.intake_verify["name"]:
                    st.success(f"**Item:** {st.session_state.intake_verify['name']}")
                    with st.form("int_form", clear_on_submit=True):
                        qty, dt = st.number_input("Qty Received", min_value=1), st.date_input("Date", value=date.today())
                        if st.form_submit_button("Record Intake"):
                            supabase.table("Shipments").insert({"Date": str(dt), "SKU": in_sku, "Wig Name": st.session_state.intake_verify["name"], "Category": st.session_state.intake_verify["cat"], "Quantity": qty, "User": username, "Location": "Pv"}).execute()
                            st.toast("Intake Saved!")
                            st.cache_data.clear()
            with col2:
                h = get_sb_data("Shipments")
                if not h.empty: st.dataframe(h[['Date', 'SKU', 'Wig Name', 'Quantity']].sort_values(by="Date", ascending=False), hide_index=True)

    # --- TAB: AUDIT ---
    if "Audit" in tab_list:
        with tabs[tab_list.index("Audit")]:
            st.subheader("Manual Inventory Audit")
            exp_data = get_sb_data("Exposed_Wigs")
            dep_data = get_sb_data("Big_Depot")
            
            ca, cb = st.columns([1, 2])
            with ca:
                counter = st.selectbox("Counter Name", usernames_list)
                a_sku = st.text_input("SKU to Audit", key="aud_sku_input").strip()
                
                if a_sku and a_sku != st.session_state.audit_verify["sku"]:
                    match = master_inventory[(master_inventory['SKU'].str.lower() == a_sku.lower()) & (master_inventory['Location'] == "Pv")]
                    if not match.empty:
                        sys_qty = int(match['Stock'].iloc[0])
                        exp_qty = int(exp_data[(exp_data['SKU'].str.lower() == a_sku.lower()) & (exp_data['Location'] == "Pv")]['Quantity'].sum()) if not exp_data.empty else 0
                        depot_qty = 0
                        if not dep_data.empty:
                            d_match = dep_data[dep_data['SKU'].str.lower() == a_sku.lower()]
                            depot_qty = int(d_match[d_match['Type'] == "Addition"]['Quantity'].sum() - d_match[d_match['Type'] == "Subtraction"]['Quantity'].sum())

                        st.session_state.audit_verify = {"name": match['Full Name'].iloc[0], "cat": match['Category'].iloc[0], "sys": sys_qty, "sku": a_sku, "auto_exp": exp_qty, "auto_depot": depot_qty}
                    else:
                        st.session_state.audit_verify = {"name": None, "cat": None, "sys": 0, "sku": a_sku, "auto_exp": 0, "auto_depot": 0}

                if st.session_state.audit_verify["name"]:
                    st.success(f"Item: {st.session_state.audit_verify['name']}")
                    with st.form("aud_form"):
                        m = st.number_input("Manual (Shelf)", min_value=0)
                        e = st.number_input("Exposed (Auto)", value=st.session_state.audit_verify["auto_exp"])
                        r = st.number_input("Returns", min_value=0)
                        b = st.number_input("Big Depot (Auto)", value=st.session_state.audit_verify["auto_depot"])
                        if st.form_submit_button("Save Audit"):
                            tp = m + e + r + b
                            payload = {"Date": str(date.today()), "SKU": a_sku, "Name": st.session_state.audit_verify["name"], "Category": st.session_state.audit_verify["cat"], "Counter_Name": counter, "Total_Physical": tp, "System_Stock": st.session_state.audit_verify["sys"], "Discrepancy": tp - st.session_state.audit_verify["sys"]}
                            supabase.table("Inventory_Audit").insert(payload).execute()
                            st.cache_data.clear()
                            st.rerun()
            with cb:
                aud_h = get_sb_data("Inventory_Audit")
                if not aud_h.empty: st.dataframe(aud_h.sort_values(by="Date", ascending=False), hide_index=True)

    # --- TAB: SALES ---
    if "Sales" in tab_list:
        with tabs[tab_list.index("Sales")]:
            cs1, cs2 = st.columns(2)
            old_f, new_f = cs1.file_uploader("OLD Square File", type=['xlsx']), cs2.file_uploader("NEW Square File", type=['xlsx'])
            if old_f and new_f:
                df_o, df_n = clean_location_data(old_f, "Pv"), clean_location_data(new_f, "Pv")
                comp = pd.merge(df_o[['SKU', 'Full Name', 'Category', 'Stock', 'Price']], df_n[['SKU', 'Stock']], on='SKU', suffixes=('_old', '_new'))
                comp['Sold'] = comp['Stock_old'] - comp['Stock_new']
                sales_df = comp[comp['Sold'] > 0].copy()
                if not sales_df.empty:
                    ed_sales = st.data_editor(sales_df[['Category', 'Full Name', 'SKU', 'Sold', 'Price']], hide_index=True)
                    st.metric("Revenue", f"${(ed_sales['Sold'] * ed_sales['Price']).sum():,.2f}")

    # --- TAB: COMPARISON ---
    if "Comparison" in tab_list:
        with tabs[tab_list.index("Comparison")]:
            c_comp1, c_comp2 = st.columns(2)
            f_cv, f_pv = c_comp1.file_uploader("Canape-Vert File", type=['xlsx'], key="c1"), c_comp2.file_uploader("PV File", type=['xlsx'], key="c2")
            if f_cv and f_pv:
                d_cv, d_pv = clean_location_data(f_cv, "Canape-Vert"), clean_location_data(f_pv, "Pv")
                m_comp = pd.merge(d_cv[['Full Name', 'Category', 'Stock', 'SKU']], d_pv[['Full Name', 'Stock', 'SKU']], on='Full Name', how='outer', suffixes=('_CV', '_PV')).fillna(0)
                st.dataframe(m_comp, use_container_width=True, hide_index=True)

    # --- TAB: FAST/SLOW ---
    if "Fast/Slow" in tab_list:
        with tabs[tab_list.index("Fast/Slow")]:
            cfs1, cfs2 = st.columns(2)
            old_fs, new_fs = cfs1.file_uploader("OLD File", type=['xlsx'], key="f1"), cfs2.file_uploader("NEW File", type=['xlsx'], key="f2")
            if old_fs and new_fs:
                df_o, df_n = clean_location_data(old_fs, "Pv"), clean_location_data(new_fs, "Pv")
                comp = pd.merge(df_o, df_n[['SKU', 'Stock']], on='SKU', suffixes=('_old', '_new'))
                comp['Sold'] = comp['Stock_old'] - comp['Stock_new']
                st.subheader("🚀 Top Selling")
                st.dataframe(comp.sort_values("Sold", ascending=False).head(10)[['Full Name', 'Sold']], hide_index=True)

    # --- TAB: BIG DEPOT ---
    if "Big Depot" in tab_list:
        with tabs[tab_list.index("Big Depot")]:
            depot_data = get_sb_data("Big_Depot")
            cd1, cd2 = st.columns([1, 2])
            with cd1:
                d_sku = st.text_input("Depot SKU", key="dep_sku").strip()
                if d_sku and d_sku != st.session_state.depot_verify["sku"]:
                    match = master_inventory[master_inventory['SKU'].str.lower() == d_sku.lower()]
                    st.session_state.depot_verify = {"name": match['Full Name'].iloc[0] if not match.empty else None, "sku": d_sku}
                if st.session_state.depot_verify["name"]:
                    st.success(f"Item: {st.session_state.depot_verify['name']}")
                    with st.form("dep_form", clear_on_submit=True):
                        dtype, dqty = st.selectbox("Action", ["Addition", "Subtraction"]), st.number_input("Qty", 1)
                        if st.form_submit_button("Save"):
                            supabase.table("Big_Depot").insert({"Date": str(date.today()), "SKU": d_sku, "Wig Name": st.session_state.depot_verify["name"], "Type": dtype, "Quantity": dqty, "User": username}).execute()
                            st.cache_data.clear()
                            st.rerun()
            with cd2:
                st.dataframe(depot_data.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)

    # --- TAB: EXPOSED ---
    if "Exposed" in tab_list:
        with tabs[tab_list.index("Exposed")]:
            exp_data = get_sb_data("Exposed_Wigs")
            if not exp_data.empty:
                exp_disp = exp_data[exp_data['Location'] == user_location] if user_role == "Staff" and user_location != "Both" else exp_data
                st.dataframe(exp_disp[['SKU', 'Full Name', 'Quantity', 'Location', 'Last_Updated']], use_container_width=True, hide_index=True)
            with st.form("exposed_form", clear_on_submit=True):
                e_sku, e_qty = st.text_input("SKU").strip(), st.number_input("Quantity", min_value=0)
                e_loc = st.selectbox("Location", ["Pv", "Canape-Vert"])
                if st.form_submit_button("Save Exposed"):
                    match = master_inventory[master_inventory['SKU'].str.lower() == e_sku.lower()]
                    e_name = match['Full Name'].iloc[0] if not match.empty else "Unknown"
                    payload = {"SKU": e_sku, "Full Name": e_name, "Quantity": e_qty, "Location": e_loc, "Last_Updated": datetime.now().strftime("%Y-%m-%d %H:%M")}
                    existing = exp_data[(exp_data['SKU'] == e_sku) & (exp_data['Location'] == e_loc)]
                    if not existing.empty:
                        supabase.table("Exposed_Wigs").update(payload).eq("id", existing['id'].iloc[0]).execute()
                    else:
                        supabase.table("Exposed_Wigs").insert(payload).execute()
                    st.cache_data.clear()
                    st.rerun()

    # --- TAB: PASSWORD ---
    if "Password" in tab_list:
        with tabs[tab_list.index("Password")]:
            authenticator.reset_password(username, 'Update Password')

    # --- TAB: ADMIN ---
    if "Admin" in tab_list:
        with tabs[tab_list.index("Admin")]:
            st.header("🛡️ Administrative Control Panel")
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.subheader("👤 User Management")
                if not roles_df.empty:
                    sel_u = st.selectbox("Select Staff", roles_df['User Name'].tolist())
                    u_info = roles_df[roles_df['User Name'] == sel_u].iloc[0]
                    u_email = st.text_input("Email", value=u_info.get('Email', ""))
                    u_loc = st.selectbox("Location Permission", ["Pv", "Canape-Vert", "Both"], index=["Pv", "Canape-Vert", "Both"].index(u_info['Assigned Location']))
                    if st.button("Update Profile"):
                        supabase.table("Role").update({"Email": u_email, "Assigned Location": u_loc}).eq("User Name", sel_u).execute()
                        st.success("Updated!")
            
            with col_b:
                st.subheader("📧 Send Task/Email")
                with st.form("admin_email"):
                    dest = st.text_input("Recipient Email")
                    subj = st.text_input("Subject")
                    body = st.text_area("Message")
                    if st.form_submit_button("Send"):
                        if send_email(subj, body, [dest]): st.success("Sent!")

    # --- TAB: CLEANUP ---
    if "Cleanup" in tab_list:
        with tabs[tab_list.index("Cleanup")]:
            st.header("🧹 Data Quality Check")
            clean_f = st.file_uploader("Upload Square Export", type=['xlsx'], key="clean_up")
            if clean_f:
                rdf = pd.read_excel(clean_f, skiprows=1)
                rdf.columns = [str(c).strip() for c in rdf.columns]
                c_sku = 'SKU' if 'SKU' in rdf.columns else None
                c_cat = 'Category' if 'Category' in rdf.columns else ('Categories' if 'Categories' in rdf.columns else None)
                if c_sku and c_cat:
                    bad_sku = rdf[rdf[c_sku].isna()]
                    bad_cat = rdf[rdf[c_cat].isna()]
                    st.error(f"Missing SKU: {len(bad_sku)}")
                    st.dataframe(bad_sku)
                    st.warning(f"Missing Category: {len(bad_cat)}")
                    st.dataframe(bad_cat)

elif authentication_status is False: st.error('Incorrect Login')
elif authentication_status is None: st.warning('Please Login')
