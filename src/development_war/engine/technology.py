"""Data-driven technology graph. Add technologies in scenario data, not in code."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .resources import Resources


class Technology(BaseModel):
    id: str
    name: str
    category: str
    prerequisites: list[str] = Field(default_factory=list)
    cost: Resources = Field(default_factory=Resources)
    risk: float = Field(0.0, ge=0.0, le=1.0)  # chance a research attempt fails

    @property
    def is_advanced(self) -> bool:
        return bool(self.prerequisites)


class TechGraph:
    def __init__(self, techs: list[Technology]):
        self._techs = {t.id: t for t in techs}
        if len(self._techs) != len(techs):
            raise ValueError("duplicate technology ids")
        for t in techs:
            for p in t.prerequisites:
                if p not in self._techs:
                    raise ValueError(f"{t.id} has unknown prerequisite {p}")
        self._check_acyclic()

    def _check_acyclic(self) -> None:
        state: dict[str, int] = {}

        def visit(tid: str) -> None:
            if state.get(tid) == 1:
                raise ValueError(f"cycle in technology graph at {tid}")
            if state.get(tid) == 2:
                return
            state[tid] = 1
            for p in self._techs[tid].prerequisites:
                visit(p)
            state[tid] = 2

        for tid in sorted(self._techs):
            visit(tid)

    def get(self, tech_id: str) -> Technology:
        return self._techs[tech_id]

    def __contains__(self, tech_id: str) -> bool:
        return tech_id in self._techs

    def all(self) -> list[Technology]:
        return [self._techs[k] for k in sorted(self._techs)]

    def can_research(self, owned: set[str] | frozenset[str], tech_id: str) -> tuple[bool, str]:
        if tech_id not in self._techs:
            return False, f"unknown technology '{tech_id}'"
        if tech_id in owned:
            return False, f"technology '{tech_id}' already acquired"
        missing = [p for p in self._techs[tech_id].prerequisites if p not in owned]
        if missing:
            return False, f"missing prerequisites for '{tech_id}': {', '.join(sorted(missing))}"
        return True, ""

    def path_to(self, owned: set[str] | frozenset[str], targets: list[str]) -> list[str]:
        """Technologies still to research (prerequisites first) so that all `targets` are owned."""
        order: list[str] = []
        seen: set[str] = set()

        def visit(tid: str) -> None:
            if tid in owned or tid in seen:
                return
            seen.add(tid)
            for p in sorted(self._techs[tid].prerequisites):
                visit(p)
            order.append(tid)

        for t in sorted(targets):
            visit(t)
        return order
