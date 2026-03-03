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
        st.header("🚢 Arrival")
        st.write("Placeholder for receiving new shipments.")

    # --- 3. INVENTORY (AUDIT) TAB ---
    with tabs[2]:
        st.header("📋 Inventory Audit")
        st.write("Placeholder for physical stock counting.")

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




