import streamlit as st
import pandas as pd
from supabase import create_client, Client
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import io
import requests

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Dressupht ERP v6.0", layout="wide")

# --- 2. SUPABASE CONNECTION ---
@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

# --- 3. HELPER FUNCTIONS ---
@st.cache_data(ttl=600)
def fetch_master_inventory():
    try:
        query = supabase.table("Master_Inventory").select("*").execute()
        df = pd.DataFrame(query.data)
        if not df.empty:
            # Default sort by Name as per your preference
            df = df.sort_values(by="Full Name")
        return df
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

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
        
        # We ADDED 'Token' to the mapping here
        mapping = {
            'Item Name': 'Full Name', 
            'SKU': 'SKU', 
            'Categories': 'Category', 
            'Price': 'Price',
            'Token': 'Token' 
        }
        df = df.rename(columns=mapping)
        
        stock_col = "Current Quantity Dressup Haiti" if loc_name == "Canape-Vert" else "Current Quantity Dressupht Pv"
        
        if 'Token' not in df.columns:
            df['Token'] = "NO_TOKEN"

        df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int) if stock_col in df.columns else 0
        df['SKU'] = df['SKU'].astype(str).str.strip().replace(['nan', ''], 'NO_SKU')
        df['Category'] = df['Category'].fillna("Uncategorized").astype(str)
        df['Location'] = loc_name
        df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
        
        return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location', 'Token']].copy()

    df1 = process_file(file_cv, "Canape-Vert")
    df2 = process_file(file_pv, "Pv")
    return pd.concat([df1, df2], ignore_index=True)

# --- 3. HELPER FUNCTIONS (Continued) ---

SQUARE_API_URL = "https://connect.squareup.com/v2"
HEADERS = {
    "Square-Version": "2024-01-17", 
    "Authorization": f"Bearer {st.secrets['SQUARE_ACCESS_TOKEN']}",
    "Content-Type": "application/json"
}

def process_square_json(catalog_json, inventory_json, locations_map):
    categories = {obj['id']: obj.get('category_data', {}).get('name', 'Uncategorized') 
                  for obj in catalog_json.get('objects', []) if obj['type'] == 'CATEGORY'}

    counts = {(entry.get('catalog_object_id'), entry.get('location_id')): int(float(entry.get('quantity', 0))) 
              for entry in inventory_json.get('counts', [])}

    # Map Square's names to your internal App names
    target_locs = {
        "Dressup Haiti": "Canape-Vert",
        "Dressup Pv": "Pv"
    }

    rows = []
    for obj in catalog_json.get('objects', []):
        if obj['type'] == 'ITEM':
            item_name = obj.get('item_data', {}).get('name', 'Unknown')
            cat_id = obj.get('item_data', {}).get('category_id')
            cat_name = categories.get(cat_id, "Uncategorized")
            
            for var in obj.get('item_data', {}).get('variations', []):
                var_id = var['id']
                sku = var.get('item_variation_data', {}).get('sku', 'NO_SKU')
                price_data = var.get('item_variation_data', {}).get('price_money', {})
                price = price_data.get('amount', 0) / 100

                for square_name, app_name in target_locs.items():
                    loc_id = locations_map.get(square_name)
                    if loc_id:
                        rows.append({
                            'SKU': sku, 'Full Name': item_name, 'Stock': counts.get((var_id, loc_id), 0),
                            'Price': price, 'Category': cat_name, 'Location': app_name, 'Token': var_id
                        })
    return pd.DataFrame(rows)

def fetch_square_data():
    try:
        loc_res = requests.get(f"{SQUARE_API_URL}/locations", headers=HEADERS).json()
        # Create a map of {Name: ID}
        locations = {l['name']: l['id'] for l in loc_res.get('locations', [])}
        
        cat_res = requests.get(f"{SQUARE_API_URL}/catalog/list?types=ITEM,CATEGORY", headers=HEADERS).json()
        inv_res = requests.get(f"{SQUARE_API_URL}/inventory/counts", headers=HEADERS).json()
        
        return process_square_json(cat_res, inv_res, locations)
    except Exception as e:
        st.error(f"API Error: {e}")
        return pd.DataFrame()

