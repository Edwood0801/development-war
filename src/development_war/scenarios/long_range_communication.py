"""The V0.1 starter scenario. All content lives in data/long_range_communication.json."""
from __future__ import annotations

import json
from importlib import resources

from ..engine.scenario import Scenario


def load() -> Scenario:
    text = resources.files("development_war.scenarios").joinpath("data/long_range_communication.json").read_text()
    sc = Scenario.model_validate(json.loads(text))
    sc.validate_consistency()
    return sc
