import streamlit as st
import pandas as pd
import os
from datetime import date

# --- PAGE CONFIG ---
st.set_page_config(page_title="Dressupht Pv Multi-Loc", layout="wide", page_icon="🦱")

# --- FILE SETUP ---
LOG_FILE = "wig_intake_log.csv"
if not os.path.exists(LOG_FILE):
    # Ensure 'Name' is in the columns of the log file
    pd.DataFrame(columns=["Date", "SKU", "Name", "Quantity"]).to_csv(LOG_FILE, index=False)

def clean_data(file, location_col_name):
    df = pd.read_excel(file, skiprows=1)
    df.columns = [str(c).strip().lower() for c in df.columns]
    needed = {
        'item name': 'Wig Name', 
        'variation name': 'Style', 
        'sku': 'SKU', 
        'price': 'Price', 
        'categories': 'Category',
        location_col_name.lower(): 'Stock'
    }
    existing = [c for c in needed.keys() if c in df.columns]
    df = df[existing].copy()
    df.columns = [needed[c] for c in existing]
    if 'Category' not in df.columns:
        df['Category'] = 'Uncategorized'
    df = df.dropna(subset=['SKU'])
    df['SKU'] = df['SKU'].astype(str).str.strip()
    df['Full Name'] = df['Wig Name'] + " (" + df['Style'].fillna('') + ")"
    df['Stock'] = pd.to_numeric(df['Stock'], errors='coerce').fillna(0)
    df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)
    return df

# --- HEADER & UPLOADS ---
st.title("🦱 Dressupht Pv: Intelligence Center")

st.subheader("📂 Upload Square Exports")
col_u1, col_u2, col_u3 = st.columns(3)
file_pv = col_u1.file_uploader("📍 THIS Saturday (PV)", type=['xlsx'])
file_pv_prev = col_u2.file_uploader("🕒 LAST Saturday (PV)", type=['xlsx'])
file_haiti = col_u3.file_uploader("🌐 Dressup Haiti", type=['xlsx'])

if file_pv:
    df_pv = clean_data(file_pv, "current quantity dressupht pv")
    sku_to_name = dict(zip(df_pv['SKU'], df_pv['Full Name']))
    
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

    # --- TABS ---
    t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([
        "➕ Shipment Intake", "🔄 Comparison", "🚚 Smart Transfers", "🔥 Fast/Slow", 
        "❌ OOS", "⚠️ Low Stock", "💰 Financials", "📋 Full Library"
    ])

    with t1:
        st.subheader("Record New Shipment")
        
        # UI for SKU Lookup
        col_in1, col_in2 = st.columns([1, 2])
        input_sku = col_in1.text_input("Scan/Type SKU Number").strip()
        
        detected_name = sku_to_name.get(input_sku, None)
        
        if input_sku:
            if detected_name:
                st.success(f"✅ **Item Found:** {detected_name}")
            else:
                st.error("❌ SKU not found in the uploaded PV file.")

        with st.form("intake_form", clear_on_submit=True):
            input_qty = st.number_input("Quantity Received", min_value=1, step=1)
            input_date = st.date_input("Date Received", value=date.today())
            
            submit = st.form_submit_button("📥 Save to CSV Log")
            
            if submit:
                if detected_name:
                    # Creating the row including the Name
                    new_entry = pd.DataFrame([[str(input_date), input_sku, detected_name, input_qty]], 
                                             columns=["Date", "SKU", "Name", "Quantity"])
                    # Save to local CSV
                    new_entry.to_csv(LOG_FILE, mode='a', header=False, index=False)
                    st.toast(f"Saved {detected_name} to log!")
                    st.rerun()
                else:
                    st.error("Please enter a valid SKU before saving.")

        st.divider()
        st.subheader("Intake History (Stored in CSV)")
        log_df = pd.read_csv(LOG_FILE)
        if not log_df.empty:
            # Displaying the log so you can see the 'Name' column
            st.dataframe(log_df.iloc[::-1], use_container_width=True)
            
            # Preparation for CSV download
            csv_output = log_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📊 Download Full CSV with Names",
                data=csv_output,
                file_name=f"intake_report_{date.today()}.csv",
                mime='text/csv'
            )
            
            if st.button("🗑️ Delete Last Entry"):
                log_df[:-1].to_csv(LOG_FILE, index=False)
                st.rerun()
        else:
            st.info("Log is currently empty.")

    # [Remaining tabs: Comparison, Smart Transfers, Fast/Slow, etc. remain unchanged]
    with t2:
        if haiti_active:
            compare_all = pd.merge(df_haiti[['SKU', 'Stock']], df_pv, on='SKU', suffixes=('_haiti', '_pv')).drop_duplicates(subset=['SKU'])
            comparison_view = compare_all[((compare_all['Stock_haiti'] > 75) & (compare_all['Stock_pv'] <= 35)) | (compare_all['Stock_pv'] < 5)].copy()
            def color_comparison(row):
                if row['Stock_pv'] < 5 and row['Stock_haiti'] > 25: return ['background-color: #2ecc71; color: white']*len(row)
                if row['Stock_pv'] < 5 and row['Stock_haiti'] < 5: return ['background-color: #e74c3c; color: white']*len(row)
                return ['']*len(row)
            st.dataframe(comparison_view[['Full Name', 'SKU', 'Stock_pv', 'Stock_haiti']].style.apply(color_comparison, axis=1), use_container_width=True)

    with t3:
        if haiti_active:
            def calculate_request(row):
                if row['Stock_pv'] == 0 and row['Stock_haiti'] > 20: return 5
                if row['Sold'] >= 10 and row['Stock_pv'] <= 20 and row['Stock_haiti'] > 20: return 25
                if row['Stock_haiti'] > 75 and row['Stock_pv'] <= 35: return 15
                return 0
            compare_all['Request Qty'] = compare_all.apply(calculate_request, axis=1)
            st.dataframe(compare_all[compare_all['Request Qty'] > 0][['Full Name', 'SKU', 'Stock_haiti', 'Stock_pv', 'Sold', 'Request Qty']], use_container_width=True)

    with t4:
        st.subheader("🏆 Sales Performance")
        cw1, cw2 = st.columns(2)
        cw1.write("Top 10 Selling Wigs")
        cw1.table(df_pv.nlargest(10, 'Sold')[['Full Name', 'Sold']])
        cw2.write("Worst 10 Selling Wigs")
        cw2.table(df_pv[df_pv['Stock'] > 0].nsmallest(10, 'Sold')[['Full Name', 'Sold']])

else:
    st.info("👋 Upload the PV file to start.")
