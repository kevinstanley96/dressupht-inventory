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
st.set_page_config(page_title="Dressupht ERP v5.2.2", layout="wide")

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

def send_email(subject, body, recipients):
    if not recipients: return False
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'], msg['From'], msg['To'] = subject, st.secrets["EMAIL_ADDRESS"], ", ".join(recipients)
    try:
        with smtplib.SMTP(st.secrets.get("SMTP_SERVER", "smtp.gmail.com"), int(st.secrets.get("SMTP_PORT", 587))) as smtp:
            smtp.starttls()
            smtp.login(st.secrets["EMAIL_ADDRESS"], st.secrets["EMAIL_PASSWORD"])
            smtp.send_message(msg)
            return True
    except Exception as e:
        st.error(f"Email failed: {e}")
        return False

def clean_location_data(file, loc_name):
    file_bytes = file.read()
    df = pd.read_excel(io.BytesIO(file_bytes), skiprows=1)
    df.columns = [str(c).strip() for c in df.columns]
    
    if 'Item Name' in df.columns:
        df['Item Name'] = (df['Item Name'].astype(str)
                           .str.replace('”', '"').str.replace('“', '"')
                           .str.replace('’', "'").str.replace('‘', "'"))
        
    mapping = {'Item Name': 'Full Name', 'SKU': 'SKU', 'Categories': 'Category', 'Price': 'Price'}
    df = df.rename(columns=mapping)
    stock_col = "Current Quantity Dressup Haiti" if loc_name == "Canape-Vert" else "Current Quantity Dressupht Pv"
    df['Stock'] = pd.to_numeric(df[stock_col], errors='coerce').fillna(0).astype(int) if stock_col in df.columns else 0
    df['Category'] = df['Category'].fillna("Uncategorized")
    df['Location'] = loc_name
    df['SKU'] = df['SKU'].astype(str).str.strip().replace(['nan', ''], 'NO_SKU')
    df['Price'] = pd.to_numeric(df.get('Price', 0), errors='coerce').fillna(0.0)
    return df[['SKU', 'Full Name', 'Stock', 'Price', 'Category', 'Location']].copy()

