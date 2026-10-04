"""Rule-based King: allocates resources, picks projects within its risk tolerance, researches blockers, trades."""
from __future__ import annotations

import math
from typing import Optional

from ..engine.actions import Action, AttemptProject, Pass, ResearchTech, Trade
from ..engine.country import CountryProfile
from ..engine.projects import Proposal, quote_proposal
from ..engine.resources import RESOURCE_NAMES, Resources
from ..engine.technology import TechGraph
from ..information.intelligence import Observation
from .base import BaseKing, Evaluation, SpyBrief, adjusted_risk

MAX_TECHS_PER_TURN = 3
TRADE_PREMIUM = 1.5  # we offer 1.5 units for every 1 unit requested


class RuleBasedKing(BaseKing):
    def __init__(self, profile: CountryProfile):
        self.profile = profile

    # ---- decision ---------------------------------------------------------------------------
    def decide(self, obs: Observation, evaluations: list[Evaluation], brief: SpyBrief) -> list[Action]:
        own = obs.own
        if own.completed_turn is not None or obs.finished:
            return [Pass()]
        rules = obs.rules
        graph = TechGraph(obs.technologies)
        owned = set(own.techs)
        reserve = own.resources.scaled(self.profile.reserve_fraction)
        spendable = own.resources - reserve
        remaining = max(1, rules.target_progress - own.project_progress)
        # Everything this country could possibly have by the end: do not chase what it can never pay for.
        horizon = own.resources + own.income.scaled(max(0, obs.turns_remaining - 1))

        def reachable(cost: Resources, techs: list[str]) -> bool:
            need = cost
            for t in graph.path_to(owned, techs):
                need = need + graph.get(t).cost
            return horizon.covers(need)

        def score(prop: Proposal) -> Optional[tuple[float, int, Proposal]]:
            q = quote_proposal(rules, graph, owned, prop)
            if not q.feasible:
                return None
            risk = adjusted_risk(obs, prop, q.est_risk)
            if risk > self.profile.risk_tolerance:
                return None
            return (min(q.est_progress, remaining) * (1 - risk) / max(1, q.cost.total()), q.cost.total(), prop)

        # 1. sort evaluator output into: affordable now / unaffordable (maybe tradeable) / blocked by technology
        affordable, unaffordable, blocked = [], [], []
        for ev in evaluations:
            for prop in (ev.suggested, ev.proposal if ev.verdict == "approve" else None):
                sc = score(prop) if prop is not None else None
                if sc is None:
                    continue
                cost = quote_proposal(rules, graph, owned, prop).cost
                (affordable if spendable.covers(cost) else unaffordable).append(sc)
            if ev.est_risk > self.profile.risk_tolerance:
                continue
            q = quote_proposal(rules, graph, owned, ev.proposal)
            value = min(q.est_progress, remaining) * (1 - ev.est_risk) / max(1, q.cost.total())
            if not reachable(q.cost, ev.missing_techs):
                continue
            if ev.missing_techs:
                blocked.append((value, q.cost.total(), ev))
            elif ev.feasible and not ev.affordable:
                unaffordable.append((value, q.cost.total(), ev.proposal))

        if affordable:
            _, _, best = sorted(affordable, key=lambda t: (-t[0], t[1], t[2].name))[0]
            return [AttemptProject(proposal=best)]

        actions: list[Action] = []
        # 2. research the technologies that block the most promising approach
        if blocked:
            _, _, ev = sorted(blocked, key=lambda t: (-t[0], t[1], t[2].proposal.name))[0]
            budget = spendable
            for tid in graph.path_to(owned, ev.missing_techs):
                ok, _ = graph.can_research(owned, tid)
                cost = graph.get(tid).cost
                if ok and budget.covers(cost) and len(actions) < MAX_TECHS_PER_TURN:
                    actions.append(ResearchTech(tech_id=tid))
                    budget = budget - cost
            if actions:
                return actions

        # 3. close a resource gap by trading, if something promising is only slightly out of reach
        if unaffordable:
            _, _, prop = sorted(unaffordable, key=lambda t: (t[1], t[2].name))[0]
            trade = self._trade_for(obs, quote_proposal(rules, graph, owned, prop).cost, spendable)
            if trade:
                return [trade]
        return [Pass()]

    def _trade_for(self, obs: Observation, cost: Resources, spendable: Resources) -> Optional[Trade]:
        gap = spendable.shortfall(cost)
        need = max(RESOURCE_NAMES, key=lambda r: getattr(gap, r))
        short = getattr(gap, need)
        if short <= 0 or not self.profile.trade_partners:
            return None
        surplus = {r: getattr(spendable, r) - getattr(cost, r) for r in RESOURCE_NAMES if r != need}
        give_res = max(surplus, key=lambda r: (surplus[r], r))
        give_amt = math.ceil(short * TRADE_PREMIUM)
        if surplus[give_res] < give_amt:
            return None
        return Trade(partner=self.profile.trade_partners[0], give=Resources(**{give_res: give_amt}), receive=Resources(**{need: short}))

    # ---- diplomacy --------------------------------------------------------------------------
    def respond_to_trade(self, obs: Observation, proposer: str, offered_to_me: Resources, asked_from_me: Resources) -> bool:
        reserve = obs.own.resources.scaled(self.profile.reserve_fraction)
        if not (obs.own.resources - reserve).covers(asked_from_me):
            return False
        required_ratio = 1.0 + 0.5 * self.profile.caution
        return offered_to_me.total() >= asked_from_me.total() * required_ratio
