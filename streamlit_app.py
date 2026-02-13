import streamlit as st
import os
import pandas as pd

st.set_page_config(page_title="Global MBM Dashboard", layout="wide")
st.title("Global Market-Based Mechanisms Dashboard")

st.subheader("Debug: files in repo")
st.code(os.getcwd())

st.subheader("Root directory")
st.write(os.listdir("."))

st.subheader("Data directory")
if os.path.exists("data"):
    st.write(os.listdir("data"))
else:
    st.error("Folder 'data' tidak ditemukan di repo.")

# --- Try to load any matching file automatically
st.subheader("Try loading data")
candidates = []
if os.path.exists("data"):
    for fn in os.listdir("data"):
        if fn.lower().endswith((".xlsx", ".xls", ".csv", ".parquet")):
            candidates.append(fn)

if not candidates:
    st.error("Tidak ada file data (.xlsx/.csv/.parquet) di folder data/")
else:
    st.success(f"Ketemu file data: {candidates}")
    chosen = st.selectbox("Pilih file data", candidates)

    path = os.path.join("data", chosen)
    if chosen.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(path)
    elif chosen.lower().endswith(".csv"):
        df = pd.read_csv(path)
    else:
        df = pd.read_parquet(path)

    st.success("Data berhasil dibaca ✅")
    st.dataframe(df.head(), use_container_width=True)
    st.write("Columns:", list(df.columns))
