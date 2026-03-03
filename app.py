import streamlit as st
import pandas as pd
from supabase import create_client, Client
import streamlit_authenticator as stauth
from datetime import datetime, date
import time
import plotly.express as px
import io

# --- CONFIG ---
st.set_page_config(page_title="Dressupht ERP v5.3.2", layout="wide")

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
    # Initialize session states
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

    st.sidebar.markdown(f"### 👤 {username.title()}\n**📍 Loc:** {user_location}\n**🛡️ Role:** {user_role}")
    authenticator.logout('Logout', 'sidebar')

    tab_list = ["Library", "Intake", "Audit", "Sales", "Comparison", "Fast/Slow", "Big Depot", "Exposed", "Password"]
    if user_role == "Staff": tab_list = ["Library", "Exposed", "Password"]
    
    tabs = st.tabs(tab_list)

    # --- TAB: LIBRARY ---
    if "Library" in tab_list:
        with tabs[tab_list.index("Library")]:
            if user_role in ["Admin", "Manager"]:
                with st.expander("⬆️ Upload & Sync Master Inventory"):
                    c_up1, c_up2 = st.columns(2)
                    f_cv = c_up1.file_uploader("Canape-Vert Master File", type=['xlsx'], key="l_cv")
                    f_pv = c_up2.file_uploader("PV Master File", type=['xlsx'], key="l_pv")
                    if st.button("🚀 Overwrite Database"):
                        if f_cv and f_pv:
                            with st.spinner("Processing..."):
                                df_cv, df_pv = clean_location_data(f_cv, "Canape-Vert"), clean_location_data(f_pv, "Pv")
                                final = pd.concat([df_cv, df_pv], ignore_index=True)
                                supabase.table("Master_Inventory").delete().neq("SKU", "VOID").execute()
                                supabase.table("Master_Inventory").insert(final.to_dict('records')).execute()
                                st.cache_data.clear(); st.success("Database Updated!"); st.rerun()

            c1, c2 = st.columns([2, 1])
            search = c1.text_input("🔍 Search Name or SKU")
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
                in_sku = st.text_input("Scan SKU", key="int_sku").strip()
                if in_sku and in_sku != st.session_state.intake_verify["sku"]:
                    match = master_inventory[(master_inventory['SKU'].str.lower() == in_sku.lower()) & (master_inventory['Location'] == "Pv")]
                    st.session_state.intake_verify = {"name": match['Full Name'].iloc[0] if not match.empty else None, "cat": match['Category'].iloc[0] if not match.empty else None, "sku": in_sku}
                if st.session_state.intake_verify["name"]:
                    st.success(f"Item: {st.session_state.intake_verify['name']}")
                    with st.form("int_form", clear_on_submit=True):
                        qty, dt = st.number_input("Quantity Received", 1), st.date_input("Date", value=date.today())
                        if st.form_submit_button("Record Intake"):
                            supabase.table("Shipments").insert({"Date": str(dt), "SKU": in_sku, "Wig Name": st.session_state.intake_verify["name"], "Category": str(st.session_state.intake_verify["cat"]), "Quantity": qty, "User": username, "Location": "Pv"}).execute()
                            st.cache_data.clear(); st.rerun()
            with col2:
                sh_data = get_sb_data("Shipments")
                if not sh_data.empty: st.dataframe(sh_data.sort_values("Date", ascending=False), hide_index=True)

    # --- TAB: AUDIT ---
    if "Audit" in tab_list:
        with tabs[tab_list.index("Audit")]:
            exp_data, dep_data = get_sb_data("Exposed_Wigs"), get_sb_data("Big_Depot")
            ca, cb = st.columns([1, 2])
            with ca:
                counter = st.selectbox("Counter Name", usernames_list)
                a_sku = st.text_input("Audit SKU Scan", key="aud_sku").strip()
                if a_sku and a_sku != st.session_state.audit_verify["sku"]:
                    m = master_inventory[(master_inventory['SKU'].str.lower() == a_sku.lower()) & (master_inventory['Location'] == "Pv")]
                    if not m.empty:
                        e_val = int(exp_data[exp_data['SKU'].str.lower() == a_sku.lower()]['Quantity'].sum()) if not exp_data.empty else 0
                        d_val = 0
                        if not dep_data.empty:
                            dm = dep_data[dep_data['SKU'].str.lower() == a_sku.lower()]
                            d_val = int(dm[dm['Type'] == "Addition"]['Quantity'].sum() - dm[dm['Type'] == "Subtraction"]['Quantity'].sum())
                        st.session_state.audit_verify = {"name": m['Full Name'].iloc[0], "cat": m['Category'].iloc[0], "sys": int(m['Stock'].iloc[0]), "sku": a_sku, "auto_exp": e_val, "auto_depot": d_val}
                
                if st.session_state.audit_verify["name"]:
                    st.info(f"System Record: {st.session_state.audit_verify['sys']}")
                    with st.form("aud_f", clear_on_submit=True):
                        f_shelf = st.number_input("Shelf", 0)
                        f_exp = st.number_input("Exposed", value=st.session_state.audit_verify["auto_exp"])
                        f_dep = st.number_input("Depot", value=st.session_state.audit_verify["auto_depot"])
                        f_ret = st.number_input("Returns", 0)
                        if st.form_submit_button("Save Audit"):
                            total = f_shelf + f_exp + f_dep + f_ret
                            diff = total - st.session_state.audit_verify["sys"]
                            supabase.table("Inventory_Audit").insert({"Date": str(date.today()), "SKU": a_sku, "Name": st.session_state.audit_verify["name"], "Category": str(st.session_state.audit_verify["cat"]), "Counter_Name": counter, "Total_Physical": total, "System_Stock": st.session_state.audit_verify["sys"], "Discrepancy": diff}).execute()
                            st.cache_data.clear(); st.success(f"Saved! Diff: {diff}"); time.sleep(1); st.rerun()
            with cb:
                aud_log = get_sb_data("Inventory_Audit")
                if not aud_log.empty: st.dataframe(aud_log.sort_values("Date", ascending=False), hide_index=True)

    # --- TAB: SALES ---
    if "Sales" in tab_list:
        with tabs[tab_list.index("Sales")]:
            cs1, cs2 = st.columns(2)
            f_old = cs1.file_uploader("Upload Start File (Square)", type=['xlsx'], key="s_o")
            f_new = cs2.file_uploader("Upload End File (Square)", type=['xlsx'], key="s_n")
            if f_old and f_new:
                d1, d2 = clean_location_data(f_old, "Pv"), clean_location_data(f_new, "Pv")
                c = pd.merge(d1, d2[['SKU', 'Stock']], on='SKU', suffixes=('_old', '_new'))
                c['Sold'] = c['Stock_old'] - c['Stock_new']
                sales = c[c['Sold'] > 0].copy()
                if not sales.empty:
                    st.metric("Total Period Revenue", f"${(sales['Sold'] * sales['Price']).sum():,.2f}")
                    st.plotly_chart(px.pie(sales, values='Sold', names='Category', title="Sales Distribution"))
                    st.dataframe(sales[['Category', 'Full Name', 'Sold', 'Price']], use_container_width=True, hide_index=True)

    # --- TAB: COMPARISON ---
    if "Comparison" in tab_list:
        with tabs[tab_list.index("Comparison")]:
            cc1, cc2 = st.columns(2)
            f_cv, f_pv = cc1.file_uploader("CV File", type=['xlsx']), cc2.file_uploader("PV File", type=['xlsx'])
            if f_cv and f_pv:
                d_cv, d_pv = clean_location_data(f_cv, "Canape-Vert"), clean_location_data(f_pv, "Pv")
                m = pd.merge(d_cv[['Full Name', 'Category', 'Stock']], d_pv[['Full Name', 'Stock']], on='Full Name', how='outer', suffixes=('_CV', '_PV')).fillna(0)
                cats = sorted(m['Category'].astype(str).unique().tolist())
                sel = st.selectbox("Category Filter", ["All"] + cats)
                if sel != "All": m = m[m['Category'] == sel]
                st.dataframe(m, use_container_width=True, hide_index=True)

    # --- TAB: FAST/SLOW ---
    if "Fast/Slow" in tab_list:
        with tabs[tab_list.index("Fast/Slow")]:
            cf1, cf2 = st.columns(2)
            fs_o, fs_n = cf1.file_uploader("Period Start", type=['xlsx'], key="f_o"), cf2.file_uploader("Period End", type=['xlsx'], key="f_n")
            if fs_o and fs_n:
                d_o, d_n = clean_location_data(fs_o, "Pv"), clean_location_data(fs_n, "Pv")
                comp = pd.merge(d_o, d_n[['SKU', 'Stock']], on='SKU', suffixes=('_o', '_n'))
                comp['Move'] = comp['Stock_o'] - comp['Stock_n']
                st.subheader("🚀 Top Sellers")
                st.dataframe(comp.sort_values("Move", ascending=False).head(10)[['Full Name', 'Move']], hide_index=True)
                st.subheader("🐢 Slow Movers")
                st.dataframe(comp[comp['Move'] <= 0].sort_values("Stock_o", ascending=False).head(10)[['Full Name', 'Stock_o']], hide_index=True)

    # --- TAB: BIG DEPOT ---
    if "Big Depot" in tab_list:
        with tabs[tab_list.index("Big Depot")]:
            depot_data = get_sb_data("Big_Depot")
            cd1, cd2 = st.columns([1, 2])
            with cd1:
                d_sku = st.text_input("Depot SKU").strip()
                if d_sku and d_sku != st.session_state.depot_verify["sku"]:
                    match = master_inventory[master_inventory['SKU'].str.lower() == d_sku.lower()]
                    st.session_state.depot_verify = {"name": match['Full Name'].iloc[0] if not match.empty else None, "sku": d_sku}
                if st.session_state.depot_verify["name"]:
                    with st.form("d_f"):
                        dtype, dqty = st.selectbox("Action", ["Addition", "Subtraction"]), st.number_input("Qty", 1)
                        if st.form_submit_button("Log Action"):
                            supabase.table("Big_Depot").insert({"Date": str(date.today()), "SKU": d_sku, "Wig Name": st.session_state.depot_verify["name"], "Type": dtype, "Quantity": dqty, "User": username}).execute()
                            st.cache_data.clear(); st.rerun()
            with cd2:
                if not depot_data.empty: st.dataframe(depot_data.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)

    # --- TAB: EXPOSED ---
    if "Exposed" in tab_list:
        with tabs[tab_list.index("Exposed")]:
            ex_data = get_sb_data("Exposed_Wigs")
            st.dataframe(ex_data[['SKU', 'Full Name', 'Quantity', 'Location']] if not ex_data.empty else pd.DataFrame(), use_container_width=True, hide_index=True)
            with st.form("ex_f"):
                e_sku, e_qty, e_loc = st.text_input("SKU").strip(), st.number_input("Qty", 0), st.selectbox("Loc", ["Pv", "Canape-Vert"])
                if st.form_submit_button("Update Display"):
                    m = master_inventory[master_inventory['SKU'].str.lower() == e_sku.lower()]
                    supabase.table("Exposed_Wigs").insert({"SKU": e_sku, "Full Name": m['Full Name'].iloc[0] if not m.empty else "Unknown", "Quantity": e_qty, "Location": e_loc, "Last_Updated": datetime.now().strftime("%Y-%m-%d %H:%M")}).execute()
                    st.cache_data.clear(); st.rerun()

    # --- TAB: PASSWORD ---
    if "Password" in tab_list:
        with tabs[tab_list.index("Password")]:
            authenticator.reset_password(username=username)

elif authentication_status is False: st.error('Incorrect Password')
elif authentication_status is None: st.warning('Please Login')
