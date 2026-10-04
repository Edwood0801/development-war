"""Rule-based Inventor: generates alternative approaches, avoiding ones that already failed repeatedly."""
from __future__ import annotations

from collections import Counter

from ..engine.country import CountryProfile
from ..engine.projects import Proposal, quote_proposal
from ..engine.technology import TechGraph
from ..information.intelligence import Observation
from .base import BaseInventor

# Candidate tag combinations, in the order an inventor would think of them. Unknown tags are skipped,
# so scenarios with different tag sets still work.
LIBRARY: list[tuple[str, ...]] = [
    ("simplify_design",),
    ("reuse_infrastructure", "simplify_design"),
    ("novel_architecture", "simplify_design"),
    ("combine_technologies",),
    ("substitute_materials",),
    ("partial_solution",),
    ("novel_architecture",),
    ("reuse_infrastructure",),
    ("reuse_infrastructure", "partial_solution"),
    ("combine_technologies", "simplify_design"),
]


def pick_techs(obs: Observation, limit: int = 3) -> list[str]:
    """Owned technologies from distinct categories, advanced and expensive first."""
    owned = set(obs.own.techs)
    techs = sorted((t for t in obs.technologies if t.id in owned), key=lambda t: (not t.is_advanced, -t.cost.total(), t.id))
    seen: set[str] = set()
    out: list[str] = []
    for t in techs:
        if t.category not in seen:
            seen.add(t.category)
            out.append(t.id)
        if len(out) == limit:
            break
    return sorted(out)


class RuleBasedInventor(BaseInventor):
    def __init__(self, profile: CountryProfile, max_alternatives: int = 4):
        self.profile = profile
        self.max_alternatives = max_alternatives

    def propose(self, obs: Observation) -> list[Proposal]:
        rules = obs.rules
        graph = TechGraph(obs.technologies)
        owned = set(obs.own.techs)
        uses = pick_techs(obs)
        proposals = [Proposal(name="Standard development", description=rules.standard.description)]

        failures = Counter(l.subject for l in obs.own.lessons if l.kind == "project" and l.outcome == "failure")
        tried = {l.subject for l in obs.own.lessons if l.kind == "project"}
        cands = []
        for order, combo in enumerate(LIBRARY):
            if any(t not in rules.strategy_tags for t in combo):
                continue
            p = Proposal(name=" + ".join(combo), tags=list(combo), uses_techs=uses, description="Alternative approach")
            if failures[p.signature] >= 2:
                continue  # adapt: stop repeating an approach that keeps failing
            q = quote_proposal(rules, graph, owned, p)
            bold = self.profile.risk_tolerance >= 0.5
            cands.append(((failures[p.signature], p.signature in tried, -q.est_risk if bold else q.est_risk, order), p))
        cands.sort(key=lambda x: x[0])  # untried and fewest-failures first, then personality
        proposals += [p for _, p in cands[: self.max_alternatives]]
        return proposals
