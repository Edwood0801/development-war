from ..engine.country import CountryProfile
from .base import CountryTeam
from .evaluator import RuleBasedEvaluator
from .inventor import RuleBasedInventor
from .king import RuleBasedKing
from .spy import RuleBasedSpy


def build_rule_based_team(profile: CountryProfile) -> CountryTeam:
    """A complete team that needs no API key. Swap individual members for LLM-backed agents later."""
    return CountryTeam(
        king=RuleBasedKing(profile),
        inventor=RuleBasedInventor(profile),
        evaluator=RuleBasedEvaluator(profile),
        spy=RuleBasedSpy(profile),
    )


__all__ = ["CountryTeam", "build_rule_based_team", "RuleBasedKing", "RuleBasedInventor", "RuleBasedEvaluator", "RuleBasedSpy"]
