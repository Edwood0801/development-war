"""Scenario definition (pure data). `Scenario.rules` is public; `countries` setup is private to the engine."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from .country import CountryProfile
from .projects import ProjectRules
from .resources import RESOURCE_NAMES, Resources
from .technology import TechGraph, Technology


class Shock(BaseModel):
    name: str
    resource: str
    loss_fraction: float
    description: str = ""


class EventConfig(BaseModel):
    probability: float = 0.0
    shocks: list[Shock] = Field(default_factory=list)


class Scenario(BaseModel):
    id: str
    title: str
    objective: str
    max_turns: int
    probe_cost: Resources = Field(default_factory=Resources)
    events: EventConfig = Field(default_factory=EventConfig)
    technologies: list[Technology]
    project: ProjectRules
    countries: dict[str, CountryProfile]

    def tech_graph(self) -> TechGraph:
        return TechGraph(self.technologies)

    def validate_consistency(self) -> None:
        graph = self.tech_graph()
        referenced = set(self.project.required_for_any_attempt) | set(self.project.standard.requires_techs)
        for tag in self.project.strategy_tags.values():
            referenced |= set(tag.requires_techs)
        for c in self.countries.values():
            referenced |= set(c.starting_techs)
        for t in referenced:
            if t not in graph:
                raise ValueError(f"scenario references unknown technology '{t}'")
        for s in self.events.shocks:
            if s.resource not in RESOURCE_NAMES:
                raise ValueError(f"shock {s.name} targets unknown resource {s.resource}")


def load_scenario_file(path: str | Path) -> Scenario:
    sc = Scenario.model_validate(json.loads(Path(path).read_text()))
    sc.validate_consistency()
    return sc
