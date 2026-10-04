import pytest

from development_war.agents import build_rule_based_team
from development_war.agents.base import BaseKing
from development_war.engine.actions import AttemptProject, Pass, ResearchTech, Trade
from development_war.engine.projects import Proposal
from development_war.engine.resources import Resources
from development_war.engine.simulator import PHASES, Simulator
from development_war.engine.world import WorldConfig
from development_war.information.intelligence import build_observation
from tests.conftest import events, external_turn

SPEC_ORDER = ["world_update", "intelligence_update", "engineering_proposals", "engineering_evaluation", "king_decision",
              "action_validation", "action_execution", "resource_update", "technology_update", "outcome_recording",
              "memory_update", "advance_turn"]


def test_phase_order_matches_spec_and_is_configurable(make_sim):
    assert list(PHASES) == SPEC_ORDER
    sim = Simulator(phases=("world_update", "advance_turn"))
    sim.step()
    assert sim.world.turn == 2  # reduced pipeline still runs


def test_three_countries_with_four_roles_each(make_sim):
    sim = make_sim()
    assert sorted(sim.world.countries) == ["A", "B", "D"]
    for team in sim.teams.values():
        assert all(hasattr(team, r) for r in ("king", "inventor", "evaluator", "spy"))


def test_turn_progression_and_income(make_sim):
    sim = make_sim()
    a = sim.world.countries["A"]
    assert sim.world.turn == 1
    external_turn(sim)
    assert sim.world.turn == 2
    assert a.resources == a.profile.starting_resources + a.income  # one income payment, nothing spent


def test_failed_experiment_produces_persistent_lesson(scenario, make_sim):
    scenario.project.risk_ceiling = 1.0
    sim = make_sim(scenario_override=scenario)
    sim.world.hidden.risk_bias["partial_solution"] = 5.0  # hidden truth: this approach always fails
    a = sim.world.countries["A"]
    a.techs.add("radio_systems")
    attempt = AttemptProject(proposal=Proposal(name="small", tags=["partial_solution"]))
    external_turn(sim, A=[attempt])
    assert len(a.lessons) == 1 and a.lessons[0].outcome == "failure" and a.lessons[0].reason
    assert a.project_progress == 0 and a.project_failures == 1
    assert events(sim, "lesson_recorded")[0].entry["reason"] == a.lessons[0].reason
    # the lesson persists, is visible to the country, and makes its evaluator warier than a country without it
    external_turn(sim)
    obs_a = build_observation(sim.world, "A")
    assert obs_a.own.lessons and obs_a.own.lessons[0].turn == 1
    sim.world.countries["B"].techs.add("radio_systems")
    risk_a = sim.teams["A"].evaluator.evaluate(obs_a, [attempt.proposal])[0].est_risk
    risk_b = sim.teams["B"].evaluator.evaluate(build_observation(sim.world, "B"), [attempt.proposal])[0].est_risk
    assert risk_a > risk_b


def test_constraint_record_captures_scarcity(make_sim):
    sim = make_sim()
    sim.world.countries["A"].techs.add("radio_systems")
    external_turn(sim, A=[AttemptProject(proposal=Proposal(name="cheap", tags=["partial_solution"]))])
    rec = sim.world.constraint_records[0]
    assert rec.country == "A" and rec.scarcity_ratio < 1.0  # normal solution was unaffordable
    assert rec.normal_solution_cost.money == 100 and rec.alternative_tags == ["partial_solution"]
    assert rec.result in {"success", "failure"} and rec.lessons
    assert any(e.event == "constraint_record" for e in sim.world.log.all())


def test_event_log_format_matches_spec(make_sim):
    sim = make_sim()
    sim.world.countries["A"].techs.add("radio_systems")
    external_turn(sim, A=[AttemptProject(proposal=Proposal(name="cheap", tags=["partial_solution"]))])
    e = events(sim, "research_attempt")[0].model_dump()
    for key in ("turn", "country", "event", "project", "cost", "success"):
        assert key in e
    assert set(e["cost"]) == {"money", "materials", "research"}


def test_determinism_same_seed_same_history(make_sim):
    runs = []
    for _ in range(2):
        sim = Simulator(config=WorldConfig(seed=11))
        sim.run()
        runs.append((sim.history(truth=True), sim.summary()))
    assert runs[0] == runs[1]
    other = Simulator(config=WorldConfig(seed=12))
    other.run()
    assert other.history(truth=True) != runs[0][0]


