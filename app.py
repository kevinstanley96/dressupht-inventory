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
    tab_list = ["Library", "Arrival", "Inventory", "Mannequin", "Depot", "Compare", "Sales", "Admin", "Password"]
    tabs = st.tabs(tab_list)

    # --- 1. LIBRARY TAB ---
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
            # Sort by Name by default as per requirements
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
            if 'arrival_verify' not in st.session_state: st.session_state.arrival_verify = {"name": None, "cat": None, "sku": ""}
            col1, col2 = st.columns([1, 2])
            with col1:
                in_sku = st.text_input("Scan or Enter SKU", key="arr_sku_input").strip()
                if in_sku and in_sku != st.session_state.arrival_verify["sku"]:
                    match = master_inventory[master_inventory['SKU'].str.lower() == in_sku.lower()]
                    if not match.empty:
                        st.session_state.arrival_verify = {"name": match['Full Name'].iloc[0], "cat": match['Category'].iloc[0], "sku": in_sku}
                    else:
                        st.session_state.arrival_verify = {"name": None, "cat": None, "sku": in_sku}
                        st.error("SKU not found.")
                
                if st.session_state.arrival_verify["name"]:
                    with st.form("arrival_form", clear_on_submit=True):
                        arr_qty = st.number_input("Quantity Received", min_value=1, step=1)
                        arr_loc = st.selectbox("Receiving Location", ["Pv", "Canape-Vert"])
                        if st.form_submit_button("✅ Confirm Arrival"):
                            arrival_data = {"Date": str(date.today()), "SKU": st.session_state.arrival_verify["sku"], "Wig Name": st.session_state.arrival_verify["name"], "Category": st.session_state.arrival_verify["cat"], "Quantity": arr_qty, "User": username, "Location": arr_loc}
                            supabase.table("Arrival").insert(arrival_data).execute()
                            st.success("Logged!")
                            st.session_state.arrival_verify = {"name": None, "cat": None, "sku": ""}
                            time.sleep(1); st.rerun()

            with col2:
                st.subheader("Recent Arrivals")
                try:
                    arr_log = supabase.table("Arrival").select("*").order("Date", desc=True).limit(15).execute()
                    if arr_log.data: st.dataframe(pd.DataFrame(arr_log.data)[['Date', 'Wig Name', 'Quantity', 'Location', 'User']], use_container_width=True, hide_index=True)
                except: st.error("Log error.")

    # --- 3. INVENTORY (AUDIT) TAB ---
    with tabs[2]:
        st.header("📋 Physical Inventory Audit (PV Only)")
        if 'audit_verify' not in st.session_state: st.session_state.audit_verify = {"name": None, "sku": "", "sys": 0}
        ca, cb = st.columns([1, 2])
        with ca:
            search_input = st.text_input("🔍 Search SKU or Name for Audit").lower()
            if search_input:
                match = master_inventory[(master_inventory['Location'] == "Pv") & (master_inventory['Full Name'].str.lower().str.contains(search_input) | master_inventory['SKU'].str.lower().str.contains(search_input))]
                if not match.empty:
                    item = match.iloc[0]
                    st.info(f"**Item:** {item['Full Name']}")
                    with st.form("audit_form"):
                        f_shelf = st.number_input("Shelf Count", min_value=0)
                        if st.form_submit_button("💾 Save Audit"):
                            audit_entry = {"Date": str(date.today()), "SKU": item['SKU'], "Name": item['Full Name'], "Total_Physical": f_shelf, "System_Stock": int(item['Stock']), "Discrepancy": f_shelf - int(item['Stock']), "Counter_Name": username, "Location": "Pv"}
                            supabase.table("Inventory").insert(audit_entry).execute()
                            st.success("Audit Saved!"); time.sleep(1); st.rerun()

        with cb:
            st.subheader("Audit History")
            try:
                aud_log = supabase.table("Inventory").select("*").order("Date", desc=True).limit(20).execute()
                if aud_log.data: st.dataframe(pd.DataFrame(aud_log.data)[['Date', 'Name', 'Total_Physical', 'System_Stock', 'Discrepancy']], use_container_width=True, hide_index=True)
            except: pass

    # --- 4. MANNEQUIN TAB ---
    with tabs[3]:
        st.header("👤 Mannequin Display")
        m_query = supabase.table("Mannequin").select("*").execute()
        m_df = pd.DataFrame(m_query.data) if m_query.data else pd.DataFrame()
        if not m_df.empty:
            st.dataframe(m_df[['SKU', 'Full Name', 'Quantity', 'Last_Updated']], use_container_width=True, hide_index=True)
            if st.button("Clear Selected Row"): st.info("Use Admin tab for bulk cleanup.")
        
        m_search = st.text_input("🔍 Add to Display").lower()
        if m_search:
            match = master_inventory[master_inventory['Full Name'].str.lower().str.contains(m_search)].head(1)
            if not match.empty:
                with st.form("man_form"):
                    m_qty = st.number_input("Qty", 1, 2)
                    if st.form_submit_button("Set on Mannequin"):
                        entry = {"SKU": match.iloc[0]['SKU'], "Full Name": match.iloc[0]['Full Name'], "Quantity": m_qty, "Location": match.iloc[0]['Location'], "Last_Updated": datetime.now().strftime("%Y-%m-%d %H:%M")}
                        supabase.table("Mannequin").delete().eq("SKU", entry['SKU']).execute()
                        supabase.table("Mannequin").insert(entry).execute()
                        st.rerun()

    # --- 5. DEPOT TAB ---
    with tabs[4]:
        st.header("📦 Depot Management")
        d_search = st.text_input("🔍 Search Depot Item").lower()
        if d_search:
            match = master_inventory[master_inventory['Full Name'].str.lower().str.contains(d_search)].head(1)
            if not match.empty:
                with st.form("dep_form"):
                    d_type = st.radio("Type", ["Addition", "Withdrawal"])
                    d_qty = st.number_input("Qty", 1)
                    if st.form_submit_button("Log Movement"):
                        supabase.table("Depot").insert({"Date": str(date.today()), "SKU": match.iloc[0]['SKU'], "Wig Name": match.iloc[0]['Full Name'], "Type": d_type, "Quantity": d_qty, "User": username}).execute()
                        st.success("Logged"); time.sleep(1); st.rerun()

    # --- 6. COMPARE TAB ---
    with tabs[5]:
        st.header("🔄 Stock Comparison")
        if not master_inventory.empty:
            df_cv = master_inventory[master_inventory['Location'] == "Canape-Vert"][['SKU', 'Full Name', 'Stock']]
            df_pv = master_inventory[master_inventory['Location'] == "Pv"][['SKU', 'Stock']]
            comp = pd.merge(df_cv, df_pv, on="SKU", how="outer", suffixes=('_CV', '_PV')).fillna(0)
            st.dataframe(comp, use_container_width=True)

    # --- 7. SALES TAB ---
    with tabs[6]:
        st.header("💰 Sales Analysis (Token-Based)")
        old_file = st.file_uploader("Upload Old Square Export", type=['xlsx'])
        if old_file and not master_inventory.empty:
            df_old = pd.read_excel(old_file, skiprows=1)
            if 'Token' in df_old.columns:
                df_curr = master_inventory[master_inventory['Location'] == "Pv"].copy()
                sales_comp = pd.merge(df_old[['Token', 'Current Quantity Dressupht Pv']], df_curr, on='Token', how='inner')
                sales_comp['Sales'] = sales_comp['Current Quantity Dressupht Pv'] - sales_comp['Stock']
                st.subheader("Top 10 Fast Movers")
                st.dataframe(sales_comp[sales_comp['Sales'] > 0].sort_values('Sales', ascending=False).head(10)[['Full Name', 'Sales']])

    # --- 8. ADMIN TAB ---
    with tabs[7]:
        st.header("⚙️ Admin Control Tower")
        if role != "Admin":
            st.error("🚫 Restricted to System Administrators.")
        else:
            adm_tabs = st.tabs(["👤 Users", "📜 Logs", "🧹 Maintenance"])
            with adm_tabs[0]:
                res = supabase.table("Role").select("*").execute()
                df_u = pd.DataFrame(res.data)
                st.dataframe(df_u[['User Name', 'Roles', 'Location']], use_container_width=True, hide_index=True)
                
                c_u1, c_u2 = st.columns(2)
                with c_u1:
                    with st.form("up_perm"):
                        u_name = st.selectbox("Select User", df_u['User Name'].unique())
                        u_role = st.selectbox("New Role", ["Admin", "Manager", "Staff"])
                        if st.form_submit_button("Update Permissions"):
                            supabase.table("Role").update({"Roles": u_role}).eq("User Name", u_name).execute()
                            st.success("Updated"); st.rerun()
                with c_u2:
                    with st.form("up_loc"):
                        u_name_l = st.selectbox("Select User", df_u['User Name'].unique(), key="l1")
                        u_loc = st.selectbox("New Location", ["Pv", "Canape-Vert", "Both"])
                        if st.form_submit_button("Update Location"):
                            supabase.table("Role").update({"Location": u_loc}).eq("User Name", u_name_l).execute()
                            st.success("Relocated"); st.rerun()
            
            with adm_tabs[1]:
                l_type = st.radio("Log Source", ["Arrival", "Inventory", "Depot", "Mannequin"], horizontal=True)
                log_data = supabase.table(l_type).select("*").execute()
                if log_data.data: st.dataframe(pd.DataFrame(log_data.data), use_container_width=True)

            with adm_tabs[2]:
                st.download_button("📥 Export Master Inventory", master_inventory.to_csv(index=False), "master.csv")

    # --- 9. PASSWORD TAB ---
    with tabs[8]:
        st.header("🔐 Account Security")
        try:
            if authenticator.reset_password(username, 'Reset Password'):
                st.success('Password modified successfully')
        except Exception as e:
            st.error(e)
