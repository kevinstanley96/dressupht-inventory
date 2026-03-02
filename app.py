import streamlit as st
import pandas as pd
from supabase import create_client, Client
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import plotly.express as px
import smtplib
from email.message import EmailMessage
import io

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v5.2.5", layout="wide")

# --- SUPABASE SETUP ---
@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

# --- AUTHENTICATION SETUP ---
usernames_list = [u.lower() for u in ["Djessie", "Kevin", "Casimir", "Melchisedek", "David", "Darius", "Eliada", "Sebastien", "Guirlene", "Carmela", "Angelina", "Tamara", "Dorotheline", "Sarah", "Valerie", "Saouda", "Marie France", "Carelle", "Annaelle", "Gerdine", "Martilda"]]
credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames_list}}
credentials['usernames']['kevin']['password'] = "The$100$Raven"

authenticator = stauth.Authenticate(credentials, "inventory_cookie", "abcdef123456_key", 30)

# --- SHARED FUNCTIONS ---
@st.cache_data(ttl=60)
def get_sb_data(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(response.data)
    except Exception:
        return pd.DataFrame()

def clean_location_data(file, loc_name):
    # Ensure we are reading from the start of the file
    file.seek(0)
    df = pd.read_excel(file, skiprows=1)
    df.columns = [str(c).strip() for c in df.columns]
    
    mapping = {'Item Name': 'Full Name', 'SKU': 'SKU', 'Categories': 'Category', 'Price': 'Price'}
    df = df.rename(columns=mapping)
    
    stock_col = "Current Quantity Dressup Haiti" if loc_name == "Canape-Vert" else "Current Quantity Dressupht Pv"
    df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int) if stock_col in df.columns else 0
    df['Category'] = df['Category'].fillna("Uncategorized").astype(str)
    df['Location'] = loc_name
    df['SKU'] = df['SKU'].astype(str).str.strip().replace(['nan', ''], 'NO_SKU')
    df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
    
    return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']].copy()

# --- LOGIN ---
name, authentication_status, username = authenticator.login(location='main')

if authentication_status:
    # Initialize session states
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
    authenticator.logout('Logout', 'sidebar')

    st.title("DRESSUP HAITI STOCK SYSTEM")

    # Tabs definition based on Roles
    all_tabs = ["Library", "Intake", "Audit", "Sales", "Comparison", "Fast/Slow", "Big Depot", "Exposed"]
    if user_role == "Manager":
        tab_list = ["Library", "Intake", "Audit", "Comparison", "Fast/Slow", "Big Depot", "Exposed"]
    elif user_role == "Staff":
        tab_list = ["Library", "Exposed"]
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
                # Ensure categories are strings for sorting
                disp_df['Category'] = disp_df['Category'].fillna("Uncategorized").astype(str)
                sort_map = {"Name": "Full Name", "Category": ["Category", "Full Name"], "Location": ["Location", "Full Name"]}
                disp_df = disp_df.sort_values(by=sort_map[sort_choice])
                
                if search:
                    tokens = search.lower().split()
                    disp_df = disp_df[disp_df.apply(lambda r: all(t in str(r['Full Name']).lower() or t in str(r['SKU']).lower() for t in tokens), axis=1)]
                
                st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB: INTAKE ---
