# app.py — Global MBM Dashboard (interactive: click map -> country panel -> 8 mechanism cards -> drilldown)
# Requirements:
#   streamlit, pandas, plotly, pycountry, openpyxl
# Optional (recommended for best map click reliability across Streamlit versions):
#   pip install streamlit-plotly-events

import streamlit as st
import pandas as pd
import plotly.express as px
import pycountry
from streamlit_plotly_events import plotly_events
# ---------- Page ----------
st.set_page_config(page_title="Global MBM Dashboard", layout="wide")

FILE_PATH = "data/Global Market Based Mechanism.xlsx"

# IMPORTANT: remove trailing spaces in keys
MECH_COLS = {
    "1. Carbon Tax": "Carbon Tax",
    "2. ETS": "ETS",
    "3. Tax Incentives": "Tax Incentives",
    "4. Fuel Mandates": "Fuel Mandates",
    "5. VCM project": "VCM project",
    "6. Feebates": "Feebates",
    "7. CBAM": "CBAM",
    "8. AMC": "AMC",
}

MECH_LIST = list(MECH_COLS.values())

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
    "Palestine": "PSE",
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
    # Keep only expected columns if they exist
    keep = ["No", "Country", "Region"] + [c.strip() for c in MECH_COLS.keys()] + ["Total Mechanism"]
    keep = [c for c in keep if c in df_raw.columns]
    df = df_raw[keep].copy()

    # Clean country rows
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

    # Map numbered headers -> clean mechanism type label
    mapping = {k.strip(): v for k, v in MECH_COLS.items()}
    long["mechanism_type"] = long["mechanism_type_raw"].map(mapping).fillna(long["mechanism_type_raw"])
    long = long.drop(columns=["mechanism_type_raw"])

    # Clean detail text
    long["mechanism_detail"] = long["mechanism_detail"].astype(str).str.strip()
    long = long[(long["mechanism_detail"] != "") & (long["mechanism_detail"].str.lower() != "nan")]

    # VCM numeric
    long["vcm_projects"] = pd.NA
    mask_vcm = long["mechanism_type"] == "VCM project"
    long.loc[mask_vcm, "vcm_projects"] = pd.to_numeric(long.loc[mask_vcm, "mechanism_detail"], errors="coerce")

    # Drop non-VCM "0" noise
    long = long[~((~mask_vcm) & (long["mechanism_detail"] == "0"))]

    return df, long

def summarize_mechanisms(df_long: pd.DataFrame) -> pd.DataFrame:
    # collapse detail per country/type
    g = (
        df_long.groupby(["Country", "mechanism_type"])["mechanism_detail"]
        .apply(lambda s: "; ".join(sorted({x for x in s.astype(str).str.strip() if x and x.lower() != "nan"})))
        .reset_index()
    )

    # numbered list of mechanism types (no details)
    types_list = (
        g.groupby("Country")["mechanism_type"]
        .apply(lambda s: "<br>".join([f"{i+1}. {t}" for i, t in enumerate(sorted(set(s.tolist())))]))
        .reset_index(name="mechanism_types_list_html")
    )

    counts = g.groupby("Country")["mechanism_type"].nunique().reset_index(name="mechanism_type_count")

    vcm = (
        df_long[df_long["mechanism_type"] == "VCM project"]
        .dropna(subset=["vcm_projects"])
        .groupby("Country")["vcm_projects"]
        .sum()
        .reset_index(name="vcm_projects_sum")
    )

    out = counts.merge(types_list, on="Country", how="left").merge(vcm, on="Country", how="left")
    out["vcm_projects_sum"] = pd.to_numeric(out["vcm_projects_sum"], errors="coerce").fillna(0).astype(int)
    out["mechanism_types_list_html"] = out["mechanism_types_list_html"].fillna("No recorded mechanisms in this dataset.")
    return out

@st.cache_data
def add_iso3_col(df_wide: pd.DataFrame) -> pd.DataFrame:
    out = df_wide.copy()
    out["iso3"] = out["Country"].apply(to_iso3)
    return out

def safe_unique_sorted(series: pd.Series) -> list[str]:
    return sorted([x for x in series.dropna().astype(str).unique().tolist() if x.strip() != ""])

