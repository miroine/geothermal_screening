"""Sanity tests for the geothermal model. Run:  python test_model.py   (or pytest)."""
import math
from dataclasses import replace

import numpy as np

import model as m
from model import Inputs

BASE = Inputs(permeability_md=200, flow_kg_s=55, well_spacing_m=1000)


def test_doublet_straight_streamline_matches_classic_formula():
    # t_min = pi * phi * h * d^2 / (3 Q)  <=>  I(theta->0) = 4/3
    assert abs(m._doublet_I()[0] - 4 / 3) < 0.005


def test_doublet_travel_times_increase_with_leaving_angle():
    I = m._doublet_I()
    assert np.all(np.diff(I) > 0)


def test_thermal_decline_is_monotonic_and_bounded():
    t = np.linspace(0, 80, 321)
    d = m.bottomhole_drop_fraction(BASE, t, 55.0)
    assert d[0] == 0.0
    assert np.all(np.diff(d) >= -1e-12)
    assert d.max() <= 1.0


def test_wider_spacing_delays_breakthrough_and_more_flow_hastens_it():
    assert m.breakthrough_time(replace(BASE, well_spacing_m=1400)) > m.breakthrough_time(BASE)
    assert m.breakthrough_time(replace(BASE, flow_kg_s=40)) > m.breakthrough_time(BASE)


def test_breakthrough_scales_with_spacing_squared():
    # without conduction effects the direct streamline front arrival scales with d^2;
    # the 2 % criterion makes it roughly proportional too
    r = m.breakthrough_time(replace(BASE, well_spacing_m=1400)) / m.breakthrough_time(BASE)
    assert 1.5 < r < 2.4   # (1.4)^2 = 1.96


def test_wellhead_temperature_limits():
    T_res = m.reservoir_temp(BASE)
    wh = float(m.wellhead_temp(BASE, T_res, 55.0, 5.0))
    assert BASE.surface_temp_c < wh < T_res
    # higher flow -> hotter wellhead, and tends to reservoir temperature
    assert float(m.wellhead_temp(BASE, T_res, 150.0, 5.0)) > wh
    assert T_res - float(m.wellhead_temp(BASE, T_res, 1e5, 5.0)) < 0.5
    # colder bottom hole -> colder wellhead
    assert float(m.wellhead_temp(BASE, T_res - 10, 55.0, 5.0)) < wh


def test_property_correlations():
    assert abs(m.water_density(20) - 998.2) < 0.3
    assert abs(m.water_density(90) - 965.3) < 0.6
    assert abs(m.brine_viscosity(20, 0) - 1.0e-3) < 0.03e-3
    assert m.brine_viscosity(90, 0) < 0.4e-3


def test_effective_flow_respects_pump_head_budget():
    # plenty of kh: design flow is delivered
    assert m.effective_flow(replace(BASE, permeability_md=2000)) == 55.0
    # tight rock: flow is cut and the head budget is (almost exactly) used
    tight = replace(BASE, permeability_md=20, flow_kg_s=120)
    q = m.effective_flow(tight)
    assert q < 120
    assert abs(m._dp_total_bar(tight, q) - tight.max_dp_bar) < 0.5
    # lower permeability never increases deliverable flow
    assert m.effective_flow(replace(tight, permeability_md=10)) <= q


def test_pump_power_increases_with_flow():
    big = replace(BASE, permeability_md=2000)
    assert m.pump_power_kw(big, 80.0) > m.pump_power_kw(big, 40.0)


def test_heat_energy_balance_first_year():
    df = m.forecast(BASE)
    q = df.attrs["flow_kg_s"]
    mw = q * m.brine_cp(BASE.salinity_g_l) * (df.t_prod_c.iloc[0] - BASE.reinjection_temp_c) / 1e6
    assert abs(df.thermal_mw.iloc[0] - mw) < 1e-9
    assert abs(df.useful_mw.iloc[0] - mw * (1 - BASE.heat_cop_loss)) < 1e-9


def test_orc_efficiency_below_carnot_and_zero_when_cold():
    o = replace(BASE, use_case="Power (ORC)", reinjection_temp_c=70)
    for T in (110.0, 140.0, 180.0):
        eta = float(m.orc_efficiency(T, o))
        carnot = 1 - (o.surface_temp_c + 12 + 273.15) / (T + 273.15)
        assert 0 <= eta < carnot
    assert float(m.orc_efficiency(60.0, o)) == 0.0   # brine colder than reinjection
    assert float(m.orc_efficiency(150.0, o)) > float(m.orc_efficiency(120.0, o))


def test_economics_matches_independent_npv():
    e = m.economics(BASE)
    cf = e["cashflow"]
    npv = sum(c / (1 + BASE.discount_rate) ** k for k, c in enumerate(cf))
    assert abs(npv - e["npv"]) < 1.0
    assert abs(sum([e["drilling"], e["surface"], e["exploration"], e["contingency"]]) - e["capex"]) < 1.0
    assert abs(cf[0] + e["capex"]) < 1.0
    if e["irr"] == e["irr"]:
        irr_npv = sum(c / (1 + e["irr"]) ** k for k, c in enumerate(cf))
        assert abs(irr_npv) < 1e3


