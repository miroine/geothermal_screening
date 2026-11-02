"""Benchmark dataset of well-known geothermal projects, with sources.

Every number below was read from the cited source (looked up 2026-10-31). A blank
(None) means the source did not report it; nothing is filled in from memory.
`basis` says how solid the figure is:
  Reported  - operating figure from the source
  Planned   - design/target figure (plant not confirmed at that level)
  Older     - from an older source; verify before relying on it
Flow is stored as kg/s; sources quote l/s or kg/s, treated as equal (brine density
1.0-1.1 kg/l, so up to ~10 % difference). Unit conversions (ft -> m, F -> C) and
the derived columns (MWth per kg/s, delta-T, capex per MW) are my arithmetic.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

import model as m

# Short source keys -> URL
SRC = {
    "tge_insheim": "https://db.thinkgeoenergy.com/plants/4747",
    "springer_plants": "https://geothermal-energy-journal.springeropen.com/articles/10.1186/2195-9706-1-4/tables/3",
    "springer_molasse": "https://geothermal-energy-journal.springeropen.com/articles/10.1186/s40517-016-0059-3/tables/2",
    "openei_soultz": "https://openei.org/wiki/Soultz_Geothermal_Area",
    "tge_munich1": "https://www.thinkgeoenergy.com/work-has-started-on-50-mw-geothermal-heating-project-in-munich-germany/",
    "tge_munich2": "https://www.thinkgeoenergy.com/second-well-drilled-for-geothermal-project-in-munich-exceeds-expectations/",
    "tge_sauerlach": "https://www.thinkgeoenergy.com/start-of-operation-of-sauerlach-combined-heat-and-power-plant/",
    "paris_mouche": "https://pangea.stanford.edu/ERE/pdf/IGAstandard/SGW/2025/Mouche.pdf",
    "nlog_2025": "https://www.nlog.nl/sites/default/files/2025-11/molen-2025-geothermal.pdf",
    "ens_dk": "https://ens.dk/en/energy-sources/geothermal-plants-operation",
    "interreg_pyrzyce": "https://www.interregeurope.eu/good-practices/geothermal-installation-in-pyrzyce-as-example-of-clean-renewable-energy-in-heating-sector",
    "tge_pyrzyce": "https://www.thinkgeoenergy.com/geothermal-energy-for-heating-supply-to-help-fight-smog-in-pyrzyce-poland/",
    "tge_ritt": "https://www.thinkgeoenergy.com/industrial-heating-project-of-rittershofen-in-france-innaugurated/",
    "destress_ritt": "https://www.destress-h2020.eu/demonstration-sites/rittershoffen-france",
    "tge_red": "https://www.thinkgeoenergy.com/fervo-energy-reports-breakthrough-in-field-scale-egs-project-in-nevada/",
    "tge_cape1": "https://www.thinkgeoenergy.com/fervo-announces-technical-and-commercial-breakthroughs-at-cape-station-geothermal-site/",
    "eg_cape": "https://www.energyglobal.com/other-renewables/05102026/fervo-energy-declares-commercial-operation-at-cape-station-ahead-of-schedule/",
    "forge": "https://utahforge.com/?p=1377079",
    "eavor1": "https://www.thinkgeoenergy.com/eavor-reports-first-electricity-generation-at-pioneering-geothermal-project-in-geretsried-germany/",
    "eavor2": "https://eavor.com/?p=12722",
    "imperial_hh": "https://www.imperial.ac.uk/energy-futures-lab/research/succeed/research/pilot-sites/hellisheidi/",
    "wiki_nesjavellir": "https://en.wikipedia.org/wiki/Nesjavellir_Geothermal_Power_Station",
    "wiki_wairakei": "https://en.wikipedia.org/wiki/Wairakei_Power_Station",
    "geysers": "https://geysers.com/wp-content/uploads/2025/08/2025-The-Geysers-by-the-Numbers-AV.pdf",
    "enel_larderello": "https://www.enelgreenpower.com/our-projects/operating/geothermal-power-plant-larderello",
    "tge_kengen": "https://www.thinkgeoenergy.com/kengen-seeks-to-double-geothermal-capacity-by-2030/",
    "power_sarulla": "https://www.powermag.com/sarulla-one-of-the-worlds-largest-geothermal-power-projects-comes-alive-with-private-finance/",
}

COLUMNS = ["project", "country", "category", "use", "year", "depth_m", "t_c", "t_kind", "flow_kg_s",
           "spacing_km", "mwe", "mwth", "capex_m", "capex_ccy", "basis", "notes", "source", "source2"]

_ROWS = [
    # ---- hydrothermal doublets (Germany, Austria)
    dict(project="Insheim", country="Germany", category="Hydrothermal doublet", use="Power (ORC)", year=2012,
         depth_m=3600, t_c=165, t_kind="production", flow_kg_s=75, spacing_km=None, mwe=4.3, mwth=None,
         basis="Reported",
         notes="4.8 MWe installed, 4.3 MWe operational. Flow 65-85 l/s is the planned range. Water from ~3,600 m (well to 3,850 m MD). 6-10 MWth thermal capacity quoted.",
         source="tge_insheim", source2="springer_plants"),
    dict(project="Landau", country="Germany", category="Hydrothermal doublet", use="Power (ORC)", year=None,
         depth_m=None, t_c=None, t_kind=None, flow_kg_s=75, spacing_km=1.5, mwe=3.6, mwth=None,
         basis="Older", notes="Up to 3.6 MWe; 70-80 l/s; 2-5 MWth.", source="springer_plants"),
    dict(project="Unterhaching", country="Germany", category="Hydrothermal doublet", use="Power + heat", year=None,
         depth_m=None, t_c=123, t_kind="measured at depth", flow_kg_s=150, spacing_km=4.5, mwe=3.36, mwth=38,
         basis="Older",
         notes="Kalina cycle plus district heating. 123 C measured at about 3,032 m below sea level (a temperature table; surface elevation not given, so depth below surface is not stated).",
         source="springer_plants", source2="springer_molasse"),
    dict(project="Sauerlach (SWM)", country="Germany", category="Hydrothermal doublet", use="Power + heat", year=2014,
         depth_m=None, t_c=140, t_kind="approx.", flow_kg_s=None, spacing_km=None, mwe=5.0, mwth=None,
         basis="Reported",
         notes="Operation announced Jan 2014. Wells about 5,000 m long (article); 140 C measured at about 3,853 m below sea level (temperature table). The article calls it a '5 MW' project; households served suggest this is electric. ORC by Turboden; also district heat for Sauerlach.",
         source="tge_sauerlach", source2="springer_molasse"),
    dict(project="Neustadt-Glewe", country="Germany", category="Hydrothermal doublet", use="Power + heat", year=None,
         depth_m=None, t_c=None, t_kind=None, flow_kg_s=35, spacing_km=1.5, mwe=0.21, mwth=4,
         basis="Older", notes="High salt and gas content.", source="springer_plants"),
    dict(project="Bruchsal", country="Germany", category="Hydrothermal doublet", use="Power + heat", year=None,
         depth_m=None, t_c=None, t_kind=None, flow_kg_s=28.5, spacing_km=1.4, mwe=0.55, mwth=5.5,
         basis="Older", notes="Kalina cycle; ~100 g/l salinity and high CO2 (flow-assurance problems).",
         source="springer_plants"),
    dict(project="Altheim", country="Austria", category="Hydrothermal doublet", use="Power + heat", year=None,
         depth_m=None, t_c=None, t_kind=None, flow_kg_s=81.7, spacing_km=1.7, mwe=1.0, mwth=12.4,
         basis="Older", notes="Clogging by rock fragments and bentonite reported.", source="springer_plants"),
    dict(project="Munich Schäftlarnstraße (SWM)", country="Germany", category="Hydrothermal doublet", use="Heat",
         year=2020, depth_m=3044, t_c=108, t_kind="production", flow_kg_s=None, spacing_km=1.2, mwe=None, mwth=50,
         basis="Planned",
         notes="2019 reports: 50 MWth planned, 6 wells in a star pattern, spacing >1.2 km, 2nd well 3,044 m at 108 C (102 C expected), up to 80,000 residents. Start-up was planned for 2020; current status not verified.",
         source="tge_munich1", source2="tge_munich2"),
    # ---- hydrothermal heat elsewhere in Europe
    dict(project="Paris Basin (Dogger)", country="France", category="Hydrothermal doublet", use="Heat", year=None,
         depth_m=1725, t_c=68, t_kind="production (56-80 C)", flow_kg_s=None, spacing_km=1.3, mwe=None, mwth=None,
         basis="Reported",
         notes="54 district-heating production units. Depth 1,450-2,000 m, 56-80 C; productive layers ~2 m thick. Alfortville study: 1.3 km spacing and thermal breakthrough ~4.35 yr in the modelled case (a model result, not a measurement).",
         source="paris_mouche"),
    dict(project="Netherlands (national)", country="Netherlands", category="Hydrothermal doublet", use="Heat", year=2024,
         depth_m=None, t_c=None, t_kind=None, flow_kg_s=None, spacing_km=None, mwe=None, mwth=None,
         basis="Reported",
         notes="23 systems in production (33 realised), 7.49 PJ delivered in 2024, 25-110 C. 7.49 PJ/yr is about 237 MWth average, roughly 10 MWth per producing system (my arithmetic, not a source figure).",
         source="nlog_2025"),
    dict(project="Pyrzyce", country="Poland", category="Hydrothermal doublet", use="Heat", year=None,
         depth_m=1640, t_c=64, t_kind="production", flow_kg_s=None, spacing_km=None, mwe=None, mwth=None,
         basis="Reported",
         notes="Five wells in operation (1 production, 4 injection). Brine ~122 g/l, mostly NaCl. Geothermal water supplied 60 % of district heat in 2023 (emissions compared with coal-only 1997).",
         source="interreg_pyrzyce", source2="tge_pyrzyce"),
    dict(project="Aarhus (planned)", country="Denmark", category="Hydrothermal doublet", use="Heat", year=None,
         depth_m=None, t_c=None, t_kind=None, flow_kg_s=None, spacing_km=None, mwe=None, mwth=110,
         basis="Planned",
         notes="Danish Energy Agency lists 110 MW planned total capacity for Aarhus (page does not say thermal, but it is district heating). Thisted has run since 1984 (heat for about 2,000 households); Sønderborg was commissioned in 2013.",
         source="ens_dk"),
    # ---- EGS and enhanced systems
    dict(project="Soultz-sous-Forêts", country="France", category="EGS", use="Power (ORC)", year=None,
         depth_m=5000, t_c=168, t_kind="reservoir mean", flow_kg_s=30, spacing_km=0.6, mwe=1.5, mwth=None,
         basis="Older",
         notes="Reservoir 3,211-5,000 m; mean reservoir temperature 168 C (2015 database page). Corrosion from high salinity. Current injection temperature 70 C (2021 study).",
         source="openei_soultz", source2="springer_plants"),
    dict(project="Rittershoffen (ECOGI)", country="France", category="EGS", use="Heat (industrial)", year=2016,
         depth_m=2500, t_c=165, t_kind="production", flow_kg_s=None, spacing_km=None, mwe=None, mwth=24,
         capex_m=55, capex_ccy="EUR", basis="Reported",
         notes="Industrial steam-equivalent heat for the Roquette site via a 15 km pipeline; 190,000 MWh/yr thermal; ~8,000 h/yr. Fractured sandstone/granite reservoir ~2,600 m; brine ~100 g/l. Injector exceeded 70 l/s after stimulation; production well flowed artesian at over 40 l/s. EUR 55 M total investment.",
         source="tge_ritt", source2="destress_ritt"),
    dict(project="Fervo Project Red", country="USA", category="EGS", use="Power (ORC)", year=2023,
         depth_m=2347, t_c=169, t_kind="production (max)", flow_kg_s=63, spacing_km=None, mwe=3.5, mwth=None,
         basis="Reported",
         notes="Horizontal pair, ~990 m laterals. 63 l/s at high temperature; 3.5 MW assumes a supercritical ORC (2-3.5 MW gross seen during the test). Max measured temperature 190 C.",
         source="tge_red"),
    dict(project="Fervo Cape Station", country="USA", category="EGS", use="Power", year=2026,
         depth_m=None, t_c=None, t_kind=None, flow_kg_s=107, spacing_km=None, mwe=33, mwth=None,
         basis="Reported",
         notes="First 33 MW net GeoBlock declared commercial in Oct 2026; Phase I ~100 MW (3 GeoBlocks, others due by 1 Jan 2027); +400 MW due 2028. 107 kg/s = max rate in a 30-day well test; >10 MW per producer. First block built in 23 months.",
         source="eg_cape", source2="tge_cape1"),
    dict(project="Utah FORGE", country="USA", category="EGS", use="Research", year=2024,
         depth_m=None, t_c=188, t_kind="approx.", flow_kg_s=26.5, spacing_km=None, mwe=None, mwth=None,
         basis="Reported",
         notes="Aug 2024 circulation test of nearly a month at 420 gpm; >90 % of injected fluid recovered.",
         source="forge"),
    # ---- closed loop
    dict(project="Eavor-Loop Geretsried", country="Germany", category="Closed loop", use="Power + heat", year=2025,
         depth_m=None, t_c=None, t_kind=None, flow_kg_s=None, spacing_km=None, mwe=8.2, mwth=64,
         basis="Planned",
         notes="First grid power Dec 2025 ('partial commercial operation'); 8.2 MWe / 64 MWth are goals. Two vertical wells, 12 laterals as six pairs (16 km of wellbore per pair); runs by thermosiphon after a start-up pump (3 kg/s).",
         source="eavor1", source2="eavor2"),
    # ---- high enthalpy
    dict(project="The Geysers", country="USA", category="High enthalpy", use="Power", year=1960,
         depth_m=2591, t_c=186, t_kind="wellhead steam (avg)", flow_kg_s=None, spacing_km=None, mwe=725, mwth=None,
         basis="Reported",
         notes="725 MW net for Calpine's 13 plants (694 MW net maximum in 2024); 15 plants in the field incl. 2 run by NCPA. 322 active steam wells, 60 injection wells; average well depth 8,500 ft (2,591 m), deepest 12,900 ft; flow-weighted wellhead 366.6 F (186 C). 5.47 TWh net in 2024. First unit 1960.",
         source="geysers"),
    dict(project="Larderello", country="Italy", category="High enthalpy", use="Power", year=None,
         depth_m=None, t_c=None, t_kind=None, flow_kg_s=None, spacing_km=None, mwe=800, mwth=None,
         basis="Reported",
         notes="About 800 MW across 34 plants / 37 units. Valle Secolo (early 1990s) is Europe's largest at nearly 120 MW (two 60 MW sections), serving about 316,000 households. About 40 % of steam condensate reinjected.",
         source="enel_larderello", source2="springer_plants"),
    dict(project="Hellisheiði", country="Iceland", category="High enthalpy", use="Power + heat", year=2006,
         depth_m=None, t_c=None, t_kind=None, flow_kg_s=None, spacing_km=None, mwe=303, mwth=133,
         basis="Reported", notes="Flash power plus district-heat production.", source="imperial_hh"),
    dict(project="Nesjavellir", country="Iceland", category="High enthalpy", use="Power + heat", year=1990,
         depth_m=2000, t_c=None, t_kind=None, flow_kg_s=None, spacing_km=None, mwe=120, mwth=300,
         basis="Reported",
         notes="Source: Wikipedia. Max well depth ~2,000 m; 21 wells in use. District-heat water of 1,100 l/s at 82-85 C is surface water heated by the plant, not well fluid, so it is not used as a flow or production temperature.",
         source="wiki_nesjavellir"),
    dict(project="Wairakei", country="New Zealand", category="High enthalpy", use="Power", year=1958,
         depth_m=660, t_c=None, t_kind=None, flow_kg_s=None, spacing_km=None, mwe=175, mwth=None,
         basis="Reported",
         notes="Source: Wikipedia (page is inconsistent: 175 MW infobox, 181 MW including the 14 MW binary unit added in 2005). Max well depth 660 m; 55 production, 6 reinjection wells; 1,365 GWh/yr at 89 % capacity factor. Due to be phased out in 2027 and replaced by Te Mihi.",
         source="wiki_wairakei"),
    dict(project="Sarulla", country="Indonesia", category="High enthalpy", use="Power", year=2017,
         depth_m=None, t_c=276, t_kind="well fluid (max)", flow_kg_s=None, spacing_km=None, mwe=330, mwth=None,
         capex_m=1600, capex_ccy="USD", basis="Reported",
         notes="Dec 2017 article: 330 MW in three units, flash plus ORC (IGCC). Unit 1 commercial Mar 2017, unit 2 Oct 2017, third unit still under construction then, so check current status. Fluids above 260 C, up to 276 C. About USD 1.6 bn total cost (~USD 5 M/MW).",
         source="power_sarulla"),
    dict(project="Olkaria / KenGen", country="Kenya", category="High enthalpy", use="Power", year=None,
         depth_m=None, t_c=None, t_kind=None, flow_kg_s=None, spacing_km=None, mwe=713, mwth=None,
         basis="Older",
         notes="KenGen installed geothermal capacity 713.13 MW as of July 2021 (Kenya total quoted as 861 MW; context unclear). Olkaria I Unit 6 (83.3 MW) was then under construction; KenGen planned +682 MW. Likely higher today.",
         source="tge_kengen"),
]


def benchmark_df() -> pd.DataFrame:
    df = pd.DataFrame(_ROWS, columns=COLUMNS)
    df["source_url"] = df["source"].map(SRC)
    df["source2_url"] = df["source2"].map(SRC)
    df["mwth_per_kg_s"] = df["mwth"] / df["flow_kg_s"]
    df["delta_t_k"] = df["mwth"] * 1e6 / (df["flow_kg_s"] * m.brine_cp(50.0))
    cap = df["mwe"].fillna(df["mwth"])
    df["capex_basis"] = np.where(df["capex_m"].notna(), np.where(df["mwe"].notna(), "MWe", "MWth"), None)
    df["capex_per_mw_m"] = df["capex_m"] / cap
    return df


def model_check(df: pd.DataFrame, t_inj: dict, base: m.Inputs | None = None) -> pd.DataFrame:
    """Compare the model's ORC output with reported electric output.

    Only projects with a reported production temperature, flow and MWe qualify.
    Reinjection temperature is not reported by these sources, so it is an explicit
    assumption (t_inj, per project). Model output = thermal power x ORC efficiency
    x (1 - parasitics); it excludes pumping power, so it compares with net/operational
    figures only approximately.
    """
    base = base or m.Inputs()
    rows = []
    prod = df[df["t_kind"].fillna("").str.startswith("production")]      # reservoir-mean temperatures do not qualify
    for _, r in prod.dropna(subset=["t_c", "flow_kg_s", "mwe"]).iterrows():
        ti = float(t_inj.get(r["project"], 70.0))
        i = replace(base, use_case="Power (ORC)", reinjection_temp_c=ti, surface_temp_c=10.0)
        mwth = r["flow_kg_s"] * m.brine_cp(i.salinity_g_l) * (r["t_c"] - ti) / 1e6
        eta = float(m.orc_efficiency(r["t_c"], i))
        model_mwe = mwth * eta * (1.0 - m.ORC_PARASITIC)
        rows.append(dict(project=r["project"], t_prod_c=r["t_c"], flow_kg_s=r["flow_kg_s"], assumed_t_inj_c=ti,
                         thermal_mw=mwth, efficiency=eta, model_mwe=model_mwe, reported_mwe=r["mwe"],
                         error_pct=100.0 * (model_mwe / r["mwe"] - 1.0)))
    return pd.DataFrame(rows)
