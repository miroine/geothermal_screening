from dataclasses import asdict

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import streamlit.components.v1 as components

import benchmarks as bench
import model as m
from concepts_diagram import build_concepts_html
from process_diagram import build_html

st.set_page_config(page_title="Geothermal Opportunity Designer", page_icon="🌋", layout="wide")

PALETTE = dict(hot="#ff5a3c", warm="#ffb347", cold="#4cc9f0", ok="#35d49a", ink="#e7edf7", grid="#243350", bg="#0b1220")

st.markdown(
    """
<style>
  .block-container {padding-top: 1.4rem; max-width: 1350px;}
  .kpi {background:linear-gradient(160deg,#121b2e,#0f1a30); border:1px solid #243350; border-radius:14px; padding:14px 16px;}
  .kpi .l {color:#8fa3c2; font-size:12px; text-transform:uppercase; letter-spacing:.06em;}
  .kpi .v {color:#e7edf7; font-size:26px; font-weight:700; line-height:1.15;}
  .kpi .s {color:#8fa3c2; font-size:12px;}
  .good {color:#35d49a !important;} .bad {color:#ff6b5c !important;} .mid {color:#ffb347 !important;}
  h1, h2, h3 {letter-spacing:-.01em;}
</style>
""",
    unsafe_allow_html=True,
)


def _apply_calibration(het_v: float, skin_v: float):
    """Button callback: push calibrated values into the sidebar sliders."""
    st.session_state["het_slider"] = float(np.clip(round(het_v, 2), 0.2, 1.2))
    st.session_state["skin_slider"] = float(np.clip(round(skin_v, 1), -2.0, 12.0))


def kpi(col, label, value, sub="", cls=""):
    col.markdown(f'<div class="kpi"><div class="l">{label}</div><div class="v {cls}">{value}</div><div class="s">{sub}</div></div>', unsafe_allow_html=True)


def style(fig, h=380, title=None):
    fig.update_layout(template="plotly_dark", height=h, title=title, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=10, r=10, t=50 if title else 20, b=10), font=dict(family="Inter, system-ui"),
                      legend=dict(orientation="h", y=1.12, x=0))
    fig.update_xaxes(gridcolor=PALETTE["grid"], zeroline=False)
    fig.update_yaxes(gridcolor=PALETTE["grid"], zeroline=False)
    return fig


# ---------------------------------------------------------------- sidebar
st.sidebar.title("🌋 Design inputs")
use_case = st.sidebar.radio("Use case", ["District heating", "Power (ORC)"], horizontal=True)

with st.sidebar.expander("Subsurface", expanded=True):
    depth = st.slider("Reservoir depth (m)", 1000, 6000, 3000 if use_case == "District heating" else 4500, 100)
    grad = st.slider("Geothermal gradient (°C/km)", 15.0, 60.0, 30.0, 0.5)
    t_surf = st.slider("Surface temperature (°C)", -5.0, 25.0, 8.0, 0.5)
    perm = st.select_slider("Permeability (mD)", [10, 25, 50, 100, 150, 200, 250, 500, 1000, 2000],
                            200 if use_case == "District heating" else 500)
    thick = st.slider("Net thickness (m)", 20, 300, 80, 5)
    poro = st.slider("Porosity", 0.05, 0.35, 0.18, 0.01)

with st.sidebar.expander("Reservoir physics (advanced)", expanded=False):
    sal = st.slider("Brine salinity (g/L)", 0, 250, 50, 5)
    skin = st.slider("Well skin (damage +, stimulation −)", -2.0, 12.0, 2.0, 0.1, key="skin_slider")
    het = st.slider("Heterogeneity factor", 0.2, 1.2, 0.6, 0.01, key="het_slider",
                    help="Multiplies fluid travel times. 1 = homogeneous layer; lower = channelled flow and earlier cold breakthrough.")
    maxdp = st.slider("Pump head available (bar)", 30, 200, 90, 5,
                      help="Total pressure budget for production + injection + surface. Flow is cut back if the reservoir cannot deliver it.")