if "Intake" in tab_list:
    with tabs[tab_list.index("Intake")]:
        st.subheader("📦 Product Intake (PV Location)")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.markdown("### 📥 Record New Entry")
            # SKU Input
            in_sku = st.text_input("Scan or Type SKU", key="int_sku_input").strip()
            
            # Logic to find item when SKU changes
            if in_sku and in_sku != st.session_state.intake_verify["sku"]:
                # We specifically look for the item in the PV master list
                match = master_inventory[(master_inventory['SKU'].str.lower() == in_sku.lower()) & (master_inventory['Location'] == "Pv")]
                
                if not match.empty:
                    st.session_state.intake_verify = {
                        "name": match['Full Name'].iloc[0], 
                        "cat": match['Category'].iloc[0], 
                        "sku": in_sku
                    }
                else:
                    st.session_state.intake_verify = {"name": None, "cat": None, "sku": in_sku}
                    st.error("SKU Not Found in PV Master Inventory. Please sync master data first.")
            
            # Show Form if item is found
            if st.session_state.intake_verify["name"]:
                st.success(f"**Item identified:** {st.session_state.intake_verify['name']}")
                
                with st.form("intake_submission_form", clear_on_submit=True):
                    qty = st.number_input("Quantity Received", min_value=1, step=1, value=1)
                    dt = st.date_input("Date of Arrival", value=date.today())
                    
                    submit_button = st.form_submit_button("Confirm & Save to Database")
                    
                    if submit_button:
                        # Prepare the data packet
                        payload = {
                            "Date": str(dt), 
                            "SKU": st.session_state.intake_verify["sku"], 
                            "Wig Name": st.session_state.intake_verify["name"], 
                            "Category": str(st.session_state.intake_verify["cat"]), 
                            "Quantity": int(qty), 
                            "User": username, 
                            "Location": "Pv"
                        }
                        
                        try:
                            # Attempt to insert into Supabase
                            supabase.table("Shipments").insert(payload).execute()
                            
                            # Success Actions
                            st.cache_data.clear() # Refresh data for the history table
                            st.toast(f"Successfully added {qty} of {st.session_state.intake_verify['name']}")
                            time.sleep(1) # Brief pause for user feedback
                            st.rerun()
                            
                        except Exception as e:
                            # Catching specific database errors (Missing columns, RLS violations, etc)
                            st.error("⚠️ Database Sync Failed")
                            st.info(f"Technical Details: {e}")
                            st.warning("Check if 'Shipments' table in Supabase has these columns: Date, SKU, Wig Name, Category, Quantity, User, Location")

        with col2:
            st.markdown("### 🕒 Recent Intake History")
            # Fetch fresh shipment data
            shipment_history = get_sb_data("Shipments")
            
            if not shipment_history.empty:
                # Basic cleaning for display
                display_hist = shipment_history.copy()
                # Ensure date sorting works correctly
                display_hist = display_hist.sort_values(by="Date", ascending=False)
                
                st.dataframe(
                    display_hist[['Date', 'SKU', 'Wig Name', 'Quantity', 'User']], 
                    use_container_width=True, 
                    hide_index=True
                )
                
                # Download option for the history
                csv = display_hist.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download History CSV",
                    data=csv,
                    file_name=f"intake_report_{date.today()}.csv",
                    mime='text/csv',
                )
            else:
                st.info("No intake records found for this period.")

    # --- TAB: AUDIT ---
    if "Audit" in tab_list:
        with tabs[tab_list.index("Audit")]:
            st.subheader("Manual Inventory Audit")
            exp_data, dep_data = get_sb_data("Exposed_Wigs"), get_sb_data("Big_Depot")
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
                        st.error("SKU Not Found in Pv")

                if st.session_state.audit_verify["name"]:
                    st.info(f"System Stock: {st.session_state.audit_verify['sys']}")
                    with st.form("aud_form"):
                        m = st.number_input("Manual (Shelf)", min_value=0)
                        e = st.number_input("Exposed (Auto)", value=st.session_state.audit_verify["auto_exp"])
                        r = st.number_input("Returns", min_value=0)
                        b = st.number_input("Big Depot (Auto)", value=st.session_state.audit_verify["auto_depot"])
                        if st.form_submit_button("Save Audit"):
                            tp = m + e + r + b
                            ds = tp - st.session_state.audit_verify["sys"]
                            supabase.table("Inventory_Audit").insert({"Date": str(date.today()), "SKU": a_sku, "Name": st.session_state.audit_verify["name"], "Category": st.session_state.audit_verify["cat"], "Counter_Name": counter, "Total_Physical": tp, "System_Stock": st.session_state.audit_verify["sys"], "Discrepancy": ds}).execute()
                            st.cache_data.clear()
                            st.success(f"Recorded! Diff: {ds}")
                            st.rerun()
            with cb:
                st.markdown("### Recent Audits")
                aud_h = get_sb_data("Inventory_Audit")
                if not aud_h.empty: st.dataframe(aud_h.sort_values(by="Date", ascending=False), use_container_width=True, hide_index=True)

    # --- TAB: SALES ---
    if "Sales" in tab_list:
        with tabs[tab_list.index("Sales")]:
            cs1, cs2 = st.columns(2)
            old_f, new_f = cs1.file_uploader("OLD Square File", type=['xlsx'], key="sales_old"), cs2.file_uploader("NEW Square File", type=['xlsx'], key="sales_new")
            if old_f and new_f:
                df_o, df_n = clean_location_data(old_f, "Pv"), clean_location_data(new_f, "Pv")
                comp = pd.merge(df_o[['SKU', 'Full Name', 'Category', 'Stock', 'Price']], df_n[['SKU', 'Stock']], on='SKU', suffixes=('_old', '_new'))
                comp['Sold'] = comp['Stock_old'] - comp['Stock_new']
                sales_df = comp[comp['Sold'] > 0].copy()
                if not sales_df.empty:
                    ed_sales = st.data_editor(sales_df[['Category', 'Full Name', 'SKU', 'Sold', 'Price']], hide_index=True)
                    st.metric("Total Revenue", f"${(ed_sales['Sold'] * ed_sales['Price']).sum():,.2f}")
                    st.plotly_chart(px.pie(ed_sales, values='Sold', names='Category'))

    # --- TAB: COMPARISON ---
    if "Comparison" in tab_list:
        with tabs[tab_list.index("Comparison")]:
            c_comp1, c_comp2 = st.columns(2)
            f_cv, f_pv = c_comp1.file_uploader("Canape-Vert File", type=['xlsx'], key="c1"), c_comp2.file_uploader("PV File", type=['xlsx'], key="c2")
            if f_cv and f_pv:
                d_cv, d_pv = clean_location_data(f_cv, "Canape-Vert"), clean_location_data(f_pv, "Pv")
                m_comp = pd.merge(d_cv[['Full Name', 'Category', 'Stock']], d_pv[['Full Name', 'Stock']], on='Full Name', how='outer', suffixes=('_CV', '_PV')).fillna(0)
                
                # Fix: Handle mixed types/NaN in Categories before sorting
                cats = sorted(m_comp['Category'].astype(str).unique().tolist())
                sel_cat = st.selectbox("Filter Category", ["All"] + cats)
                
                if sel_cat != "All": m_comp = m_comp[m_comp['Category'].astype(str) == sel_cat]
                m_comp['Status'] = m_comp.apply(lambda x: "Request Needed" if x['Stock_PV'] == 0 and x['Stock_CV'] > 0 else "Balanced", axis=1)
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
                st.subheader("🐢 Slow Moving")
                st.dataframe(comp[(comp['Sold'] <= 0) & (comp['Stock_old'] > 0)].sort_values("Stock_old", ascending=False).head(10)[['Full Name', 'Stock_old']], hide_index=True)

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
                if not depot_data.empty: st.dataframe(depot_data.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)

    # --- TAB: EXPOSED ---
    if "Exposed" in tab_list:
        with tabs[tab_list.index("Exposed")]:
            exp_data = get_sb_data("Exposed_Wigs")
            st.dataframe(exp_data[['SKU', 'Full Name', 'Quantity', 'Location', 'Last_Updated']] if not exp_data.empty else pd.DataFrame(), use_container_width=True, hide_index=True)
            with st.form("exposed_form", clear_on_submit=True):
                e_sku = st.text_input("SKU").strip()
                e_qty = st.number_input("Qty on Display", min_value=0)
                e_loc = st.selectbox("Location", ["Pv", "Canape-Vert"])
                if st.form_submit_button("Save"):
                    match = master_inventory[master_inventory['SKU'].str.lower() == e_sku.lower()]
                    payload = {"SKU": e_sku, "Full Name": match['Full Name'].iloc[0] if not match.empty else "Unknown", "Quantity": e_qty, "Location": e_loc, "Last_Updated": datetime.now().strftime("%Y-%m-%d %H:%M")}
                    existing = exp_data[(exp_data['SKU'] == e_sku) & (exp_data['Location'] == e_loc)] if not exp_data.empty else pd.DataFrame()
                    if not existing.empty:
                        supabase.table("Exposed_Wigs").update(payload).eq("id", existing['id'].iloc[0]).execute()
                    else:
                        supabase.table("Exposed_Wigs").insert(payload).execute()
                    st.cache_data.clear()
                    st.rerun()

    # --- CLEANUP TAB ---
    if "Cleanup" in tab_list:
        with tabs[tab_list.index("Cleanup")]:
            clean_f = st.file_uploader("Upload Square Export for Audit", type=['xlsx'])
            if clean_f:
                rdf = pd.read_excel(clean_f, skiprows=1)
                c_sku = 'SKU' if 'SKU' in rdf.columns else None
                c_cat = 'Category' if 'Category' in rdf.columns else ('Categories' if 'Categories' in rdf.columns else None)
                if c_sku and c_cat:
                    st.warning(f"Missing SKU: {len(rdf[rdf[c_sku].isna()])}")
                    st.dataframe(rdf[rdf[c_sku].isna()])

elif authentication_status is False: st.error('Incorrect Login')
elif authentication_status is None: st.warning('Please Login')




