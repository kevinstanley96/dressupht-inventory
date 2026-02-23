import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import streamlit_authenticator as stauth
import os
from datetime import date

# --- 1. USER AUTHENTICATION SETUP ---
config = {
    'credentials': {
        'usernames': {
            'kevin': {
                'name': 'Dressup Haiti Admin',
                'password': 'The$100$Raven' 
            },
            'staff1': {
                'name': 'Inventory Manager',
                'password': 'secretpassword456'
            }
        }
    },
    'cookie': {
        'expiry_days': 30,
        'key': 'inventory_signature_key',
        'name': 'inventory_cookie'
    }
}

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

login_data = authenticator.login()

if st.session_state["authentication_status"] == False:
    st.error("Username/password is incorrect")
elif st.session_state["authentication_status"] == None:
    st.warning("Please enter your username and password")
elif st.session_state["authentication_status"]:
    
    authenticator.logout('Logout', 'sidebar')
    st.sidebar.title(f"Welcome {st.session_state['name']}")

    # --- 2. CLOUD CONNECTION ---
    conn = st.connection("gsheets", type=GSheetsConnection)

    def clean_data(file, location_col_name):
        df = pd.read_excel(file, skiprows=1)
        df.columns = [str(c).strip().lower() for c in df.columns]
        needed = {
            'item name': 'Wig Name', 'variation name': 'Style', 
            'sku': 'SKU', 'price': 'Price', 'categories': 'Category',
            location_col_name.lower(): 'Stock'
        }
        existing = [c for c in needed.keys() if c in df.columns]
        df = df[existing].copy()
        df.columns = [needed[c] for c in existing]
        if 'Category' not in df.columns: df['Category'] = 'Uncategorized'
        df = df.dropna(subset=['SKU'])
        df['SKU'] = df['SKU'].astype(str).str.strip()
        df['Full Name'] = df['Wig Name'] + " (" + df['Style'].fillna('') + ")"
        df['Stock'] = pd.to_numeric(df['Stock'], errors='coerce').fillna(0)
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)
        return df

    # --- 3. MAIN APP ---
    st.title("🦱 Dressupht Pv: Full Intelligence Center")

    col_u1, col_u2, col_u3 = st.columns(3)
    file_pv = col_u1.file_uploader("📍 THIS Saturday (PV)", type=['xlsx'])
    file_pv_prev = col_u2.file_uploader("🕒 LAST Saturday (PV)", type=['xlsx'])
    file_haiti = col_u3.file_uploader("🌐 Dressup Haiti", type=['xlsx'])

    if file_pv:
        df_pv = clean_data(file_pv, "current quantity dressupht pv")
        sku_to_name = dict(zip(df_pv['SKU'], df_pv['Full Name']))

        # Sales Calculations
        if file_pv_prev:
            df_prev = clean_data(file_pv_prev, "current quantity dressupht pv")
            df_pv = pd.merge(df_pv, df_prev[['SKU', 'Stock']], on='SKU', how='left', suffixes=('', '_prev'))
            df_pv['Sold'] = (df_pv['Stock_prev'].fillna(0) - df_pv['Stock']).clip(lower=0)
        else:
            df_pv['Sold'] = 0

        haiti_active = False
        if file_haiti:
            df_haiti = clean_data(file_haiti, "current quantity dressup haiti")
            haiti_active = True

        search = st.text_input("🔍 Search Name or SKU")
        def get_view(df_to_filter):
            if search:
                return df_to_filter[df_to_filter['Full Name'].astype(str).str.contains(search, case=False) | 
                                    df_to_filter['SKU'].astype(str).str.contains(search, case=False)]
            return df_to_filter

        # --- THE TABS (ALL LOGIC REINSTATED) ---
        t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([
            "➕ Shipment Intake", "🔄 Comparison", "🚚 Smart Transfers", "🔥 Fast/Slow", 
            "❌ OOS", "⚠️ Low Stock", "💰 Financials", "📋 Full Library"
        ])

        with t1:
            st.subheader("Cloud Shipment Record")
            input_sku = st.text_input("Enter SKU").strip()
            detected_name = sku_to_name.get(input_sku, None)
            if input_sku and detected_name: st.success(f"Verified: {detected_name}")

            try:
                existing_data = conn.read(ttl=0)
            except:
                existing_data = pd.DataFrame(columns=["Date", "SKU", "Name", "Quantity", "User"])

            with st.form("intake_form", clear_on_submit=True):
                qty = st.number_input("Quantity Received", min_value=1)
                if st.form_submit_button("✅ Sync to Cloud"):
                    if detected_name:
                        new_row = pd.DataFrame([{"Date": str(date.today()), "SKU": input_sku, "Name": detected_name, "Quantity": qty, "User": st.session_state['username']}])
                        updated_df = pd.concat([existing_data, new_row], ignore_index=True)
                        conn.update(data=updated_df)
                        st.success("Synced!")
                        st.rerun()

            st.dataframe(existing_data.iloc[::-1], use_container_width=True)

        with t2:
            if haiti_active:
                compare_all = pd.merge(df_haiti[['SKU', 'Stock']], df_pv, on='SKU', suffixes=('_haiti', '_pv')).drop_duplicates(subset=['SKU'])
                comparison_view = compare_all[((compare_all['Stock_haiti'] > 75) & (compare_all['Stock_pv'] <= 35)) | (compare_all['Stock_pv'] < 5)].copy()
                def color_comparison(row):
                    if row['Stock_pv'] < 5 and row['Stock_haiti'] > 25: return ['background-color: #2ecc71; color: white']*len(row)
                    if row['Stock_pv'] < 5 and row['Stock_haiti'] < 5: return ['background-color: #e74c3c; color: white']*len(row)
                    return ['']*len(row)
                st.dataframe(get_view(comparison_view[['Full Name', 'SKU', 'Stock_pv', 'Stock_haiti']]).style.apply(color_comparison, axis=1), use_container_width=True)

        with t3:
            if haiti_active:
                def calculate_request(row):
                    if row['Stock_pv'] == 0 and row['Stock_haiti'] > 20: return 5
                    if row['Sold'] >= 10 and row['Stock_pv'] <= 20 and row['Stock_haiti'] > 20: return 25
                    return 0
                compare_all['Request Qty'] = compare_all.apply(calculate_request, axis=1)
                st.dataframe(get_view(compare_all[compare_all['Request Qty'] > 0][['Full Name', 'SKU', 'Stock_haiti', 'Stock_pv', 'Sold', 'Request Qty']]), use_container_width=True)

        with t4:
            st.subheader("🏆 Performance Leaders")
            cw1, cw2 = st.columns(2)
            cw1.write("Top 10 Selling Wigs")
            cw1.table(df_pv.nlargest(10, 'Sold')[['Full Name', 'Sold']])
            cw2.write("Worst 10 (Dead Stock)")
            cw2.table(df_pv[df_pv['Stock'] > 0].nsmallest(10, 'Sold')[['Full Name', 'Sold']])

        with t5: st.dataframe(get_view(df_pv[df_pv['Stock'] == 0]), use_container_width=True)
        with t6: st.dataframe(get_view(df_pv[(df_pv['Stock'] > 0) & (df_pv['Stock'] <= 5)]), use_container_width=True)
        with t7:
            df_pv['Value'] = df_pv['Stock'] * df_pv['Price']
            st.dataframe(get_view(df_pv[['Full Name', 'SKU', 'Stock', 'Price', 'Value']].sort_values('Value', ascending=False)), use_container_width=True)
        with t8:
            st.dataframe(get_view(df_pv), use_container_width=True)
    else:
        st.info("👋 Upload PV file to begin.")