with st.sidebar.expander("Wells & plant", expanded=True):
    flow = st.slider("Design production rate (kg/s)", 20, 140, 55 if use_case == "District heating" else 100, 5)
    spacing = st.slider("Well spacing (m)", 500, 2500, 1000, 50)
    t_inj = st.slider("Reinjection temperature (°C)", 20, 90, 40 if use_case == "District heating" else 70, 1)
    ndbl = st.number_input("Number of doublets", 1, 10, 1)
    life = st.slider("Project life (years)", 10, 40, 30)
    avail = st.slider("Availability", 0.70, 0.99, 0.92, 0.01)

with st.sidebar.expander("Economics", expanded=False):
    dcost = st.slider("Drilling cost (€/m at 3 km, rises with depth)", 1500, 9000, 4000, 100)
    wfix = st.slider("Fixed cost per well (€ M)", 0.0, 8.0, 2.0, 0.25) * 1e6
    scapex = st.slider("Surface capex (€/kW, heat basis)", 300, 2000, 900, 50)
    opex = st.slider("Opex (% of capex / yr)", 1.0, 8.0, 3.5, 0.1) / 100
    hp = st.slider("Heat price (€/MWh)", 20, 200, 75)
    pp = st.slider("Power price (€/MWh)", 20, 250, 90)
    disc = st.slider("Discount rate", 0.02, 0.15, 0.07, 0.005)
    tax = st.slider("Corporate tax (%)", 0, 50, 0) / 100
    subs = st.slider("Capex subsidy (%)", 0, 60, 0) / 100
    cprice = st.slider("Carbon price (€/t CO₂)", 0, 250, 80)
    pos = st.slider("Geological chance of success", 0.3, 1.0, 0.75, 0.01)

inp = m.Inputs(surface_temp_c=t_surf, gradient_c_per_km=grad, depth_m=depth, permeability_md=perm, thickness_m=thick,
               porosity=poro, flow_kg_s=flow, well_spacing_m=spacing, reinjection_temp_c=t_inj, n_doublets=int(ndbl),
               use_case=use_case, plant_life_yr=life, availability=avail, drilling_cost_per_m=dcost,
               surface_capex_per_kw=scapex, opex_pct_capex=opex, heat_price_eur_mwh=hp, power_price_eur_mwh=pp,
               discount_rate=disc, subsidy_pct_capex=subs, carbon_price_eur_t=cprice, success_prob=pos,
               salinity_g_l=sal, skin=skin, heterogeneity_factor=het, max_dp_bar=maxdp,
               well_fixed_cost_eur=wfix, tax_rate=tax)


# Streamlit re-runs the whole script on every click, so cache the expensive sweeps.
@st.cache_data(show_spinner=False)
def run_mc(params: dict, n: int):
    return m.monte_carlo(m.Inputs(**params), n)


@st.cache_data(show_spinner=False)
def run_tornado(params: dict):
    return m.tornado(m.Inputs(**params))


@st.cache_data(show_spinner=False)
def run_scans(params: dict):
    p = m.Inputs(**params)
    return m.depth_scan(p), m.flow_scan(p)


params = asdict(inp)
df = m.forecast(inp)
eco = m.economics(inp, df)
t_res = m.reservoir_temp(inp)
t_bt = m.breakthrough_time(inp, eco["eff_flow"])
eff_flow = eco["eff_flow"]
bt_txt = f"~{t_bt:.0f} yr" if t_bt < 100 else ">100 yr"

# ---------------------------------------------------------------- header + KPIs
st.title("Geothermal Opportunity Designer")
st.caption("Screening-level design → forecast → value. Change inputs on the left; everything updates.")

if eco["flow_limited"]:
    st.warning(f"Deliverability-limited: the reservoir and the {maxdp} bar pump budget support only "
               f"{eff_flow:.0f} kg/s of the {flow} kg/s design rate. Higher permeability, thickness, "
               f"lower skin or more pump head would unlock the rest.")
if use_case == "Power (ORC)" and t_res < 110:
    st.warning(f"Reservoir temperature {t_res:.0f} °C is low for ORC power; expect little or no net output. Try deeper or switch to heating.")

