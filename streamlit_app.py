# streamlit_app.py
# ------------------------------------------------------------
# ETS Dashboard (reads ETS.xlsx, sheet: "Copy of 1. ETS")
# Features:
# - Sidebar filters: search, Type, Region, start-year, price (USD), coverage (%)
# - Metrics: instrument count, price stats, coverage stats
# - Charts: top USD prices, USD histogram, start-year vs USD scatter,
#           coverage histogram, avg coverage by Region/Type
# - Table + CSV download
#
# Put ETS.xlsx in:
#   ./data/ETS.xlsx   (recommended)
# or beside this file, or (in sandbox) /mnt/data/ETS.xlsx
# ------------------------------------------------------------

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

APP_TITLE = "ETS & Carbon Pricing Instruments Dashboard"
DEFAULT_SHEET = "Copy of 1. ETS"

# -------------------------
# Page config
# -------------------------
st.set_page_config(page_title=APP_TITLE, page_icon="📊", layout="wide")
st.title("📊 ETS Dashboard")
st.caption("Interactive dashboard from ETS.xlsx (filters, charts, and table export).")

# -------------------------
# File resolver
# -------------------------
def resolve_excel_path() -> Path:
    candidates = [
        Path("data") / "ETS.xlsx",
        Path("ETS.xlsx"),
        Path("/mnt/data/ETS.xlsx"),
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError("ETS.xlsx not found. Put it in ./data/ETS.xlsx or beside streamlit_app.py.")

# -------------------------
# Parsing helpers
# -------------------------
USD_RE = re.compile(r"USD\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)

def parse_usd_price(x) -> float:
    """
    Extract first 'USD <number>' from 'Price rate' text.
    Examples:
      'USD 59.47 / 55 EURO' -> 59.47
      'USD 12.34 / 86.13 CNY' -> 12.34
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

def to_coverage_pct(x) -> float:
    """
    Converts coverage share to percentage.
    Accepts:
      - 0.59 -> 59
      - 59 -> 59
      - '59%' -> 59
    """
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.nan

    s = str(x).strip()
    if not s:
        return np.nan

    if s.endswith("%"):
        s = s[:-1].strip()

    try:
        v = float(s)
    except ValueError:
        return np.nan

    # heuristic: share vs percent
    if v <= 1.5:
        return v * 100.0
    return v

def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    # price
    if "Price rate" in df.columns:
        df["price_usd"] = df["Price rate"].apply(parse_usd_price)
    else:
        df["price_usd"] = np.nan

    # start year
    if "Start date" in df.columns:
        df["start_year"] = pd.to_numeric(df["Start date"], errors="coerce").astype("Int64")
    else:
        df["start_year"] = pd.Series([pd.NA] * len(df), dtype="Int64")

    # coverage
    share_col = "Share of jurisdiction's"
    if share_col in df.columns:
        df["coverage_pct"] = df[share_col].apply(to_coverage_pct)
    else:
        df["coverage_pct"] = np.nan

    # clean text columns for filtering
    for c in ["Instrument name", "Type", "Jurisdiction", "Region", "GHG", "Sector coverage"]:
        if c in df.columns:
            df[c] = df[c].replace({np.nan: None})
            df[c] = df[c].astype(str).replace({"None": np.nan, "nan": np.nan}).str.strip()

    return df

@st.cache_data(show_spinner=False)
def load_data(path: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet)
    return clean_columns(df)

# -------------------------
# Load data
# -------------------------
try:
    excel_path = resolve_excel_path()
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()

with st.spinner("Loading ETS.xlsx ..."):
    df = load_data(excel_path, DEFAULT_SHEET)

# -------------------------
# Sidebar filters
# -------------------------
st.sidebar.header("Filters")

q = st.sidebar.text_input("Search (Instrument / Jurisdiction)", value="").strip()

type_options = sorted([x for x in df.get("Type", pd.Series([], dtype=str)).dropna().unique()])
region_options = sorted([x for x in df.get("Region", pd.Series([], dtype=str)).dropna().unique()])

sel_types = st.sidebar.multiselect("Type", options=type_options, default=type_options)
sel_regions = st.sidebar.multiselect("Region", options=region_options, default=region_options)

# Start year range
if "start_year" in df.columns and df["start_year"].notna().any():
    min_year = int(df["start_year"].min())
    max_year = int(df["start_year"].max())
else:
    min_year, max_year = 1900, 2100

year_range = st.sidebar.slider(
    "Start year range",
    min_value=min_year,
    max_value=max_year,
    value=(min_year, max_year),
)

# Price range (USD)
price_series = df["price_usd"].dropna() if "price_usd" in df.columns else pd.Series([], dtype=float)
if len(price_series) > 0:
    pmin = float(price_series.min())
    pmax = float(price_series.max())
    price_range = st.sidebar.slider(
        "Price (USD) range",
        min_value=float(np.floor(pmin)),
        max_value=float(np.ceil(pmax)),
        value=(float(np.floor(pmin)), float(np.ceil(pmax))),
    )
else:
    price_range = (0.0, 1.0)
    st.sidebar.info("No USD prices could be parsed from 'Price rate'.")

# Coverage range (%)
cov_series = df["coverage_pct"].dropna() if "coverage_pct" in df.columns else pd.Series([], dtype=float)
if len(cov_series) > 0:
    cmin = float(np.floor(cov_series.min()))
    cmax = float(np.ceil(cov_series.max()))
    # keep slider sane; if data somehow >100, still allow (up to 150 cap for UI)
    slider_min = max(0.0, cmin)
    slider_max = min(150.0, cmax) if cmax <= 150 else cmax
    default_max = min(100.0, cmax) if cmax <= 150 else cmax

    coverage_range = st.sidebar.slider(
        "Coverage (%) range",
        min_value=float(slider_min),
        max_value=float(slider_max),
        value=(float(slider_min), float(default_max)),
    )
else:
    coverage_range = (0.0, 100.0)
    st.sidebar.info("No coverage values found in 'Share of jurisdiction's'.")

top_n = st.sidebar.slider("Top N (for top-price chart)", min_value=5, max_value=30, value=15)

st.sidebar.divider()
st.sidebar.caption(f"📄 Data file: {excel_path}")

# -------------------------
# Apply filters
# -------------------------
f = df.copy()

if "Type" in f.columns and sel_types:
    f = f[f["Type"].isin(sel_types)]

if "Region" in f.columns and sel_regions:
    f = f[f["Region"].isin(sel_regions)]

if "start_year" in f.columns:
    f = f[f["start_year"].between(year_range[0], year_range[1]) | f["start_year"].isna()]

# price filter (only apply to rows with parsed USD)
if "price_usd" in f.columns:
    f = f[(f["price_usd"].isna()) | (f["price_usd"].between(price_range[0], price_range[1]))]

# coverage filter (only apply to rows with coverage)
if "coverage_pct" in f.columns:
    f = f[(f["coverage_pct"].isna()) | (f["coverage_pct"].between(coverage_range[0], coverage_range[1]))]

if q:
    mask = pd.Series(False, index=f.index)
    if "Instrument name" in f.columns:
        mask = mask | f["Instrument name"].fillna("").str.contains(q, case=False, na=False)
    if "Jurisdiction" in f.columns:
        mask = mask | f["Jurisdiction"].fillna("").str.contains(q, case=False, na=False)
    f = f[mask]

# -------------------------
# Metrics
# -------------------------
c1, c2, c3, c4, c5, c6 = st.columns(6)

count_instruments = int(len(f))
prices = f["price_usd"].dropna() if "price_usd" in f.columns else pd.Series([], dtype=float)
cov = f["coverage_pct"].dropna() if "coverage_pct" in f.columns else pd.Series([], dtype=float)

c1.metric("Instruments", f"{count_instruments:,}")

if len(prices) > 0:
    c2.metric("Avg price (USD)", f"{prices.mean():.2f}")
    c3.metric("Median price (USD)", f"{prices.median():.2f}")
else:
    c2.metric("Avg price (USD)", "—")
    c3.metric("Median price (USD)", "—")

if len(cov) > 0:
    c4.metric("Avg coverage (%)", f"{cov.mean():.1f}")
    c5.metric("Median coverage (%)", f"{cov.median():.1f}")
    c6.metric("Max coverage (%)", f"{cov.max():.1f}")
else:
    c4.metric("Avg coverage (%)", "—")
    c5.metric("Median coverage (%)", "—")
    c6.metric("Max coverage (%)", "—")

st.divider()

# -------------------------
# Charts
# -------------------------
left, right = st.columns([1.15, 0.85])

with left:
    st.subheader("Top prices (USD)")
    if len(prices) == 0 or "price_usd" not in f.columns:
        st.info("No parsed USD prices to plot. Check 'Price rate' formatting.")
    else:
        top = f.dropna(subset=["price_usd"]).sort_values("price_usd", ascending=False).head(top_n)
        y_col = "Instrument name" if "Instrument name" in top.columns else top.index
        fig = px.bar(
            top,
            x="price_usd",
            y=y_col,
            orientation="h",
            hover_data=[c for c in ["Jurisdiction", "Region", "Type", "start_year", "coverage_pct"] if c in top.columns],
        )
        fig.update_layout(height=520, yaxis_title="", xaxis_title="Price (USD)")
        st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Price distribution (USD)")
    if len(prices) == 0:
        st.info("No parsed USD prices to plot.")
    else:
        fig2 = px.histogram(f.dropna(subset=["price_usd"]), x="price_usd", nbins=15)
        fig2.update_layout(height=230, xaxis_title="Price (USD)", yaxis_title="Count")
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
            hover_data=[c for c in ["Instrument name", "Jurisdiction", "Region", "coverage_pct"] if c in scat.columns],
        )
        fig3.update_layout(height=240, xaxis_title="Start year", yaxis_title="Price (USD)")
        st.plotly_chart(fig3, use_container_width=True)

    st.subheader("Coverage distribution (%)")
    if "coverage_pct" not in f.columns or f["coverage_pct"].dropna().empty:
        st.info("No coverage data to plot.")
    else:
        fig4 = px.histogram(f.dropna(subset=["coverage_pct"]), x="coverage_pct", nbins=12)
        fig4.update_layout(height=230, xaxis_title="Coverage (%)", yaxis_title="Count")
        st.plotly_chart(fig4, use_container_width=True)

    st.subheader("Avg coverage by Region / Type")
    if "coverage_pct" not in f.columns or f["coverage_pct"].dropna().empty:
        st.info("No coverage data to aggregate.")
    else:
        group_cols = []
        if "Region" in f.columns:
            group_cols.append("Region")
        if "Type" in f.columns:
            group_cols.append("Type")

        if group_cols:
            agg = (
                f.dropna(subset=["coverage_pct"])
                .groupby(group_cols, dropna=False)["coverage_pct"]
                .mean()
                .reset_index()
                .sort_values("coverage_pct", ascending=False)
                .head(20)
            )
            y = "Region" if "Region" in agg.columns else group_cols[0]
            color = "Type" if ("Type" in agg.columns and y != "Type") else None
            fig5 = px.bar(agg, x="coverage_pct", y=y, color=color, orientation="h")
            fig5.update_layout(height=320, xaxis_title="Avg coverage (%)", yaxis_title="")
            st.plotly_chart(fig5, use_container_width=True)
        else:
            st.info("Region/Type columns not available for grouping.")

st.divider()

# -------------------------
# Table + download
# -------------------------
st.subheader("Data table")

preferred_cols = [
    "Instrument name",
    "Type",
    "Start date",
    "start_year",
    "Jurisdiction",
    "Region",
    "Price rate",
    "price_usd",
    "Share of jurisdiction's",
    "coverage_pct",
    "GHG",
    "Sector coverage",
    "Threshold",
    "Description",
    "Source",
]
show_cols = [c for c in preferred_cols if c in f.columns]

sort_cols = []
if "price_usd" in f.columns:
    sort_cols.append("price_usd")
if "coverage_pct" in f.columns:
    sort_cols.append("coverage_pct")
if "start_year" in f.columns:
    sort_cols.append("start_year")

if sort_cols:
    table_df = f[show_cols].sort_values(sort_cols, ascending=[False] * len(sort_cols), na_position="last")
else:
    table_df = f[show_cols]

st.dataframe(table_df, use_container_width=True, height=540)

csv = table_df.to_csv(index=False).encode("utf-8")
st.download_button(
    "⬇️ Download filtered CSV",
    data=csv,
    file_name="ETS_filtered.csv",
    mime="text/csv",
)

st.caption("Notes: `price_usd` parsed from first 'USD <number>' in 'Price rate'. `coverage_pct` derived from 'Share of jurisdiction's'.")
