import json
import re
from pathlib import Path

import pytest

from development_war.engine.resources import Resources
from development_war.information.intelligence import IntelligenceService, build_observation
from tests.conftest import external_turn


def test_observation_never_contains_hidden_state_or_exact_foreign_values(make_sim):
    sim = make_sim(seed=3)
    w = sim.world
    w.countries["B"].resources = Resources(money=1337, materials=7331, research=4242)
    sim.step()  # populates intel reports
    w.countries["B"].resources = Resources(money=1337, materials=7331, research=4242)
    obs = build_observation(w, "A")
    blob = obs.model_dump_json()
    for forbidden in ("risk_bias", "progress_bias", "hidden", "starting_resources", "last_activity"):
        assert forbidden not in blob
    # foreign resources appear only as (low, high) ranges
    view = obs.others["B"]
    assert view.resource_estimates is not None
    for lo, hi in view.resource_estimates.values():
        assert lo < hi
    assert not hasattr(view, "resources")
    assert "B" not in {k for k in obs.model_dump()["own"]}  # own block holds only A's data


def test_agents_never_import_the_world():
    for f in Path("src/development_war/agents").glob("*.py"):
        text = f.read_text()
        assert not re.search(r"from \.\.engine\.world|import World|engine\.world", text), f.name


def test_spy_reports_carry_uncertainty(make_sim):
    sim = make_sim(seed=1)
    svc = IntelligenceService(sim.world)
    hits = total = 0
    for seed in range(60):
        sim.world.config.seed = seed
        r = svc.gather("A", "B", deep=False)
        assert 0 < r.confidence < 1
        truth = sim.world.countries["B"].resources
        for name, (lo, hi) in r.resource_estimates.items():
            assert lo < hi  # a range, never a point value
            total += 1
            hits += lo <= getattr(truth, name) <= hi
    assert 0.4 < hits / total < 1.0  # usually right, but genuinely fallible


def test_deep_probe_is_more_precise_and_noise_knob_degrades_it(make_sim):
    def mean_width(deep, noise):
        sim = make_sim(information_noise=noise)
        svc, widths = IntelligenceService(sim.world), []
        for seed in range(40):
            sim.world.config.seed = seed
            r = svc.gather("A", "B", deep=deep)
            widths += [hi - lo for lo, hi in r.resource_estimates.values()]
        return sum(widths) / len(widths)

    assert mean_width(True, 1.0) < mean_width(False, 1.0) < mean_width(False, 2.5)
    # stronger intelligence service (D) beats weaker one (A)
    sim = make_sim()
    svc = IntelligenceService(sim.world)
    assert svc.gather("D", "B", False).confidence > svc.gather("A", "B", False).confidence


def test_spy_observations_can_be_wrong_but_report_confidence(make_sim):
    sim = make_sim(seed=5)
    external_turn(sim)
    reports = [e for e in sim.world.log.all() if e.event == "intel_report"]
    assert reports and all("confidence" in e.report and e.report["observations"] for e in reports)


def test_intel_events_are_private_to_the_source(make_sim):
    sim = make_sim()
    sim.step()
    for e in sim.world.log.visible_to("B"):
        assert e.visible_to is None or "B" in e.visible_to
    assert not any(e.event == "intel_report" and e.country == "A" for e in sim.world.log.visible_to("B"))