c = st.columns(6)
npv_cls = "good" if eco["npv"] > 0 else "bad"
kpi(c[0], "NPV", f"€{eco['npv']/1e6:,.1f} M", f"risked: €{eco['risked_npv']/1e6:,.1f} M", npv_cls)
kpi(c[1], "IRR", f"{eco['irr']*100:.1f} %" if eco["irr"] == eco["irr"] else "n/a", f"hurdle {disc*100:.1f} %", "good" if eco["irr"] == eco["irr"] and eco["irr"] > disc else "bad")
kpi(c[2], "LCOE", f"€{eco['lcoe']:,.0f}/MWh", f"price €{hp if use_case != 'Power (ORC)' else pp}/MWh", "good" if eco["lcoe"] < (hp if use_case != "Power (ORC)" else pp) else "bad")
kpi(c[3], "Capex", f"€{eco['capex']/1e6:,.1f} M", f"{eco['capex']/max(eco['peak_mw'],1e-6)/1e6:.1f} M€/MW")
kpi(c[4], "Initial output", f"{eco['peak_mw']:.1f} MW", "thermal" if use_case != "Power (ORC)" else "net electric")
kpi(c[5], "CO₂ avoided", f"{eco['life_co2_t']/1e3:,.0f} kt", f"payback {eco['payback']:.0f} yr" if eco["payback"] == eco["payback"] else "no payback", "mid")

# ---------------------------------------------------------------- tabs
tab_proc, tab_con, tab_fc, tab_eco, tab_risk, tab_opt, tab_opp, tab_cal, tab_bm = st.tabs(
    ["⚙️ Process", "🎬 Concepts", "📈 Forecast", "💶 Economics", "🎲 Risk", "🧭 Optimise", "🎯 Opportunity", "🧪 Calibrate", "📚 Benchmarks"])

with tab_proc:
    pdat = dict(
        t_res=float(t_res), depth=int(depth), k=int(perm), grad=float(grad), t_inj=float(t_inj), flow=float(eff_flow),
        use_case=use_case, homes=int(eco["homes"]), life_gwh=float(eco["life_mwh"] / 1e3),
        pump_kw=float(eco["pump_kw"]),
        years=[float(x) for x in df["year"].iloc[::4]],
        t_prod=[float(x) for x in df["t_prod_c"].iloc[::4]],
        mw=[float(x) for x in df["useful_mw"].iloc[::4]],
        bt_years=float(min(t_bt, life)),
    )
    components.html(build_html(pdat), height=560, scrolling=False)
    a, b, c3 = st.columns(3)
    a.metric("Reservoir temperature", f"{t_res:.0f} °C")
    b.metric("Thermal breakthrough", bt_txt, help="Time until bottom-hole temperature has dropped 2 % of the way to the reinjection temperature.")
    c3.metric("Pump power", f"{eco['pump_kw']:,.0f} kW", f"{eff_flow:.0f} kg/s delivered")

with tab_con:
    st.caption("Five ways to get heat out of the ground, animated side by side. Temperatures come from your design; "
               "the geometry is schematic, not to scale.")
    cdat = dict(t_res=float(t_res), t_inj=float(t_inj), depth=int(depth), k=int(perm), flow=float(eff_flow),
                use_case=use_case, mw0=float(df["useful_mw"].iloc[0]))
    components.html(build_concepts_html(cdat), height=930, scrolling=False)

with tab_fc:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=df.year, y=df.t_bh_c, name="Bottom-hole temp (°C)", line=dict(color=PALETTE["hot"], width=2, dash="dot")), secondary_y=False)
    fig.add_trace(go.Scatter(x=df.year, y=df.t_prod_c, name="Wellhead temp (°C)", line=dict(color=PALETTE["hot"], width=3)), secondary_y=False)
    fig.add_trace(go.Scatter(x=df.year, y=df.useful_mw, name="Useful output (MW)", fill="tozeroy",
                             line=dict(color=PALETTE["warm"], width=2), fillcolor="rgba(255,179,71,.18)"), secondary_y=True)
    if t_bt < life:
        fig.add_vline(x=t_bt, line_dash="dot", line_color=PALETTE["cold"], annotation_text="thermal breakthrough")
    fig.update_yaxes(title_text="°C", secondary_y=False); fig.update_yaxes(title_text="MW", secondary_y=True)
    st.plotly_chart(style(fig, 420, "Temperature and output forecast"), use_container_width=True)

    col1, col2 = st.columns(2)
    ann = pd.DataFrame({"year": eco["years"], "GWh": eco["energy_mwh"] / 1e3})
    f2 = go.Figure(go.Bar(x=ann.year, y=ann.GWh, marker=dict(color=ann.GWh, colorscale=[[0, "#4cc9f0"], [1, "#ff5a3c"]])))
    col1.plotly_chart(style(f2, 340, "Annual energy (GWh)"), use_container_width=True)
    yy = np.linspace(0, life, 60); dd = np.linspace(0, depth, 60)
    prof = t_surf + grad * dd / 1000
    f3 = go.Figure(go.Scatter(x=prof, y=dd, line=dict(color=PALETTE["hot"], width=3)))
    f3.add_hline(y=depth, line_dash="dot", line_color=PALETTE["warm"], annotation_text=f"reservoir {t_res:.0f} °C")
    f3.update_yaxes(autorange="reversed", title_text="Depth (m)"); f3.update_xaxes(title_text="Temperature (°C)")
    col2.plotly_chart(style(f3, 340, "Geotherm"), use_container_width=True)