# ---------- Load ----------
raw = load_raw()
wide, long = tidy_long(raw)
wide = add_iso3_col(wide)

# ---------- Interaction state ----------
if "selected_country" not in st.session_state:
    st.session_state.selected_country = None
if "selected_mechanism" not in st.session_state:
    st.session_state.selected_mechanism = None

# ---------- Header ----------
st.title("Global Market-Based Mechanisms Dashboard")
st.caption(
    "Coverage: 194 countries and territories, including UN member states, microstates, and UN observer entities "
    "(e.g. Vatican City and Palestine). Kosovo is not included."
)

# ---------- Sidebar filters ----------
st.sidebar.header("Filters")
region_sel = st.sidebar.multiselect("Region", safe_unique_sorted(long["Region"]), key="f_region")
type_sel = st.sidebar.multiselect("Mechanism type", safe_unique_sorted(long["mechanism_type"]), key="f_type")
country_sel = st.sidebar.multiselect("Country", safe_unique_sorted(long["Country"]), key="f_country")
keyword = st.sidebar.text_input("Search in details", value="", key="f_kw").strip()
st.sidebar.caption(
    f"Active filters → Region:{len(region_sel)} | Type:{len(type_sel)} | Country:{len(country_sel)} | Keyword:'{keyword}'"
)

if st.sidebar.button("Reset filters", use_container_width=True):
    for k in ["f_region", "f_type", "f_country", "f_kw"]:
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()

# Apply filters to LONG
f = long.copy()
if region_sel:
    f = f[f["Region"].isin(region_sel)]
if type_sel:
    f = f[f["mechanism_type"].isin(type_sel)]
if country_sel:
    f = f[f["Country"].isin(country_sel)]
if keyword:
    f = f[f["mechanism_detail"].str.contains(keyword, case=False, na=False)]

# Apply region/country filters to WIDE (for base map inclusion)
wide_view = wide.copy()
if region_sel:
    wide_view = wide_view[wide_view["Region"].isin(region_sel)]
if country_sel:
    wide_view = wide_view[wide_view["Country"].isin(country_sel)]

# ---------- KPIs ----------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Countries covered", int(wide["Country"].nunique()))
k2.metric("Countries in view", int(wide_view["Country"].nunique()))
k3.metric("Mechanism types in view", int(f["mechanism_type"].nunique()))
vcm_sum = f.loc[f["mechanism_type"] == "VCM project", "vcm_projects"].sum(min_count=1)
k4.metric("VCM projects (sum)", 0 if pd.isna(vcm_sum) else int(vcm_sum))

st.divider()

# ---------- Two-column layout: map (left) + country panel (right) ----------
left, right = st.columns([1.35, 1.0], gap="large")

