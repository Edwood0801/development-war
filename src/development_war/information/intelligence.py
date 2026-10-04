"""Information layer: the ONLY place where hidden world state is turned into something agents may see.

World (truth)  ->  IntelligenceService / build_observation  ->  Observation (what a country knows)
Agents only ever receive `Observation` objects, never `World`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from ..engine.country import Lesson
from ..engine.projects import ProjectRules
from ..engine.resources import RESOURCE_NAMES, Resources
from ..engine.technology import Technology

if TYPE_CHECKING:  # pragma: no cover
    from ..engine.world import World


class IntelReport(BaseModel):
    turn: int
    source: str
    target: str
    resource_estimates: dict[str, tuple[int, int]]  # (low, high) ranges, never exact truth
    observations: list[str]
    confidence: float
    deep: bool = False


class OwnState(BaseModel):
    resources: Resources
    income: Resources
    techs: list[str]
    project_progress: int
    completed_turn: Optional[int]
    lessons: list[Lesson]


class OtherCountryView(BaseModel):
    id: str
    name: str
    resource_estimates: Optional[dict[str, tuple[int, int]]] = None
    observations: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    last_report_turn: Optional[int] = None


class Observation(BaseModel):
    country: str
    turn: int
    max_turns: int
    turns_remaining: int
    finished: bool
    objective: str
    rules: ProjectRules
    technologies: list[Technology]
    own: OwnState
    others: dict[str, OtherCountryView]
    recent_intel: list[IntelReport]
    public_events: list[dict]
    own_events: list[dict]


class IntelligenceService:
    """Generates noisy reports from truth. Runs inside the engine, never inside an agent."""

    def __init__(self, world: "World"):
        self.world = world

    def gather(self, source: str, target: str, deep: bool) -> IntelReport:
        w = self.world
        src, tgt = w.countries[source], w.countries[target]
        rng = w.rng("intel", w.turn, source, target)
        skill = src.profile.intel_skill * (1.8 if deep else 1.0) / max(0.1, w.config.information_noise)
        sigma = 0.20 / skill
        half = 0.35 / skill
        estimates: dict[str, tuple[int, int]] = {}
        for name in RESOURCE_NAMES:
            true = getattr(tgt.resources, name)
            center = true * (1 + rng.gauss(0, sigma))
            lo = max(0, int(center - true * half))
            hi = max(lo + 1, int(center + true * half) + 1)
            estimates[name] = (lo, hi)
        confidence = round(max(0.2, min(0.95, 0.30 + 0.25 * skill)), 2)
        return IntelReport(
            turn=w.turn,
            source=source,
            target=target,
            resource_estimates=estimates,
            observations=self._observations(tgt, confidence, rng),
            confidence=confidence,
            deep=deep,
        )

    def _observations(self, tgt, confidence: float, rng) -> list[str]:
        act = tgt.last_activity
        cats = sorted(self.world.graph.get(t).category for t in act.get("techs_acquired", []))
        notes: list[str] = []
        if cats:
            cat = cats[0]
            if rng.random() < (1 - confidence) * 0.5:  # unreliable source: wrong field
                cat = rng.choice(sorted({t.category for t in self.world.graph.all()}))
            notes.append(f"{tgt.profile.name} appears to have made scientific progress in {cat}")
        if act.get("project_attempt"):
            notes.append(f"{tgt.profile.name} shows unusual activity around communication infrastructure")
        if not notes:
            notes.append(f"No notable activity observed in {tgt.profile.name}")
            if rng.random() < (1 - confidence) * 0.25:  # false lead
                notes.append(f"Rumours of a secret programme in {tgt.profile.name} (unverified)")
        return notes


def build_observation(world: "World", country_id: str, recent_intel_turns: int = 3) -> Observation:
    c = world.countries[country_id]
    reports = world.knowledge[country_id]
    others: dict[str, OtherCountryView] = {}
    for oid, other in sorted(world.countries.items()):
        if oid == country_id:
            continue
        latest = [r for r in reports if r.target == oid]
        view = OtherCountryView(id=oid, name=other.profile.name)
        if latest:
            r = max(latest, key=lambda x: (x.turn, x.deep))
            view = view.model_copy(
                update=dict(
                    resource_estimates=r.resource_estimates,
                    observations=r.observations,
                    confidence=r.confidence,
                    last_report_turn=r.turn,
                )
            )
        others[oid] = view
    return Observation(
        country=country_id,
        turn=world.turn,
        max_turns=world.max_turns,
        turns_remaining=max(0, world.max_turns - world.turn + 1),
        finished=world.finished,
        objective=world.scenario.objective,
        rules=world.scenario.project,
        technologies=world.graph.all(),
        own=OwnState(
            resources=c.resources,
            income=c.income,
            techs=sorted(c.techs),
            project_progress=c.project_progress,
            completed_turn=c.completed_turn,
            lessons=list(c.lessons),
        ),
        others=others,
        recent_intel=[r for r in reports if r.turn > world.turn - recent_intel_turns],
        public_events=[e.model_dump() for e in world.log.public()][-20:],
        own_events=[e.model_dump() for e in world.log.visible_to(country_id) if e.visible_to is not None][-30:],
    )