with tab_eco:
    cf = eco["cashflow"]; yrs = np.arange(len(cf))
    f = go.Figure()
    f.add_bar(x=yrs, y=cf / 1e6, name="Net cash flow", marker_color=[PALETTE["hot"] if v < 0 else PALETTE["ok"] for v in cf])
    f.add_scatter(x=yrs, y=eco["cumulative"] / 1e6, name="Cumulative", line=dict(color=PALETTE["warm"], width=3))
    f.update_yaxes(title_text="€ M"); f.update_xaxes(title_text="Year")
    st.plotly_chart(style(f, 400, "Cash flow and payback"), use_container_width=True)
    c1, c2 = st.columns(2)
    capex_items = ["Drilling", "Surface plant", "Exploration", "Contingency"]
    vals = [eco["drilling"], eco["surface"], eco["exploration"], eco["contingency"]]
    w = go.Figure(go.Waterfall(x=capex_items + ["Total"], y=[v / 1e6 for v in vals] + [0], measure=["relative"] * 4 + ["total"],
                               connector=dict(line=dict(color=PALETTE["grid"])),
                               increasing=dict(marker=dict(color=PALETTE["warm"])), totals=dict(marker=dict(color=PALETTE["hot"]))))
    c1.plotly_chart(style(w, 340, "Capex build-up (€ M, before subsidy)"), use_container_width=True)
    rv = go.Figure()
    rv.add_bar(x=eco["years"], y=eco["revenue"] / 1e6, name="Revenue", marker_color=PALETTE["ok"])
    rv.add_bar(x=eco["years"], y=-eco["opex"] / 1e6, name="Opex + workovers", marker_color=PALETTE["hot"])
    if tax > 0:
        rv.add_bar(x=eco["years"], y=-eco["tax"] / 1e6, name="Tax", marker_color=PALETTE["warm"])
    rv.update_layout(barmode="relative")
    c2.plotly_chart(style(rv, 340, "Revenue, opex and tax (€ M/yr)"), use_container_width=True)

with tab_risk:
    n = st.select_slider("Monte-Carlo samples", [300, 600, 1000, 1500, 3000], 1000)
    mc = run_mc(params, n)
    p10, p50, p90 = [mc.npv.quantile(q) / 1e6 for q in (0.1, 0.5, 0.9)]
    h = go.Figure(go.Histogram(x=mc.npv / 1e6, nbinsx=50, marker_color=PALETTE["cold"], opacity=.85))
    for v, nm, col in [(p10, "P10", PALETTE["hot"]), (p50, "P50", PALETTE["warm"]), (p90, "P90", PALETTE["ok"])]:
        h.add_vline(x=v, line_dash="dash", line_color=col, annotation_text=f"{nm} {v:,.0f}")
    h.add_vline(x=0, line_color="white")
    h.update_xaxes(title_text="NPV (€ M)")
    st.plotly_chart(style(h, 380, "NPV distribution (geology, cost, price uncertainty + chance of success)"), use_container_width=True)
    r1, r2, r3 = st.columns(3)
    r1.metric("P(NPV > 0)", f"{(mc.npv > 0).mean()*100:.0f} %")
    r2.metric("Expected NPV (EMV)", f"€{mc.npv.mean()/1e6:,.1f} M")
    r3.metric("Dry-hole share", f"{(~mc.success).mean()*100:.0f} %")
    tr = run_tornado(params)
    t = go.Figure()
    t.add_bar(y=tr.driver, x=tr.low / 1e6, orientation="h", name="Low case", marker_color=PALETTE["hot"])
    t.add_bar(y=tr.driver, x=tr.high / 1e6, orientation="h", name="High case", marker_color=PALETTE["ok"])
    t.update_layout(barmode="overlay"); t.update_xaxes(title_text="Δ NPV vs base (€ M)")
    st.plotly_chart(style(t, 400, "What drives value (tornado)"), use_container_width=True)

