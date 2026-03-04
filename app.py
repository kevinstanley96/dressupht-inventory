import streamlit as st
import pandas as pd
from supabase import create_client
import streamlit_authenticator as stauth
from datetime import datetime, date
import time

# --- PAGE CONFIG ---
st.set_page_config(page_title="Dressup Haiti ERP", layout="wide")

# --- SUPABASE CONNECTION ---
@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
supabase = init_connection()

# --- HELPERS ---
def get_user_role(username):
    try:
        res = supabase.table("Role").select("Roles, Location").eq("User Name", username.lower()).execute()
        if res.data:
            return res.data[0]['Roles'], res.data[0]['Location']
        return "Staff", "Unknown"
    except Exception:
        return "Staff", "Unknown"

def search_inventory(df, query):
    tokens = query.lower().split()
    result = df.copy()
    for t in tokens:
        result = result[
            result['Full Name'].str.lower().str.contains(t) |
            result['SKU'].str.lower().str.startswith(t)
        ]
    return result

@st.cache_data(ttl=60)
def get_table(name):
    q = supabase.table(name).select("*").order("Date", desc=True).execute()
    return pd.DataFrame(q.data) if q.data else pd.DataFrame()

# --- AUTH ---
usernames_list = ["djessie","kevin","casimir","melchisedek","david","darius","eliada","sebastien","guirlene","carmela","angelina","tamara","dorotheline","sarah","valerie","saouda","marie france","carelle","annaelle","gerdine","martilda"]
credentials = {"usernames": {u: {"name": u, "password": "temppassword123"} for u in usernames_list}}
credentials['usernames']['kevin']['password'] = "The$100$Raven"

authenticator = stauth.Authenticate(credentials, "inventory_cookie", "abcdef123456_key", 30)
name, authentication_status, username = authenticator.login(location='main')

