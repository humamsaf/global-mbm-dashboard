import streamlit as st
import pandas as pd
import plotly.express as px
import pycountry

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

# --- helper: country name -> ISO3
MANUAL_ISO3 = {
    "Côte d’Ivoire": "CIV",
    "Côte d'Ivoire": "CIV",
    "São Tomé and Príncipe": "STP",
    "Democratic Republic of the Congo": "COD",
    "Republic of the Congo": "COG",
    "United States": "USA",
    "Russia": "RUS",
    "Iran": "IRN",
    "Syria": "SYR",
    "Vatican City": "VAT",
    "North Korea": "PRK",
    "South Korea": "KOR",
    "Laos": "LAO",
    "Timor-Leste": "TLS",
    "Brunei Darussalam": "BRN",
    "Bolivia": "BOL",
    "Venezuela": "VEN",
    "Tanzania": "TZA",
    "Micronesia": "FSM",
}

def to_iso3(name: str):
    name = (name or "").strip()
    if name in MANUAL_ISO3:
        return MANUAL_ISO3[name]
    try:
        c = pycountry.countries.lookup(name)
        return c.alpha_3
    except Exception:
        return None

@st.cache_data
def load_raw() -> pd.DataFrame:
    df = pd.read_excel(FILE_PATH)
    df.columns = [str(c).strip() for c in df.columns]
    return df