# --- LOGIN ---
name, authentication_status, username = authenticator.login(location='main')

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
    authenticator.logout('Logout', 'sidebar')

    st.title("DRESSUP HAITI STOCK SYSTEM")

    if user_role == "Admin":
        with st.expander("🛡️ Master Data Sync", expanded=False):
            c_u1, c_u2 = st.columns(2)
            fp, fh = c_u1.file_uploader("PV File", type=['xlsx']), c_u2.file_uploader("CV File", type=['xlsx'])
            if fp and fh and st.button("🚀 Run Wipe & Sync"):
                with st.spinner("Processing..."):
                    full = pd.concat([clean_location_data(fp, "Pv"), clean_location_data(fh, "Canape-Vert")], ignore_index=True)
                    supabase.table("Master_Inventory").delete().neq("SKU", "NON_EXISTENT").execute()
                    for i in range(0, len(full), 100):
                        supabase.table("Master_Inventory").insert(full.iloc[i:i+100].to_dict('records')).execute()
                    st.cache_data.clear()
                    st.success("Sync Complete!")
                    st.rerun()

    all_tabs = ["Library", "Intake", "Audit", "Sales", "Comparison", "Fast/Slow", "Big Depot", "Exposed", "Admin", "Cleanup"]
    if user_role == "Manager":
        tab_list = ["Library", "Intake", "Audit", "Comparison", "Fast/Slow", "Big Depot", "Exposed"]
    elif user_role == "Staff":
        tab_list = ["Library", "Exposed"]
    else:
        tab_list = all_tabs
    
    tabs = st.tabs(tab_list)

    if "Library" in tab_list:
        with tabs[tab_list.index("Library")]:
            c1, c2 = st.columns([2, 1])
            search = c1.text_input("🔍 Search")
            sort_choice = c2.selectbox("Sort By", ["Name", "Category", "Location"])
            disp_df = master_inventory.copy()
            if user_role == "Staff" and user_location != "Both":
                disp_df = disp_df[disp_df['Location'] == user_location]
            if not disp_df.empty:
                sort_map = {"Name": "Full Name", "Category": ["Category", "Full Name"], "Location": ["Location", "Full Name"]}
                disp_df = disp_df.sort_values(by=sort_map[sort_choice])
                if search:
                    disp_df = disp_df[disp_df.apply(lambda r: search.lower() in str(r['Full Name']).lower() or search.lower() in str(r['SKU']).lower(), axis=1)]
                st.dataframe(disp_df[['Location', 'Category', 'Full Name', 'SKU', 'Stock', 'Price']], use_container_width=True, hide_index=True)
                csv_data = disp_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                st.download_button("📥 Download CSV", data=csv_data, file_name=f"inventory_{date.today()}.csv", mime='text/csv')

    if "Intake" in tab_list:
        with tabs[tab_list.index("Intake")]:
            in_sku = st.text_input("Scan SKU for Intake").strip()
            if in_sku:
                match = master_inventory[(master_inventory['SKU'].str.lower() == in_sku.lower()) & (master_inventory['Location'] == "Pv")]
                if not match.empty:
                    st.success(f"Item: {match['Full Name'].iloc[0]}")
                    with st.form("int_f"):
                        # Added date selector
                        intake_date = st.date_input("Date of Intake", date.today())
                        qty = st.number_input("Qty", 1)
                        
                        if st.form_submit_button("Save"):
                            # Using the selected intake_date instead of hardcoded date.today()
                            supabase.table("Shipments").insert({
                                "Date": str(intake_date), 
                                "SKU": in_sku, 
                                "Wig Name": match['Full Name'].iloc[0], 
                                "Category": match['Category'].iloc[0], 
                                "Quantity": qty, 
                                "User": username, 
                                "Location": "Pv"
                            }).execute()
                            st.cache_data.clear()
                            st.rerun()

    if "Audit" in tab_list:
        with tabs[tab_list.index("Audit")]:
            exp_data = get_sb_data("Exposed_Wigs")
            dep_data = get_sb_data("Big_Depot")
            a_sku = st.text_input("SKU to Audit").strip()
            if a_sku:
                match = master_inventory[(master_inventory['SKU'].str.lower() == a_sku.lower()) & (master_inventory['Location'] == "Pv")]
                if not match.empty:
                    sys_qty = int(match['Stock'].iloc[0])
                    exp_qty = int(exp_data[(exp_data['SKU'].str.lower() == a_sku.lower()) & (exp_data['Location'] == "Pv")]['Quantity'].sum()) if not exp_data.empty else 0
                    depot_qty = 0
                    if not dep_data.empty:
                        d_match = dep_data[dep_data['SKU'].str.lower() == a_sku.lower()]
                        depot_qty = int(d_match[d_match['Type'] == "Addition"]['Quantity'].sum() - d_match[d_match['Type'] == "Subtraction"]['Quantity'].sum())
                    with st.form("aud_f"):
                        m = st.number_input("Manual", 0)
                        e = st.number_input("Exposed (Auto)", value=exp_qty)
                        b = st.number_input("Depot (Auto)", value=depot_qty)
                        if st.form_submit_button("Record Audit"):
                            tp = m + e + b
                            supabase.table("Inventory_Audit").insert({"Date": str(date.today()), "SKU": a_sku, "Name": match['Full Name'].iloc[0], "Counter_Name": username, "Total_Physical": tp, "System_Stock": sys_qty, "Discrepancy": tp - sys_qty}).execute()
                            st.cache_data.clear()
                            st.rerun()

    if "Big Depot" in tab_list:
        with tabs[tab_list.index("Big Depot")]:
            d_sku = st.text_input("Depot SKU Input").strip()
            if d_sku:
                match = master_inventory[master_inventory['SKU'].str.lower() == d_sku.lower()]
                if not match.empty:
                    st.success(f"Item: {match['Full Name'].iloc[0]}")
                    with st.form("dep_f"):
                        # Added date selector
                        depot_date = st.date_input("Date of Action", date.today())
                        dtype = st.selectbox("Type", ["Addition", "Subtraction"])
                        dqty = st.number_input("Qty", 1)
                        if st.form_submit_button("Submit"):
                            # Using the selected depot_date
                            supabase.table("Big_Depot").insert({
                                "Date": str(depot_date), 
                                "SKU": d_sku, 
                                "Wig Name": match['Full Name'].iloc[0], 
                                "Type": dtype, 
                                "Quantity": dqty, 
                                "User": username
                            }).execute()
                            st.cache_data.clear()
                            st.rerun()

    if "Exposed" in tab_list:
        with tabs[tab_list.index("Exposed")]:
            exp_data = get_sb_data("Exposed_Wigs")
            st.dataframe(exp_data, hide_index=True)
            with st.form("exp_f"):
                e_sku = st.text_input("SKU").strip()
                e_qty = st.number_input("Qty", 0)
                e_loc = st.selectbox("Loc", ["Pv", "Canape-Vert"])
                if st.form_submit_button("Save"):
                    match = master_inventory[master_inventory['SKU'].str.lower() == e_sku.lower()]
                    payload = {"SKU": e_sku, "Full Name": match['Full Name'].iloc[0] if not match.empty else "Unknown", "Quantity": e_qty, "Location": e_loc, "Last_Updated": datetime.now().strftime("%Y-%m-%d %H:%M")}
                    supabase.table("Exposed_Wigs").insert(payload).execute()
                    st.cache_data.clear()
                    st.rerun()

    if "Admin" in tab_list:
        with tabs[tab_list.index("Admin")]:
            st.header("Admin Control")
            col_admin1, col_admin2 = st.columns(2)
            with col_admin1:
                st.subheader("User Profiles")
                if not roles_df.empty:
                    sel_u = st.selectbox("Select User", roles_df['User Name'].tolist())
                    u_email = st.text_input("Update Email", value=roles_df[roles_df['User Name'] == sel_u]['Email'].iloc[0] if 'Email' in roles_df.columns else "")
                    if st.button("Save Profile"):
                        supabase.table("Role").update({"Email": u_email}).eq("User Name", sel_u).execute()
                        st.success("Done!")
            with col_admin2:
                st.subheader("Send Task")
                with st.form("task_f"):
                    t_to = st.text_input("Email To")
                    t_sub = st.text_input("Subject")
                    t_msg = st.text_area("Message")
                    if st.form_submit_button("Send Email"):
                        if send_email(t_sub, t_msg, [t_to]): st.success("Sent!")

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