def test_economics_monotonicity():
    base = m.economics(BASE)["npv"]
    assert m.economics(replace(BASE, heat_price_eur_mwh=90))["npv"] > base
    assert m.economics(replace(BASE, drilling_cost_per_m=5000))["npv"] < base
    assert m.economics(replace(BASE, discount_rate=0.10))["npv"] < base
    assert m.economics(replace(BASE, subsidy_pct_capex=0.3))["npv"] > base


def test_tax_reduces_npv_and_never_goes_negative():
    pre = m.economics(BASE)
    post = m.economics(replace(BASE, tax_rate=0.25))
    assert post["npv"] < pre["npv"]
    assert np.all(post["tax"] >= 0)
    assert abs(post["annual_cash"].sum() - (pre["annual_cash"].sum() - post["tax"].sum())) < 1.0


def test_workover_cost_is_charged_on_interval():
    e = m.economics(replace(BASE, workover_interval_yr=5))
    yrs = e["years"][e["workover"] > 0]
    assert list(yrs) == [5, 10, 15, 20, 25]


def test_dry_hole_risk_lowers_value():
    e = m.economics(BASE)
    assert e["risked_npv"] < e["npv"] or e["npv"] < -e["dry_hole_loss"]
    certain = m.economics(replace(BASE, success_prob=1.0))
    assert abs(certain["risked_npv"] - certain["npv"]) < 1.0


def test_depth_scaled_drilling_cost():
    assert m.well_cost(replace(BASE, depth_m=5000)) > m.well_cost(BASE)
    per_m_3k = (m.well_cost(BASE) - BASE.well_fixed_cost_eur) / (3000 * BASE.md_tvd_ratio)
    assert abs(per_m_3k - BASE.drilling_cost_per_m) < 1e-6


def test_monte_carlo_reproducible_and_success_rate():
    a = m.monte_carlo(BASE, n=200, seed=3)
    b = m.monte_carlo(BASE, n=200, seed=3)
    assert a["npv"].equals(b["npv"])
    assert abs(a["success"].mean() - BASE.success_prob) < 0.1
    assert a.loc[~a["success"], "npv"].nunique() >= 1


def test_tornado_and_scans_run():
    t = m.tornado(BASE)
    assert len(t) >= 9 and (t["swing"] >= 0).all()
    assert len(m.depth_scan(BASE)) > 10
    fs = m.flow_scan(BASE)
    assert (fs["eff_flow"] <= fs["flow"] + 1e-9).all()


def test_skin_fit_round_trips():
    truth = replace(BASE, skin=6.0)
    q = 40.0
    dd = m._hydraulics(truth, q)["drawdown"] / 1e5
    inj = m._hydraulics(truth, q)["injection"] / 1e5
    assert abs(m.fit_skin(BASE, q, drawdown_bar=dd)["skin"] - 6.0) < 1e-6
    assert abs(m.fit_skin(BASE, q, injection_bar=inj)["skin"] - 6.0) < 1e-6
    both = m.fit_skin(BASE, q, dd, inj)
    assert abs(both["skin"] - 6.0) < 1e-6


def test_tracer_fit_round_trips():
    truth = replace(BASE, heterogeneity_factor=0.45)
    q = 50.0
    rho = m.brine_density(m.reservoir_temp(truth), truth.salinity_g_l)
    tau_days = (truth.heterogeneity_factor * math.pi * truth.porosity * truth.thickness_m
                * truth.well_spacing_m ** 2 * m._doublet_I()[0] / (4 * q / rho)) / 86400
    assert abs(m.fit_heterogeneity_tracer(BASE, tau_days, q) - 0.45) < 1e-6
    assert 100 < tau_days < 3000   # a plausible tracer first-arrival time


def test_temperature_history_fit_recovers_truth_and_brackets_it():
    tight = replace(BASE, well_spacing_m=600)
    truth = replace(tight, heterogeneity_factor=0.35)
    yrs = np.arange(1, 21, 2.0)
    q = m.effective_flow(truth)
    _, obs = m._temps(truth, yrs, q)
    fit = m.fit_heterogeneity_history(tight, yrs, obs, q)
    assert abs(fit["het"] - 0.35) < 0.03
    assert fit["rmse"] < 0.05
    assert fit["het_lo"] <= 0.35 <= fit["het_hi"]


def test_flat_history_gives_only_a_lower_bound():
    yrs = np.arange(1, 11, 1.0)
    q = m.effective_flow(BASE)
    _, obs = m._temps(replace(BASE, heterogeneity_factor=2.0), yrs, q)   # no decline in 10 y
    fit = m.fit_heterogeneity_history(BASE, yrs, obs, q)
    assert fit["het_hi"] >= 1.8


def test_calibrate_combines_sources_and_changes_economics():
    cal = m.calibrate(BASE, tracer=dict(days=500, q=50.0), welltest=dict(q=40.0, drawdown_bar=20.0))
    assert set(cal["het_estimates"]) == {"tracer"}
    assert cal["inputs"].heterogeneity_factor == cal["heterogeneity_factor"]
    assert -2.0 <= cal["skin"] <= 15.0
    assert m.economics(cal["inputs"])["npv"] != m.economics(BASE)["npv"]
    untouched = m.calibrate(BASE)
    assert untouched["inputs"] == BASE


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for n, f in tests:
        try:
            f()
            print(f"PASS  {n}")
        except Exception as ex:   # noqa: BLE001
            failed += 1
            print(f"FAIL  {n}: {type(ex).__name__}: {ex}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