with tab_opt:
    ds, fs = run_scans(params)
    o1, o2 = st.columns(2)
    f = make_subplots(specs=[[{"secondary_y": True}]])
    f.add_scatter(x=ds.depth_m, y=ds.npv / 1e6, name="NPV (€ M)", line=dict(color=PALETTE["ok"], width=3), secondary_y=False)
    f.add_scatter(x=ds.depth_m, y=ds.t_res_c, name="Reservoir T (°C)", line=dict(color=PALETTE["hot"], dash="dot"), secondary_y=True)
    f.add_vline(x=depth, line_color=PALETTE["warm"], line_dash="dash")
    o1.plotly_chart(style(f, 360, "Depth sweep"), use_container_width=True)
    g = make_subplots(specs=[[{"secondary_y": True}]])
    g.add_scatter(x=fs.flow, y=fs.npv / 1e6, name="NPV (€ M)", line=dict(color=PALETTE["ok"], width=3), secondary_y=False)
    g.add_scatter(x=fs.flow, y=fs.pump_kw, name="Pump power (kW)", line=dict(color=PALETTE["cold"], dash="dot"), secondary_y=True)
    g.add_scatter(x=fs.flow, y=fs.eff_flow, name="Deliverable flow (kg/s)", line=dict(color=PALETTE["warm"], dash="dot"), secondary_y=True)
    g.add_vline(x=flow, line_color=PALETTE["warm"], line_dash="dash")
    o2.plotly_chart(style(g, 360, "Flow-rate sweep"), use_container_width=True)
    bd = ds.loc[ds.npv.idxmax()]; bf = fs.loc[fs.npv.idxmax()]
    st.success(f"Best depth in sweep: **{bd.depth_m:,.0f} m** ({bd.t_res_c:.0f} °C, NPV €{bd.npv/1e6:,.1f} M).  "
               f"Best flow rate: **{bf.flow:.0f} kg/s** (NPV €{bf.npv/1e6:,.1f} M). One variable at a time; combine with care.")

with tab_opp:
    st.subheader("Opportunity sizing")
    gwh_y = eco["life_mwh"] / life / 1e3
    o = st.columns(4)
    o[0].metric("Annual energy (avg)", f"{gwh_y:,.0f} GWh/yr")
    o[1].metric("Households served", f"{eco['homes']:,.0f}")
    o[2].metric("CO₂ avoided (life)", f"{eco['life_co2_t']/1e3:,.0f} kt")
    o[3].metric("Carbon value (life)", f"€{eco['life_co2_t']*cprice/1e6:,.1f} M")
    nd = st.slider("If replicated across N sites (same quality)", 1, 50, 5)
    risked = eco["risked_npv"] * nd / 1e6
    inv = eco["capex"] * nd / 1e6
    q = go.Figure()
    q.add_bar(x=["Capital required", "Risked NPV", "Carbon value"], y=[inv, risked, eco["life_co2_t"] * cprice * nd / 1e6],
              marker_color=[PALETTE["warm"], PALETTE["ok"] if risked > 0 else PALETTE["hot"], PALETTE["cold"]])
    q.update_yaxes(title_text="€ M")
    st.plotly_chart(style(q, 340, f"Portfolio of {nd} site(s)"), use_container_width=True)
    verdict = ("**Attractive**: positive risked NPV and IRR above hurdle."
               if eco["risked_npv"] > 0 and eco["irr"] == eco["irr"] and eco["irr"] > disc
               else "**Marginal / not yet attractive**: improve flow, temperature, cost or price, or add subsidy.")
    st.info(verdict)
    st.download_button("Download annual forecast (CSV)", df.to_csv(index=False), "geothermal_forecast.csv")