# ===== LEFT: MAP =====
with left:
    st.subheader("World map")

    MAP_OPTIONS = ["Total mechanisms (0–8)"] + MECH_LIST
    map_choice = st.selectbox("Map mode", MAP_OPTIONS, index=0, key="map_choice")

    # Base countries (include zeros)
    base = wide_view[["Country", "Region", "iso3"]].drop_duplicates().copy()

    # Summary from filtered long
    country_summary = summarize_mechanisms(f)

    # Merge to base so missing countries become 0
    m = base.merge(country_summary, on="Country", how="left")
    m["mechanism_type_count"] = m["mechanism_type_count"].fillna(0).astype(int)
    m["vcm_projects_sum"] = pd.to_numeric(m["vcm_projects_sum"], errors="coerce").fillna(0).astype(int)
    m["mechanism_types_list_html"] = m["mechanism_types_list_html"].fillna("No recorded mechanisms in this dataset.")

    missing_iso = m[m["iso3"].isna()]["Country"].tolist()
    if missing_iso:
        st.warning(
            f"ISO3 not found for {len(missing_iso)} countries/territories (not shown on map). "
            f"Examples: {', '.join(missing_iso[:10])}"
        )

    m_plot = m.dropna(subset=["iso3"]).copy()

    # ---- Choose metric for coloring
    if map_choice == "Total mechanisms (0–8)":
        fig_map = px.choropleth(
            m_plot,
            locations="iso3",
            color="mechanism_type_count",
            hover_name="Country",
        )
        fig_map.update_coloraxes(cmin=0, cmax=8)
        fig_map.update_traces(
            hovertemplate=
            "<b>%{hovertext}</b><br>" +
            "Total mechanisms (0–8): %{customdata[0]}<br><br>" +
            "%{customdata[1]}<extra></extra>",
            customdata=m_plot[["mechanism_type_count", "mechanism_types_list_html"]].values,
        )

    elif map_choice == "VCM project":
        fig_map = px.choropleth(
            m_plot,
            locations="iso3",
            color="vcm_projects_sum",
            hover_name="Country",
        )
        fig_map.update_traces(
            hovertemplate=
            "<b>%{hovertext}</b><br>" +
            "VCM projects (sum): %{customdata[0]}<br><br>" +
            "%{customdata[1]}<extra></extra>",
            customdata=m_plot[["vcm_projects_sum", "mechanism_types_list_html"]].values,
        )

    else:
        pres = (
            f[f["mechanism_type"] == map_choice]
            .groupby("Country")["mechanism_type"]
            .size()
            .reset_index(name="present")
        )
        pres["present"] = 1

        m_plot2 = m_plot.merge(pres[["Country", "present"]], on="Country", how="left")
        m_plot2["present"] = m_plot2["present"].fillna(0).astype(int)

        fig_map = px.choropleth(
            m_plot2,
            locations="iso3",
            color="present",
            hover_name="Country",
        )
        fig_map.update_coloraxes(cmin=0, cmax=1)
        fig_map.update_traces(
            hovertemplate=
            "<b>%{hovertext}</b><br>" +
            f"{map_choice} present: %{{customdata[0]}}<br><br>" +
            "%{customdata[1]}<extra></extra>",
            customdata=m_plot2[["present", "mechanism_types_list_html"]].values,
        )

    # ===== MAP CLICK CAPTURE (two strategies) =====
    # Strategy A (new Streamlit): on_select selection events
    # Strategy B (most reliable): streamlit-plotly-events if installed
    click_mode = st.caption("Tip: Click a country (or use box select) to update the Country panel ➜")

    clicked_country = None

    # Try B first if available (best single-click behavior)
    try:
        from streamlit_plotly_events import plotly_events  # type: ignore
        selected = plotly_events(
            fig_map,
            click_event=True,
            select_event=False,
            hover_event=False,
            key="map_evt",
        )
        if selected:
            clicked_country = selected[0].get("hovertext")
            if clicked_country:
                st.session_state.selected_country = clicked_country
                st.session_state.selected_mechanism = None
                st.rerun()
    except Exception:
        # Fallback A: native event selection (works with click/box/lasso in newer versions)
        event = st.plotly_chart(
            fig_map,
            use_container_width=True,
            key="map_choropleth",
            on_select="rerun",
        )
        try:
            pts = event["selection"]["points"]
            if pts:
                clicked_country = pts[0].get("hovertext")
                if clicked_country:
                    st.session_state.selected_country = clicked_country
                    st.session_state.selected_mechanism = None
        except Exception:
            pass

