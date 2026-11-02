# Geothermal Opportunity Designer

    pip install -r requirements.txt
    streamlit run app.py        # the app
    python test_model.py        # 24 physics, economics and calibration tests

## Model (model.py)
1. Reservoir: exact doublet streamlines (circles through both wells), per-streamline thermal front
   (heat-capacity retardation) with conduction from the confining beds (Lauwerier); flow-weighted production temperature.
2. Wellbore: Ramey heat loss (depth, flow and time dependent).
3. Hydraulics: Darcy drawdown/injectivity with T- and salinity-dependent viscosity, friction, buoyancy head.
   Flow is cut back if the pump budget cannot deliver the design rate (deliverability limit).
4. Plant: district heating, or ORC power (second-law fraction of Carnot on brine inlet temperature).
5. Economics: depth-scaled drilling + fixed well cost, workovers, tax with depreciation and loss carry-forward,
   NPV / IRR / LCOE / payback, dry-hole-risked NPV, Monte Carlo, tornado, depth and flow sweeps.

Screening tool: calibrate heterogeneity factor, skin and costs against your own well/simulator data.

## Calibration tab
Fits the two parameters first principles cannot give you:
- Well test (drawdown and/or injection overpressure at a known rate) -> skin
- Tracer first-arrival time -> heterogeneity factor
- Observed wellhead temperatures -> heterogeneity factor (with a plausible range)
"Apply" pushes the fitted values into the sidebar so every tab, including the Monte Carlo, uses them.
Note: skin is only meaningful if permeability x thickness is right; the two trade off in a single well test.

## Benchmarks tab
`benchmarks.py` holds 25 well-known projects (hydrothermal doublets, EGS, closed loop, high enthalpy),
each with a source link and a basis label (Reported / Planned / Older). Blank = not reported by the source.
Capex (two projects only) is the source's total cost, per MWe or per MWth as stated; currencies are not converted.
The tab overlays your design on depth-vs-temperature, flow-vs-capacity and specific-output charts, and
compares the model's ORC output with reported plants (reinjection temperature is an editable assumption).
`python test_benchmarks.py` checks data integrity and the Insheim comparison.

## Concepts tab
`concepts_diagram.py` animates five designs in plain JavaScript (canvas): hydrothermal doublet, EGS (stimulation then circulation),
closed loop, flash/dry steam and district heating. Temperatures come from your inputs; geometry is schematic.
