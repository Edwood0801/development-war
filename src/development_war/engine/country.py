"""Country: authoritative per-country state (owned by the engine, never handed to agents directly)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .resources import Resources


class CountryProfile(BaseModel):
    name: str
    description: str = ""
    risk_tolerance: float
    caution: float
    intel_skill: float
    reserve_fraction: float = 0.0
    spy_probe_interval: int = 4
    trade_partners: list[str] = Field(default_factory=list)
    starting_resources: Resources
    income: Resources
    starting_techs: list[str] = Field(default_factory=list)


class Lesson(BaseModel):
    """Persistent memory produced by an attempt (failure *or* success)."""

    turn: int
    kind: Literal["project", "research"]
    outcome: Literal["failure", "success"]
    subject: str  # proposal signature or tech id
    tags: list[str] = Field(default_factory=list)
    reason: str = ""
    lesson: str = ""


@dataclass
class Country:
    id: str
    profile: CountryProfile
    resources: Resources
    income: Resources
    techs: set[str] = field(default_factory=set)
    project_progress: int = 0
    completed_turn: Optional[int] = None
    lessons: list[Lesson] = field(default_factory=list)
    # analysis counters
    project_attempts: int = 0
    project_failures: int = 0
    tech_attempts: int = 0
    tech_failures: int = 0
    spent: Resources = field(default_factory=Resources)
    tried_signatures: set[str] = field(default_factory=set)
    # what happened last turn (read only by the intelligence service)
    last_activity: dict = field(default_factory=dict)

    def spend(self, cost: Resources) -> None:
        self.resources = self.resources - cost  # raises InsufficientResources
        self.spent = self.spent + cost

    def receive(self, amount: Resources) -> None:
        self.resources = self.resources + amount