with tab_cal:
    st.subheader("Calibrate to field data")
    st.caption("Two parameters cannot be known from first principles: well **skin** (how much flow you really get) and the "
               "**heterogeneity factor** (how early cold water arrives). Enter any test you have (leave 0 or blank when you do not), "
               "see what it implies, and apply it to the design.")
    k1, k2, k3 = st.columns(3)
    with k1:
        st.markdown("**① Well test**")
        wt_q = st.number_input("Test rate (kg/s)", min_value=1.0, value=40.0, step=1.0)
        wt_dd = st.number_input("Production drawdown (bar)", min_value=0.0, value=0.0, step=0.5, help="0 = not measured")
        wt_inj = st.number_input("Injection overpressure (bar)", min_value=0.0, value=0.0, step=0.5, help="0 = not measured")
    with k2:
        st.markdown("**② Tracer test**")
        tr_days = st.number_input("First arrival at producer (days)", min_value=0.0, value=0.0, step=10.0,
                                  help="Time to first detection, not the peak. 0 = no tracer test.")
        tr_q = st.number_input("Flow during the tracer test (kg/s)", min_value=1.0, value=50.0, step=1.0)
    with k3:
        st.markdown("**③ Temperature history**")
        h_q = st.number_input("Flow during the history (kg/s)", min_value=1.0, value=50.0, step=1.0)
    hist_in = pd.DataFrame({"Year": [None] * 6, "Wellhead temp (°C)": [None] * 6}, dtype=float)
    st.caption("Years since start and measured wellhead temperature.")
    hist = st.data_editor(hist_in, num_rows="dynamic", use_container_width=True, key="hist_editor").dropna()

    tracer = dict(days=tr_days, q=tr_q) if tr_days > 0 else None
    welltest = dict(q=wt_q, drawdown_bar=wt_dd or None, injection_bar=wt_inj or None) if (wt_dd > 0 or wt_inj > 0) else None
    history = dict(years=hist["Year"].values, temps=hist["Wellhead temp (°C)"].values, q=h_q) if len(hist) >= 2 else None

    if not (tracer or welltest or history):
        st.info("Enter a well test, a tracer first-arrival time, or at least two temperature readings to calibrate.")
    else:
        cal = m.calibrate(inp, tracer, welltest, history)
        new = cal["inputs"]
        e_new = m.economics(new)
        r = st.columns(4)
        r[0].metric("Heterogeneity factor", f"{new.heterogeneity_factor:.2f}", f"{new.heterogeneity_factor - inp.heterogeneity_factor:+.2f} vs now")
        r[1].metric("Skin", f"{new.skin:.1f}", f"{new.skin - inp.skin:+.1f} vs now")
        r[2].metric("Deliverable flow", f"{e_new['eff_flow']:.0f} kg/s", f"{e_new['eff_flow'] - eff_flow:+.0f} vs now")
        r[3].metric("NPV", f"€{e_new['npv']/1e6:,.1f} M", f"{(e_new['npv'] - eco['npv'])/1e6:+.1f} M vs now")

        rows = []
        for k, v in cal["het_estimates"].items():
            rows.append({"Parameter": "Heterogeneity", "From": k, "Value": round(v, 3)})
        sf = cal.get("skin_fit")
        if sf:
            for k, lab in (("skin_prod", "production well test"), ("skin_inj", "injection well test")):
                if sf.get(k) is not None:
                    rows.append({"Parameter": "Skin", "From": lab, "Value": round(sf[k], 2)})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        if "history_fit" in cal:
            hf = cal["history_fit"]
            st.caption(f"Temperature-history fit: RMSE {hf['rmse']:.2f} K; heterogeneity consistent with the data between "
                       f"{hf['het_lo']:.2f} and {hf['het_hi']:.2f}.")
        for note in cal["notes"]:
            st.warning(note)

        if history:
            yy = np.linspace(0, max(float(np.nanmax(hist["Year"])) * 1.5, 10.0), 80)
            q_h = float(h_q)
            _, t_now = m._temps(inp, yy, q_h)
            _, t_cal = m._temps(new, yy, q_h)
            fc = go.Figure()
            fc.add_scatter(x=yy, y=t_now, name="Current design", line=dict(color=PALETTE["cold"], dash="dot"))
            fc.add_scatter(x=yy, y=t_cal, name="Calibrated", line=dict(color=PALETTE["hot"], width=3))
            fc.add_scatter(x=hist["Year"], y=hist["Wellhead temp (°C)"], name="Observed", mode="markers",
                           marker=dict(color=PALETTE["warm"], size=10))
            fc.update_xaxes(title_text="Year"); fc.update_yaxes(title_text="Wellhead temperature (°C)")
            st.plotly_chart(style(fc, 340, "Observed vs modelled production temperature"), use_container_width=True)

        st.button("Apply calibrated values to the design", type="primary", on_click=_apply_calibration,
                  args=(new.heterogeneity_factor, new.skin))
        if not (0.2 <= new.heterogeneity_factor <= 1.2 and -2.0 <= new.skin <= 12.0):
            st.caption("Values outside the slider range will be clipped when applied.")
        st.caption("Applying updates the sidebar sliders, so every tab (including the Monte Carlo) uses the calibrated values.")

