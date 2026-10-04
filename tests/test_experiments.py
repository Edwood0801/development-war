from experiments.conditions import CONDITIONS, make_config
from development_war.engine.simulator import Simulator


def test_every_experiment_condition_runs_and_records_data():
    for name in CONDITIONS:
        sim = Simulator(config=make_config(name, seed=1))
        s = sim.run()
        assert sim.world.finished and s["constraint_records"] >= 0
        assert all("project_attempts" in c and "project_failures" in c for c in s["countries"].values())


def test_conditions_scale_resources():
    m = {n: Simulator(config=make_config(n, 0)).world.countries["A"].resources.money for n in CONDITIONS}
    assert m["A_100pct"] > m["B_70pct"] > m["C_40pct"] > m["D_20pct"]
    assert m["D_20pct"] == m["E_20pct_incomplete_info"]


def test_export_history_creates_missing_directories(tmp_path):
    sim = Simulator(config=make_config("A_100pct", seed=1))
    sim.run()
    out = tmp_path / "does" / "not" / "exist" / "run.jsonl"
    sim.export_history(out)
    assert out.read_text(encoding="utf-8").count("\n") == len(sim.world.log.all())