def test_determinism_with_fixed_external_actions(make_sim):
    outs = []
    for _ in range(2):
        sim = make_sim(seed=4)
        external_turn(sim, A=[ResearchTech(tech_id="radio_systems")])
        external_turn(sim, A=[AttemptProject(proposal=Proposal(name="c", tags=["partial_solution"]))])
        outs.append(sim.history(truth=True))
    assert outs[0] == outs[1]


@pytest.mark.parametrize("seed", range(8))
def test_full_scenario_runs_to_completion_without_api_keys(seed):
    sim = Simulator(config=WorldConfig(seed=seed))
    summary = sim.run()
    assert sim.world.finished and sim.world.turn <= 12
    assert summary["constraint_records"] > 0
    assert not events(sim, "agent_error")
    assert events(sim, "simulation_finished")
    with pytest.raises(RuntimeError):
        sim.step()


def test_scarcity_is_real_country_a_cannot_buy_the_standard_solution(make_sim):
    """Even saving every unit of income for 12 turns, A can never afford prerequisites + standard solution."""
    w = make_sim().world
    a, rules = w.countries["A"], w.scenario.project
    total = a.resources + a.income.scaled(11)
    need = rules.standard.cost
    for t in w.graph.path_to(a.techs, ["radio_systems", *rules.standard.requires_techs]):
        need = need + w.graph.get(t).cost
    assert not total.covers(need)
    b = w.countries["B"]  # by contrast B can afford the prerequisites and the standard solution outright
    assert b.resources.covers(Resources(money=53, materials=26, research=28)) and b.resources.money >= need.money - 53


def test_resource_scale_and_per_country_override(make_sim):
    sim = make_sim(resource_scale=0.4, country_resource_scale={"B": 1.0})
    assert sim.world.countries["A"].resources.money == 28
    assert sim.world.countries["B"].resources.money == 150


def test_trade_moves_resources_without_creating_any(make_sim):
    sim = make_sim()
    a, d = sim.world.countries["A"], sim.world.countries["D"]
    a0, d0 = a.resources + a.income, d.resources + d.income
    external_turn(sim, A=[Trade(partner="D", give=Resources(money=30), receive=Resources(materials=10))])
    assert a.resources == a0 - Resources(money=30) + Resources(materials=10)
    assert d.resources == d0 + Resources(money=30) - Resources(materials=10)
    assert len(events(sim, "trade")) == 1


def test_unfair_or_impossible_trades_fail(make_sim):
    sim = make_sim()
    external_turn(sim, A=[Trade(partner="D", give=Resources(money=5), receive=Resources(materials=10))])
    assert events(sim, "trade_declined")
    external_turn(sim, A=[Trade(partner="D", give=Resources(money=5), receive=Resources(materials=10_000))])
    assert "cannot supply" in events(sim, "action_rejected")[-1].reason
    external_turn(sim, A=[Trade(partner="D", give=Resources(money=10_000), receive=Resources(materials=1))])
    assert "cannot afford" in events(sim, "action_rejected")[-1].reason


def test_crashing_agent_cannot_crash_the_engine(make_sim):
    class Broken(BaseKing):
        def decide(self, *a, **k):
            raise RuntimeError("boom")

        def respond_to_trade(self, *a, **k):
            return False

    sim = make_sim()
    sim.teams["A"].king = Broken()
    sim.step()
    assert events(sim, "agent_error")[0].role == "king"
    assert sim.world.turn == 2


def test_shocks_only_destroy_resources(make_sim):
    sim = make_sim(seed=2, shock_probability=1.0)
    before = {c: v.resources.total() + v.income.total() for c, v in sim.world.countries.items()}
    external_turn(sim)
    for cid, c in sim.world.countries.items():
        assert c.resources.total() <= before[cid]
    assert events(sim, "shock")


def test_king_does_not_burn_budget_on_prerequisites_for_unreachable_projects():
    """Regression: A used to research standard-solution-only techs it could never afford to use."""
    for seed in range(10):
        sim = Simulator(config=WorldConfig(seed=seed, resource_scale=0.4, shock_probability=0.0))
        sim.run()
        researched = {e.tech for e in events(sim, "technology_research") if e.country == "A"}
        assert not researched & {"advanced_electronics", "power_systems"}, (seed, researched)
