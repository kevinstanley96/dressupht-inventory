import streamlit as st
import pandas as pd
from supabase import create_client, Client
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import io

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Dressupht ERP v6.0", layout="wide")

# --- 2. SUPABASE CONNECTION ---
@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

# --- 3. HELPER FUNCTIONS ---
def get_user_role(username):
    try:
        res = supabase.table("Role").select("Roles, Location").eq("User Name", username.lower()).execute()
        if res.data:
            return res.data[0]['Roles'], res.data[0]['Location']
        return "Staff", "Unknown"
    except Exception:
        return "Staff", "Unknown"

def clean_and_combine(file_cv, file_pv):
    def process_file(file, loc_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip() for c in df.columns]
        mapping = {'Item Name': 'Full Name', 'SKU': 'SKU', 'Categories': 'Category', 'Price': 'Price'}
        df = df.rename(columns=mapping)
        
        stock_col = "Current Quantity Dressup Haiti" if loc_name == "Canape-Vert" else "Current Quantity Dressupht Pv"
        df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int) if stock_col in df.columns else 0
        df['SKU'] = df['SKU'].astype(str).str.strip().replace(['nan', ''], 'NO_SKU')
        df['Category'] = df['Category'].fillna("Uncategorized").astype(str)
        df['Location'] = loc_name
        df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
        
        return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']].copy()

    df1 = process_file(file_cv, "Canape-Vert")
    df2 = process_file(file_pv, "Pv")
    return pd.concat([df1, df2], ignore_index=True)

# --- 4. AUTHENTICATION ---
usernames_list = ["djessie", "kevin", "casimir", "melchisedek", "david", "darius", "eliada", "sebastien", "guirlene", "carmela", "angelina", "tamara", "dorotheline", "sarah", "valerie", "saouda", "marie france", "carelle", "annaelle", "gerdine", "martilda"]
credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames_list}}
credentials['usernames']['kevin']['password'] = "The$100$Raven"

authenticator = stauth.Authenticate(credentials, "inventory_cookie", "abcdef123456_key", 30)
name, authentication_status, username = authenticator.login(location='main')

