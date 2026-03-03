import streamlit as st
import pandas as pd
from supabase import create_client, Client
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import plotly.express as px
import io

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v5.3.0", layout="wide")

# --- SUPABASE SETUP ---
@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

# --- AUTHENTICATION SETUP ---
usernames_list = [u.lower() for u in ["djessie", "kevin", "casimir", "melchisedek", "david", "darius", "eliada", "sebastien", "guirlene", "carmela", "angelina", "tamara", "dorotheline", "sarah", "valerie", "saouda", "marie france", "carelle", "annaelle", "gerdine", "martilda"]]
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
    # Session States
    for key in ['audit_verify', 'intake_verify', 'depot_verify']:
        if key not in st.session_state:
            st.session_state[key] = {"name": None, "cat": None, "sys": 0, "sku": "", "auto_exp": 0, "auto_depot": 0}

    roles_df = get_sb_data("Role")
    master_inventory = get_sb_data("Master_Inventory")

    if username == "kevin":
        user_role, user_location = "Admin", "Both"
    else:
        user_row = roles_df[roles_df['User Name'] == username.lower()] if not roles_df.empty else pd.DataFrame()
        user_role = user_row['Roles'].iloc[0] if not user_row.empty else "Staff"
        user_location = user_row['Assigned Location'].iloc[0] if not user_row.empty else "Both"

    st.sidebar.markdown(f"### 👤 {username.title()}\n**📍 Location:** {user_location}\n**🛡️ Role:** {user_role}")
    authenticator.logout('Logout', 'sidebar')

    # Tabs definition
    all_tabs = ["Library", "Intake", "Audit", "Sales", "Comparison", "Fast/Slow", "Big Depot", "Exposed", "Password"]
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
            if user_role in ["Admin", "Manager"]:
                with st.expander("⬆️ Database Update (Sync Master Inventory)"):
                    c_up1, c_up2 = st.columns(2)
                    file_cv = c_up1.file_uploader("Upload Canape-Vert Excel", type=['xlsx'], key="sync_cv")
                    file_pv = c_up2.file_uploader("Upload PV Excel", type=['xlsx'], key="sync_pv")
                    if st.button("🚀 Overwrite Database"):
                        if file_cv and file_pv:
                            df_cv, df_pv = clean_location_data(file_cv, "Canape-Vert"), clean_location_data(file_pv, "Pv")
                            final_master = pd.concat([df_cv, df_pv], ignore_index=True)
                            supabase.table("Master_Inventory").delete().neq("SKU", "VOID").execute()
                            supabase.table("Master_Inventory").insert(final_master.to_dict('records')).execute()
                            st.success("Synced successfully!"); st.cache_data.clear(); st.rerun()

            c1, c2 = st.columns([2, 1])
            search = c1.text_input("🔍 Search Name/SKU")
            sort_choice = c2.selectbox("Sort By", ["Name", "Category", "Date Entered"])
            
            disp_df = master_inventory.copy()
            if not disp_df.empty:
                disp_df['Category'] = disp_df['Category'].fillna("Uncategorized").astype(str)
                sort_map = {"Name": "Full Name", "Category": ["Category", "Full Name"], "Date Entered": "created_at" if "created_at" in disp_df.columns else "Full Name"}
                disp_df = disp_df.sort_values(by=sort_map[sort_choice])
                if search:
                    disp_df = disp_df[disp_df.apply(lambda r: search.lower() in str(r['Full Name']).lower() or search.lower() in str(r['SKU']).lower(), axis=1)]
                st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB: INTAKE ---
    if "Intake" in tab_list:
        with tabs[tab_list.index("Intake")]:
            col1, col2 = st.columns(2)
            with col1:
                in_sku = st.text_input("Scan SKU", key="int_sku_input").strip()
                if in_sku and in_sku != st.session_state.intake_verify["sku"]:
                    match = master_inventory[(master_inventory['SKU'].str.lower() == in_sku.lower()) & (master_inventory['Location'] == "Pv")]
                    st.session_state.intake_verify = {"name": match['Full Name'].iloc[0] if not match.empty else None, "cat": match['Category'].iloc[0] if not match.empty else None, "sku": in_sku}
                
                if st.session_state.intake_verify["name"]:
                    st.success(f"Item: {st.session_state.intake_verify['name']}")
                    with st.form("int_f", clear_on_submit=True):
                        qty, dt = st.number_input("Qty", 1), st.date_input("Date", value=date.today())
                        if st.form_submit_button("Save"):
                            payload = {"Date": str(dt), "SKU": in_sku, "Wig Name": st.session_state.intake_verify["name"], "Category": str(st.session_state.intake_verify["cat"]), "Quantity": qty, "User": username, "Location": "Pv"}
                            supabase.table("Shipments").insert(payload).execute()
                            st.cache_data.clear(); st.rerun()
            with col2:
                h = get_sb_data("Shipments")
                if not h.empty: st.dataframe(h[['Date', 'SKU', 'Wig Name', 'Quantity']].sort_values("Date", ascending=False), hide_index=True)

    # --- TAB: SALES ---
    if "Sales" in tab_list:
        with tabs[tab_list.index("Sales")]:
            cs1, cs2 = st.columns(2)
            old_f = cs1.file_uploader("Upload PREVIOUS Square File", type=['xlsx'], key="s_old")
            new_f = cs2.file_uploader("Upload CURRENT Square File", type=['xlsx'], key="s_new")
            if old_f and new_f:
                df_o, df_n = clean_location_data(old_f, "Pv"), clean_location_data(new_f, "Pv")
                comp = pd.merge(df_o[['SKU', 'Full Name', 'Category', 'Stock', 'Price']], df_n[['SKU', 'Stock']], on='SKU', suffixes=('_old', '_new'))
                comp['Sold'] = comp['Stock_old'] - comp['Stock_new']
                sales_df = comp[comp['Sold'] > 0].copy()
                if not sales_df.empty:
                    st.metric("Estimated Revenue", f"${(sales_df['Sold'] * sales_df['Price']).sum():,.2f}")
                    st.dataframe(sales_df[['Category', 'Full Name', 'Sold', 'Price']], use_container_width=True, hide_index=True)
                    st.plotly_chart(px.pie(sales_df, values='Sold', names='Category', title="Sales by Category"))

    # --- TAB: FAST/SLOW ---
    if "Fast/Slow" in tab_list:
        with tabs[tab_list.index("Fast/Slow")]:
            cf1, cf2 = st.columns(2)
            f_old = cf1.file_uploader("Fast/Slow: Start Period", type=['xlsx'], key="fs_old")
            f_new = cf2.file_uploader("Fast/Slow: End Period", type=['xlsx'], key="fs_new")
            if f_old and f_new:
                d_o, d_n = clean_location_data(f_old, "Pv"), clean_location_data(f_new, "Pv")
                fs_comp = pd.merge(d_o, d_n[['SKU', 'Stock']], on='SKU', suffixes=('_start', '_end'))
                fs_comp['Velocity'] = fs_comp['Stock_start'] - fs_comp['Stock_end']
                
                col_a, col_b = st.columns(2)
                col_a.subheader("🔥 Top Sellers")
                col_a.dataframe(fs_comp.sort_values("Velocity", ascending=False).head(15)[['Full Name', 'Velocity']], hide_index=True)
                col_b.subheader("🐌 Slowest (High Stock, Low Sale)")
                col_b.dataframe(fs_comp[fs_comp['Velocity'] <= 0].sort_values("Stock_start", ascending=False).head(15)[['Full Name', 'Stock_start']], hide_index=True)

    # --- TAB: BIG DEPOT ---
    if "Big Depot" in tab_list:
        with tabs[tab_list.index("Big Depot")]:
            depot_data = get_sb_data("Big_Depot")
            cd1, cd2 = st.columns([1, 2])
            with cd1:
                d_sku = st.text_input("Scan Depot SKU", key="depot_scan").strip()
                if d_sku and d_sku != st.session_state.depot_verify["sku"]:
                    match = master_inventory[master_inventory['SKU'].str.lower() == d_sku.lower()]
                    st.session_state.depot_verify = {"name": match['Full Name'].iloc[0] if not match.empty else None, "sku": d_sku}
                
                if st.session_state.depot_verify["name"]:
                    st.success(f"Item: {st.session_state.depot_verify['name']}")
                    with st.form("depot_form"):
                        dtype = st.selectbox("Action", ["Addition", "Subtraction"])
                        dqty = st.number_input("Quantity", 1)
                        if st.form_submit_button("Log to Big Depot"):
                            payload = {"Date": str(date.today()), "SKU": d_sku, "Wig Name": st.session_state.depot_verify["name"], "Type": dtype, "Quantity": dqty, "User": username}
                            supabase.table("Big_Depot").insert(payload).execute()
                            st.cache_data.clear(); st.rerun()
            with cd2:
                if not depot_data.empty: st.dataframe(depot_data.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)

    # --- TAB: AUDIT ---
    if "Audit" in tab_list:
        with tabs[tab_list.index("Audit")]:
            exp_data, dep_data = get_sb_data("Exposed_Wigs"), get_sb_data("Big_Depot")
            ca, cb = st.columns([1, 2])
            with ca:
                counter = st.selectbox("Counter", usernames_list)
                a_sku = st.text_input("Audit SKU", key="aud_sku").strip()
                if a_sku and a_sku != st.session_state.audit_verify["sku"]:
                    m = master_inventory[(master_inventory['SKU'].str.lower() == a_sku.lower()) & (master_inventory['Location'] == "Pv")]
                    if not m.empty:
                        e_qty = int(exp_data[(exp_data['SKU'].str.lower() == a_sku.lower())]['Quantity'].sum()) if not exp_data.empty else 0
                        d_qty = 0
                        if not dep_data.empty:
                            dm = dep_data[dep_data['SKU'].str.lower() == a_sku.lower()]
                            d_qty = int(dm[dm['Type'] == "Addition"]['Quantity'].sum() - dm[dm['Type'] == "Subtraction"]['Quantity'].sum())
                        st.session_state.audit_verify = {"name": m['Full Name'].iloc[0], "cat": m['Category'].iloc[0], "sys": int(m['Stock'].iloc[0]), "sku": a_sku, "auto_exp": e_qty, "auto_depot": d_qty}
                
                if st.session_state.audit_verify["name"]:
                    with st.form("aud_f"):
                        m_shelf = st.number_input("Shelf Count", 0)
                        if st.form_submit_button("Save Audit"):
                            tp = m_shelf + st.session_state.audit_verify["auto_exp"] + st.session_state.audit_verify["auto_depot"]
                            diff = tp - st.session_state.audit_verify["sys"]
                            supabase.table("Inventory_Audit").insert({"Date": str(date.today()), "SKU": a_sku, "Name": st.session_state.audit_verify["name"], "Category": str(st.session_state.audit_verify["cat"]), "Counter_Name": counter, "Total_Physical": tp, "System_Stock": st.session_state.audit_verify["sys"], "Discrepancy": diff}).execute()
                            st.cache_data.clear(); st.rerun()
            with cb:
                aud_h = get_sb_data("Inventory_Audit")
                if not aud_h.empty: st.dataframe(aud_h.sort_values("Date", ascending=False), hide_index=True)

    # --- TAB: COMPARISON ---
    if "Comparison" in tab_list:
        with tabs[tab_list.index("Comparison")]:
            c_comp1, c_comp2 = st.columns(2)
            f_cv, f_pv = c_comp1.file_uploader("Canape-Vert Comparison", type=['xlsx']), c_comp2.file_uploader("PV Comparison", type=['xlsx'])
            if f_cv and f_pv:
                d_cv, d_pv = clean_location_data(f_cv, "Canape-Vert"), clean_location_data(f_pv, "Pv")
                m_comp = pd.merge(d_cv[['Full Name', 'Category', 'Stock']], d_pv[['Full Name', 'Stock']], on='Full Name', how='outer', suffixes=('_CV', '_PV')).fillna(0)
                sel_cat = st.selectbox("Filter", ["All"] + sorted(m_comp['Category'].astype(str).unique().tolist()))
                if sel_cat != "All": m_comp = m_comp[m_comp['Category'] == sel_cat]
                st.dataframe(m_comp, hide_index=True)

    # --- TAB: EXPOSED ---
    if "Exposed" in tab_list:
        with tabs[tab_list.index("Exposed")]:
            exp_data = get_sb_data("Exposed_Wigs")
            st.dataframe(exp_data[['SKU', 'Full Name', 'Quantity', 'Location']] if not exp_data.empty else pd.DataFrame(), use_container_width=True, hide_index=True)
            with st.form("exp_f"):
                e_sku, e_qty = st.text_input("SKU").strip(), st.number_input("Qty", 0)
                e_loc = st.selectbox("Loc", ["Pv", "Canape-Vert"])
                if st.form_submit_button("Update"):
                    m = master_inventory[master_inventory['SKU'].str.lower() == e_sku.lower()]
                    payload = {"SKU": e_sku, "Full Name": m['Full Name'].iloc[0] if not m.empty else "Unknown", "Quantity": e_qty, "Location": e_loc, "Last_Updated": datetime.now().strftime("%Y-%m-%d %H:%M")}
                    supabase.table("Exposed_Wigs").insert(payload).execute()
                    st.cache_data.clear(); st.rerun()

    # --- TAB: PASSWORD ---
    if "Password" in tab_list:
        with tabs[tab_list.index("Password")]:
            authenticator.reset_password(username=username)

elif authentication_status is False: st.error('Incorrect Password')
elif authentication_status is None: st.warning('Please Login')