with tab_bm:
    st.subheader("Benchmark against known projects")
    st.caption("Figures read from the linked sources (looked up 31 Oct 2026); a blank means the source did not report it. "
               "**Planned** = design or target figure, **Older** = from an older table, verify before relying on it.")
    bm = bench.benchmark_df()
    all_cats = sorted(bm["category"].unique())
    cats = st.multiselect("Project types", all_cats, default=all_cats)
    view = bm[bm["category"].isin(cats)]
    st.dataframe(
        view[["project", "country", "category", "use", "year", "depth_m", "t_c", "flow_kg_s", "spacing_km",
              "mwe", "mwth", "capex_m", "capex_ccy", "capex_per_mw_m", "basis", "notes", "source_url",
              "source2_url"]],
        hide_index=True, use_container_width=True,
        column_config={
            "project": "Project", "country": "Country", "category": "Type", "use": "Use",
            "year": st.column_config.NumberColumn("Year", format="%d"),
            "depth_m": st.column_config.NumberColumn("Depth (m)", format="%d"),
            "t_c": st.column_config.NumberColumn("Temp (°C)", format="%.0f"),
            "flow_kg_s": st.column_config.NumberColumn("Flow (kg/s)", format="%.1f"),
            "spacing_km": st.column_config.NumberColumn("Spacing (km)", format="%.1f"),
            "mwe": st.column_config.NumberColumn("MWe", format="%.2f"),
            "mwth": st.column_config.NumberColumn("MWth", format="%.1f"),
            "capex_m": st.column_config.NumberColumn("Capex (M)", format="%.0f"),
            "capex_ccy": "Ccy",
            "capex_per_mw_m": st.column_config.NumberColumn("Capex / MW (M)", format="%.2f"),
            "basis": "Basis", "notes": st.column_config.TextColumn("Notes", width="large"),
            "source_url": st.column_config.LinkColumn("Source", display_text="open"),
            "source2_url": st.column_config.LinkColumn("Source 2", display_text="open"),
        })

    # ---- your design vs the field
    d_t = float(df["t_prod_c"].iloc[0]); d_mwth = float(df["thermal_mw"].iloc[0])
    d_mwe = float(eco["peak_mw"]) if use_case == "Power (ORC)" else None
    st.markdown("#### Where your design sits")
    p1, p2 = st.columns(2)
    ft = view.dropna(subset=["depth_m", "t_c"])
    f1 = go.Figure()
    for cat, g in ft.groupby("category"):
        f1.add_scatter(x=g["depth_m"], y=g["t_c"], mode="markers+text", text=g["project"], textposition="top center",
                       name=cat, marker=dict(size=12), textfont=dict(size=10))
    f1.add_scatter(x=[depth], y=[d_t], mode="markers+text", text=["Your design"], textposition="bottom center", name="Your design",
                   marker=dict(size=18, symbol="star", color=PALETTE["warm"], line=dict(color="white", width=1)))
    f1.update_xaxes(title_text="Depth (m)"); f1.update_yaxes(title_text="Production temperature (°C)")
    p1.plotly_chart(style(f1, 380, "Depth vs temperature"), use_container_width=True)

    basis_pick = p2.radio("Capacity basis", ["Thermal (MWth)", "Electric (MWe)"], horizontal=True)
    cap_col, d_cap = ("mwth", d_mwth) if basis_pick.startswith("Thermal") else ("mwe", d_mwe)
    fc2 = view.dropna(subset=["flow_kg_s", cap_col])
    f2 = go.Figure()
    for cat, g in fc2.groupby("category"):
        f2.add_scatter(x=g["flow_kg_s"], y=g[cap_col], mode="markers+text", text=g["project"], textposition="top center",
                       name=cat, marker=dict(size=12), textfont=dict(size=10))
    if d_cap is not None:
        f2.add_scatter(x=[eff_flow], y=[d_cap], mode="markers+text", text=["Your design"], textposition="bottom center",
                       name="Your design", marker=dict(size=18, symbol="star", color=PALETTE["warm"], line=dict(color="white", width=1)))
    f2.update_xaxes(title_text="Flow (kg/s)", type="log"); f2.update_yaxes(title_text=basis_pick, type="log")
    p2.plotly_chart(style(f2, 340, "Flow vs capacity"), use_container_width=True)
    if d_cap is None:
        p2.caption("Your design is a heating case, so it has no electric output to plot.")

    spec = view.dropna(subset=["mwth_per_kg_s"])[["project", "mwth_per_kg_s"]]
    spec = pd.concat([spec, pd.DataFrame({"project": ["Your design"], "mwth_per_kg_s": [d_mwth / max(eff_flow, 1e-9)]})])
    spec = spec.sort_values("mwth_per_kg_s")
    f3 = go.Figure(go.Bar(x=spec["mwth_per_kg_s"], y=spec["project"], orientation="h",
                          marker_color=[PALETTE["warm"] if p == "Your design" else PALETTE["cold"] for p in spec["project"]]))
    f3.update_xaxes(title_text="MWth per kg/s of brine (larger = more heat per unit of flow)")
    st.plotly_chart(style(f3, 300, "Specific thermal output"), use_container_width=True)

    # ---- does the model reproduce reported plants?
    st.markdown("#### Does the model reproduce reported plants?")
    qual = bm[bm["t_kind"].fillna("").str.startswith("production")].dropna(subset=["t_c", "flow_kg_s", "mwe"])
    cols = st.columns(max(len(qual), 1))
    tmap = {}
    for col, (_, r) in zip(cols, qual.iterrows()):
        tmap[r["project"]] = col.number_input(f"{r['project']}: assumed reinjection temp (°C)", 20.0, 120.0, 70.0, 5.0,
                                              help="Not reported in these sources, so it is an assumption you can vary.")
    chk = bench.model_check(bm, tmap, inp)
    if len(chk):
        st.dataframe(chk, hide_index=True, use_container_width=True, column_config={
            "project": "Project", "t_prod_c": st.column_config.NumberColumn("Prod. temp (°C)", format="%.0f"),
            "flow_kg_s": st.column_config.NumberColumn("Flow (kg/s)", format="%.1f"),
            "assumed_t_inj_c": st.column_config.NumberColumn("Assumed T inj (°C)", format="%.0f"),
            "thermal_mw": st.column_config.NumberColumn("Thermal (MW)", format="%.1f"),
            "efficiency": st.column_config.NumberColumn("ORC efficiency", format="%.3f"),
            "model_mwe": st.column_config.NumberColumn("Model MWe", format="%.2f"),
            "reported_mwe": st.column_config.NumberColumn("Reported MWe", format="%.2f"),
            "error_pct": st.column_config.NumberColumn("Error (%)", format="%+.0f"),
        })
    st.caption("Model output = thermal power × ORC efficiency × (1 − parasitics), before pumping. Only two projects have a reported "
               "production temperature, flow and electric output, so this is a plausibility check, not a validation. "
               "Project Red's 3.5 MW assumes a supercritical ORC and its temperature is the maximum seen in the test.")

st.caption("Screening model with simplified physics (volumetric thermal breakthrough, Darcy productivity, ORC Carnot fraction). "
           "Calibrate against your own simulator/well data before using for decisions.")
