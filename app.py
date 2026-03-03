import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date
import time
import plotly.express as px

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Dressupht Stock ERP v6.0", layout="wide")

# --- 2. SUPABASE CONNECTION ---
@st.cache_resource
def init_connection():
    # Ensure these are set in your .streamlit/secrets.toml
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- 3. INITIAL STATE ---
if 'audit_verify' not in st.session_state:
    st.session_state.audit_verify = {
        "name": None, 
        "cat": None, 
        "sys": 0, 
        "sku": "", 
        "auto_exp": 0, 
        "auto_depot": 0
    }

# --- 4. HELPER FUNCTIONS ---
def get_user_role(username):
    try:
        # Fetch role and location from the 'Role' table for the current user
        res = supabase.table("Role").select("Roles, Assigned Location").eq("User Name", username.lower()).execute()
        if res.data:
            return res.data[0]['Roles'], res.data[0]['Assigned Location']
        return "Staff", "Unknown"
    except Exception:
        return "Staff", "Unknown"

# --- 5. SIDEBAR DESIGN ---
with st.sidebar:
    # We are using a placeholder for the username since we'll add the login logic later
    # For now, let's assume 'kevin' for development
    current_user = "kevin" 
    
    # A. Centered Username in Caps
    st.markdown(f"<h1 style='text-align: center;'>{current_user.upper()}</h1>", unsafe_allow_html=True)
    
    # B. Access Level & Location
    role, loc = get_user_role(current_user)
    st.write(f"**Access Level:** {role}")
    st.write(f"**Location:** {loc}")
    
    # C. Separator
    st.divider()
    
    # D. Upload Slots
    st.subheader("📦 Sync Master Inventory")
    file_cv = st.file_uploader("Upload Canape-Vert (Excel)", type=['xlsx'])
    file_pv = st.file_uploader("Upload PV (Excel)", type=['xlsx'])
    
    if st.button("🚀 Process & Sync", use_container_width=True):
        if file_cv and file_pv:
            st.info("Files detected. Ready for the cleaning logic!")
        else:
            st.warning("Please upload both files first.")

st.title("DRESSUP HAITI STOCK SYSTEM")
st.write("System initialized and connected.")


