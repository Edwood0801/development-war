"""Actions agents may request, and the validator that decides whether the engine will accept them.

Agents (or LLMs) only ever *request* actions. The simulator validates every request against the
authoritative world state and a per-turn working budget, so resource limits are enforced by code.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

from .projects import Proposal, quote_proposal
from .resources import Resources

if TYPE_CHECKING:  # pragma: no cover
    from .world import World


class Pass(BaseModel):
    type: Literal["pass"] = "pass"


class ResearchTech(BaseModel):
    type: Literal["research_tech"] = "research_tech"
    tech_id: str


class AttemptProject(BaseModel):
    type: Literal["attempt_project"] = "attempt_project"
    proposal: Proposal


class Trade(BaseModel):
    """Offer `give` to `partner` in exchange for `receive`. Executes only if the partner accepts."""

    type: Literal["trade"] = "trade"
    partner: str
    give: Resources
    receive: Resources


Action = Annotated[Union[Pass, ResearchTech, AttemptProject, Trade], Field(discriminator="type")]
_adapter = TypeAdapter(Action)


def parse_action(data: Any) -> Union[Pass, ResearchTech, AttemptProject, Trade]:
    """Parse an untrusted dict (e.g. from an LLM) into an Action. Raises pydantic.ValidationError."""
    return _adapter.validate_python(data)


class ValidationResult(BaseModel):
    ok: bool
    reason: str = ""
    charges: dict[str, Resources] = Field(default_factory=dict)  # what each country would pay


class ActionValidator:
    def validate(self, world: "World", country_id: str, action: Any, budget: dict[str, Resources]) -> ValidationResult:
        c = world.countries[country_id]
        mine = budget[country_id]

        if isinstance(action, Pass):
            return ValidationResult(ok=True)

        if isinstance(action, ResearchTech):
            ok, why = world.graph.can_research(c.techs, action.tech_id)
            if not ok:
                return ValidationResult(ok=False, reason=why)
            cost = world.graph.get(action.tech_id).cost
            if not mine.covers(cost):
                return ValidationResult(ok=False, reason=f"insufficient resources: need {cost.as_dict()}, have {mine.as_dict()}")
            return ValidationResult(ok=True, charges={country_id: cost})

        if isinstance(action, AttemptProject):
            if c.completed_turn is not None:
                return ValidationResult(ok=False, reason="project already completed")
            q = quote_proposal(world.scenario.project, world.graph, c.techs, action.proposal)
            if not q.feasible:
                return ValidationResult(ok=False, reason="; ".join(q.problems))
            if not mine.covers(q.cost):
                return ValidationResult(ok=False, reason=f"insufficient resources: need {q.cost.as_dict()}, have {mine.as_dict()}")
            return ValidationResult(ok=True, charges={country_id: q.cost})

        if isinstance(action, Trade):
            if action.partner not in world.countries or action.partner == country_id:
                return ValidationResult(ok=False, reason=f"invalid trade partner '{action.partner}'")
            if action.give.is_zero() or action.receive.is_zero():
                return ValidationResult(ok=False, reason="trade must give and receive something")
            if not mine.covers(action.give):
                return ValidationResult(ok=False, reason="cannot afford the resources offered")
            if not budget[action.partner].covers(action.receive):
                return ValidationResult(ok=False, reason="partner cannot supply the requested resources")
            return ValidationResult(ok=True, charges={})  # trade moves resources; committed after acceptance

        return ValidationResult(ok=False, reason=f"unknown action type {type(action).__name__}")