# --- 4. AUTHENTICATION ---
usernames_list = ["djessie", "kevin", "casimir", "melchisedek", "david", "darius", "eliada", "sebastien", "guirlene", "carmela", "angelina", "tamara", "dorotheline", "sarah", "valerie", "saouda", "marie france", "carelle", "annaelle", "gerdine", "martilda"]
credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames_list}}
credentials['usernames']['kevin']['password'] = "The$100$Raven"

authenticator = stauth.Authenticate(credentials, "inventory_cookie", "abcdef123456_key", 30)
name, authentication_status, username = authenticator.login(location='main')

# --- 5. APP LOGIC ---
if authentication_status:
    role, loc = get_user_role(username)
    master_inventory = fetch_master_inventory()

    # --- SIDEBAR ---
    with st.sidebar:
        st.markdown(f"<h1 style='text-align: center;'>{username.upper()}</h1>", unsafe_allow_html=True)
        st.write(f"**🛡️ Access:** {role}")
        st.write(f"**📍 Location:** {loc}")
        st.divider()
        
        if role in ["Admin", "Manager"]:
            st.subheader("🔄 Square API Sync")
            if st.button("Sync Live from Square", use_container_width=True):
                with st.spinner("Fetching live data..."):
                    api_df = fetch_square_data()
                    if not api_df.empty:
                        supabase.table("Master_Inventory").delete().neq("SKU", "VOID").execute()
                        supabase.table("Master_Inventory").insert(api_df.to_dict('records')).execute()
                        st.cache_data.clear()
                        st.success("API Sync Successful!")
                        time.sleep(1)
                        st.rerun()

            st.divider()
            st.subheader("📦 Manual Excel Sync")
            f_cv = st.file_uploader("Canape-Vert (Excel)", type=['xlsx'], key="side_cv")
            f_pv = st.file_uploader("PV (Excel)", type=['xlsx'], key="side_pv")
            
            if st.button("🚀 Overwrite via Excel", use_container_width=True):
                if f_cv and f_pv:
                    with st.spinner("Processing..."):
                        final_df = clean_and_combine(f_cv, f_pv)
                        supabase.table("Master_Inventory").delete().neq("SKU", "VOID").execute()
                        supabase.table("Master_Inventory").insert(final_df.to_dict('records')).execute()
                        st.cache_data.clear()
                        st.success("Database Updated via Excel!")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.warning("Please upload both files first.")
        
        authenticator.logout('Logout', 'sidebar')

    # --- TABS SETUP ---
    tab_list = ["Library", "Arrival", "Inventory", "Mannequin", "Depot", "Compare", "Sales", "Admin", "Password"]
    tabs = st.tabs(tab_list)

    # --- 1. LIBRARY TAB ---
    with tabs[0]:
        if not master_inventory.empty:
            c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
            search_query = c1.text_input("🔍 Search", placeholder="Tokenized search...").lower()
            sel_loc = c2.selectbox("Location", ["All Locations"] + sorted(master_inventory['Location'].unique().tolist()))
            sel_cat = c3.selectbox("Category", ["All Categories"] + sorted(master_inventory['Category'].unique().tolist()))
            sort_choice = c4.selectbox("Sort By", ["Name", "Category", "Location", "Stock (High-Low)"])

            disp_df = master_inventory.copy()
            if sel_loc != "All Locations": disp_df = disp_df[disp_df['Location'] == sel_loc]
            if sel_cat != "All Categories": disp_df = disp_df[disp_df['Category'] == sel_cat]

            if search_query:
                for token in search_query.split():
                    disp_df = disp_df[disp_df['Full Name'].str.lower().str.contains(token) | disp_df['SKU'].str.lower().str.contains(token)]

            sort_map = {"Name": "Full Name", "Category": ["Category", "Full Name"], "Location": ["Location", "Full Name"], "Stock (High-Low)": "Stock"}
            ascending_logic = False if sort_choice == "Stock (High-Low)" else True
            disp_df = disp_df.sort_values(by=sort_map[sort_choice], ascending=ascending_logic)

            st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)
            st.caption(f"Showing {len(disp_df)} items")
        else:
            st.info("No data in Master_Inventory.")

    # --- 2. ARRIVAL TAB ---
    with tabs[1]:
        st.header("🚢 Arrival Management")
        if role not in ["Admin", "Manager"]:
            st.warning("🔒 Access Denied. Only Admins and Managers can log new arrivals.")
        else:
            if 'arrival_verify' not in st.session_state:
                st.session_state.arrival_verify = {"name": None, "cat": None, "sku": ""}

            col1, col2 = st.columns([1, 2])
            with col1:
                st.subheader("Log Received Stock")
                in_sku = st.text_input("Scan or Enter SKU", key="arr_sku_input").strip()
                
                if in_sku and in_sku != st.session_state.arrival_verify["sku"]:
                    match = master_inventory[master_inventory['SKU'].str.lower() == in_sku.lower()]
                    if not match.empty:
                        st.session_state.arrival_verify = {"name": match['Full Name'].iloc[0], "cat": match['Category'].iloc[0], "sku": in_sku}
                    else:
                        st.session_state.arrival_verify = {"name": None, "cat": None, "sku": in_sku}
                        st.error("SKU not found.")

                if st.session_state.arrival_verify["name"]:
                    st.info(f"**Item:** {st.session_state.arrival_verify['name']}\n\n**Category:** {st.session_state.arrival_verify['cat']}")
                    with st.form("arrival_form", clear_on_submit=True):
                        arr_date = st.date_input("Arrival Date", value=date.today())
                        arr_qty = st.number_input("Quantity Received", min_value=1, step=1)
                        arr_loc = st.selectbox("Receiving Location", ["Pv", "Canape-Vert"])
                        if st.form_submit_button("✅ Confirm Arrival"):
                            arrival_data = {"Date": str(arr_date), "SKU": st.session_state.arrival_verify["sku"], "Wig Name": st.session_state.arrival_verify["name"], "Category": st.session_state.arrival_verify["cat"], "Quantity": arr_qty, "User": username, "Location": arr_loc}
                            supabase.table("Arrival").insert(arrival_data).execute()
                            st.success("Logged Arrival!")
                            st.session_state.arrival_verify = {"name": None, "cat": None, "sku": ""}
                            time.sleep(1)
                            st.rerun()
            with col2:
                st.subheader("Recent Arrivals")
                arr_log = supabase.table("Arrival").select("*").order("Date", desc=True).limit(20).execute()
                if arr_log.data:
                    st.dataframe(pd.DataFrame(arr_log.data)[['Date', 'Wig Name', 'Quantity', 'Location', 'User']], use_container_width=True, hide_index=True)

    # --- 3. INVENTORY (AUDIT) TAB ---
    with tabs[2]:
        st.header("📋 Physical Inventory Audit (PV Only)")
        col_select1, col_select2 = st.columns(2)
        with col_select1:
            audit_cat = st.selectbox("1. Select Category to Audit", sorted(master_inventory['Category'].unique().tolist()) if not master_inventory.empty else ["None"])
        with col_select2:
            counter = st.selectbox("2. Person Counting", [u.upper() for u in usernames_list])

        exp_data = supabase.table("Mannequin").select("SKU, Quantity").execute()
        dep_data = supabase.table("Depot").select("SKU, Quantity, Type").execute()
        df_exp = pd.DataFrame(exp_data.data) if exp_data.data else pd.DataFrame(columns=['SKU', 'Quantity'])
        df_dep = pd.DataFrame(dep_data.data) if dep_data.data else pd.DataFrame(columns=['SKU', 'Quantity', 'Type'])

        cat_items = master_inventory[(master_inventory['Category'] == audit_cat) & (master_inventory['Location'] == "Pv")].copy()
        
        if not cat_items.empty:
            def get_depot_net(sku):
                if df_dep.empty: return 0
                dm = df_dep[df_dep['SKU'].str.lower() == sku.lower()]
                return int(dm[dm['Type'] == "Addition"]['Quantity'].sum() - dm[dm['Type'] == "Subtraction"]['Quantity'].sum())

            cat_items['Exposed'] = cat_items['SKU'].apply(lambda x: int(df_exp[df_exp['SKU'].str.lower() == x.lower()]['Quantity'].sum()) if not df_exp.empty else 0)
            cat_items['Depot'] = cat_items['SKU'].apply(get_depot_net)
            cat_items['Shelf_Count'] = 0
            cat_items['Returns'] = 0

            edited_df = st.data_editor(
                cat_items[['SKU', 'Full Name', 'Stock', 'Exposed', 'Depot', 'Shelf_Count', 'Returns']],
                column_config={"Stock": "System", "Exposed": "📍 Mannequin", "Depot": "📦 Depot", "Shelf_Count": st.column_config.NumberColumn("🏢 Shelf", min_value=0), "Returns": st.column_config.NumberColumn("🔄 Returns", min_value=0)},
                disabled=["SKU", "Full Name", "Stock", "Exposed", "Depot"], hide_index=True, use_container_width=True, key=f"ed_{audit_cat}"
            )

            if st.button(f"💾 Submit All {len(edited_df)} Records", use_container_width=True):
                audit_entries = []
                for _, row in edited_df.iterrows():
                    total_phys = int(row['Shelf_Count'] + row['Exposed'] + row['Depot'] + row['Returns'])
                    audit_entries.append({"Date": str(date.today()), "SKU": str(row['SKU']), "Name": str(row['Full Name']), "Category": str(audit_cat), "Counter_Name": str(counter), "Total_Physical": total_phys, "System_Stock": int(row['Stock']), "Discrepancy": int(total_phys - row['Stock']), "Location": "Pv"})
                supabase.table("Inventory").insert(audit_entries).execute()
                st.success("Audit Saved!")
                time.sleep(1)
                st.rerun()

        st.divider()
        st.subheader("Audit History Log")
        log_sort = st.radio("Sort Log By:", ["Latest Date", "Category"], horizontal=True)
        log_res = supabase.table("Inventory").select("*").order("id", desc=True).limit(50).execute()
        if log_res.data:
            log_df = pd.DataFrame(log_res.data)
            if log_sort == "Latest Date": log_df = log_df.sort_values(by="id", ascending=False)
            else: log_df = log_df.sort_values(by=["Category", "Date"], ascending=[True, False])
            st.dataframe(log_df[['Date', 'Category', 'Name', 'Total_Physical', 'System_Stock', 'Discrepancy', 'Counter_Name']], use_container_width=True, hide_index=True)

    # --- 4. MANNEQUIN TAB ---
    with tabs[3]:
        st.header("👤 Mannequin Display")
        m_df = pd.DataFrame(supabase.table("Mannequin").select("*").execute().data)
        if not m_df.empty:
            m_df = m_df.sort_values(by="Last_Updated", ascending=False)
            st.write(f"Total on Display: {int(m_df['Quantity'].sum())}")
            for _, row in m_df.iterrows():
                c1, c2, c3, c4, c5 = st.columns([1, 2, 1, 2, 1])
                c1.write(row['SKU']); c2.write(row['Full Name']); c3.write(str(row['Quantity'])); c4.write(row['Last_Updated'])
                if c5.button("🗑️", key=f"m_{row['SKU']}"):
                    supabase.table("Mannequin").delete().eq("SKU", row['SKU']).execute()
                    st.rerun()
        
        st.divider()
        m_search = st.text_input("🔍 Add to Display").lower()
        if m_search:
            match = master_inventory[master_inventory['Full Name'].str.lower().contains(m_search) | master_inventory['SKU'].str.lower().contains(m_search)]
            if not match.empty:
                it = match.iloc[0]
                with st.form("m_form"):
                    q = st.number_input("Qty", 1, 2)
                    l = st.selectbox("Loc", ["Pv", "Canape-Vert"])
                    if st.form_submit_button("Set"):
                        supabase.table("Mannequin").delete().eq("SKU", it['SKU']).execute()
                        supabase.table("Mannequin").insert({"SKU": it['SKU'], "Full Name": it['Full Name'], "Quantity": q, "Location": l, "Last_Updated": datetime.now().strftime("%Y-%m-%d %H:%M")}).execute()
                        st.rerun()

    # --- 5. DEPOT TAB ---
    with tabs[4]:
        st.header("📦 Depot Management")
        d_df = pd.DataFrame(supabase.table("Depot").select("*").order("Date", desc=True).execute().data)
        if not d_df.empty:
            st.dataframe(d_df.head(10)[['Date', 'Wig Name', 'Type', 'Quantity', 'User']], use_container_width=True, hide_index=True)
        
        st.divider()
        d_search = st.text_input("🔍 Depot Search").lower()
        if d_search:
            match = master_inventory[master_inventory['Full Name'].str.lower().contains(d_search)]
            if not match.empty:
                it = match.iloc[0]
                with st.form("d_form"):
                    t = st.radio("Type", ["Addition", "Withdrawal"])
                    q = st.number_input("Qty", 1)
                    if st.form_submit_button("Log"):
                        supabase.table("Depot").insert({"Date": str(date.today()), "SKU": it['SKU'], "Wig Name": it['Full Name'], "Type": t, "Quantity": q, "User": username}).execute()
                        st.rerun()

    # --- 6. COMPARE TAB ---
    with tabs[5]:
        st.header("🔄 Location Comparison")
        if not master_inventory.empty:
            df_cv = master_inventory[master_inventory['Location'] == "Canape-Vert"][['SKU', 'Full Name', 'Stock']]
            df_pv = master_inventory[master_inventory['Location'] == "Pv"][['SKU', 'Stock']]
            comp = pd.merge(df_cv, df_pv, on="SKU", how="outer", suffixes=('_CV', '_PV')).fillna(0)
            st.dataframe(comp, use_container_width=True)

    # --- 7. SALES (FAST/SLOW MOVERS) ---
    with tabs[6]:
        st.header("💰 Sales Analysis (Token-Based)")
        
        # 1. Upload Old Export
        old_file = st.file_uploader("Upload Old Square Export (Excel)", type=['xlsx'], key="sales_old_file")

        if old_file and not master_inventory.empty:
            try:
                df_old = pd.read_excel(old_file, skiprows=1)
                df_old.columns = [str(c).strip() for c in df_old.columns]
                
                token_col = 'Token' if 'Token' in df_old.columns else None
                old_qty_col = "Current Quantity Dressupht Pv" 

                if not token_col:
                    st.error("Token column missing in uploaded file.")
                else:
                    df_current_pv = master_inventory[master_inventory['Location'] == "Pv"].copy()
                    
                    # Merge on Token
                    sales_comp = pd.merge(
                        df_old[[token_col, old_qty_col]], 
                        df_current_pv, 
                        on=token_col, 
                        how='inner',
                        suffixes=('_old', '_current')
                    )

                    # Calculate Actual Sales (Movement)
                    sales_comp['Sales'] = pd.to_numeric(sales_comp[old_qty_col], errors='coerce').fillna(0) - sales_comp['Stock']
                    
                    # --- A. FULL SALES VIEW ---
                    st.subheader("📊 All Sales Movement")
                    full_view = sales_comp[sales_comp['Sales'] != 0].copy()
                    st.dataframe(
                        full_view[['Full Name', 'SKU', 'Sales', 'Stock']].rename(columns={'Stock': 'Remaining'}),
                        use_container_width=True, 
                        hide_index=True
                    )

                    st.divider()

                    # --- B. TOP 10 RANKINGS ---
                    col_s1, col_s2 = st.columns(2)
                    
                    with col_s1:
                        st.subheader("🚀 Top 10 Fast Movers")
                        # Highest sales count first
                        fast_10 = sales_comp[sales_comp['Sales'] > 0].sort_values(by='Sales', ascending=False).head(10)
                        if not fast_10.empty:
                            st.dataframe(fast_10[['Full Name', 'Sales']], use_container_width=True, hide_index=True)
                        else:
                            st.write("No sales recorded.")

                    with col_s2:
                        st.subheader("🐢 Top 10 Slow Movers")
                        # Items with 0 or negative sales (returns), showing highest stock sitting idle
                        slow_10 = sales_comp[sales_comp['Sales'] <= 0].sort_values(by='Stock', ascending=False).head(10)
                        if not slow_10.empty:
                            st.dataframe(slow_10[['Full Name', 'Stock']], use_container_width=True, hide_index=True)
                        else:
                            st.write("Everything is moving!")
            
            except Exception as e:
                st.error(f"Error processing sales data: {e}")
        else:
            st.info("Upload an older Square export to calculate sales movement against current PV stock.")

    # --- 8. ADMIN TAB ---
    with tabs[7]:
        st.header("⚙️ Admin Control Tower")
        
        # Restriction: Strictly Admin Only
        if role != "Admin":
            st.error("🚫 Access Denied. This section is restricted to System Administrators.")
        else:
            admin_subtab = st.tabs(["👤 User Management", "📜 Global Activity Log", "🧹 Database Maintenance"])

            # --- SUB-TAB 1: USER MANAGEMENT ---
            with admin_subtab[0]:
                st.subheader("Manage Team Roles & Locations")
                try:
                    # Fetching from 'Role' table with your exact columns
                    users_query = supabase.table("Role").select("*").execute()
                    users_df = pd.DataFrame(users_query.data)
                    
                    if not users_df.empty:
                        # Displaying your specific columns
                        st.dataframe(
                            users_df[['User Name', 'Roles', 'Email', 'Location']], 
                            use_container_width=True, 
                            hide_index=True
                        )
                        
                        st.divider()
                        
                        col_up1, col_up2 = st.columns(2)
                        with col_up1:
                            st.markdown("##### 🔐 Update Permissions")
                            with st.form("role_update_form"):
                                target_user = st.selectbox("Select User", users_df['User Name'].unique())
                                new_role = st.selectbox("Assign New Role", ["Admin", "Manager", "Staff"])
                                if st.form_submit_button("Update Role"):
                                    supabase.table("Role").update({"Roles": new_role}).eq("User Name", target_user).execute()
                                    st.success(f"Updated {target_user} to {new_role}")
                                    time.sleep(1)
                                    st.rerun()
                        
                        with col_up2:
                            st.markdown("##### 📍 Update Staff Location")
                            with st.form("loc_update_form"):
                                target_user_loc = st.selectbox("Select User", users_df['User Name'].unique())
                                new_loc = st.selectbox("Assign Location", ["Pv", "Canape-Vert", "Both"])
                                if st.form_submit_button("Update Location"):
                                    supabase.table("Role").update({"Location": new_loc}).eq("User Name", target_user_loc).execute()
                                    st.success(f"Relocated {target_user_loc} to {new_loc}")
                                    time.sleep(1)
                                    st.rerun()
                    else:
                        st.warning("The Role table is currently empty.")
                except Exception as e:
                    st.error(f"Could not load user table: {e}")

            # --- SUB-TAB 2: GLOBAL ACTIVITY LOG ---
            with admin_subtab[1]:
                st.subheader("Recent System-Wide Actions")
                log_choice = st.radio("View Logs From:", ["Arrivals", "Inventory Audits", "Depot Movements", "Mannequin Display"], horizontal=True)
                
                # Mapping the selection to your exact Supabase table names
                table_map = {
                    "Arrivals": "Arrival",
                    "Inventory Audits": "Inventory",
                    "Depot Movements": "Depot",
                    "Mannequin Display": "Mannequin"
                }
                
                try:
                    # Fetch the last 50 actions from the selected table
                    logs = supabase.table(table_map[log_choice]).select("*").execute()
                    if logs.data:
                        logs_df = pd.DataFrame(logs.data)
                        
                        # Apply a sort if a date column exists
                        date_cols = ['Date', 'Last_Updated', 'created_at']
                        found_date = next((c for c in date_cols if c in logs_df.columns), None)
                        if found_date:
                            logs_df = logs_df.sort_values(by=found_date, ascending=False)
                        
                        st.dataframe(logs_df, use_container_width=True, hide_index=True)
                    else:
                        st.info(f"No records found in the {log_choice} table.")
                except Exception as e:
                    st.error(f"Error fetching logs: {e}")

            # --- SUB-TAB 3: DATABASE MAINTENANCE ---
            with admin_subtab[2]:
                st.subheader("Data Management")
                st.warning("⚠️ These tools allow you to export or manage bulk data.")
                
                col_maint1, col_maint2 = st.columns(2)
                
                with col_maint1:
                    st.write("### Export Data")
                    csv = master_inventory.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Master Inventory (CSV)",
                        data=csv,
                        file_name=f"Master_Inventory_{date.today()}.csv",
                        mime='text/csv',
                    )
                
                with col_maint2:
                    st.write("### System Status")
                    total_items = len(master_inventory)
                    st.metric("Total Items in System", total_items)
                    st.info("To clear or reset database tables, please use the Supabase SQL Editor for safety.")

    # --- 9. PASSWORD TAB ---
    with tabs[8]:
        st.header("🔑 Password Management")
        # Pre-integrated reset from the library
        authenticator.reset_password(username=username)
        
# --- FOOTER ---
st.sidebar.caption(f"Dressupht ERP v6.0 | {date.today()}")



