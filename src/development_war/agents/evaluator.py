"""Rule-based Evaluator: prices proposals with the public rules, adjusts for lessons, rejects the infeasible."""
from __future__ import annotations

from typing import Optional

from ..engine.country import CountryProfile
from ..engine.projects import Proposal, quote_proposal, required_techs
from ..engine.resources import Resources
from ..engine.technology import TechGraph
from ..information.intelligence import Observation
from .base import BaseEvaluator, Evaluation, adjusted_risk


def suggest_modification(obs: Observation, graph: TechGraph, proposal: Proposal, available: Resources) -> Optional[Proposal]:
    """Try adding one strategy tag so the proposal becomes feasible and affordable; prefer the lowest risk."""
    rules = obs.rules
    owned = set(obs.own.techs)
    best: Optional[tuple[float, int, Proposal]] = None
    if len(proposal.tags) >= rules.max_tags:
        return None
    for tag in sorted(rules.strategy_tags):
        if tag in proposal.tags:
            continue
        cand = proposal.model_copy(update=dict(tags=[*proposal.tags, tag], name=f"{proposal.name} + {tag}" if proposal.tags else tag))
        q = quote_proposal(rules, graph, owned, cand)
        if q.feasible and available.covers(q.cost):
            key = (adjusted_risk(obs, cand, q.est_risk), q.cost.total())
            if best is None or key < best[:2]:
                best = (key[0], key[1], cand)
    return best[2] if best else None


class RuleBasedEvaluator(BaseEvaluator):
    def __init__(self, profile: CountryProfile):
        self.profile = profile

    def evaluate(self, obs: Observation, proposals: list[Proposal]) -> list[Evaluation]:
        rules = obs.rules
        graph = TechGraph(obs.technologies)
        owned = set(obs.own.techs)
        have = obs.own.resources
        out: list[Evaluation] = []
        for i, p in enumerate(proposals):
            q = quote_proposal(rules, graph, owned, p)
            risk = adjusted_risk(obs, p, q.est_risk)
            missing = sorted(t for t in required_techs(rules, p) if t not in owned)
            affordable = have.covers(q.cost)
            concerns: list[str] = list(q.problems)
            if risk > 0.5:
                concerns.append(f"high failure risk ({risk:.0%})")
            suggested = None
            only_missing_techs = bool(missing) and len(q.problems) == 1
            if q.feasible and not affordable:
                concerns.append(f"unaffordable: short by {have.shortfall(q.cost).as_dict()}")
                suggested = suggest_modification(obs, graph, p, have)
                verdict = "modify" if suggested else "reject"
            elif q.feasible:
                verdict = "approve" if risk <= 0.8 else "reject"
            else:
                verdict = "reject"
                if only_missing_techs:
                    concerns.append("blocked until the missing technologies are researched")
            out.append(
                Evaluation(
                    proposal_index=i,
                    proposal=p,
                    feasible=q.feasible,
                    problems=q.problems,
                    missing_techs=missing,
                    cost=q.cost,
                    est_risk=risk,
                    est_progress=q.est_progress,
                    affordable=affordable,
                    verdict=verdict,
                    concerns=concerns,
                    suggested=suggested,
                )
            )
        return out
