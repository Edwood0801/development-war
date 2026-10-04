"""Project rules: how a proposed approach to the scenario objective is priced and resolved.

Costs and *estimated* risk are public and deterministic (`quote_proposal`).
The *true* outcome additionally depends on hidden per-world biases (see `world.HiddenState`),
so agents can be wrong about risk and must learn from failures.
"""
from __future__ import annotations

import random
from typing import Optional

from pydantic import BaseModel, Field

from .resources import Resources
from .technology import TechGraph

STANDARD = "standard"


class StrategyTag(BaseModel):
    description: str
    cost_mult: float
    risk_delta: float
    progress_mult: float
    progress_variance: float = 0.0
    requires_techs: list[str] = Field(default_factory=list)
    min_techs_used: int = 0  # distinct categories among `uses_techs`


class StandardSolution(BaseModel):
    description: str = "Conventional full-scale development"
    requires_techs: list[str]
    cost: Resources
    progress: int
    base_risk: float


class FailureReason(BaseModel):
    reason: str
    lesson: str


class ProjectRules(BaseModel):
    id: str
    name: str
    description: str
    target_progress: int = 100
    required_for_any_attempt: list[str] = Field(default_factory=list)
    standard: StandardSolution
    strategy_tags: dict[str, StrategyTag]
    failure_reasons: dict[str, list[FailureReason]]
    tech_discount_per_tech: float = 0.04
    tech_discount_cap: float = 0.12
    cost_floor_mult: float = 0.2
    max_tags: int = 3
    risk_floor: float = 0.03
    risk_ceiling: float = 0.90


class Proposal(BaseModel):
    """An approach to the project. No tags = the conventional ('standard') solution."""

    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    uses_techs: list[str] = Field(default_factory=list)

    @property
    def signature(self) -> str:
        return "+".join(sorted(self.tags)) if self.tags else STANDARD


class Quote(BaseModel):
    feasible: bool
    problems: list[str] = Field(default_factory=list)
    cost: Resources
    est_risk: float
    est_progress: int


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def required_techs(rules: ProjectRules, p: Proposal) -> set[str]:
    """Technologies a country must already own before it may attempt this proposal."""
    needed = set(rules.required_for_any_attempt)
    if not p.tags:
        needed |= set(rules.standard.requires_techs)
    for t in p.tags:
        if t in rules.strategy_tags:
            needed |= set(rules.strategy_tags[t].requires_techs)
    return needed


def quote_proposal(rules: ProjectRules, graph: TechGraph, owned: set[str] | frozenset[str], p: Proposal) -> Quote:
    problems: list[str] = []
    std = rules.standard

    if len(p.tags) > rules.max_tags:
        problems.append(f"too many strategy tags (max {rules.max_tags})")
    if len(set(p.tags)) != len(p.tags):
        problems.append("duplicate strategy tags")
    unknown = [t for t in p.tags if t not in rules.strategy_tags]
    if unknown:
        problems.append(f"unknown strategy tags: {', '.join(sorted(unknown))}")
    for tech in p.uses_techs:
        if tech not in graph:
            problems.append(f"unknown technology '{tech}'")
        elif tech not in owned:
            problems.append(f"uses technology not acquired: '{tech}'")

    missing = sorted(n for n in required_techs(rules, p) if n not in owned)
    if missing:
        problems.append(f"missing required technologies: {', '.join(missing)}")

    known_tags = [rules.strategy_tags[t] for t in p.tags if t in rules.strategy_tags]
    for t in p.tags:
        tag = rules.strategy_tags.get(t)
        if tag and tag.min_techs_used:
            cats = {graph.get(x).category for x in p.uses_techs if x in graph and x in owned}
            if len(cats) < tag.min_techs_used:
                problems.append(f"'{t}' needs technologies from at least {tag.min_techs_used} categories")

    cost_mult = 1.0
    prog_mult = 1.0
    risk = std.base_risk
    for tag in known_tags:
        cost_mult *= tag.cost_mult
        prog_mult *= tag.progress_mult
        risk += tag.risk_delta
    if known_tags:
        advanced = {x for x in p.uses_techs if x in graph and x in owned and graph.get(x).is_advanced}
        discount = min(rules.tech_discount_cap, rules.tech_discount_per_tech * len(advanced))
        cost_mult = max(rules.cost_floor_mult, cost_mult * (1 - discount))
    cost = std.cost.scaled(cost_mult, up=True)
    progress = int(round(std.progress * prog_mult))
    return Quote(
        feasible=not problems,
        problems=problems,
        cost=cost,
        est_risk=round(_clamp(risk, rules.risk_floor, rules.risk_ceiling), 3),
        est_progress=progress,
    )


class AttemptOutcome(BaseModel):
    success: bool
    progress_gained: int
    true_risk: float
    reason: Optional[str] = None
    lesson: Optional[str] = None


def resolve_attempt(
    rules: ProjectRules,
    quote: Quote,
    proposal: Proposal,
    risk_bias: dict[str, float],
    progress_bias: dict[str, float],
    rng: random.Random,
) -> AttemptOutcome:
    """Roll the true outcome. Hidden biases are applied here and only here."""
    keys = list(proposal.tags) if proposal.tags else [STANDARD]
    true_risk = _clamp(
        quote.est_risk + sum(risk_bias.get(k, 0.0) for k in keys), rules.risk_floor, rules.risk_ceiling
    )
    if rng.random() < true_risk:
        k = rng.choice(sorted(keys))
        fr = rules.failure_reasons.get(k) or rules.failure_reasons.get(STANDARD) or []
        pick = rng.choice(fr) if fr else FailureReason(reason="unknown failure", lesson="approach failed for unknown reasons")
        return AttemptOutcome(
            success=False, progress_gained=0, true_risk=round(true_risk, 3), reason=pick.reason, lesson=pick.lesson
        )
    variance = max((rules.strategy_tags[t].progress_variance for t in proposal.tags if t in rules.strategy_tags), default=0.0)
    mult = 1.0
    for k in keys:
        mult *= progress_bias.get(k, 1.0)
    mult *= 1.0 + rng.uniform(-variance, variance)
    gained = max(1, int(round(quote.est_progress * mult)))
    return AttemptOutcome(success=True, progress_gained=gained, true_risk=round(true_risk, 3))
