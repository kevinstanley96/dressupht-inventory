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
    # Square files often have a header row we need to skip
    df = pd.read_excel(file, skiprows=1)
    df.columns = [str(c).strip().lower() for c in df.columns]
    
    # Mapping for Square's specific column names
    needed = {
        'item name': 'Wig Name', 
        'variation name': 'Style', 
        'sku': 'SKU', 
        'price': 'Price', 
        'categories': 'Category',  # Updated to plural 'categories'
        location_col_name.lower(): 'Stock'
    }
    
    # Check which columns exist
    existing = [c for c in needed.keys() if c in df.columns]
    df = df[existing].copy()
    df.columns = [needed[c] for c in existing]
    
    # Safety check for Categories
    if 'Category' not in df.columns:
        df['Category'] = 'Uncategorized'
    else:
        df['Category'] = df['Category'].fillna('Uncategorized')
    
    # Standard Cleaning
    df = df.dropna(subset=['SKU'])
    df['SKU'] = df['SKU'].astype(str).str.strip()
    df['Full Name'] = df['Wig Name'] + " (" + df['Style'].fillna('') + ")"
    
    df['Stock'] = pd.to_numeric(df['Stock'], errors='coerce').fillna(0)
    df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)
    return df

# --- 1. HEADER & INTAKE ---
st.title("🦱 Dressupht Pv: Performance Dashboard")

with st.expander("➕ SHIPMENT INTAKE (PV)", expanded=False):
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

# --- 2. UPLOADS ---
st.divider()
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

    # --- 3. THE TABS ---
    search = st.text_input("🔍 Search Name or SKU")
    def get_view(df_to_filter):
        if search:
            return df_to_filter[df_to_filter['Full Name'].astype(str).str.contains(search, case=False) | 
                                df_to_filter['SKU'].astype(str).str.contains(search, case=False)]
        return df_to_filter

    t1, t2, t3, t4, t5, t6, t7 = st.tabs([
        "🔄 Comparison", "🚚 Smart Transfers", "🔥 Fast/Slow (Leaderboard)", "❌ OOS", 
        "⚠️ Low Stock", "💰 Financials", "📋 Full Library"
    ])

    with t1:
        st.subheader("PV vs Haiti Visual Comparison")
        if haiti_active:
            compare_all = pd.merge(df_haiti[['SKU', 'Stock']], df_pv, on='SKU', suffixes=('_haiti', '_pv')).drop_duplicates(subset=['SKU'])
            comparison_view = compare_all[((compare_all['Stock_haiti'] > 75) & (compare_all['Stock_pv'] <= 35)) | (compare_all['Stock_pv'] < 5)].copy()
            def color_comparison(row):
                if row['Stock_pv'] < 5 and row['Stock_haiti'] > 25: return ['background-color: #2ecc71; color: white']*len(row)
                if row['Stock_pv'] < 5 and row['Stock_haiti'] < 5: return ['background-color: #e74c3c; color: white']*len(row)
                return ['']*len(row)
            st.dataframe(get_view(comparison_view[['Full Name', 'SKU', 'Stock_pv', 'Stock_haiti']]).style.apply(color_comparison, axis=1), use_container_width=True)

    with t2:
        if haiti_active:
            def calculate_request(row):
                if row['Stock_pv'] == 0 and row['Stock_haiti'] > 20: return 5
                if row['Sold'] >= 10 and row['Stock_pv'] <= 20 and row['Stock_haiti'] > 20: return 25
                if row['Stock_haiti'] > 75 and row['Stock_pv'] <= 35: return 15
                return 0
            compare_all['Request Qty'] = compare_all.apply(calculate_request, axis=1)
            transfers = compare_all[compare_all['Request Qty'] > 0]
            st.dataframe(get_view(transfers[['Full Name', 'SKU', 'Stock_haiti', 'Stock_pv', 'Sold', 'Request Qty']]), use_container_width=True)

    with t3:
        st.subheader("🏆 Sales Performance (Weekly)")
        col_w1, col_w2 = st.columns(2)
        with col_w1:
            st.write("✅ **Top 10 Selling Wigs**")
            st.table(df_pv.nlargest(10, 'Sold')[['Full Name', 'Sold', 'Stock']])
        with col_w2:
            st.write("❌ **Worst 10 Selling Wigs (Dead Stock)**")
            st.table(df_pv[df_pv['Stock'] > 0].nsmallest(10, 'Sold')[['Full Name', 'Sold', 'Stock']])
        
        st.divider()
        st.subheader("📁 Category Insights")
        cat_perf = df_pv.groupby('Category')['Sold'].sum().reset_index()
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.write("🌟 **Top 10 Categories**")
            st.table(cat_perf.nlargest(10, 'Sold'))
        with col_c2:
            st.write("📉 **Worst 10 Categories**")
            st.table(cat_perf.nsmallest(10, 'Sold'))

    with t4: st.dataframe(get_view(df_pv[df_pv['Stock'] == 0]), use_container_width=True)
    with t5: st.dataframe(get_view(df_pv[(df_pv['Stock'] > 0) & (df_pv['Stock'] <= 5)]), use_container_width=True)
    with t6:
        df_pv['Total Value'] = df_pv['Stock'] * df_pv['Price']
        st.dataframe(get_view(df_pv[['Full Name', 'SKU', 'Stock', 'Price', 'Total Value']].sort_values('Total Value', ascending=False)), use_container_width=True)
    with t7:
        if haiti_active:
            full_lib = pd.merge(df_pv, df_haiti[['SKU', 'Stock']], on='SKU', how='left', suffixes=('', '_haiti')).rename(columns={'Stock_haiti': 'Haiti Stock'})
            cols = [c for c in full_lib.columns if c != 'Haiti Stock'] + ['Haiti Stock']
            st.dataframe(get_view(full_lib[cols]), use_container_width=True)
        else:
            st.dataframe(get_view(df_pv), use_container_width=True)

else:
    st.info("👋 Upload the PV file to start.")
