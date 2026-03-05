# streamlit_app.py
# ------------------------------------------------------------
# ETS Dashboard (reads ETS.xlsx)
# - Filters: Type, Region, Jurisdiction search, Start year range, Price range
# - Metrics: count, avg/median/min/max USD price, earliest start year
# - Charts: Top prices bar, price histogram, start-year vs price scatter
# - Table + CSV download
# ------------------------------------------------------------

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

APP_TITLE = "ETS & Carbon Pricing Instruments Dashboard"
DEFAULT_SHEET = "Copy of 1. ETS"

# ---------- Page config ----------
st.set_page_config(page_title=APP_TITLE, page_icon="📊", layout="wide")
st.title("📊 ETS Dashboard")
st.caption("Interactive dashboard from ETS.xlsx (filters, charts, and table export).")

# ---------- File resolver ----------
def resolve_excel_path() -> Path:
    """
    Tries common locations:
    - ./data/ETS.xlsx   (recommended for repo)
    - ./ETS.xlsx
    - /mnt/data/ETS.xlsx (ChatGPT sandbox / notebooks)
    """
    candidates = [
        Path("data") / "ETS.xlsx",
        Path("ETS.xlsx"),
        Path("/mnt/data/ETS.xlsx"),
    ]
    for p in candidates:
        if p.exists():
            return p
    # If not found, show helpful error
    raise FileNotFoundError(
        "ETS.xlsx not found. Put it in ./data/ETS.xlsx or beside streamlit_app.py."
    )

