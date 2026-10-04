"""Rule-based Spy: chooses where to look and summarises uncertain reports. Never sees ground truth."""
from __future__ import annotations

from ..engine.country import CountryProfile
from ..information.intelligence import Observation
from .base import BaseSpy, SpyBrief, SpyTask


def _midpoint_total(est: dict[str, tuple[int, int]]) -> float:
    return sum((lo + hi) / 2 for lo, hi in est.values())


class RuleBasedSpy(BaseSpy):
    def __init__(self, profile: CountryProfile):
        self.profile = profile

    def plan(self, obs: Observation) -> SpyTask:
        others = sorted(obs.others.values(), key=lambda o: o.id)
        if not others:
            return SpyTask()
        known = [o for o in others if o.resource_estimates]
        focus = max(known, key=lambda o: _midpoint_total(o.resource_estimates)).id if known else others[0].id
        interval = max(1, self.profile.spy_probe_interval)
        deep = obs.turn % interval == 0 and obs.own.resources.money >= 20
        return SpyTask(focus=focus, deep=deep)

    def brief(self, obs: Observation) -> SpyBrief:
        notes: list[str] = []
        confs: list[float] = []
        for o in sorted(obs.others.values(), key=lambda x: x.id):
            if not o.resource_estimates:
                notes.append(f"{o.name}: no intelligence yet")
                continue
            rng = ", ".join(f"{k} {lo}-{hi}" for k, (lo, hi) in o.resource_estimates.items())
            notes.append(f"{o.name} (confidence {o.confidence}): approx. {rng}. " + "; ".join(o.observations))
            confs.append(o.confidence or 0.0)
        summary = "Estimates only; ranges are uncertain and observations may be wrong." if notes else "No intelligence."
        return SpyBrief(summary=summary, notes=notes, confidence=round(sum(confs) / len(confs), 2) if confs else None)
