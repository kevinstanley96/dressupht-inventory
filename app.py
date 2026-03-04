import streamlit as st
import pandas as pd
from supabase import create_client, Client
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import io

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Dressup Haiti Stock", layout="wide")

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
        
        # We ADDED 'Token' to the mapping here
        mapping = {
            'Item Name': 'Full Name', 
            'SKU': 'SKU', 
            'Categories': 'Category', 
            'Price': 'Price',
            'Token': 'Token' # <--- This matches the column name in Square Excel
        }
        df = df.rename(columns=mapping)
        
        stock_col = "Current Quantity Dressup Haiti" if loc_name == "Canape-Vert" else "Current Quantity Dressupht Pv"
        
        # Ensure the column exists in the Excel, if not, create an empty one so it doesn't crash
        if 'Token' not in df.columns:
            df['Token'] = "NO_TOKEN"

        df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int) if stock_col in df.columns else 0
        df['SKU'] = df['SKU'].astype(str).str.strip().replace(['nan', ''], 'NO_SKU')
        df['Category'] = df['Category'].fillna("Uncategorized").astype(str)
        df['Location'] = loc_name
        df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
        
        # Include 'Token' in the return list
        return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location', 'Token']].copy()

    df1 = process_file(file_cv, "Canape-Vert")
    df2 = process_file(file_pv, "Pv")
    return pd.concat([df1, df2], ignore_index=True)

    def search_inventory(df, query):
        tokens = query.lower().split()
        result = df.copy()
        for t in tokens:
            result = result[
                result['Full Name'].str.lower().str.contains(t) |
                result['SKU'].str.lower().str.startswith(t)
            ]
        return result

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
                disp_df = search_inventory(disp_df, search_query)

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
        st.header("📋 Physical Inventory ")

        if 'audit_verify' not in st.session_state:
            st.session_state.audit_verify = {"name": None, "cat": None, "sys": 0, "sku": "", "auto_exp": 0, "auto_depot": 0}

        # 1. Fetch live data for calculations
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
            counter = st.selectbox("Person Counting", [u.upper() for u in usernames_list])
            search_input = st.text_input("🔍 Search SKU or Name", key="audit_search").lower()
            
            if search_input:
                pv_master = master_inventory[master_inventory['Location'] == "Pv"]
                tokens = search_input.split()
                match = pv_master.copy()
                for t in tokens:
                    match = search_inventory(pv_master, search_input)
                
                if not match.empty:
                    selected_item = match.iloc[0]
                    sku_to_audit = selected_item['SKU']
                    
                    e_val = int(df_exp[df_exp['SKU'].str.lower() == sku_to_audit.lower()]['Quantity'].sum()) if not df_exp.empty else 0
                    d_val = 0
                    if not df_dep.empty:
                        dm = df_dep[df_dep['SKU'].str.lower() == sku_to_audit.lower()]
                        # Note: Summing Depot logic (Additions - Subtractions)
                        d_val = int(dm[dm['Type'] == "Addition"]['Quantity'].sum() - dm[dm['Type'] == "Subtraction"]['Quantity'].sum())

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

            if st.session_state.audit_verify["name"]:
                st.info(f"**Item:** {st.session_state.audit_verify['name']}\n\n**System Stock:** {st.session_state.audit_verify['sys']}")
                with st.form("audit_form_pv", clear_on_submit=True):
                    f_shelf = st.number_input("Shelf (Manual Count)", min_value=0, step=1)
                    f_exp = st.number_input("Exposed (Mannequin)", value=st.session_state.audit_verify["auto_exp"])
                    f_dep = st.number_input("Depot (Backstock)", value=st.session_state.audit_verify["auto_depot"])
                    f_ret = st.number_input("Returns", min_value=0, step=1)
                    
                    if st.form_submit_button("💾 Save Audit Record"):
                        total_phys = int(f_shelf + f_exp + f_dep + f_ret)
                        sys_stock = int(st.session_state.audit_verify["sys"])
                        discrepancy = int(total_phys - sys_stock)
                        
                        audit_entry = {
                            "Date": str(date.today()),
                            "SKU": str(st.session_state.audit_verify["sku"]),
                            "Name": str(st.session_state.audit_verify["name"]),
                            "Category": str(st.session_state.audit_verify["cat"]),
                            "Counter_Name": str(counter),
                            "Total_Physical": total_phys,
                            "System_Stock": sys_stock,
                            "Discrepancy": discrepancy,
                            "Location": "Pv"
                        }
                        
                        # UPDATED TABLE NAME: Inventory
                        supabase.table("Inventory").insert(audit_entry).execute()
                        st.success(f"Audit Saved! Discrepancy: {discrepancy}")
                        st.session_state.audit_verify = {"name": None, "cat": None, "sys": 0, "sku": "", "auto_exp": 0, "auto_depot": 0}
                        time.sleep(1)
                        st.rerun()

        with cb:
            st.subheader("Audit History Log")
            try:
                # UPDATED TABLE NAME: Inventory
                # We pull the last 50 audits sorted by date
                aud_log_res = supabase.table("Inventory").select("*").order("Date", desc=True).limit(50).execute()
                
                if aud_log_res.data:
                    df_log = pd.DataFrame(aud_log_res.data)
                    
                    # Displaying the log with relevant columns
                    st.dataframe(
                        df_log[['Date', 'Name', 'Total_Physical', 'System_Stock', 'Discrepancy', 'Counter_Name']], 
                        use_container_width=True, 
                        hide_index=True
                    )
                else:
                    st.info("No audit records found in the 'Inventory' table yet.")
            except Exception as e:
                st.error(f"Error fetching history: {e}")

    # --- 4. MANNEQUIN (EXPOSED) TAB ---
    with tabs[3]:
        st.header("👤 Mannequin Display Management")

        # 1. FETCH & DISPLAY HISTORY (AT THE TOP)
        st.subheader("Current Wigs on Display")
        try:
            m_query = supabase.table("Mannequin").select("*").execute()
            m_df = pd.DataFrame(m_query.data) if m_query.data else pd.DataFrame()
            
            if not m_df.empty:
                # Sort by Last_Updated string so newest entries appear first
                m_df = m_df.sort_values(by="Last_Updated", ascending=False)

                st.write(f"**Total Items on Display:** {int(m_df['Quantity'].sum())}")

                # Table Header
                h1, h2, h3, h4, h5 = st.columns([1, 2, 1, 2, 1])
                h1.write("**SKU**")
                h2.write("**Name**")
                h3.write("**Qty**")
                h4.write("**Last Updated**")
                h5.write("**Action**")
                st.divider()

                # Row display with Delete functionality based on SKU + Location
                for index, row in m_df.iterrows():
                    r1, r2, r3, r4, r5 = st.columns([1, 2, 1, 2, 1])
                    r1.write(row['SKU'])
                    r2.write(row['Full Name'])
                    r3.write(str(row['Quantity']))
                    r4.write(row['Last_Updated'])
                    
                    # DELETE BUTTON: Uses SKU and Location to find the row
                    if r5.button("🗑️ Delete", key=f"del_man_{row['SKU']}_{row['Location']}"):
                        supabase.table("Mannequin").delete().eq("SKU", row['SKU']).eq("Location", row['Location']).execute()
                        st.success(f"Removed {row['Full Name']} from display.")
                        time.sleep(0.5)
                        st.rerun()
            else:
                st.info("No wigs currently on display.")
        except Exception as e:
            st.error(f"Error loading Mannequin history: {e}")

        st.divider()

        # 2. LOG IN OPTIONS (AT THE BOTTOM)
        st.subheader("Add/Update Display")
        
        # Tokenized Search (Name or SKU)
        m_search = st.text_input("🔍 Search Item to Display", placeholder="Type Name or SKU...").lower()
        
        if m_search:
            tokens = m_search.split()
            match = master_inventory.copy()
            for t in tokens:
                match = search_inventory(master_inventory, m_search)
            
            if not match.empty:
                m_item = match.iloc[0]
                st.success(f"Selected: **{m_item['Full Name']}** ({m_item['SKU']})")
                
                with st.form("man_form", clear_on_submit=True):
                    # Constraints: Max 2, Current Date only
                    m_qty = st.number_input("Quantity", min_value=1, max_value=2, step=1)
                    m_loc = st.selectbox("Location", ["Pv", "Canape-Vert"], index=0 if m_item['Location'] == "Pv" else 1)
                    
                    if st.form_submit_button("🚀 Set on Mannequin"):
                        man_entry = {
                            "SKU": str(m_item['SKU']),
                            "Full Name": str(m_item['Full Name']),
                            "Quantity": int(m_qty),
                            "Location": str(m_loc),
                            "Last_Updated": datetime.now().strftime("%Y-%m-%d %H:%M")
                        }
                        
                        # Upsert logic: Delete existing for that SKU+Location then insert fresh
                        supabase.table("Mannequin").delete().eq("SKU", m_item['SKU']).eq("Location", m_loc).execute()
                        supabase.table("Mannequin").insert(man_entry).execute()
                        
                        st.success(f"Updated display for {m_item['Full Name']}!")
                        time.sleep(1)
                        st.rerun()
            else:
                st.error("No item found in Master Inventory.")

    # --- 5. DEPOT (BIG DEPOT) TAB ---
    with tabs[4]:
        st.header("📦 Depot Management ")

        # 1. FETCH DEPOT DATA
        try:
            d_query = supabase.table("Depot").select("*").order("Date", desc=True).execute()
            d_df = pd.DataFrame(d_query.data) if d_query.data else pd.DataFrame()
        except Exception:
            d_df = pd.DataFrame()

        # 2. DISPLAY LOG (AT THE TOP)
        # --- DEPOT TAB FULL HISTORY DISPLAY ---
        st.subheader("Depot Activity History")
        
        if not d_df.empty:
            # Show all entries with delete option
            h1, h2, h3, h4, h5, h6 = st.columns([1, 2, 1, 1, 1, 1])
            h1.write("**Date**")
            h2.write("**Wig Name**")
            h3.write("**Type**")
            h4.write("**Qty**")
            h5.write("**User**")
            h6.write("**Action**")
            st.divider()
        
            for index, row in d_df.iterrows():   # <-- show ALL rows, not just head(10)
                r1, r2, r3, r4, r5, r6 = st.columns([1, 2, 1, 1, 1, 1])
                r1.write(row['Date'])
                r2.write(row['Wig Name'])
                type_color = "🟢" if row['Type'] == "Addition" else "🔴"
                r3.write(f"{type_color} {row['Type']}")
                r4.write(str(row['Quantity']))
                r5.write(row['User'])
        
                # Delete button for each row
                if r6.button("🗑️ Delete", key=f"del_dep_{row['id']}"):
                    supabase.table("Depot").delete().eq("id", row['id']).execute()
                    st.success(f"Deleted entry for {row['Wig Name']} on {row['Date']}")
                    time.sleep(0.5)
                    st.rerun()
        else:
            st.info("No activity recorded in the Depot yet.")
    
        # 3. LOG IN OPTIONS (AT THE BOTTOM)
        st.subheader("Log Depot Movement")
        col_d1, col_d2 = st.columns([2, 1])

        with col_d1:
            # --- DEPOT TAB SEARCH BLOCK (Rewritten with multiple options) ---
            d_search = st.text_input("🔍 Search Item for Depot", placeholder="Search by SKU or Name...", key="dep_search").lower()
            
            if d_search:
                tokens = d_search.split()
                match = master_inventory.copy()
                for t in tokens:
                    match = search_inventory(master_inventory, d_search)
            
                if not match.empty:
                    # Let user choose from multiple matches
                    options = match[['SKU', 'Full Name']].apply(lambda x: f"{x['SKU']} - {x['Full Name']}", axis=1).tolist()
                    selected_option = st.selectbox("Select Item", options)
            
                    # Extract SKU and Name from selection
                    selected_sku = selected_option.split(" - ")[0]
                    d_item = match[match['SKU'] == selected_sku].iloc[0]
            
                    st.success(f"Selected: **{d_item['Full Name']}** ({d_item['SKU']})")
            
                    # Calculate Current Net Stock in Depot for this SKU
                    if not d_df.empty:
                        sku_df = d_df[d_df['SKU'] == d_item['SKU']]
                        adds = sku_df[sku_df['Type'] == "Addition"]['Quantity'].sum()
                        subs = sku_df[sku_df['Type'] == "Withdrawal"]['Quantity'].sum()
                        net_depot = adds - subs
                        st.metric("Current Net in Depot", f"{int(net_depot)} units")
            
                    with st.form("depot_form", clear_on_submit=True):
                        d_type = st.radio("Movement Type", ["Addition", "Withdrawal"], horizontal=True)
                        d_qty = st.number_input("Quantity", min_value=1, step=1)
                        d_date = st.date_input("Date", value=date.today())
            
                        if st.form_submit_button("Confirm Depot Entry"):
                            dep_entry = {
                                "Date": str(d_date),
                                "SKU": str(d_item['SKU']),
                                "Wig Name": str(d_item['Full Name']),
                                "Type": d_type,
                                "Quantity": int(d_qty),
                                "User": str(username)
                            }
            
                            supabase.table("Depot").insert(dep_entry).execute()
                            st.success(f"Recorded {d_type} for {d_item['Full Name']}")
                            time.sleep(1)
                            st.rerun()
                else:
                    st.error("Item not found.")

    # --- 6. COMPARE TAB ---
    with tabs[5]:
        st.header("🔄 Stock Comparison ")

        if not master_inventory.empty:
            # --- PART A: SIDE-BY-SIDE COMPARISON ---
            st.subheader("Location Comparison (CV vs PV)")
            
            # Split the master inventory into two dataframes
            df_cv = master_inventory[master_inventory['Location'] == "Canape-Vert"][['SKU', 'Full Name', 'Stock', 'Category']]
            df_pv = master_inventory[master_inventory['Location'] == "Pv"][['SKU', 'Full Name', 'Stock']]
            
            # Merge on SKU to show them side-by-side. 
            # How='outer' ensures that if a SKU is in CV but not PV (or vice versa), it still shows.
            comparison_df = pd.merge(
                df_cv, 
                df_pv, 
                on="SKU", 
                how="outer", 
                suffixes=('_CV', '_PV')
            )
            
            # Clean up the merged data
            comparison_df['Full Name_CV'] = comparison_df['Full Name_CV'].fillna(comparison_df['Full Name_PV'])
            comparison_df['Stock_CV'] = comparison_df['Stock_CV'].fillna(0).astype(int)
            comparison_df['Stock_PV'] = comparison_df['Stock_PV'].fillna(0).astype(int)
            
            # Formatting for display
            display_comp = comparison_df[['SKU', 'Full Name_CV', 'Stock_CV', 'Stock_PV']].rename(columns={
                'Full Name_CV': 'Wig Name',
                'Stock_CV': 'Qty (Canape-Vert)',
                'Stock_PV': 'Qty (PV)'
            })

            # Search within comparison
            comp_search = st.text_input("🔍 Search Comparison", placeholder="Filter by Name or SKU...").lower()
            if comp_search:
                display_comp = search_inventory(display_comp.rename(columns={'Wig Name':'Full Name'}), comp_search)

            st.dataframe(display_comp, use_container_width=True, hide_index=True)

            st.divider()

            # --- PART B: OVER 50 STOCK CHECK ---
            st.subheader("🔥 High Stock Alert (Over 50 Units)")
            col_high1, col_high2 = st.columns(2)

            with col_high1:
                st.markdown("##### 📍 Canape-Vert (> 50)")
                high_cv = df_cv[df_cv['Stock'] > 50].sort_values(by="Stock", ascending=False)
                if not high_cv.empty:
                    st.dataframe(high_cv[['SKU', 'Full Name', 'Stock']], use_container_width=True, hide_index=True)
                else:
                    st.write("No items over 50 in Canape-Vert.")

            with col_high2:
                st.markdown("##### 📍 PV (> 50)")
                high_pv = df_pv[df_pv['Stock'] > 50].sort_values(by="Stock", ascending=False)
                if not high_pv.empty:
                    st.dataframe(high_pv[['SKU', 'Full Name', 'Stock']], use_container_width=True, hide_index=True)
                else:
                    st.write("No items over 50 in PV.")
        else:
            st.info("Please upload inventory files in the sidebar to perform comparison.")

    # --- 7. SALES (FAST/SLOW MOVERS) ---
    with tabs[6]:
        st.header("💰 Sales Analysis ")
        
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
        st.header("⚙️ Admin Control ")
        
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

elif authentication_status is False:
    st.error('Username/password is incorrect')
elif authentication_status is None:
    st.warning('Please login')