# --- 5. APP LOGIC ---
if authentication_status:
    role, loc = get_user_role(username)

    # --- SIDEBAR ---
    with st.sidebar:
        st.markdown(f"<h1 style='text-align: center;'>{username.upper()}</h1>", unsafe_allow_html=True)
        st.write(f"**🛡️ Access:** {role}")
        st.write(f"**📍 Location:** {loc}")
        st.divider()
        
        if role in ["Admin", "Manager"]:
            st.subheader("📦 Sync Master Inventory")
            f_cv = st.file_uploader("Canape-Vert (Excel)", type=['xlsx'], key="side_cv")
            f_pv = st.file_uploader("PV (Excel)", type=['xlsx'], key="side_pv")
            
            if st.button("🚀 Overwrite & Sync", use_container_width=True):
                if f_cv and f_pv:
                    with st.spinner("Processing..."):
                        final_df = clean_and_combine(f_cv, f_pv)
                        supabase.table("Master_Inventory").delete().neq("SKU", "VOID").execute()
                        supabase.table("Master_Inventory").insert(final_df.to_dict('records')).execute()
                        st.success("Database Updated!")
                        time.sleep(1)
                        st.rerun()
        
        authenticator.logout('Logout', 'sidebar')

    # --- TABS SETUP ---
    tab_list = [
        "Library", 
        "Arrival", 
        "Inventory", 
        "Mannequin", 
        "Depot", 
        "Compare", 
        "Sales", 
        "Admin", 
        "Password"
    ]
    tabs = st.tabs(tab_list)

    # --- 1. LIBRARY TAB (Functional) ---
    with tabs[0]:
        try:
            query = supabase.table("Master_Inventory").select("*").execute()
            master_inventory = pd.DataFrame(query.data)
        except Exception:
            master_inventory = pd.DataFrame()

        if not master_inventory.empty:
            c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
            search_query = c1.text_input("🔍 Search", placeholder="Tokenized search...").lower()
            sel_loc = c2.selectbox("Location", ["All Locations"] + sorted(master_inventory['Location'].unique().tolist()))
            sel_cat = c3.selectbox("Category", ["All Categories"] + sorted(master_inventory['Category'].unique().tolist()))
            sort_choice = c4.selectbox("Sort By", ["Name", "Category", "Location", "Stock (High-Low)"])

            disp_df = master_inventory.copy()

            # Filters
            if sel_loc != "All Locations":
                disp_df = disp_df[disp_df['Location'] == sel_loc]
            if sel_cat != "All Categories":
                disp_df = disp_df[disp_df['Category'] == sel_cat]

            # Tokenized Search
            if search_query:
                for token in search_query.split():
                    disp_df = disp_df[
                        disp_df['Full Name'].str.lower().str.contains(token) | 
                        disp_df['SKU'].str.lower().str.contains(token)
                    ]

            # Sorting
            sort_map = {
                "Name": "Full Name",
                "Category": ["Category", "Full Name"],
                "Location": ["Location", "Full Name"],
                "Stock (High-Low)": "Stock"
            }
            ascending_logic = False if sort_choice == "Stock (High-Low)" else True
            disp_df = disp_df.sort_values(by=sort_map[sort_choice], ascending=ascending_logic)

            st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)
            st.caption(f"Showing {len(disp_df)} items")
        else:
            st.info("No data in Master_Inventory.")

    # --- 2. ARRIVAL TAB ---
    with tabs[1]:
        st.header("🚢 Arrival Management")
        
        # Restriction: Only Admins and Managers
        if role not in ["Admin", "Manager"]:
            st.warning("🔒 Access Denied. Only Admins and Managers can log new arrivals.")
        else:
            # Initialize session state for SKU verification if not exists
            if 'arrival_verify' not in st.session_state:
                st.session_state.arrival_verify = {"name": None, "cat": None, "sku": ""}

            col1, col2 = st.columns([1, 2])

            with col1:
                st.subheader("Log Received Stock")
                # A. SKU Entry
                in_sku = st.text_input("Scan or Enter SKU", key="arr_sku_input").strip()
                
                # Trigger lookup when SKU changes
                if in_sku and in_sku != st.session_state.arrival_verify["sku"]:
                    # Search in Master Inventory (checking PV by default as it's the main intake)
                    match = master_inventory[master_inventory['SKU'].str.lower() == in_sku.lower()]
                    
                    if not match.empty:
                        # Take the first match found
                        st.session_state.arrival_verify = {
                            "name": match['Full Name'].iloc[0],
                            "cat": match['Category'].iloc[0],
                            "sku": in_sku
                        }
                    else:
                        st.session_state.arrival_verify = {"name": None, "cat": None, "sku": in_sku}
                        st.error("SKU not found in Master Inventory. Please check the Library.")

                # B. Data Entry Form (Only shows if SKU is verified)
                if st.session_state.arrival_verify["name"]:
                    st.info(f"**Item:** {st.session_state.arrival_verify['name']}\n\n**Category:** {st.session_state.arrival_verify['cat']}")
                    
                    with st.form("arrival_form", clear_on_submit=True):
                        arr_date = st.date_input("Arrival Date", value=date.today())
                        arr_qty = st.number_input("Quantity Received", min_value=1, step=1)
                        arr_loc = st.selectbox("Receiving Location", ["Pv", "Canape-Vert"])
                        
                        if st.form_submit_button("✅ Confirm Arrival"):
                            arrival_data = {
                                "Date": str(arr_date),
                                "SKU": st.session_state.arrival_verify["sku"],
                                "Wig Name": st.session_state.arrival_verify["name"],
                                "Category": st.session_state.arrival_verify["cat"],
                                "Quantity": arr_qty,
                                "User": username,
                                "Location": arr_loc
                            }
                            
                            # Insert into Supabase 'Arrival' table
                            supabase.table("Arrival").insert(arrival_data).execute()
                            
                            st.success(f"Logged {arr_qty} units of {st.session_state.arrival_verify['name']}")
                            # Clear verification state for next scan
                            st.session_state.arrival_verify = {"name": None, "cat": None, "sku": ""}
                            time.sleep(1)
                            st.rerun()

            with col2:
                st.subheader("Recent Arrivals")
                try:
                    # Fetch logs from the Arrival table
                    arr_log = supabase.table("Arrival").select("*").order("Date", desc=True).limit(20).execute()
                    if arr_log.data:
                        log_df = pd.DataFrame(arr_log.data)
                        st.dataframe(
                            log_df[['Date', 'Wig Name', 'Quantity', 'Location', 'User']], 
                            use_container_width=True, 
                            hide_index=True
                        )
                    else:
                        st.write("No recent arrivals logged.")
                except Exception:
                    st.error("Could not load arrival logs.")

    # --- 3. INVENTORY (AUDIT) TAB ---
    with tabs[2]:
        st.header("📋 Physical Inventory Audit (PV Only)")

        # Initialize Session State for Audit
        if 'audit_verify' not in st.session_state:
            st.session_state.audit_verify = {"name": None, "cat": None, "sys": 0, "sku": "", "auto_exp": 0, "auto_depot": 0}

        # 1. Fetch live data for Mannequin and Depot to pre-fill the form
        try:
            exp_data = supabase.table("Mannequin").select("*").execute()
            dep_data = supabase.table("Depot").select("*").execute()
            df_exp = pd.DataFrame(exp_data.data) if exp_data.data else pd.DataFrame()
            df_dep = pd.DataFrame(dep_data.data) if dep_data.data else pd.DataFrame()
        except Exception:
            df_exp, df_dep = pd.DataFrame(), pd.DataFrame()

        ca, cb = st.columns([1, 2])

        with ca:
            st.subheader("Audit Entry")
            # A. Counter Selection
            counter = st.selectbox("Person Counting", [u.upper() for u in usernames_list])
            
            # B. SKU / Name Search (Tokenized)
            search_input = st.text_input("🔍 Search SKU or Name", key="audit_search").lower()
            
            if search_input:
                # Filter Master Inventory for PV only
                pv_master = master_inventory[master_inventory['Location'] == "Pv"]
                
                # Tokenized Search Logic
                tokens = search_input.split()
                match = pv_master.copy()
                for t in tokens:
                    match = match[match['Full Name'].str.lower().str.contains(t) | match['SKU'].str.lower().str.contains(t)]
                
                if not match.empty:
                    selected_item = match.iloc[0] # Grab the first match
                    sku_to_audit = selected_item['SKU']
                    
                    # C. Auto-Calculate Live Totals from other tables
                    # Calculate Exposed (Mannequin)
                    e_val = int(df_exp[df_exp['SKU'].str.lower() == sku_to_audit.lower()]['Quantity'].sum()) if not df_exp.empty else 0
                    
                    # Calculate Depot (Additions - Subtractions)
                    d_val = 0
                    if not df_dep.empty:
                        dm = df_dep[df_dep['SKU'].str.lower() == sku_to_audit.lower()]
                        d_val = int(dm[dm['Type'] == "Addition"]['Quantity'].sum() - dm[dm['Type'] == "Subtraction"]['Quantity'].sum())

                    # Update Session State
                    st.session_state.audit_verify = {
                        "name": selected_item['Full Name'],
                        "cat": selected_item['Category'],
                        "sys": int(selected_item['Stock']),
                        "sku": sku_to_audit,
                        "auto_exp": e_val,
                        "auto_depot": d_val
                    }
                else:
                    st.session_state.audit_verify["name"] = None

            # D. The Audit Form
            if st.session_state.audit_verify["name"]:
                st.info(f"**Item:** {st.session_state.audit_verify['name']}\n\n**System Stock:** {st.session_state.audit_verify['sys']}")
                
                with st.form("audit_form_pv", clear_on_submit=True):
                    f_shelf = st.number_input("Shelf (Manual Count)", min_value=0, step=1)
                    f_exp = st.number_input("Exposed (Mannequin)", value=st.session_state.audit_verify["auto_exp"])
                    f_dep = st.number_input("Depot (Backstock)", value=st.session_state.audit_verify["auto_depot"])
                    f_ret = st.number_input("Returns", min_value=0, step=1)
                    
                    if st.form_submit_button("💾 Save Audit Record"):
                        total_phys = f_shelf + f_exp + f_dep + f_ret
                        discrepancy = total_phys - st.session_state.audit_verify["sys"]
                        
                        audit_entry = {
                            "Date": str(date.today()),
                            "SKU": st.session_state.audit_verify["sku"],
                            "Name": st.session_state.audit_verify["name"],
                            "Category": st.session_state.audit_verify["cat"],
                            "Counter_Name": counter,
                            "Total_Physical": total_phys,
                            "System_Stock": st.session_state.audit_verify["sys"],
                            "Discrepancy": discrepancy,
                            "Location": "Pv"
                        }
                        
                        supabase.table("Inventory_Audit").insert(audit_entry).execute()
                        st.success(f"Audit Saved! Discrepancy: {discrepancy}")
                        time.sleep(1)
                        st.rerun()

        with cb:
            st.subheader("Inventory Audit Log")
            try:
                aud_log = supabase.table("Inventory_Audit").select("*").order("Date", desc=True).limit(15).execute()
                if aud_log.data:
                    df_log = pd.DataFrame(aud_log.data)
                    # Color coding discrepancies
                    def color_diff(val):
                        color = 'red' if val < 0 else 'green' if val > 0 else 'white'
                        return f'color: {color}'
                    
                    st.dataframe(df_log[['Date', 'Name', 'Total_Physical', 'System_Stock', 'Discrepancy', 'Counter_Name']], 
                                 use_container_width=True, hide_index=True)
                else:
                    st.write("No audit records found.")
            except Exception:
                st.write("Ready to log audits.")

    # --- 4. MANNEQUIN (EXPOSED) TAB ---
    with tabs[3]:
        st.header("👤 Mannequin Display")
        st.write("Placeholder for wigs currently on display.")

    # --- 5. DEPOT (BIG DEPOT) TAB ---
    with tabs[4]:
        st.header("📦 Depot")
        st.write("Placeholder for back-stock management.")

    # --- 6. COMPARE TAB ---
    with tabs[5]:
        st.header("🔄 Compare")
        st.write("Placeholder for location comparison (CV vs PV).")

    # --- 7. SALES TAB ---
    with tabs[6]:
        st.header("💰 Sales & Movement")
        st.write("Placeholder for Sales data and Fast/Slow movers.")

    # --- 8. ADMIN TAB ---
    with tabs[7]:
        st.header("⚙️ Admin Panel")
        st.write("Placeholder for user roles and system settings.")

    # --- 9. PASSWORD TAB ---
    with tabs[8]:
        st.header("🔑 Password Management")
        # Pre-integrated reset from the library
        authenticator.reset_password(username=username)

elif authentication_status is False:
    st.error('Username/password is incorrect')
elif authentication_status is None:
    st.warning('Please login')






