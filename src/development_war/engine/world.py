"""Authoritative world state. Agents never touch this object; the simulator mutates it after validation."""
from __future__ import annotations

import random
from typing import Optional

from pydantic import BaseModel, Field

from ..information.intelligence import IntelReport
from .country import Country
from .events import ConstraintRecord, EventLog
from .scenario import Scenario


class WorldConfig(BaseModel):
    seed: int = 0
    max_turns: Optional[int] = None  # default: scenario value
    resource_scale: float = 1.0  # applied to starting resources AND income
    country_resource_scale: dict[str, float] = Field(default_factory=dict)  # overrides per country
    information_noise: float = 1.0  # >1 = noisier intelligence (experiment E)
    shock_probability: Optional[float] = None  # None = scenario default; 0 disables
    max_actions_per_turn: int = 4


class HiddenState(BaseModel):
    """Per-world truths no agent can read: how risky/productive each approach *really* is."""

    risk_bias: dict[str, float]
    progress_bias: dict[str, float]


class World:
    def __init__(self, scenario: Scenario, config: Optional[WorldConfig] = None):
        self.scenario = scenario
        self.config = config or WorldConfig()
        self.graph = scenario.tech_graph()
        self.max_turns = self.config.max_turns or scenario.max_turns
        self.turn = 1
        self.finished = False
        self.log = EventLog()
        self.constraint_records: list[ConstraintRecord] = []
        self.countries: dict[str, Country] = {}
        self.knowledge: dict[str, list[IntelReport]] = {}

        for cid in sorted(scenario.countries):
            prof = scenario.countries[cid]
            scale = self.config.country_resource_scale.get(cid, self.config.resource_scale)
            self.countries[cid] = Country(
                id=cid,
                profile=prof,
                resources=prof.starting_resources.scaled(scale),
                income=prof.income.scaled(scale),
                techs=set(prof.starting_techs),
            )
            self.knowledge[cid] = []

        rng = self.rng("hidden")
        rules = scenario.project
        keys = ["standard"] + sorted(rules.strategy_tags)
        self.hidden = HiddenState(
            risk_bias={k: round(rng.uniform(*rules.hidden_risk_bias_range), 3) for k in keys},
            progress_bias={k: round(rng.uniform(*rules.hidden_progress_bias_range), 3) for k in keys},
        )
        self.log.add(0, "world_created", visible_to=[], seed=self.config.seed, hidden=self.hidden.model_dump())

    def rng(self, stream: str, *keys) -> random.Random:
        """Independent deterministic stream: same seed + same keys => same numbers."""
        return random.Random("|".join([str(self.config.seed), stream, *map(str, keys)]))

    def truth(self) -> dict:
        """Full ground truth. For admin/analysis only."""
        return {
            "turn": self.turn,
            "finished": self.finished,
            "hidden": self.hidden.model_dump(),
            "countries": {
                cid: {
                    "resources": c.resources.as_dict(),
                    "income": c.income.as_dict(),
                    "techs": sorted(c.techs),
                    "project_progress": c.project_progress,
                    "completed_turn": c.completed_turn,
                    "project_attempts": c.project_attempts,
                    "project_failures": c.project_failures,
                }
                for cid, c in self.countries.items()
            },
        }