def tidy_long(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    keep = ["No", "Country", "Region"] + [c.strip() for c in MECH_COLS.keys()] + ["Total Mechanism"]
    keep = [c for c in keep if c in df_raw.columns]
    df = df_raw[keep].copy()

    df = df[df["Country"].notna()]
    df["Country"] = df["Country"].astype(str).str.strip()
    df = df[df["Country"].str.lower() != "country"]

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

    # VCM numeric
    long["vcm_projects"] = pd.NA
    mask_vcm = long["mechanism_type"] == "VCM project"
    long.loc[mask_vcm, "vcm_projects"] = pd.to_numeric(long.loc[mask_vcm, "mechanism_detail"], errors="coerce")

    # buang non-VCM yang "0"
    long = long[~((~mask_vcm) & (long["mechanism_detail"] == "0"))]

    return df, long

def summarize_mechanisms(df_long: pd.DataFrame) -> pd.DataFrame:
    g = (
        df_long.groupby(["Country", "mechanism_type"])["mechanism_detail"]
        .apply(lambda s: "; ".join(sorted({x for x in s.astype(str).str.strip() if x and x.lower() != "nan"})))
        .reset_index()
    )

    lines = (
        g.assign(line=lambda d: d["mechanism_type"] + ": " + d["mechanism_detail"])
         .groupby("Country")["line"]
         .apply(lambda s: "<br>".join(s.tolist()))
         .reset_index(name="existing_mechanisms_html")
    )

    counts = g.groupby("Country")["mechanism_type"].nunique().reset_index(name="mechanism_type_count")

    vcm = (
        df_long[df_long["mechanism_type"] == "VCM project"]
        .dropna(subset=["vcm_projects"])
        .groupby("Country")["vcm_projects"]
        .sum()
        .reset_index(name="vcm_projects_sum")
    )

    out = counts.merge(lines, on="Country", how="left").merge(vcm, on="Country", how="left")
    out["vcm_projects_sum"] = out["vcm_projects_sum"].fillna(0)
    return out

# ===== Load
raw = load_raw()
wide, long = tidy_long(raw)

# ===== Header
st.title("Global Market-Based Mechanisms Dashboard")
st.caption(
    "Coverage: 194 countries and territories, including UN member states, microstates, and UN observer entities "
    "(e.g. Vatican City and Palestine). Kosovo is not included."
)

# ===== Sidebar (clean)
st.sidebar.header("Filters")
region_sel = st.sidebar.multiselect("Region", sorted(long["Region"].dropna().unique()), key="f_region")
type_sel = st.sidebar.multiselect("Mechanism type", sorted(long["mechanism_type"].dropna().unique()), key="f_type")
country_sel = st.sidebar.multiselect("Country", sorted(long["Country"].dropna().unique()), key="f_country")
keyword = st.sidebar.text_input("Search in details", value="", key="f_kw").strip()

if st.sidebar.button("Reset filters", use_container_width=True):
    st.session_state["f_region"] = []
    st.session_state["f_type"] = []
    st.session_state["f_country"] = []
    st.session_state["f_kw"] = ""
    st.rerun()

f = long.copy()
if region_sel:
    f = f[f["Region"].isin(region_sel)]
if type_sel:
    f = f[f["mechanism_type"].isin(type_sel)]
if country_sel:
    f = f[f["Country"].isin(country_sel)]
if keyword:
    f = f[f["mechanism_detail"].str.contains(keyword, case=False, na=False)]

# ===== KPIs (stable + in-view)
k1, k2, k3, k4 = st.columns(4)
k1.metric("Countries covered", int(wide["Country"].nunique()))
k2.metric("Countries in view", int(f["Country"].nunique()))
k3.metric("Mechanism types in view", int(f["mechanism_type"].nunique()))
vcm_sum = f.loc[f["mechanism_type"] == "VCM project", "vcm_projects"].sum(min_count=1)
k4.metric("VCM projects (sum)", 0 if pd.isna(vcm_sum) else int(vcm_sum))

st.divider()

# ===== Map (single metric, clean)
country_summary = summarize_mechanisms(f)
country_summary["iso3"] = country_summary["Country"].apply(to_iso3)

missing_iso = country_summary[country_summary["iso3"].isna()]["Country"].tolist()
if missing_iso:
    st.warning(
        f"ISO3 not found for {len(missing_iso)} countries/territories (not shown on map). "
        f"Examples: {', '.join(missing_iso[:10])}"
    )

m = country_summary.dropna(subset=["iso3"]).copy()

st.subheader("World map — total market-based mechanisms (0–8)")
st.caption("Color indicates the number of existing mechanism categories per country; hover for policy details.")

fig_map = px.choropleth(
    m,
    locations="iso3",
    color="mechanism_type_count",
    hover_name="Country",
)
fig_map.update_coloraxes(cmin=0, cmax=8)

fig_map.update_traces(
    hovertemplate=
    "<b>%{hovertext}</b><br>" +
    "Total mechanisms (0–8): %{customdata[0]}<br>" +
    "VCM projects (sum): %{customdata[1]}<br><br>" +
    "%{customdata[2]}<extra></extra>",
    customdata=m[["mechanism_type_count", "vcm_projects_sum", "existing_mechanisms_html"]].values,
)

st.plotly_chart(fig_map, use_container_width=True, key="map_choropleth")

# ===== Tabs for the rest
tab1, tab2, tab3 = st.tabs(["Summary charts", "Country profile", "Data table"])

with tab1:
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Countries by mechanism type")
        by_type = (
            f.groupby("mechanism_type")["Country"].nunique()
            .reset_index(name="countries")
            .sort_values("countries", ascending=False)
        )
        st.plotly_chart(px.bar(by_type, x="mechanism_type", y="countries"), use_container_width=True, key="bar_type")

    with c2:
        st.subheader("Top countries by VCM projects")
        v = f[f["mechanism_type"] == "VCM project"].dropna(subset=["vcm_projects"]).copy()
        if len(v) == 0:
            st.info("No VCM data under the current filters.")
        else:
            top = (
                v.groupby("Country")["vcm_projects"].sum()
                .reset_index()
                .sort_values("vcm_projects", ascending=False)
                .head(20)
            )
            st.plotly_chart(px.bar(top, x="Country", y="vcm_projects"), use_container_width=True, key="bar_vcm")

with tab2:
    st.subheader("Country profile")
    countries_all = sorted(wide["Country"].unique())
    default_idx = countries_all.index("United Kingdom") if "United Kingdom" in countries_all else 0
    sel = st.selectbox("Select a country", countries_all, index=default_idx, key="country_profile")

    cf = long[long["Country"] == sel].copy()
    st.write("Region:", cf["Region"].iloc[0] if len(cf) else "—")

    prof = (
        cf.groupby("mechanism_type")["mechanism_detail"]
        .apply(lambda s: "\n".join(f"- {x}" for x in sorted({v.strip() for v in s.astype(str) if v and v.lower() != "nan"})))
        .reset_index()
        .sort_values("mechanism_type")
    )

    for _, r in prof.iterrows():
        st.markdown(f"**{r['mechanism_type']}**")
        st.markdown(r["mechanism_detail"])

with tab3:
    st.subheader("Detail table (filtered)")
    show_cols = ["Country", "Region", "mechanism_type", "mechanism_detail", "vcm_projects"]
    st.dataframe(
        f[show_cols].sort_values(["Country", "mechanism_type"]),
        use_container_width=True,
        hide_index=True,
    )

    csv = f[["Country", "Region", "mechanism_type", "mechanism_detail"]].to_csv(index=False).encode("utf-8")
    st.download_button("Download filtered data (CSV)", csv, "filtered_mbm.csv", "text/csv", use_container_width=True)
