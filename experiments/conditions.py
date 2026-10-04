"""The planned resource-scarcity conditions (A-E). Only configuration; analysis is future work."""
from __future__ import annotations

from development_war.engine.world import WorldConfig

CONDITIONS: dict[str, dict] = {
    "A_100pct": dict(resource_scale=1.0),
    "B_70pct": dict(resource_scale=0.7),
    "C_40pct": dict(resource_scale=0.4),
    "D_20pct": dict(resource_scale=0.2),
    "E_20pct_incomplete_info": dict(resource_scale=0.2, information_noise=2.5),
}


def make_config(condition: str, seed: int) -> WorldConfig:
    return WorldConfig(seed=seed, **CONDITIONS[condition])
