import pytest

from development_war.engine.actions import ActionValidator, AttemptProject, ResearchTech, parse_action
from development_war.engine.projects import Proposal, quote_proposal
from development_war.engine.resources import InsufficientResources, Resources
from development_war.engine.technology import TechGraph, Technology
from tests.conftest import events, external_turn

STANDARD = Proposal(name="Standard development")


def test_resources_cannot_go_negative():
    with pytest.raises(InsufficientResources):
        Resources(money=5) - Resources(money=6)
    assert (Resources(money=5) - Resources(money=5)).money == 0


def test_engine_rejects_unaffordable_action_and_spends_nothing(make_sim):
    sim = make_sim()
    a = sim.world.countries["A"]
    a.techs |= {"radio_systems", "advanced_electronics", "power_systems"}  # tech is fine; money is not
    before = a.resources
    external_turn(sim, A=[AttemptProject(proposal=STANDARD)])
    rej = events(sim, "action_rejected")
    assert len(rej) == 1 and "insufficient resources" in rej[0].reason
    assert a.resources == before + a.income  # only income changed
    assert a.project_attempts == 0


def test_country_spend_is_guarded_in_depth(make_sim):
    sim = make_sim()
    with pytest.raises(InsufficientResources):
        sim.world.countries["A"].spend(Resources(money=10_000))


def test_cannot_use_technology_not_acquired(make_sim):
    sim = make_sim()
    w = sim.world
    rules = w.scenario.project
    a = w.countries["A"]
    # attempting the project at all requires radio_systems, which A starts without
    q = quote_proposal(rules, w.graph, a.techs, Proposal(name="x", tags=["simplify_design"]))
    assert not q.feasible and "radio_systems" in " ".join(q.problems)
    # listing a technology you do not own is also rejected
    q = quote_proposal(rules, w.graph, a.techs | {"radio_systems"}, Proposal(name="y", tags=["simplify_design"], uses_techs=["radar"]))
    assert not q.feasible and "not acquired" in " ".join(q.problems)
    external_turn(sim, A=[AttemptProject(proposal=Proposal(name="x", tags=["simplify_design"]))])
    assert "missing required technologies" in events(sim, "action_rejected")[0].reason


def test_prerequisites_enforced_for_research(make_sim):
    sim = make_sim()
    external_turn(sim, A=[ResearchTech(tech_id="signal_processing")])  # needs basic_computing + advanced_electronics
    assert "missing prerequisites" in events(sim, "action_rejected")[0].reason
    assert "signal_processing" not in sim.world.countries["A"].techs


def test_technology_is_acquired_in_technology_update_phase(make_sim):
    sim = make_sim()
    external_turn(sim, A=[ResearchTech(tech_id="radio_systems")])
    assert "radio_systems" in sim.world.countries["A"].techs


def test_tech_graph_is_data_driven_and_validated():
    t = lambda i, pre=(): Technology(id=i, name=i, category="X", prerequisites=list(pre))
    g = TechGraph([t("a"), t("b", ["a"]), t("c", ["b"])])
    assert g.path_to(set(), ["c"]) == ["a", "b", "c"]
    with pytest.raises(ValueError):
        TechGraph([t("a", ["b"]), t("b", ["a"])])
    with pytest.raises(ValueError):
        TechGraph([t("a", ["missing"])])


def test_new_technology_via_scenario_data_only(scenario, make_sim):
    scenario.technologies.append(Technology(id="fiber_optics", name="Fiber Optics", category="Communication", prerequisites=["basic_electronics"], cost=Resources(money=5)))
    sim = make_sim(scenario_override=scenario)
    external_turn(sim, A=[ResearchTech(tech_id="fiber_optics")])
    assert "fiber_optics" in sim.world.countries["A"].techs


def test_untrusted_action_payloads_are_rejected():
    with pytest.raises(Exception):
        parse_action({"type": "set_resources", "money": 10**9})  # an LLM cannot invent world mutations
    assert parse_action({"type": "research_tech", "tech_id": "radio_systems"}).tech_id == "radio_systems"
