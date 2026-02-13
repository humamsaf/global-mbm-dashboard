import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Global MBM Dashboard", layout="wide")

FILE_PATH = "data/Global Market Based Mechanism.xlsx"

MECH_COLS = {
    "1. Carbon Tax": "Carbon Tax",
    "2. ETS": "ETS",
    "3. Tax Incentives": "Tax Incentives",
    "4. Fuel Mandates": "Fuel Mandates",
    "5. VCM project ": "VCM project",
    "6. Feebates": "Feebates",
    "7. CBAM": "CBAM",
    "8. AMC": "AMC",
}

@st.cache_data
def load_raw() -> pd.DataFrame:
    df = pd.read_excel(FILE_PATH)
    # rapikan nama kolom
    df.columns = [str(c).strip() for c in df.columns]
    return df

def tidy_long(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # buang kolom aneh (angka / unnamed)
    keep = ["No", "Country", "Region"] + [c.strip() for c in MECH_COLS.keys()] + ["Total Mechanism"]
    keep = [c for c in keep if c in df_raw.columns]
    df = df_raw[keep].copy()

    # pastikan No numeric & drop baris kosong
    df = df[df["Country"].notna()]
    df["Country"] = df["Country"].astype(str).str.strip()
    df = df[df["Country"].str.lower() != "country"]

    # buat presence matrix (0/1) untuk KPI
    presence = df.copy()
    for col in MECH_COLS.keys():
        c = col.strip()
        if c in presence.columns:
            s = presence[c].astype(str).str.strip()
            s = s.replace({"nan": "", "None": ""})
            # VCM: anggap ada kalau angka > 0
            if MECH_COLS[col] == "VCM project":
                v = pd.to_numeric(s, errors="coerce").fillna(0)
                presence[c] = (v > 0).astype(int)
            else:
                presence[c] = (s != "") & (s != "0")
                presence[c] = presence[c].astype(int)

    # reshape ke long
    value_cols = [c.strip() for c in MECH_COLS.keys() if c.strip() in df.columns]
    long = df.melt(
        id_vars=["No", "Country", "Region"],
        value_vars=value_cols,
        var_name="mechanism_type_raw",
        value_name="mechanism_detail",
    )
    long["mechanism_type"] = long["mechanism_type_raw"].map(
        {k.strip(): v for k, v in MECH_COLS.items()}
    ).fillna(long["mechanism_type_raw"])
    long = long.drop(columns=["mechanism_type_raw"])

    long["mechanism_detail"] = long["mechanism_detail"].astype(str).str.strip()
    long = long[long["mechanism_detail"].notna()]
    long = long[long["mechanism_detail"] != ""]
    long = long[long["mechanism_detail"].str.lower() != "nan"]

    # standardize VCM numeric
    long["vcm_projects"] = pd.NA
    mask_vcm = long["mechanism_type"] == "VCM project"
    long.loc[mask_vcm, "vcm_projects"] = pd.to_numeric(long.loc[mask_vcm, "mechanism_detail"], errors="coerce")

    # buang non-VCM yang "0"
    long = long[~((~mask_vcm) & (long["mechanism_detail"] == "0"))]

    return df, long

raw = load_raw()
wide, long = tidy_long(raw)

st.title("Global Market-Based Mechanisms Dashboard")

# ---- Sidebar filters
st.sidebar.header("Filters")
region_sel = st.sidebar.multiselect("Region", sorted(long["Region"].dropna().unique()))
type_sel = st.sidebar.multiselect("Mechanism type", sorted(long["mechanism_type"].dropna().unique()))
country_sel = st.sidebar.multiselect("Country", sorted(long["Country"].dropna().unique()))

f = long.copy()
if region_sel:
    f = f[f["Region"].isin(region_sel)]
if type_sel:
    f = f[f["mechanism_type"].isin(type_sel)]
if country_sel:
    f = f[f["Country"].isin(country_sel)]

# ---- KPIs
k1, k2, k3, k4 = st.columns(4)
k1.metric("Countries (filtered)", f["Country"].nunique())
k2.metric("Mechanism entries", len(f))
k3.metric("Mechanism types", f["mechanism_type"].nunique())

vcm_sum = f.loc[f["mechanism_type"] == "VCM project", "vcm_projects"].sum(min_count=1)
k4.metric("VCM projects (sum)", 0 if pd.isna(vcm_sum) else int(vcm_sum))

st.divider()

# ---- Charts
c1, c2 = st.columns(2)

with c1:
    st.subheader("Countries by mechanism type")
    by_type = f.groupby("mechanism_type")["Country"].nunique().reset_index(name="countries")
    by_type = by_type.sort_values("countries", ascending=False)
    fig1 = px.bar(by_type, x="mechanism_type", y="countries")
    st.plotly_chart(fig1, use_container_width=True)

with c2:
    st.subheader("Top countries by VCM projects")
    v = f[f["mechanism_type"] == "VCM project"].dropna(subset=["vcm_projects"]).copy()
    if len(v) == 0:
        st.info("Tidak ada data VCM project di filter saat ini.")
    else:
        top = v.groupby("Country")["vcm_projects"].sum().reset_index()
        top = top.sort_values("vcm_projects", ascending=False).head(15)
        fig2 = px.bar(top, x="Country", y="vcm_projects")
        st.plotly_chart(fig2, use_container_width=True)

st.subheader("Detail table (filtered)")
show_cols = ["Country", "Region", "mechanism_type", "mechanism_detail", "vcm_projects"]
st.dataframe(f[show_cols].sort_values(["Country", "mechanism_type"]), use_container_width=True, hide_index=True)

with st.expander("Show wide table (original)"):
    st.dataframe(wide, use_container_width=True, hide_index=True)
