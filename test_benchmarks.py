"""Integrity tests for the benchmark dataset and the model-vs-reported check."""
import benchmarks as b


def test_every_row_is_sourced_and_labelled():
    df = b.benchmark_df()
    assert df["project"].is_unique
    assert df["source_url"].notna().all() and df["source_url"].str.startswith("https://").all()
    assert set(df["basis"]) <= {"Reported", "Planned", "Older"}
    assert df["notes"].str.len().min() > 20


def test_numbers_are_physically_plausible():
    df = b.benchmark_df()
    for col in ("depth_m", "t_c", "flow_kg_s", "mwe", "mwth"):
        assert (df[col].dropna() > 0).all(), col
    assert df["t_c"].dropna().between(20, 400).all()
    assert df["depth_m"].dropna().between(500, 8000).all()
    # thermal output per kg/s implies a believable temperature drop across the plant
    assert df["delta_t_k"].dropna().between(10, 120).all()


def test_derived_columns():
    df = b.benchmark_df().set_index("project")
    assert abs(df.loc["Unterhaching", "mwth_per_kg_s"] - 38 / 150) < 1e-9


def test_model_check_uses_only_production_temperatures():
    chk = b.model_check(b.benchmark_df(), {})
    assert "Soultz-sous-Forêts" not in set(chk["project"])      # reservoir-mean temperature only
    assert {"Insheim", "Fervo Project Red"} <= set(chk["project"])


def test_model_reproduces_insheim_within_15_percent():
    chk = b.model_check(b.benchmark_df(), {"Insheim": 70}).set_index("project")
    assert abs(chk.loc["Insheim", "error_pct"]) < 15


def test_colder_reinjection_means_more_modelled_power():
    df = b.benchmark_df()
    cold = b.model_check(df, {"Insheim": 60}).set_index("project").loc["Insheim", "model_mwe"]
    warm = b.model_check(df, {"Insheim": 90}).set_index("project").loc["Insheim", "model_mwe"]
    assert cold > warm


def test_second_sources_and_capex_are_consistent():
    df = b.benchmark_df()
    assert (df["source2"].isna() | df["source2_url"].notna()).all()
    c = df.dropna(subset=["capex_m"])
    assert c["capex_ccy"].notna().all() and (c["capex_per_mw_m"] > 0.5).all() and (c["capex_per_mw_m"] < 20).all()
    assert len(df) >= 25


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in tests:
        try:
            f(); print("PASS ", n)
        except Exception as ex:   # noqa: BLE001
            bad += 1; print("FAIL ", n, type(ex).__name__, ex)
    print(f"\n{len(tests)-bad}/{len(tests)} passed")
    raise SystemExit(1 if bad else 0)
