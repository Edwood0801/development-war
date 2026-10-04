"""Agent roles as abstract interfaces. Agents see only `Observation`, never the world.

Anything implementing these interfaces (rule-based, LLM-backed, human, scripted) can drive a country.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field

from ..engine.actions import Action
from ..engine.projects import Proposal
from ..engine.resources import Resources
from ..information.intelligence import Observation


class Evaluation(BaseModel):
    proposal_index: int
    proposal: Proposal
    feasible: bool
    problems: list[str] = Field(default_factory=list)
    missing_techs: list[str] = Field(default_factory=list)
    cost: Resources
    est_risk: float  # includes this country's own lessons
    est_progress: int
    affordable: bool
    verdict: Literal["approve", "modify", "reject"]
    concerns: list[str] = Field(default_factory=list)
    suggested: Optional[Proposal] = None


class SpyTask(BaseModel):
    focus: Optional[str] = None
    deep: bool = False


class SpyBrief(BaseModel):
    summary: str
    notes: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None


class BaseInventor(ABC):
    @abstractmethod
    def propose(self, obs: Observation) -> list[Proposal]: ...


class BaseEvaluator(ABC):
    @abstractmethod
    def evaluate(self, obs: Observation, proposals: list[Proposal]) -> list[Evaluation]: ...


class BaseSpy(ABC):
    @abstractmethod
    def plan(self, obs: Observation) -> SpyTask: ...

    @abstractmethod
    def brief(self, obs: Observation) -> SpyBrief: ...


class BaseKing(ABC):
    @abstractmethod
    def decide(self, obs: Observation, evaluations: list[Evaluation], brief: SpyBrief) -> list[Action]: ...

    @abstractmethod
    def respond_to_trade(self, obs: Observation, proposer: str, offered_to_me: Resources, asked_from_me: Resources) -> bool: ...


@dataclass
class CountryTeam:
    king: BaseKing
    inventor: BaseInventor
    evaluator: BaseEvaluator
    spy: BaseSpy


def lesson_risk_adjustment(obs: Observation, proposal: Proposal) -> float:
    """Shift a public risk estimate using this country's own memory: failures raise it, successes lower it."""
    keys = list(proposal.tags) if proposal.tags else ["standard"]
    adj = 0.0
    for k in keys:
        f = s = 0
        for les in obs.own.lessons:
            if les.kind != "project":
                continue
            hit = (k in les.tags) if k != "standard" else (les.subject == "standard")
            if hit:
                f += les.outcome == "failure"
                s += les.outcome == "success"
        adj += min(0.2, 0.05 * f) - min(0.09, 0.03 * s)
    return max(-0.1, min(0.25, adj))


def adjusted_risk(obs: Observation, proposal: Proposal, est_risk: float) -> float:
    return round(max(obs.rules.risk_floor, min(obs.rules.risk_ceiling, est_risk + lesson_risk_adjustment(obs, proposal))), 3)