# --- APP ---
if authentication_status:
    role, loc = get_user_role(username)

    with st.sidebar:
        st.markdown(f"<h1 style='text-align: center;'>{username.upper()}</h1>", unsafe_allow_html=True)
        st.write(f"**🛡️ Access:** {role}")
        st.write(f"**📍 Location:** {loc}")
        st.divider()
        authenticator.logout('Logout', 'sidebar')

    # Tabs
    tab_list = ["Library","Arrival","Inventory","Mannequin","Depot","Compare","Sales"]
    tabs = st.tabs(tab_list)

    # --- LIBRARY ---
    with tabs[0]:
        master_inventory = get_table("Master_Inventory")
        if not master_inventory.empty:
            search_query = st.text_input("🔍 Search", placeholder="Search by SKU or Name...").lower()
            disp_df = search_inventory(master_inventory, search_query) if search_query else master_inventory
            st.dataframe(disp_df[['Location','Category','Full Name','SKU','Stock','Price']], use_container_width=True, hide_index=True)
            st.caption(f"Showing {len(disp_df)} items")
        else:
            st.info("No data in Master_Inventory.")

    # --- ARRIVAL ---
    with tabs[1]:
        st.header("🚢 Arrival Management")
        if role not in ["Admin","Manager"]:
            st.warning("🔒 Access Denied.")
        else:
            arr_df = get_table("Arrival")
            st.dataframe(arr_df[['Date','Wig Name','Quantity','Location','User']], use_container_width=True, hide_index=True)

            sku = st.text_input("Enter SKU").strip()
            if sku:
                match = master_inventory[master_inventory['SKU'].str.lower().str.startswith(sku.lower())]
                if not match.empty:
                    item = match.iloc[0]
                    with st.form("arrival_form", clear_on_submit=True):
                        arr_date = st.date_input("Arrival Date", value=date.today())
                        arr_qty = st.number_input("Quantity", min_value=1, step=1)
                        arr_loc = st.selectbox("Location", ["Pv","Canape-Vert"])
                        if st.form_submit_button("Confirm"):
                            supabase.table("Arrival").insert({
                                "Date": str(arr_date),
                                "SKU": item['SKU'],
                                "Wig Name": item['Full Name'],
                                "Category": item['Category'],
                                "Quantity": arr_qty,
                                "User": username,
                                "Location": arr_loc
                            }).execute()
                            st.success("Arrival logged.")
                            st.rerun()

    # --- INVENTORY ---
    with tabs[2]:
        st.header("📋 Inventory Audit")
        inv_df = get_table("Inventory")
        st.dataframe(inv_df[['Date','Name','Total_Physical','System_Stock','Discrepancy','Counter_Name']], use_container_width=True, hide_index=True)

    # --- MANNEQUIN ---
    with tabs[3]:
        st.header("👤 Mannequin Display")
        man_df = get_table("Mannequin")
        st.dataframe(man_df[['SKU','Full Name','Quantity','Location','Last_Updated']], use_container_width=True, hide_index=True)

        m_search = st.text_input("Search Item").lower()
        if m_search:
            match = search_inventory(master_inventory, m_search)
            if not match.empty:
                item = match.iloc[0]
                with st.form("man_form", clear_on_submit=True):
                    qty = st.number_input("Quantity", min_value=1, max_value=2)
                    loc_sel = st.selectbox("Location", ["Pv","Canape-Vert"])
                    if st.form_submit_button("Set Display"):
                        supabase.table("Mannequin").delete().eq("SKU", item['SKU']).eq("Location", loc_sel).execute()
                        supabase.table("Mannequin").insert({
                            "SKU": item['SKU'],
                            "Full Name": item['Full Name'],
                            "Quantity": qty,
                            "Location": loc_sel,
                            "Last_Updated": datetime.now().strftime("%Y-%m-%d %H:%M")
                        }).execute()
                        st.success("Display updated.")
                        st.rerun()

    # --- DEPOT ---
    with tabs[4]:
        st.header("📦 Depot Management")
        d_df = get_table("Depot")
        st.dataframe(d_df[['id','Date','Wig Name','Type','Quantity','User']], use_container_width=True, hide_index=True)

        delete_id = st.selectbox("Select entry to delete", d_df['id'].tolist()) if not d_df.empty else None
        if delete_id and st.button("Delete Selected"):
            supabase.table("Depot").delete().eq("id", delete_id).execute()
            st.success("Entry deleted.")
            st.rerun()

        d_search = st.text_input("Search Item for Depot").lower()
        if d_search:
            match = search_inventory(master_inventory, d_search)
            if not match.empty:
                item = match.iloc[0]
                with st.form("depot_form", clear_on_submit=True):
                    d_type = st.radio("Movement Type", ["Addition","Withdrawal"], horizontal=True)
                    d_qty = st.number_input("Quantity", min_value=1, step=1)
                    d_date = st.date_input("Date", value=date.today())
                    if st.form_submit_button("Confirm Depot Entry"):
                        supabase.table("Depot").insert({
                            "Date": str(d_date),
                            "SKU": item['SKU'],
                            "Wig Name": item['Full Name'],
                            "Type": d_type,
                            "Quantity": d_qty,
                            "User": username
                        }).execute()
                        st.success("Depot entry recorded.")
                        st.rerun()

        # --- COMPARE ---
    with tabs[5]:
        st.header("🔄 Stock Comparison")
        if not master_inventory.empty:
            df_cv = master_inventory[master_inventory['Location']=="Canape-Vert"][['SKU','Full Name','Stock']]
            df_pv = master_inventory[master_inventory['Location']=="Pv"][['SKU','Full Name','Stock']]

            comp = pd.merge(df_cv, df_pv, on="SKU", how="outer", suffixes=('_CV','_PV'))
            comp['Full Name_CV'] = comp['Full Name_CV'].fillna(comp['Full Name_PV'])
            comp['Stock_CV'] = comp['Stock_CV'].fillna(0).astype(int)
            comp['Stock_PV'] = comp['Stock_PV'].fillna(0).astype(int)

            display_comp = comp[['SKU','Full Name_CV','Stock_CV','Stock_PV']].rename(columns={
                'Full Name_CV':'Wig Name',
                'Stock_CV':'Qty (Canape-Vert)',
                'Stock_PV':'Qty (PV)'
            })

            comp_search = st.text_input("Search Comparison").lower()
            if comp_search:
                display_comp = display_comp[
                    display_comp['Wig Name'].str.lower().str.contains(comp_search) |
                    display_comp['SKU'].str.lower().str.contains(comp_search)
                ]

            st.dataframe(display_comp, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("🔥 High Stock Alert (> 50 Units)")
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("##### Canape-Vert")
                high_cv = df_cv[df_cv['Stock'] > 50].sort_values(by="Stock", ascending=False)
                st.dataframe(high_cv[['SKU','Full Name','Stock']], use_container_width=True, hide_index=True)

            with col2:
                st.markdown("##### PV")
                high_pv = df_pv[df_pv['Stock'] > 50].sort_values(by="Stock", ascending=False)
                st.dataframe(high_pv[['SKU','Full Name','Stock']], use_container_width=True, hide_index=True)
        else:
            st.info("Upload inventory files to compare.")

    # --- SALES ---
    with tabs[6]:
        st.header("💰 Sales Analysis")
        old_file = st.file_uploader("Upload Old Square Export (Excel)", type=['xlsx'])
        if old_file and not master_inventory.empty:
            try:
                df_old = pd.read_excel(old_file, skiprows=1)
                df_old.columns = [str(c).strip() for c in df_old.columns]

                token_col = 'Token' if 'Token' in df_old.columns else None
                old_qty_col = "Current Quantity Dressupht Pv"

                if not token_col:
                    st.error("Token column missing in uploaded file.")
                else:
                    # Merge old vs new inventory by Token
                    df_old = df_old.rename(columns={'Item Name':'Full Name','SKU':'SKU','Categories':'Category','Price':'Price'})
                    merged = pd.merge(master_inventory, df_old, on="Token", suffixes=('_New','_Old'))

                    merged['Diff'] = merged['Stock_New'] - merged[old_qty_col]
                    st.dataframe(merged[['SKU','Full Name_New','Category_New','Stock_New',old_qty_col,'Diff']], use_container_width=True, hide_index=True)

                    st.subheader("Fast Movers (Stock Decreased)")
                    fast = merged[merged['Diff'] < 0].sort_values(by='Diff')
                    st.dataframe(fast[['SKU','Full Name_New','Diff']], use_container_width=True, hide_index=True)

                    st.subheader("Slow Movers (Stock Increased)")
                    slow = merged[merged['Diff'] > 0].sort_values(by='Diff', ascending=False)
                    st.dataframe(slow[['SKU','Full Name_New','Diff']], use_container_width=True, hide_index=True)

            except Exception as e:
                st.error(f"Error processing file: {e}")
                
        # --- ADMIN ---
    with tabs[7]:
        st.header("⚙️ Admin Panel")
        if role not in ["Admin","Manager"]:
            st.warning("🔒 Access Denied.")
        else:
            st.subheader("System Controls")
            st.write("Here you can manage advanced settings.")

            # Example: Clear Master Inventory
            if st.button("🗑️ Clear Master Inventory"):
                supabase.table("Master_Inventory").delete().neq("SKU","VOID").execute()
                st.success("Master Inventory cleared.")
                st.rerun()

            # Example: View Roles
            roles_df = get_table("Role")
            if not roles_df.empty:
                st.dataframe(roles_df[['User Name','Roles','Location']], use_container_width=True, hide_index=True)
                
        # --- PASSWORD ---
    with tabs[8]:
        st.header("🔑 Password Management")
        try:
            if authenticator.reset_password(username, location='main'):
                st.success("Password reset successful!")
        except Exception as e:
            st.error(f"Error resetting password: {e}")

elif authentication_status is False:
    st.error('Username/password is incorrect')
elif authentication_status is None:
    st.warning('Please login')
