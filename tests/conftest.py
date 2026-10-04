import copy

import pytest

from development_war.engine.actions import AttemptProject, Pass, ResearchTech, Trade
from development_war.engine.projects import Proposal
from development_war.engine.resources import Resources
from development_war.engine.simulator import Simulator
from development_war.engine.world import WorldConfig
from development_war.scenarios import load_long_range_communication


@pytest.fixture
def scenario():
    return load_long_range_communication()


@pytest.fixture
def make_sim(scenario):
    def _make(seed=0, shocks=False, scenario_override=None, **cfg):
        cfg.setdefault("shock_probability", None if shocks else 0.0)
        return Simulator(scenario_override or copy.deepcopy(scenario), WorldConfig(seed=seed, **cfg))

    return _make


def external_turn(sim, **by_country):
    """Take over every country for one turn (unspecified countries pass)."""
    for cid in sim.world.countries:
        sim.submit_actions(cid, by_country.get(cid, [Pass()]))
    return sim.step()


def events(sim, name):
    return [e for e in sim.world.log.all() if e.event == name]
