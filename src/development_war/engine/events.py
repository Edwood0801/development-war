"""Event log and the scarcity-experiment record.

Visibility: `visible_to=None` -> public; a list -> only those countries (plus admin);
`[]` -> ground truth only (never shown to any country).
"""
from __future__ import annotations

import random
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .resources import Resources


class Event(BaseModel):
    model_config = ConfigDict(extra="allow")

    turn: int
    country: Optional[str] = None
    event: str
    visible_to: Optional[list[str]] = None

    def visible(self, country: Optional[str]) -> bool:
        if self.visible_to is None:
            return True
        return country is not None and country in self.visible_to


class EventLog:
    def __init__(self) -> None:
        self._events: list[Event] = []

    def add(self, turn: int, event: str, country: Optional[str] = None, visible_to: Optional[list[str]] = None, **data: Any) -> Event:
        ev = Event(turn=turn, country=country, event=event, visible_to=visible_to, **data)
        self._events.append(ev)
        return ev

    def all(self) -> list[Event]:
        return list(self._events)

    def public(self) -> list[Event]:
        return [e for e in self._events if e.visible_to is None]

    def visible_to(self, country: str) -> list[Event]:
        return [e for e in self._events if e.visible_to is None or country in e.visible_to]


class ConstraintRecord(BaseModel):
    """One 'desperate times' data point: the normal solution vs what was affordable, and what the country did."""

    turn: int
    country: str
    original_problem: str
    normal_solution_cost: Resources
    available_resources: Resources
    scarcity_ratio: float  # min over resources of available/required for the normal solution (<1 = cannot afford)
    proposed_solution: str  # proposal name
    alternative_tags: list[str]
    cost: Resources
    estimated_risk: float
    true_risk: Optional[float] = None
    result: str = "pending"  # success | failure
    progress_gained: int = 0
    lessons: list[str] = Field(default_factory=list)


def draw_shock(rng: random.Random, probability: float, shocks: list) -> Optional[Any]:
    """Return a shock definition or None. Shocks only destroy resources; they never create them."""
    if not shocks or rng.random() >= probability:
        return None
    return rng.choice(shocks)