# ---------- Parsing helpers ----------
USD_RE = re.compile(r"USD\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)

def parse_usd_price(x) -> float:
    """
    Extracts the first 'USD <number>' pattern from the Price rate column.
    Returns NaN if not parseable.
    Examples:
      'USD 59.47 / 55 EURO' -> 59.47
      'USD 12.34 / 86.13 CNY' -> 12.34
      NaN -> NaN
    """
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.nan
    s = str(x).strip()
    m = USD_RE.search(s)
    if not m:
        return np.nan
    try:
        return float(m.group(1))
    except ValueError:
        return np.nan

def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    # normalize column names (trim spaces)
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    # expected columns (based on your file)
    # "Price rate " sometimes has trailing spaces -> handled by strip above
    if "Price rate" not in df.columns and "Price rate" in [c.replace("  ", " ") for c in df.columns]:
        # just in case (rare)
        pass

    # parse USD price
    if "Price rate" in df.columns:
        price_col = "Price rate"
    else:
        # in your file it's "Price rate " (space); after strip it becomes "Price rate"
        price_col = "Price rate"

    df["price_usd"] = df[price_col].apply(parse_usd_price) if price_col in df.columns else np.nan

    # start year (your file is int)
    if "Start date" in df.columns:
        df["start_year"] = pd.to_numeric(df["Start date"], errors="coerce").astype("Int64")

    # clean some text columns for safer filtering
    for c in ["Instrument name", "Type", "Jurisdiction", "Region", "GHG"]:
        if c in df.columns:
            df[c] = df[c].astype(str).replace({"nan": np.nan}).str.strip()

    return df

@st.cache_data(show_spinner=False)
def load_data(path: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet)
    return clean_columns(df)

# ---------- Load ----------
try:
    excel_path = resolve_excel_path()
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()

with st.spinner("Loading ETS.xlsx ..."):
    df = load_data(excel_path, DEFAULT_SHEET)

# ---------- Sidebar ----------
st.sidebar.header("Filters")

# Search
q = st.sidebar.text_input("Search (Instrument / Jurisdiction)", value="").strip()

# Multi-select filters
type_options = sorted([x for x in df["Type"].dropna().unique()]) if "Type" in df.columns else []
region_options = sorted([x for x in df["Region"].dropna().unique()]) if "Region" in df.columns else []

sel_types = st.sidebar.multiselect("Type", options=type_options, default=type_options)
sel_regions = st.sidebar.multiselect("Region", options=region_options, default=region_options)

# Start year range
min_year = int(df["start_year"].min()) if "start_year" in df.columns and df["start_year"].notna().any() else 1900
max_year = int(df["start_year"].max()) if "start_year" in df.columns and df["start_year"].notna().any() else 2100
year_range = st.sidebar.slider("Start year range", min_value=min_year, max_value=max_year, value=(min_year, max_year))

# Price range (USD)
price_series = df["price_usd"].dropna()
if len(price_series) > 0:
    pmin = float(price_series.min())
    pmax = float(price_series.max())
    price_range = st.sidebar.slider("Price (USD) range", min_value=float(np.floor(pmin)), max_value=float(np.ceil(pmax)), value=(float(np.floor(pmin)), float(np.ceil(pmax))))
else:
    price_range = (0.0, 1.0)
    st.sidebar.info("No USD prices could be parsed from 'Price rate'.")

top_n = st.sidebar.slider("Top N (for bar chart)", min_value=5, max_value=30, value=15)

st.sidebar.divider()
st.sidebar.caption(f"📄 Data file: {excel_path}")

# ---------- Apply filters ----------
f = df.copy()

if "Type" in f.columns and sel_types:
    f = f[f["Type"].isin(sel_types)]

if "Region" in f.columns and sel_regions:
    f = f[f["Region"].isin(sel_regions)]

if "start_year" in f.columns:
    f = f[f["start_year"].between(year_range[0], year_range[1])]

# price filter (only apply to rows with parsed USD)
if "price_usd" in f.columns:
    f = f[(f["price_usd"].isna()) | (f["price_usd"].between(price_range[0], price_range[1]))]

if q:
    mask = False
    if "Instrument name" in f.columns:
        mask = mask | f["Instrument name"].fillna("").str.contains(q, case=False, na=False)
    if "Jurisdiction" in f.columns:
        mask = mask | f["Jurisdiction"].fillna("").str.contains(q, case=False, na=False)
    f = f[mask]

# ---------- Metrics ----------
c1, c2, c3, c4, c5 = st.columns(5)

count_instruments = int(len(f))
prices = f["price_usd"].dropna()

c1.metric("Instruments", f"{count_instruments:,}")

if len(prices) > 0:
    c2.metric("Avg price (USD)", f"{prices.mean():.2f}")
    c3.metric("Median price (USD)", f"{prices.median():.2f}")
    c4.metric("Max price (USD)", f"{prices.max():.2f}")
    c5.metric("Min price (USD)", f"{prices.min():.2f}")
else:
    c2.metric("Avg price (USD)", "—")
    c3.metric("Median price (USD)", "—")
    c4.metric("Max price (USD)", "—")
    c5.metric("Min price (USD)", "—")

st.divider()

# ---------- Charts ----------
left, right = st.columns([1.15, 0.85])

with left:
    st.subheader("Top prices (USD)")
    if len(prices) == 0:
        st.info("No parsed USD prices to plot. Check 'Price rate' formatting.")
    else:
        top = f.dropna(subset=["price_usd"]).sort_values("price_usd", ascending=False).head(top_n)
        fig = px.bar(
            top,
            x="price_usd",
            y="Instrument name" if "Instrument name" in top.columns else top.index,
            orientation="h",
            hover_data=[c for c in ["Jurisdiction", "Region", "Type", "start_year"] if c in top.columns],
        )
        fig.update_layout(height=520, yaxis_title="", xaxis_title="Price (USD)")
        st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Price distribution (USD)")
    if len(prices) == 0:
        st.info("No parsed USD prices to plot.")
    else:
        fig2 = px.histogram(f.dropna(subset=["price_usd"]), x="price_usd", nbins=15)
        fig2.update_layout(height=240, xaxis_title="Price (USD)", yaxis_title="Count")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Start year vs price (USD)")
    if ("start_year" not in f.columns) or len(prices) == 0:
        st.info("Need both start_year and parsed USD prices to plot.")
    else:
        scat = f.dropna(subset=["price_usd", "start_year"]).copy()
        color_col = "Type" if "Type" in scat.columns else None
        fig3 = px.scatter(
            scat,
            x="start_year",
            y="price_usd",
            color=color_col,
            hover_data=[c for c in ["Instrument name", "Jurisdiction", "Region"] if c in scat.columns],
        )
        fig3.update_layout(height=260, xaxis_title="Start year", yaxis_title="Price (USD)")
        st.plotly_chart(fig3, use_container_width=True)

st.divider()

# ---------- Table ----------
st.subheader("Data table")

# choose columns to show (keep original Price rate too)
preferred_cols = [
    "Instrument name",
    "Type",
    "Start date",
    "start_year",
    "Jurisdiction",
    "Region",
    "Price rate",
    "price_usd",
    "GHG",
    "Sector coverage",
    "Threshold",
    "Description",
    "Source",
]
show_cols = [c for c in preferred_cols if c in f.columns]

st.dataframe(
    f[show_cols].sort_values(["price_usd", "start_year"], ascending=[False, True], na_position="last"),
    use_container_width=True,
    height=520,
)

# Download
csv = f[show_cols].to_csv(index=False).encode("utf-8")
st.download_button(
    "⬇️ Download filtered CSV",
    data=csv,
    file_name="ETS_filtered.csv",
    mime="text/csv",
)

st.caption("Notes: `price_usd` is parsed from the first `USD <number>` found in 'Price rate'. Rows without USD stay blank.")