# ===== RIGHT: COUNTRY PANEL =====
with right:
    st.subheader("Country panel")

    countries_all = safe_unique_sorted(wide_view["Country"])
    if not countries_all:
        st.info("No countries in view (check your filters).")
        st.stop()

    # Default: last clicked (if still in view) else first
    default_country = st.session_state.selected_country if st.session_state.selected_country in countries_all else countries_all[0]
    sel = st.selectbox(
        "Selected country",
        countries_all,
        index=countries_all.index(default_country),
        key="country_selectbox",
    )
    st.session_state.selected_country = sel

    cf = long[long["Country"] == sel].copy()
    region = cf["Region"].iloc[0] if len(cf) else "—"
    st.caption(f"Region: **{region}**")

    # Country-level KPIs
    present_types = set(cf["mechanism_type"].dropna().unique())
    c1, c2 = st.columns(2)
    c1.metric("Mechanism types", len(present_types))
    vcm_sum_sel = cf.loc[cf["mechanism_type"] == "VCM project", "vcm_projects"].sum(min_count=1)
    c2.metric("VCM projects", 0 if pd.isna(vcm_sum_sel) else int(vcm_sum_sel))

    # Country search (within this country)
    st.divider()
    q_country = st.text_input("Search details (this country)", value="", key="country_search").strip()
    cf_view = cf.copy()
    if q_country:
        cf_view = cf_view[cf_view["mechanism_detail"].str.contains(q_country, case=False, na=False)]

    only_present = st.checkbox("Show only mechanisms present", value=False, key="only_present_mechs")
    mech_show = MECH_LIST if not only_present else [m for m in MECH_LIST if m in present_types]

    st.caption("Mechanisms (click to drill down)")

    # 8 mechanism cards (2 columns)
    cols = st.columns(2, gap="small")
    for i, mech in enumerate(mech_show):
        col = cols[i % 2]
        with col:
            is_on = mech in present_types
            label = f"{mech} {'✅' if is_on else '—'}"
            if st.button(label, use_container_width=True, key=f"mech_btn_{mech}"):
                st.session_state.selected_mechanism = mech

    # Drilldown detail
    st.divider()
    mech_sel = st.session_state.selected_mechanism

    if mech_sel:
        st.subheader(f"Detail: {mech_sel}")
        dfm = cf_view[cf_view["mechanism_type"] == mech_sel].copy()

        if dfm.empty:
            st.info("No detail found under the current country search / filters.")
        else:
            # Deduplicate + sort
            details = sorted({x.strip() for x in dfm["mechanism_detail"].astype(str) if x and x.lower() != "nan"})
            # If this is VCM, also show numeric summary if any
            if mech_sel == "VCM project":
                vcm_sum2 = dfm["vcm_projects"].sum(min_count=1)
                st.metric("VCM projects (sum in this view)", 0 if pd.isna(vcm_sum2) else int(vcm_sum2))

            for d in details:
                st.markdown(f"- {d}")
    else:
        st.info("Click one of the mechanisms above to see details.")

st.divider()

# ---------- Bottom tabs (optional, still useful) ----------
tab1, tab2, tab3 = st.tabs(["Summary charts", "Country profile (classic)", "Data table"])

with tab1:
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Countries by mechanism type")
        by_type = (
            f.groupby("mechanism_type")["Country"].nunique()
            .reset_index(name="countries")
            .sort_values("countries", ascending=False)
        )
       # ===== MAP CLICK HANDLER (LANGKAH 3) =====

from streamlit_plotly_events import plotly_events

# key dibuat unik agar tidak konflik bila Streamlit merender ulang komponen dalam kondisi tertentu
map_key = f"map_evt_{map_choice}"

selected = plotly_events(
    fig_map,
    click_event=True,
    select_event=False,
    hover_event=False,
    key=map_key,
)

if selected:
    iso3 = selected[0].get("location")
    if iso3:
        iso3_to_country = dict(zip(map_df["iso3"], map_df["Country"]))
        if iso3 in iso3_to_country:
            st.session_state.selected_country = iso3_to_country[iso3]
            st.session_state.selected_mechanism = None
            st.rerun()

    with c2:
        st.subheader("Top countries by VCM projects")
        v = f[f["mechanism_type"] == "VCM project"].dropna(subset=["vcm_projects"]).copy()
        if len(v) == 0:
            st.info("No VCM data under the current filters.")
        else:
            top = (
                v.groupby("Country")["vcm_projects"].sum()
                .reset_index()
                .assign(vcm_projects=lambda d: d["vcm_projects"].fillna(0).astype(int))
                .sort_values("vcm_projects", ascending=False)
                .head(20)
            )
            st.plotly_chart(px.bar(top, x="Country", y="vcm_projects"), use_container_width=True, key="bar_vcm")

with tab2:
    st.subheader("Country profile (classic)")
    countries_all = safe_unique_sorted(wide["Country"])
    default_idx = countries_all.index(st.session_state.selected_country) if st.session_state.selected_country in countries_all else 0
    sel2 = st.selectbox("Select a country", countries_all, index=default_idx, key="country_profile_tab")

    cf2 = long[long["Country"] == sel2].copy()
    st.write("Region:", cf2["Region"].iloc[0] if len(cf2) else "—")

    prof = (
        cf2.groupby("mechanism_type")["mechanism_detail"]
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
