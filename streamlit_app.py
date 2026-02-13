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
st.write("Countries (wide):", wide["Country"].nunique())
extras = (
    wide["Country"].astype(str).str.strip()
    .value_counts()
)
st.write("Sample country names (last 30 alphabetically):")
st.write(sorted(wide["Country"].astype(str).str.strip().unique())[-30:])

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
import pycountry

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

# --- Build a country-level summary for mapping (with hover details)

# Helper: satu mechanism_type bisa punya banyak detail (gabungkan)
def summarize_mechanisms(df_long: pd.DataFrame) -> pd.DataFrame:
    # Gabungkan detail per (Country, mechanism_type)
    g = (
        df_long.groupby(["Country", "mechanism_type"])["mechanism_detail"]
        .apply(lambda s: "; ".join(sorted({x for x in s.astype(str).str.strip() if x and x.lower() != "nan"})))
        .reset_index()
    )

    # Buat “bullet list” per country
    # Format: "ETS: UK ETS | Carbon Tax: UK Carbon Price Support | ..."
    lines = (
        g.assign(line=lambda d: d["mechanism_type"] + ": " + d["mechanism_detail"])
         .groupby("Country")["line"]
         .apply(lambda s: "<br>".join(s.tolist()))
         .reset_index(name="existing_mechanisms_html")
    )

    # Count mechanism types present (0–8)
    counts = g.groupby("Country")["mechanism_type"].nunique().reset_index(name="mechanism_type_count")

    # VCM projects sum (untuk angka)
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

country_summary = summarize_mechanisms(f)
country_summary["iso3"] = country_summary["Country"].apply(to_iso3)



st.caption("Map color: Total mechanisms (0–8)")
plot_col = "mechanism_type_count"

missing_iso = country_summary[country_summary["iso3"].isna()]["Country"].tolist()
if missing_iso:
    st.warning(
        f"ISO3 tidak ketemu untuk {len(missing_iso)} negara (tidak tampil di peta). "
        f"Contoh: {', '.join(missing_iso[:10])}"
    )

m = country_summary.dropna(subset=["iso3"]).copy()


fig_map = px.choropleth(
    m,
    locations="iso3",
    color=plot_col,
    hover_name="Country",
    hover_data={
        "iso3": True,
        "mechanism_type_count": True,
        "vcm_projects_sum": True,
        "existing_mechanisms_html": False,  # kita pakai hovertemplate biar rapi
    },
)

fig_map.update_traces(
    hovertemplate=
    "<b>%{hovertext}</b><br>" +
    "ISO3: %{customdata[0]}<br>" +
    "Total mechanisms (0–8): %{customdata[1]}<br>" +
    "VCM projects (sum): %{customdata[2]}<br><br>" +
    "%{customdata[3]}<extra></extra>",
    customdata=m[["iso3", "mechanism_type_count", "vcm_projects_sum", "existing_mechanisms_html"]].values,
)

st.plotly_chart(fig_map, use_container_width=True, key="map_choropleth")


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
