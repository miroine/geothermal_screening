"""Geothermal doublet physics + techno-economic model (screening level).

Physics, in the order the heat travels:

1. Reservoir: Darcy flow between an injector and a producer (a "doublet").
   The exact analytical streamlines of a doublet are circles through both wells;
   travel time along each is integrated once (dimensionless, cached). The thermal
   front on each streamline lags the fluid by the heat-capacity ratio, and heat
   conduction from the over/underburden smooths its arrival (Lauwerier solution).
   Production temperature = flow-weighted average over all streamlines.
2. Wellbore: Ramey (1962) heat loss on the way up, depth/flow/time dependent.
3. Hydraulics: Darcy drawdown and injection overpressure with temperature- and
   salinity-dependent viscosity, pipe friction, density (buoyancy) head. Flow is
   limited by the available pump head (deliverability).
4. Plant: district heating, or ORC power (Carnot-fraction on brine inlet temperature).
5. Economics: depth-scaled drilling cost, workovers, tax with depreciation and
   loss carry-forward, NPV / IRR / LCOE / payback, dry-hole risk.

All units SI unless the name says otherwise. It is a screening tool, not a
replacement for a reservoir simulator.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.special import erfc

# ---- Constants ---------------------------------------------------------------
G = 9.81
SECS_YEAR = 3.15576e7
LAM_R = 2.5                    # W/m/K rock + confining-bed conductivity
RHO_CP_R = 2.5e6               # J/m3/K rock volumetric heat capacity
ALPHA_R = LAM_R / RHO_CP_R     # m2/s thermal diffusivity
R_WELL = 0.12                  # m, outer radius for Ramey heat loss / reservoir wellbore
ORC_PINCH_K = 10.0             # K, evaporator pinch
ORC_APPROACH_K = 12.0          # K, condenser (air cooled) over ambient
ORC_PARASITIC = 0.08           # fraction of gross power (fans, feed pump)
SURFACE_DP_PA = 3.0e5          # surface piping + heat exchanger loss
DESIGN_VELOCITY = 2.0          # m/s, well tubular sizing


@dataclass
class Inputs:
    # Subsurface
    surface_temp_c: float = 8.0
    gradient_c_per_km: float = 30.0
    depth_m: float = 3000.0               # reservoir depth (TVD)
    permeability_md: float = 150.0
    thickness_m: float = 80.0
    porosity: float = 0.18
    salinity_g_l: float = 50.0            # brine salinity (density, viscosity, heat capacity)
    skin: float = 2.0                     # near-well damage (dimensionless)
    heterogeneity_factor: float = 0.6     # travel-time multiplier: 1 = homogeneous, <1 = channelled
    # Wells
    flow_kg_s: float = 60.0               # design production rate per doublet
    well_spacing_m: float = 1200.0
    reinjection_temp_c: float = 40.0
    n_doublets: int = 1
    pump_eff: float = 0.60
    max_dp_bar: float = 90.0              # total pump head available (prod + inj + surface)
    md_tvd_ratio: float = 1.15            # measured / true vertical depth
    # Plant
    use_case: str = "District heating"    # or "Power (ORC)"
    plant_life_yr: int = 30
    availability: float = 0.92
    orc_efficiency_max_frac: float = 0.55  # second-law efficiency of the ORC
    heat_cop_loss: float = 0.05            # surface heat losses
    # Economics (EUR)
    drilling_cost_per_m: float = 4000.0     # at 3 km reference depth, scales with depth^0.6
    well_fixed_cost_eur: float = 2.0e6      # rig mobilisation, wellhead, completion, testing
    surface_capex_per_kw: float = 900.0     # heat; power uses x3.5
    opex_pct_capex: float = 0.035
    workover_cost_eur: float = 0.5e6        # pump replacement per producer
    workover_interval_yr: int = 6
    heat_price_eur_mwh: float = 75.0
    power_price_eur_mwh: float = 90.0
    discount_rate: float = 0.07
    tax_rate: float = 0.0                   # 0 = pre-tax
    depreciation_years: int = 10
    carbon_price_eur_t: float = 80.0
    displaced_gas_kg_co2_mwh: float = 200.0
    displaced_grid_kg_co2_mwh: float = 250.0
    subsidy_pct_capex: float = 0.0
    # Uncertainty
    success_prob: float = 0.75


# ---- Brine properties --------------------------------------------------------
def water_density(t_c: float) -> float:
    """Kell (1975), 0-150 C, kg/m3."""
    t = float(t_c)
    num = (999.83952 + 16.945176 * t - 7.9870401e-3 * t ** 2 - 46.170461e-6 * t ** 3
           + 105.56302e-9 * t ** 4 - 280.54253e-12 * t ** 5)
    return num / (1.0 + 16.879850e-3 * t)


def brine_density(t_c: float, sal_g_l: float) -> float:
    return water_density(t_c) + 0.70 * sal_g_l


def brine_viscosity(t_c: float, sal_g_l: float) -> float:
    """Pa.s. Vogel equation for water times a mild salinity factor."""
    mu = 2.414e-5 * 10.0 ** (247.8 / (t_c + 273.15 - 140.0))
    return mu * (1.0 + 0.0015 * sal_g_l)


def brine_cp(sal_g_l: float) -> float:
    return 4180.0 - 3.7 * sal_g_l


def reservoir_temp(i: Inputs) -> float:
    return i.surface_temp_c + i.gradient_c_per_km * i.depth_m / 1000.0


# ---- Wellbore (Ramey) -------------------------------------------------------
def wellhead_temp(i: Inputs, t_bh, m_dot: float, t_years):
    """Producing-well wellhead temperature (C).

    t_bh: bottom-hole temperature (scalar or array), t_years: time (same shape or scalar).
    Ramey (1962) relaxation-distance solution with a time function for the formation.
    """
    g = i.gradient_c_per_km / 1000.0
    L = i.depth_m
    t_s = np.maximum(np.asarray(t_years, dtype=float), 0.05) * SECS_YEAR
    f = np.maximum(np.log(2.0 * np.sqrt(ALPHA_R * t_s) / R_WELL) - 0.29, 0.5)
    A = m_dot * brine_cp(i.salinity_g_l) * f / (2.0 * np.pi * LAM_R)   # relaxation distance, m
    ex = np.exp(-L / A)
    return i.surface_temp_c + g * A * (1.0 - ex) - (reservoir_temp(i) - np.asarray(t_bh, dtype=float)) * ex


# ---- Hydraulics ------------------------------------------------------------
def _hydraulics(i: Inputs, q: float) -> dict:
    """Pressure components (Pa) for a doublet producing q kg/s."""
    sal = i.salinity_g_l
    T_res = reservoir_temp(i)
    L = i.depth_m
    L_md = L * i.md_tvd_ratio
    rho_r = brine_density(T_res, sal)
    q_vol = q / rho_r
    # injected water warms only slightly on its way down (travel time ~ tens of minutes)
    T_inj_eff = i.reinjection_temp_c + 0.20 * (T_res - i.reinjection_temp_c)
    rho_i = brine_density(T_inj_eff, sal)
    re = max(0.5 * i.well_spacing_m, 50.0)
    ln_term = math.log(re / R_WELL) + i.skin
    kh = i.permeability_md * 9.869233e-16 * i.thickness_m
    dp_dd = q_vol * brine_viscosity(T_res, sal) * ln_term / (2.0 * math.pi * kh)
    dp_inj = (q / rho_i) * brine_viscosity(T_inj_eff, sal) * ln_term / (2.0 * math.pi * kh)
    # friction (Darcy-Weisbach, f=0.02) in tubulars sized for ~2 m/s
    D = min(max(math.sqrt(4.0 * q_vol / (math.pi * DESIGN_VELOCITY)), 0.15), 0.30)
    v = 4.0 * q_vol / (math.pi * D ** 2)
    T_wh0 = float(wellhead_temp(i, T_res, q, 1.0))
    rho_col = brine_density(0.5 * (T_wh0 + T_res), sal)
    fr_p = 0.02 * (L_md / D) * rho_col * v ** 2 / 2.0
    fr_i = 0.02 * (L_md / D) * rho_i * v ** 2 / 2.0
    # static (buoyancy) head: hot producer column and warm injector column are lighter
    # than the formation's hydrostatic column
    rho_ref = brine_density(0.5 * (i.surface_temp_c + T_res), sal)
    static_p = max(0.0, rho_ref - rho_col) * G * L
    rho_icol = brine_density(i.reinjection_temp_c + 0.15 * (T_res - i.reinjection_temp_c), sal)
    static_i = max(0.0, rho_ref - rho_icol) * G * L
    total = dp_dd + dp_inj + fr_p + fr_i + SURFACE_DP_PA + static_p + static_i
    return dict(drawdown=dp_dd, injection=dp_inj, friction=fr_p + fr_i, surface=SURFACE_DP_PA,
                static=static_p + static_i, total=total, rho_col=rho_col, q_vol=q_vol)


def _dp_total_bar(i: Inputs, q: float) -> float:
    return _hydraulics(i, q)["total"] / 1e5


def effective_flow(i: Inputs) -> float:
    """Design flow, reduced if the pump-head budget cannot deliver it (kg/s per doublet)."""
    q0 = i.flow_kg_s
    if _dp_total_bar(i, q0) <= i.max_dp_bar:
        return q0
    lo, hi = 2.0, q0
    if _dp_total_bar(i, lo) >= i.max_dp_bar:
        return lo
    for _ in range(20):
        mid = 0.5 * (lo + hi)
        if _dp_total_bar(i, mid) > i.max_dp_bar:
            hi = mid
        else:
            lo = mid
    return lo


def pump_power_kw(i: Inputs, q: float | None = None) -> float:
    """Electrical pumping power for one doublet (kW)."""
    if q is None:
        q = effective_flow(i)
    h = _hydraulics(i, q)
    q_surface = q / h["rho_col"]
    return h["total"] * q_surface / i.pump_eff / 1e3


def well_productivity_index(i: Inputs) -> float:
    """Production-well PI in kg/s per bar of drawdown."""
    sal = i.salinity_g_l
    T_res = reservoir_temp(i)
    re = max(0.5 * i.well_spacing_m, 50.0)
    kh = i.permeability_md * 9.869233e-16 * i.thickness_m
    pi_vol = 2.0 * math.pi * kh / (brine_viscosity(T_res, sal) * (math.log(re / R_WELL) + i.skin))
    return pi_vol * brine_density(T_res, sal) * 1e5


# ---- Doublet thermal model --------------------------------------------------
_N_STREAM = 160


@lru_cache(maxsize=1)
def _doublet_I() -> np.ndarray:
    """Dimensionless travel-time integral I(theta) for streamlines of a doublet.

    Wells at (-1,0) and (+1,0). Streamlines are circles through both wells; velocity
    magnitude = Q'/(2 pi) * 2/(r1 r2). With a = d/2, the fluid travel time on a
    streamline is  t = pi * phi * h * a^2 * I / Q  where  I = integral(r1 r2 ds).
    The straight line (theta -> 0) gives I = 4/3, i.e. the classic
    t_min = pi * phi * h * d^2 / (3 Q).
    Each streamline (equal steps in leaving angle theta) carries equal flow.
    """
    theta = (np.arange(_N_STREAM) + 0.5) * np.pi / _N_STREAM
    out = np.empty(_N_STREAM)
    for k, th in enumerate(theta):
        c = -1.0 / math.tan(th)
        R = math.hypot(1.0, c)
        phi_i = math.atan2(-c, -1.0)
        if phi_i < 0.0:
            phi_i += 2.0 * math.pi
        phi_p = math.atan2(-c, 1.0)
        phi = np.linspace(phi_i, phi_p, 1201)
        x = R * np.cos(phi)
        y = c + R * np.sin(phi)
        integrand = np.hypot(x + 1.0, y) * np.hypot(x - 1.0, y) * R
        out[k] = np.sum(0.5 * (integrand[1:] + integrand[:-1]) * np.abs(np.diff(phi)))
    return out


def bottomhole_drop_fraction(i: Inputs, t_years, q: float) -> np.ndarray:
    """Fraction (0..1) of the way the bottom-hole production temperature has fallen
    from reservoir temperature towards the reinjection temperature."""
    I = _doublet_I()
    sal = i.salinity_g_l
    rho = brine_density(reservoir_temp(i), sal)
    rcw = rho * brine_cp(sal)                       # J/m3/K of fluid
    q_vol = q / rho
    phi, h = i.porosity, i.thickness_m
    tau = i.heterogeneity_factor * math.pi * phi * h * i.well_spacing_m ** 2 * I / (4.0 * q_vol)  # s
    retard = (phi * rcw + (1.0 - phi) * RHO_CP_R) / (phi * rcw)
    t_front = retard * tau
    t = np.atleast_1d(np.asarray(t_years, dtype=float)) * SECS_YEAR
    delta = t[:, None] - t_front[None, :]
    arrived = delta > 0.0
    # Lauwerier: erfc( lam * tau / (phi * h * rcw * sqrt(alpha * (t - t_front))) )
    xi = LAM_R * tau[None, :] / (phi * h * rcw * np.sqrt(ALPHA_R * np.where(arrived, delta, 1.0)))
    return np.where(arrived, erfc(xi), 0.0).mean(axis=1)


def _temps(i: Inputs, t_years, q: float):
    t = np.atleast_1d(np.asarray(t_years, dtype=float))
    T_res = reservoir_temp(i)
    drop = bottomhole_drop_fraction(i, t, q)
    t_bh = T_res - drop * (T_res - i.reinjection_temp_c)
    t_wh = wellhead_temp(i, t_bh, q, t)
    return t_bh, t_wh


def breakthrough_time(i: Inputs, q: float | None = None) -> float:
    """Years until bottom-hole temperature has fallen by 2 % of (T_res - T_inj). Capped at 100."""
    if q is None:
        q = effective_flow(i)
    grid = np.arange(0.5, 100.01, 0.5)
    drop = bottomhole_drop_fraction(i, grid, q)
    idx = np.argmax(drop >= 0.02)
    return float(grid[idx]) if drop[idx] >= 0.02 else 100.0


def production_temp(i: Inputs, t_years=0.0, flow: float | None = None, with_bt: bool = True):
    """(wellhead production temperature [C], breakthrough time [yr])."""
    q = effective_flow(i) if flow is None else flow
    _, t_wh = _temps(i, t_years, q)
    t_bt = breakthrough_time(i, q) if with_bt else float("nan")
    if np.ndim(t_years) == 0:
        return float(t_wh[0]), t_bt
    return t_wh, t_bt


# ---- Plant -----------------------------------------------------------------
def orc_efficiency(t_wh, i: Inputs):
    """Gross thermal-to-electric efficiency of the ORC (before parasitics).

    Second-law fraction times the Carnot factor between the brine inlet
    temperature (less evaporator pinch) and the air-cooled condensing
    temperature. Calibrated so ~160 C brine gives ~16-17 %, as in operating
    binary plants.
    """
    t_wh = np.asarray(t_wh, dtype=float)
    t_hot = t_wh - ORC_PINCH_K + 273.15
    t_cold = i.surface_temp_c + ORC_APPROACH_K + 273.15
    eta = i.orc_efficiency_max_frac * (1.0 - t_cold / t_hot)
    return np.where(t_wh - i.reinjection_temp_c > 1.0, np.maximum(eta, 0.0), 0.0)


def forecast(i: Inputs) -> pd.DataFrame:
    q = effective_flow(i)
    years = np.arange(0, i.plant_life_yr + 1, 0.25)
    t_bh, t_wh = _temps(i, years, q)
    cp = brine_cp(i.salinity_g_l)
    mw_th = q * cp * np.maximum(t_wh - i.reinjection_temp_c, 0.0) / 1e6 * i.n_doublets
    pump_kw = pump_power_kw(i, q)
    pump_mw = pump_kw / 1e3 * i.n_doublets
    if i.use_case == "Power (ORC)":
        gross = mw_th * orc_efficiency(t_wh, i)
        useful = np.maximum(gross * (1.0 - ORC_PARASITIC) - pump_mw, 0.0)
    else:
        useful = mw_th * (1.0 - i.heat_cop_loss)
    df = pd.DataFrame({
        "year": years,
        "t_bh_c": t_bh,
        "t_prod_c": t_wh,
        "thermal_mw": mw_th,
        "useful_mw": useful,
        "pump_mw": np.full_like(years, pump_mw),
        "annual_mwh": useful * 8760.0 * i.availability,
    })
    df.attrs["flow_kg_s"] = q
    df.attrs["pump_kw"] = pump_kw * i.n_doublets
    return df


# ---- Economics -------------------------------------------------------------
def well_cost(i: Inputs) -> float:
    per_m = i.drilling_cost_per_m * (i.depth_m / 3000.0) ** 0.6
    return i.depth_m * i.md_tvd_ratio * per_m + i.well_fixed_cost_eur


def economics(i: Inputs, df: pd.DataFrame | None = None) -> dict:
    if df is None:
        df = forecast(i)
    n_wells = 2 * i.n_doublets
    drilling = n_wells * well_cost(i)
    peak_mw = float(df["useful_mw"].iloc[0])
    per_kw = i.surface_capex_per_kw * (3.5 if i.use_case == "Power (ORC)" else 1.0)
    surface = peak_mw * 1000.0 * per_kw
    exploration = 0.06 * drilling
    contingency = 0.15 * (drilling + surface + exploration)
    capex = drilling + surface + exploration + contingency
    capex_net = capex * (1.0 - i.subsidy_pct_capex)

    power = i.use_case == "Power (ORC)"
    price = i.power_price_eur_mwh if power else i.heat_price_eur_mwh
    d = df.assign(y=np.floor(df["year"]).astype(int))
    yr = d[d["y"] < i.plant_life_yr].groupby("y").agg(mwh=("annual_mwh", "mean"), pump_mw=("pump_mw", "mean"))
    years = yr.index.values + 1
    n = len(years)
    energy_mwh = yr["mwh"].values
    pump_mwh = yr["pump_mw"].values * 8760.0 * i.availability
    pump_cost = 0.0 if power else None
    pump_cost = np.zeros(n) if power else pump_mwh * i.power_price_eur_mwh   # ORC nets pumps off output
    revenue = energy_mwh * price
    fixed_opex = capex * i.opex_pct_capex
    opex = fixed_opex + pump_cost
    workover = np.where((years % i.workover_interval_yr == 0) & (years < i.plant_life_yr),
                        i.workover_cost_eur * i.n_doublets, 0.0)
    ebitda = revenue - opex - workover

    # tax: straight-line depreciation of net capex, losses carried forward
    dep_n = max(1, min(i.depreciation_years, n))
    dep = np.zeros(n)
    dep[:dep_n] = capex_net / dep_n
    taxable = ebitda - dep
    tax = np.zeros(n)
    pool = 0.0
    for k in range(n):
        if taxable[k] < 0.0:
            pool += -taxable[k]
        else:
            used = min(pool, taxable[k])
            pool -= used
            tax[k] = i.tax_rate * (taxable[k] - used)
    cash = ebitda - tax

    cf = np.concatenate([[-capex_net], cash])
    t = np.arange(len(cf))
    disc = (1.0 + i.discount_rate) ** t
    npv = float((cf / disc).sum())
    cum = np.cumsum(cf)
    payback = float("nan")
    hit = np.where((cum >= 0.0) & (t > 0))[0]
    if len(hit):
        k = int(hit[0])
        payback = float(k - 1 + (-cum[k - 1]) / cf[k]) if cf[k] > 0 else float(k)
    try:
        from scipy.optimize import brentq
        irr = brentq(lambda r: (cf / (1.0 + r) ** t).sum(), -0.5, 1.0)
    except Exception:
        irr = float("nan")
    disc_energy = (np.concatenate([[0.0], energy_mwh]) / disc).sum()
    disc_cost = capex_net + (np.concatenate([[0.0], opex + workover]) / disc).sum()
    lcoe = disc_cost / disc_energy if disc_energy > 0 else float("nan")

    co2_factor = i.displaced_grid_kg_co2_mwh if power else i.displaced_gas_kg_co2_mwh
    co2_t = energy_mwh * co2_factor / 1000.0
    life_mwh = float(energy_mwh.sum())
    dry_hole_loss = (exploration + well_cost(i)) * (1.0 - i.subsidy_pct_capex)
    risked_npv = i.success_prob * npv - (1.0 - i.success_prob) * dry_hole_loss
    q = df.attrs.get("flow_kg_s", i.flow_kg_s)
    return dict(
        capex=capex_net, drilling=drilling, surface=surface, exploration=exploration,
        contingency=contingency, peak_mw=peak_mw, npv=npv, irr=irr, payback=payback,
        lcoe=lcoe, annual_cash=cash, years=years, cashflow=cf, cumulative=cum,
        revenue=revenue, opex=opex + workover, workover=workover, tax=tax, energy_mwh=energy_mwh,
        life_mwh=life_mwh, life_co2_t=float(co2_t.sum()), risked_npv=risked_npv,
        dry_hole_loss=dry_hole_loss, eff_flow=q, pump_kw=df.attrs.get("pump_kw", float("nan")),
        flow_limited=bool(q < i.flow_kg_s - 1e-6),
        homes=life_mwh / i.plant_life_yr / (4.0 if power else 15.0),
    )


# ---- Risk and sensitivities ------------------------------------------------
def monte_carlo(i: Inputs, n: int = 1500, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    grad = rng.normal(i.gradient_c_per_km, 0.12 * i.gradient_c_per_km, n)
    perm = np.exp(rng.normal(np.log(i.permeability_md), 0.6, n))
    thick = np.maximum(15.0, rng.normal(i.thickness_m, 0.2 * i.thickness_m, n))
    poro = np.clip(rng.normal(i.porosity, 0.15 * i.porosity, n), 0.05, 0.35)
    het = np.clip(np.exp(rng.normal(np.log(i.heterogeneity_factor), 0.3, n)), 0.15, 1.5)
    skin = np.clip(rng.normal(i.skin, 2.0, n), -2.0, 15.0)
    dcost = rng.triangular(0.8, 1.0, 1.6, n) * i.drilling_cost_per_m
    hp = rng.normal(i.heat_price_eur_mwh, 0.15 * i.heat_price_eur_mwh, n)
    pp = rng.normal(i.power_price_eur_mwh, 0.20 * i.power_price_eur_mwh, n)
    success = rng.random(n) < i.success_prob
    rows = []
    for k in range(n):
        j = replace(i, gradient_c_per_km=float(grad[k]), permeability_md=float(perm[k]),
                    thickness_m=float(thick[k]), porosity=float(poro[k]),
                    heterogeneity_factor=float(het[k]), skin=float(skin[k]),
                    drilling_cost_per_m=float(dcost[k]), heat_price_eur_mwh=float(hp[k]),
                    power_price_eur_mwh=float(pp[k]))
        e = economics(j)
        npv = e["npv"] if success[k] else -e["dry_hole_loss"]
        rows.append((npv, e["lcoe"], e["peak_mw"], bool(success[k]), e["eff_flow"]))
    return pd.DataFrame(rows, columns=["npv", "lcoe", "peak_mw", "success", "eff_flow"])


def tornado(i: Inputs) -> pd.DataFrame:
    price_attr = "power_price_eur_mwh" if i.use_case == "Power (ORC)" else "heat_price_eur_mwh"
    base = economics(i)["npv"]
    tests = [
        ("Geothermal gradient", "gradient_c_per_km", 0.8, 1.2),
        ("Flow rate", "flow_kg_s", 0.7, 1.3),
        ("Permeability", "permeability_md", 0.5, 2.0),
        ("Heterogeneity", "heterogeneity_factor", 0.6, 1.4),
        ("Drilling cost", "drilling_cost_per_m", 1.3, 0.8),
        ("Energy price", price_attr, 0.8, 1.2),
        ("Discount rate", "discount_rate", 1.3, 0.7),
        ("Reinjection temp", "reinjection_temp_c", 1.3, 0.7),
        ("Availability", "availability", 0.92, 1.05),
        ("Well spacing", "well_spacing_m", 0.7, 1.3),
        ("Thickness", "thickness_m", 0.7, 1.3),
    ]
    rows = []
    for label, attr, lo, hi in tests:
        a = replace(i, **{attr: getattr(i, attr) * lo})
        b = replace(i, **{attr: getattr(i, attr) * hi})
        rows.append((label, economics(a)["npv"] - base, economics(b)["npv"] - base))
    df = pd.DataFrame(rows, columns=["driver", "low", "high"])
    df["swing"] = df["low"].abs() + df["high"].abs()
    return df.sort_values("swing")


def depth_scan(i: Inputs) -> pd.DataFrame:
    rows = []
    for dep in np.arange(1000, 6001, 250):
        j = replace(i, depth_m=float(dep))
        e = economics(j)
        rows.append((dep, reservoir_temp(j), e["npv"], e["lcoe"], e["peak_mw"]))
    return pd.DataFrame(rows, columns=["depth_m", "t_res_c", "npv", "lcoe", "peak_mw"])


def flow_scan(i: Inputs) -> pd.DataFrame:
    rows = []
    for q in np.arange(20, 141, 5):
        j = replace(i, flow_kg_s=float(q))
        e = economics(j)
        rows.append((q, e["npv"], e["lcoe"], e["peak_mw"], e["pump_kw"], e["eff_flow"]))
    return pd.DataFrame(rows, columns=["flow", "npv", "lcoe", "peak_mw", "pump_kw", "eff_flow"])


# ---- Calibration -----------------------------------------------------------
# Fit the two parameters the physics cannot know in advance (skin and the
# heterogeneity factor) from field data: a well test, a tracer test, or
# observed production-temperature history.
HET_BOUNDS = (0.1, 2.0)


def fit_skin(i: Inputs, q_kg_s: float, drawdown_bar: float | None = None,
             injection_bar: float | None = None) -> dict:
    """Skin from a well test: measured drawdown (production) and/or overpressure
    (injection) at a known rate. Closed-form inversion of Darcy radial flow."""
    sal = i.salinity_g_l
    T_res = reservoir_temp(i)
    kh = i.permeability_md * 9.869233e-16 * i.thickness_m
    re = max(0.5 * i.well_spacing_m, 50.0)
    ln_re = math.log(re / R_WELL)
    out = {"skin_prod": None, "skin_inj": None}
    if drawdown_bar:
        q_vol = q_kg_s / brine_density(T_res, sal)
        out["skin_prod"] = drawdown_bar * 1e5 * 2.0 * math.pi * kh / (q_vol * brine_viscosity(T_res, sal)) - ln_re
    if injection_bar:
        T_inj_eff = i.reinjection_temp_c + 0.20 * (T_res - i.reinjection_temp_c)
        q_vol = q_kg_s / brine_density(T_inj_eff, sal)
        out["skin_inj"] = injection_bar * 1e5 * 2.0 * math.pi * kh / (q_vol * brine_viscosity(T_inj_eff, sal)) - ln_re
    vals = [v for v in out.values() if v is not None]
    out["skin"] = float(np.mean(vals)) if vals else None
    return out


def fit_heterogeneity_tracer(i: Inputs, first_arrival_days: float, q_kg_s: float) -> float:
    """Heterogeneity factor from the first arrival of an inter-well tracer.

    The first arrival travels the shortest streamline: t = het * pi*phi*h*d^2*I0/(4 Q).
    (A tracer peak arrives later than first arrival; use first detection.)
    """
    rho = brine_density(reservoir_temp(i), i.salinity_g_l)
    q_vol = q_kg_s / rho
    tau = first_arrival_days * 86400.0
    return float(tau * 4.0 * q_vol / (math.pi * i.porosity * i.thickness_m * i.well_spacing_m ** 2 * _doublet_I()[0]))


def fit_heterogeneity_history(i: Inputs, years, temps_c, q_kg_s: float | None = None) -> dict:
    """Least-squares fit of the heterogeneity factor to observed production temperatures.

    Returns the best factor, RMSE (K), and the range of factors whose RMSE is within
    max(1.5x best, best + 0.5 K); a flat history gives a wide, one-sided range.
    """
    from scipy.optimize import minimize_scalar
    years = np.asarray(years, dtype=float)
    temps = np.asarray(temps_c, dtype=float)
    ok = np.isfinite(years) & np.isfinite(temps)
    years, temps = years[ok], temps[ok]
    if len(years) < 2:
        raise ValueError("need at least two (year, temperature) points")
    q = effective_flow(i) if q_kg_s is None else q_kg_s

    def rmse(log_het: float) -> float:
        j = replace(i, heterogeneity_factor=math.exp(log_het))
        _, t_wh = _temps(j, years, q)
        return float(np.sqrt(np.mean((t_wh - temps) ** 2)))

    lo, hi = math.log(HET_BOUNDS[0]), math.log(HET_BOUNDS[1])
    res = minimize_scalar(rmse, bounds=(lo, hi), method="bounded", options={"xatol": 1e-3})
    best = float(res.fun)
    grid = np.append(np.linspace(lo, hi, 160), res.x)      # the optimum is always inside its own range
    errs = np.array([rmse(g) for g in grid])
    inside = np.exp(grid[errs <= max(1.5 * best, best + 0.5)])
    return dict(het=float(math.exp(res.x)), rmse=best, het_lo=float(inside.min()), het_hi=float(inside.max()))


def calibrate(i: Inputs, tracer=None, welltest=None, history=None) -> dict:
    """Combine whichever tests are available into calibrated skin and heterogeneity.

    tracer:   dict(days=..., q=...)                       first arrival, flow during test
    welltest: dict(q=..., drawdown_bar=?, injection_bar=?)
    history:  dict(years=[...], temps=[...], q=?)         observed wellhead temperature
    Heterogeneity estimates from several sources are combined by geometric mean.
    """
    out = {"het_estimates": {}, "notes": []}
    skin = i.skin
    if welltest:
        s = fit_skin(i, welltest["q"], welltest.get("drawdown_bar"), welltest.get("injection_bar"))
        out["skin_fit"] = s
        if s["skin"] is not None:
            skin = float(np.clip(s["skin"], -2.0, 15.0))
            if s["skin"] != skin:
                out["notes"].append(f"Fitted skin {s['skin']:.1f} was clipped to {skin:.1f}.")
            if s["skin_prod"] is not None and s["skin_inj"] is not None and abs(s["skin_prod"] - s["skin_inj"]) > 4:
                out["notes"].append("Production and injection tests imply very different skins; "
                                    "check the permeability-thickness or thermal effects on injectivity.")
    base = replace(i, skin=skin)
    if tracer:
        out["het_estimates"]["tracer"] = fit_heterogeneity_tracer(base, tracer["days"], tracer["q"])
    if history and history.get("years") is not None:
        h = fit_heterogeneity_history(base, history["years"], history["temps"], history.get("q"))
        out["history_fit"] = h
        out["het_estimates"]["temperature history"] = h["het"]
        if h["het_hi"] >= 0.9 * HET_BOUNDS[1]:
            out["notes"].append("Temperature history shows little decline, so it only gives a lower bound on heterogeneity.")
    ests = list(out["het_estimates"].values())
    het = float(np.exp(np.mean(np.log(ests)))) if ests else i.heterogeneity_factor
    het = float(np.clip(het, *HET_BOUNDS))
    out["heterogeneity_factor"] = het
    out["skin"] = skin
    out["inputs"] = replace(base, heterogeneity_factor=het)
    return out
