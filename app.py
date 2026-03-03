import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date
import time
import plotly.express as px

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Dressupht ERP v6.0", layout="wide")

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

st.title("👗 Dressupht ERP NextGen")
st.write("System initialized and connected.")
