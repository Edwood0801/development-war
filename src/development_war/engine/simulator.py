"""Turn engine. Runs the phases below in order; the order is data (`PHASES`) so it can be changed later.

Rules of the road:
  * Agents only receive `Observation`s built by the information layer.
  * Agents only *request* actions; every request is validated against the authoritative state.
  * Only this module mutates the world.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Union

from pydantic import ValidationError

from ..agents import CountryTeam, build_rule_based_team
from ..agents.base import Evaluation, SpyBrief
from ..information.intelligence import IntelligenceService, build_observation
from ..scenarios import load_long_range_communication
from .actions import ActionValidator, AttemptProject, Pass, ResearchTech, Trade, parse_action
from .country import Lesson
from .events import ConstraintRecord, Event, draw_shock
from .projects import Proposal, STANDARD, quote_proposal, resolve_attempt
from .resources import RESOURCE_NAMES, Resources
from .scenario import Scenario
from .world import World, WorldConfig

PHASES = (
    "world_update",
    "intelligence_update",
    "engineering_proposals",
    "engineering_evaluation",
    "king_decision",
    "action_validation",
    "action_execution",
    "resource_update",
    "technology_update",
    "outcome_recording",
    "memory_update",
    "advance_turn",
)


@dataclass
class Outcome:
    kind: str  # "tech" | "project"
    country: str
    subject: str
    cost: Resources
    success: bool
    reason: Optional[str] = None
    lesson: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    progress_gained: int = 0
    true_risk: Optional[float] = None
    tech_id: Optional[str] = None
    record: Optional[ConstraintRecord] = None


@dataclass
class _TurnState:
    proposals: dict[str, list[Proposal]] = field(default_factory=dict)
    evaluations: dict[str, list[Evaluation]] = field(default_factory=dict)
    briefs: dict[str, SpyBrief] = field(default_factory=dict)
    actions: dict[str, list] = field(default_factory=dict)
    accepted: list[tuple[str, Any]] = field(default_factory=list)
    outcomes: list[Outcome] = field(default_factory=list)
    activity: dict[str, dict] = field(default_factory=dict)
    external: set[str] = field(default_factory=set)


class Simulator:
    def __init__(
        self,
        scenario: Optional[Scenario] = None,
        config: Optional[WorldConfig] = None,
        teams: Optional[dict[str, CountryTeam]] = None,
        phases: Iterable[str] = PHASES,
    ):
        self.scenario = scenario or load_long_range_communication()
        self.world = World(self.scenario, config)
        self.teams = teams or {cid: build_rule_based_team(p) for cid, p in self.scenario.countries.items()}
        self.phases = tuple(phases)
        self.validator = ActionValidator()
        self.intel = IntelligenceService(self.world)
        self.pending: dict[str, list] = {}
        self.state = _TurnState()

    # ---- public API ------------------------------------------------------------------------
    def submit_actions(self, country: str, actions: list[Any]) -> None:
        """Take over `country` for the next turn: its internal team is skipped and these actions are used."""
        if country not in self.world.countries:
            raise KeyError(country)
        self.pending[country] = [a if hasattr(a, "type") else parse_action(a) for a in actions]

    def step(self) -> list[Event]:
        w = self.world
        if w.finished:
            raise RuntimeError("simulation already finished")
        start = len(w.log.all())
        self.state = _TurnState(external=set(self.pending))
        for name in self.phases:
            getattr(self, f"_phase_{name}")()
        return w.log.all()[start:]

    def run(self) -> dict:
        while not self.world.finished:
            self.step()
        return self.summary()

    def history(self, country: Optional[str] = None, truth: bool = False) -> list[dict]:
        log = self.world.log
        events = log.all() if truth else (log.visible_to(country) if country else log.public())
        return [e.model_dump(exclude_none=False) for e in events]

    def export_history(self, path: Union[str, Path], truth: bool = True) -> None:
        events = self.world.log.all() if truth else self.world.log.public()
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(e.model_dump_json() for e in events) + "\n", encoding="utf-8")

    def summary(self) -> dict:
        w = self.world
        out: dict[str, Any] = {"seed": w.config.seed, "turns_played": w.turn, "finished": w.finished, "countries": {}}
        for cid, c in sorted(w.countries.items()):
            out["countries"][cid] = {
                "completed_turn": c.completed_turn,
                "project_progress": c.project_progress,
                "project_attempts": c.project_attempts,
                "project_failures": c.project_failures,
                "tech_attempts": c.tech_attempts,
                "tech_failures": c.tech_failures,
                "distinct_approaches_tried": sorted(c.tried_signatures),
                "technologies": sorted(c.techs),
                "spent": c.spent.as_dict(),
                "final_resources": c.resources.as_dict(),
                "lessons": len(c.lessons),
            }
        done = [(c.completed_turn, cid) for cid, c in w.countries.items() if c.completed_turn is not None]
        out["first_to_complete"] = min(done)[1] if done else None
        out["constraint_records"] = len(w.constraint_records)
        return out

    # ---- helpers ---------------------------------------------------------------------------
    def _obs(self, cid: str):
        return build_observation(self.world, cid)

    def _call(self, cid: str, role: str, fn: Callable[[], Any], default: Any) -> Any:
        """Agents may be LLMs; a crashing or malformed agent must never crash the engine."""
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            self.world.log.add(self.world.turn, "agent_error", cid, visible_to=[cid], role=role, error=f"{type(exc).__name__}: {exc}")
            return default

    def _log(self, event: str, country: Optional[str] = None, visible_to: Optional[list[str]] = None, **data: Any) -> None:
        self.world.log.add(self.world.turn, event, country, visible_to, **data)

    # ---- phases ----------------------------------------------------------------------------
    def _phase_world_update(self) -> None:
        w = self.world
        prob = self.scenario.events.probability if w.config.shock_probability is None else w.config.shock_probability
        self._log("turn_start", turn_number=w.turn)
        for cid, c in sorted(w.countries.items()):
            c.receive(c.income)
            self._log("income", cid, [cid], amount=c.income.as_dict())
            shock = draw_shock(w.rng("shock", w.turn, cid), prob, self.scenario.events.shocks)
            if shock:
                have = getattr(c.resources, shock.resource)
                loss = min(have, max(1, int(have * shock.loss_fraction))) if have else 0
                c.resources = c.resources - Resources(**{shock.resource: loss})
                self._log("shock", cid, [cid], shock=shock.name, resource=shock.resource, lost=loss, description=shock.description)

    def _phase_intelligence_update(self) -> None:
        w = self.world
        for cid in sorted(w.countries):
            c = w.countries[cid]
            team = self.teams[cid]
            task = None
            if cid not in self.state.external:
                from ..agents.base import SpyTask

                task = self._call(cid, "spy", lambda: team.spy.plan(self._obs(cid)), SpyTask())
            focus = task.focus if task and task.focus in w.countries and task.focus != cid else None
            deep = bool(task and task.deep and focus)
            if deep:
                cost = self.scenario.probe_cost
                if c.resources.covers(cost):
                    c.spend(cost)
                    self._log("probe", cid, [cid], target=focus, cost=cost.as_dict())
                else:
                    deep = False
                    self._log("probe_unaffordable", cid, [cid], target=focus)
            for oid in sorted(w.countries):
                if oid == cid:
                    continue
                rep = self.intel.gather(cid, oid, deep=deep and oid == focus)
                w.knowledge[cid].append(rep)
                self._log("intel_report", cid, [cid], report=rep.model_dump(mode="json"))
            if cid not in self.state.external:
                from ..agents.base import SpyBrief as _B

                self.state.briefs[cid] = self._call(cid, "spy", lambda: team.spy.brief(self._obs(cid)), _B(summary="no brief"))

    def _phase_engineering_proposals(self) -> None:
        for cid in sorted(self.world.countries):
            if cid in self.state.external:
                continue
            team = self.teams[cid]
            props = self._call(cid, "inventor", lambda: team.inventor.propose(self._obs(cid)), [])
            self.state.proposals[cid] = props
            self._log("proposals", cid, [cid], proposals=[{"name": p.name, "tags": p.tags, "uses_techs": p.uses_techs} for p in props])

    def _phase_engineering_evaluation(self) -> None:
        for cid in sorted(self.world.countries):
            if cid in self.state.external:
                continue
            team = self.teams[cid]
            props = self.state.proposals.get(cid, [])
            evs = self._call(cid, "evaluator", lambda: team.evaluator.evaluate(self._obs(cid), props), [])
            self.state.evaluations[cid] = evs
            self._log(
                "evaluation", cid, [cid],
                evaluations=[
                    {"name": e.proposal.name, "verdict": e.verdict, "cost": e.cost.as_dict(), "est_risk": e.est_risk,
                     "est_progress": e.est_progress, "affordable": e.affordable, "missing_techs": e.missing_techs,
                     "suggested": e.suggested.name if e.suggested else None}
                    for e in evs
                ],
            )

    def _phase_king_decision(self) -> None:
        from ..agents.base import SpyBrief as _B

        for cid in sorted(self.world.countries):
            if cid in self.state.external:
                acts = self.pending.get(cid, [])
            else:
                team = self.teams[cid]
                brief = self.state.briefs.get(cid, _B(summary="no brief"))
                acts = self._call(cid, "king", lambda: team.king.decide(self._obs(cid), self.state.evaluations.get(cid, []), brief), [Pass()])
            self.state.actions[cid] = list(acts)
            self._log("decision", cid, [cid], source="external" if cid in self.state.external else "team", actions=[a.model_dump(mode="json") for a in acts])
        self.pending.clear()

    def _phase_action_validation(self) -> None:
        w = self.world
        budget = {cid: c.resources for cid, c in w.countries.items()}
        for cid in sorted(w.countries):
            for idx, action in enumerate(self.state.actions.get(cid, [])):
                if idx >= w.config.max_actions_per_turn:
                    self._log("action_rejected", cid, [cid], action=action.model_dump(mode="json"), reason="too many actions this turn")
                    continue
                vr = self.validator.validate(w, cid, action, budget)
                if not vr.ok:
                    self._log("action_rejected", cid, [cid], action=action.model_dump(mode="json"), reason=vr.reason)
                    continue
                if isinstance(action, Trade):
                    ptm = self.teams[action.partner]
                    accepted = self._call(
                        action.partner, "king",
                        lambda: ptm.king.respond_to_trade(self._obs(action.partner), cid, action.give, action.receive), False,
                    )
                    if not accepted:
                        self._log("trade_declined", cid, [cid, action.partner], partner=action.partner, give=action.give.as_dict(), receive=action.receive.as_dict())
                        continue
                    budget[cid] = budget[cid] - action.give + action.receive
                    budget[action.partner] = budget[action.partner] - action.receive + action.give
                for payer, charge in vr.charges.items():
                    budget[payer] = budget[payer] - charge
                self.state.accepted.append((cid, action))

    def _phase_action_execution(self) -> None:
        w = self.world
        rules = self.scenario.project
        attempts_this_turn: dict[str, int] = {}
        for cid, action in self.state.accepted:
            c = w.countries[cid]
            if isinstance(action, Pass):
                continue
            if isinstance(action, Trade):
                p = w.countries[action.partner]
                c.resources = c.resources - action.give + action.receive
                p.resources = p.resources - action.receive + action.give
                self._log("trade", cid, [cid, action.partner], partner=action.partner, gave=action.give.as_dict(), received=action.receive.as_dict())
            elif isinstance(action, ResearchTech):
                tech = w.graph.get(action.tech_id)
                c.spend(tech.cost)
                c.tech_attempts += 1
                rng = w.rng("research", w.turn, cid, tech.id)
                ok = rng.random() >= tech.risk
                self.state.outcomes.append(
                    Outcome("tech", cid, tech.id, tech.cost, ok, None if ok else "experiment did not converge",
                            None if ok else f"{tech.name} needs more research effort than one attempt", tech_id=tech.id)
                )
            elif isinstance(action, AttemptProject):
                prop = action.proposal
                q = quote_proposal(rules, w.graph, c.techs, prop)
                available = c.resources
                c.spend(q.cost)
                c.project_attempts += 1
                c.tried_signatures.add(prop.signature)
                n = attempts_this_turn[cid] = attempts_this_turn.get(cid, 0) + 1
                rng = w.rng("project", w.turn, cid, prop.signature, n)
                res = resolve_attempt(rules, q, prop, w.hidden.risk_bias, w.hidden.progress_bias, rng)
                std = rules.standard.cost
                ratios = [getattr(available, r) / getattr(std, r) for r in RESOURCE_NAMES if getattr(std, r) > 0]
                rec = ConstraintRecord(
                    turn=w.turn, country=cid, original_problem=self.scenario.objective,
                    normal_solution_cost=std, available_resources=available, scarcity_ratio=round(min(ratios), 3),
                    proposed_solution=prop.name, alternative_tags=list(prop.tags), cost=q.cost, estimated_risk=q.est_risk,
                )
                w.constraint_records.append(rec)
                self.state.outcomes.append(
                    Outcome("project", cid, prop.signature, q.cost, res.success, res.reason, res.lesson, list(prop.tags),
                            res.progress_gained, res.true_risk, record=rec)
                )
                self.state.activity.setdefault(cid, {})["project_attempt"] = True

    def _phase_resource_update(self) -> None:
        w = self.world
        for cid, c in sorted(w.countries.items()):
            assert all(getattr(c.resources, r) >= 0 for r in RESOURCE_NAMES)
            self._log("resources_snapshot", cid, [], resources=c.resources.as_dict(), spent_total=c.spent.as_dict())

    def _phase_technology_update(self) -> None:
        for o in self.state.outcomes:
            if o.kind == "tech" and o.success:
                self.world.countries[o.country].techs.add(o.tech_id)
                self.state.activity.setdefault(o.country, {}).setdefault("techs_acquired", []).append(o.tech_id)

    def _phase_outcome_recording(self) -> None:
        w = self.world
        rules = self.scenario.project
        for o in self.state.outcomes:
            c = w.countries[o.country]
            if o.kind == "tech":
                if not o.success:
                    c.tech_failures += 1
                self._log("technology_research", o.country, [o.country], tech=o.tech_id, cost=o.cost.as_dict(), success=o.success, reason=o.reason, lesson=o.lesson)
                continue
            if o.success:
                c.project_progress = min(rules.target_progress, c.project_progress + o.progress_gained)
            else:
                c.project_failures += 1
            rec = o.record
            rec.result = "success" if o.success else "failure"
            rec.progress_gained = o.progress_gained
            rec.true_risk = o.true_risk
            self._log(
                "research_attempt", o.country, [o.country], project=rules.id, approach=o.subject, tags=o.tags,
                cost=o.cost.as_dict(), success=o.success, reason=o.reason, lesson=o.lesson,
                progress_gained=o.progress_gained, progress_total=c.project_progress, true_risk=o.true_risk,
            )
            self._log("constraint_record", o.country, [], record=rec.model_dump(mode="json"))
            if c.project_progress >= rules.target_progress and c.completed_turn is None:
                c.completed_turn = w.turn
                self._log("project_completed", o.country, None, project=rules.id)

    def _phase_memory_update(self) -> None:
        w = self.world
        for o in self.state.outcomes:
            c = w.countries[o.country]
            if o.kind == "tech":
                if o.success:
                    continue
                les = Lesson(turn=w.turn, kind="research", outcome="failure", subject=o.subject, reason=o.reason or "", lesson=o.lesson or "")
            elif o.success:
                les = Lesson(turn=w.turn, kind="project", outcome="success", subject=o.subject, tags=o.tags,
                             lesson=f"'{o.subject}' worked (+{o.progress_gained} progress)")
            else:
                les = Lesson(turn=w.turn, kind="project", outcome="failure", subject=o.subject, tags=o.tags,
                             reason=o.reason or "", lesson=o.lesson or "")
            c.lessons.append(les)
            if o.record is not None:
                o.record.lessons.append(les.lesson)
            self._log("lesson_recorded", o.country, [o.country], entry=les.model_dump(mode="json"))

    def _phase_advance_turn(self) -> None:
        w = self.world
        for cid, c in w.countries.items():
            c.last_activity = self.state.activity.get(cid, {})
        self._log("turn_end", turn_number=w.turn)
        if w.turn >= w.max_turns or all(c.completed_turn is not None for c in w.countries.values()):
            w.finished = True
            self._log("simulation_finished", turns_played=w.turn)
        else:
            w.turn += 1
