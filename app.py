import streamlit as st
import pandas as pd
import os
from datetime import date

# --- PAGE CONFIG ---
st.set_page_config(page_title="Dressupht Pv Multi-Loc", layout="wide", page_icon="🦱")

# --- FILE SETUP ---
LOG_FILE = "wig_intake_log.csv"
if not os.path.exists(LOG_FILE):
    pd.DataFrame(columns=["Date", "SKU", "Quantity"]).to_csv(LOG_FILE, index=False)

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
    else:
        df['Category'] = df['Category'].fillna('Uncategorized')
    
    df = df.dropna(subset=['SKU'])
    df['SKU'] = df['SKU'].astype(str).str.strip()
    df['Full Name'] = df['Wig Name'] + " (" + df['Style'].fillna('') + ")"
    
    df['Stock'] = pd.to_numeric(df['Stock'], errors='coerce').fillna(0)
    df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)
    return df

# --- HEADER ---
st.title("🦱 Dressupht Pv: Intelligence Center")

# --- UPLOADS ---
st.subheader("📂 Upload Square Exports")
col_u1, col_u2, col_u3 = st.columns(3)
file_pv = col_u1.file_uploader("📍 THIS Saturday (PV)", type=['xlsx'])
file_pv_prev = col_u2.file_uploader("🕒 LAST Saturday (PV)", type=['xlsx'])
file_haiti = col_u3.file_uploader("🌐 Dressup Haiti", type=['xlsx'])

if file_pv:
    df_pv = clean_data(file_pv, "current quantity dressupht pv")
    
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
    search = st.text_input("🔍 Search Name or SKU")
    def get_view(df_to_filter):
        if search:
            return df_to_filter[df_to_filter['Full Name'].astype(str).str.contains(search, case=False) | 
                                df_to_filter['SKU'].astype(str).str.contains(search, case=False)]
        return df_to_filter

    t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([
        "➕ Shipment Intake", "🔄 Comparison", "🚚 Smart Transfers", "🔥 Fast/Slow", 
        "❌ OOS", "⚠️ Low Stock", "💰 Financials", "📋 Full Library"
    ])

    with t1:
        st.subheader("Record New Shipment")
        with st.form("intake_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            input_sku = col1.text_input("SKU Number")
            input_qty = col2.number_input("Quantity Received", min_value=1, step=1)
            input_date = col3.date_input("Date Received", value=date.today())
            if st.form_submit_button("✅ Save Intake"):
                if input_sku:
                    new_entry = pd.DataFrame([[str(input_date), input_sku, input_qty]], columns=["Date", "SKU", "Quantity"])
                    new_entry.to_csv(LOG_FILE, mode='a', header=False, index=False)
                    st.success(f"Logged {input_qty} for SKU: {input_sku}")
                    st.rerun()

        st.divider()
        st.subheader("Recent History")
        log_df = pd.read_csv(LOG_FILE)
        if not log_df.empty:
            st.dataframe(log_df.iloc[::-1], use_container_width=True)
            
            # Download Button
            csv_data = log_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Intake History (CSV)",
                data=csv_data,
                file_name=f"wig_intake_{date.today()}.csv",
                mime='text/csv',
            )
            
            if st.button("🗑️ Delete Last Entry"):
                log_df[:-1].to_csv(LOG_FILE, index=False)
                st.warning("Last entry deleted.")
                st.rerun()
        else:
            st.info("No intake entries found yet.")

    # [Remaining Performance/Stock Tabs Logic Stays the Same]
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
                if row['Stock_haiti'] > 75 and row['Stock_pv'] <= 35: return 15
                return 0
            compare_all['Request Qty'] = compare_all.apply(calculate_request, axis=1)
            st.dataframe(get_view(compare_all[compare_all['Request Qty'] > 0][['Full Name', 'SKU', 'Stock_haiti', 'Stock_pv', 'Sold', 'Request Qty']]), use_container_width=True)

    with t4:
        st.subheader("🏆 Sales Performance")
        cw1, cw2 = st.columns(2)
        cw1.table(df_pv.nlargest(10, 'Sold')[['Full Name', 'Sold']])
        cw2.table(df_pv[df_pv['Stock'] > 0].nsmallest(10, 'Sold')[['Full Name', 'Sold']])

    # T5-T8 (OOS, Low Stock, Financials, Library) logic follows...
    with t8:
        if haiti_active:
            full_lib = pd.merge(df_pv, df_haiti[['SKU', 'Stock']], on='SKU', how='left', suffixes=('', '_haiti')).rename(columns={'Stock_haiti': 'Haiti Stock'})
            st.dataframe(get_view(full_lib), use_container_width=True)
        else:
            st.dataframe(get_view(df_pv), use_container_width=True)
else:
    st.info("👋 Upload the PV file to start.")
