import streamlit as st
import pandas as pd

st.set_page_config(page_title="Global MBM Dashboard", layout="wide")

st.title("Global Market-Based Mechanisms Dashboard")

# === Load data ===
@st.cache_data
def load_data():
    # ganti ke .csv kalau file kamu csv
    return pd.read_excel("data/mbm_raw.xlsx")

df = load_data()

st.success("Data berhasil dibaca ✅")

st.subheader("Preview data (5 baris pertama)")
st.dataframe(df.head(), use_container_width=True)

st.subheader("Kolom yang terbaca")
st.write(list(df.columns))
