"""Finite resources. The only way to obtain resources is income, trade, or a world event."""
from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

RESOURCE_NAMES = ("money", "materials", "research")


class InsufficientResources(Exception):
    """Raised when an operation would drive any resource below zero."""

    def __init__(self, required: "Resources", available: "Resources"):
        self.required = required
        self.available = available
        super().__init__(f"insufficient resources: need {required.as_dict()}, have {available.as_dict()}")


class Resources(BaseModel):
    """Immutable bundle of the three V0.1 resources (integers, for determinism)."""

    model_config = ConfigDict(frozen=True)

    money: int = Field(0, ge=0)
    materials: int = Field(0, ge=0)
    research: int = Field(0, ge=0)

    def as_dict(self) -> dict[str, int]:
        return {n: getattr(self, n) for n in RESOURCE_NAMES}

    def total(self) -> int:
        return self.money + self.materials + self.research

    def is_zero(self) -> bool:
        return self.total() == 0

    def covers(self, other: "Resources") -> bool:
        return all(getattr(self, n) >= getattr(other, n) for n in RESOURCE_NAMES)

    def shortfall(self, required: "Resources") -> "Resources":
        """What is missing for `self` to cover `required` (zero where already covered)."""
        return Resources(**{n: max(0, getattr(required, n) - getattr(self, n)) for n in RESOURCE_NAMES})

    def __add__(self, other: "Resources") -> "Resources":
        return Resources(**{n: getattr(self, n) + getattr(other, n) for n in RESOURCE_NAMES})

    def __sub__(self, other: "Resources") -> "Resources":
        if not self.covers(other):
            raise InsufficientResources(other, self)
        return Resources(**{n: getattr(self, n) - getattr(other, n) for n in RESOURCE_NAMES})

    def scaled(self, factor: float, *, up: bool = False) -> "Resources":
        """Scale by `factor`. `up=True` rounds costs up so scaling never makes things free."""
        fn = math.ceil if up else round
        return Resources(**{n: int(fn(round(getattr(self, n) * factor, 6))) for n in RESOURCE_NAMES})
