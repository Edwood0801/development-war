---
name: development-war
description: Play a country in the Development War simulation - a turn-based environment where you solve a technological development problem under scarce resources and incomplete information. Use when asked to act as a King, Inventor, Evaluator or Spy in Development War, or to drive a country through its HTTP API.
---

# Development War - agent skill

You control (part of) one country in a 12-turn, non-military development race. The **Python engine is the
source of truth**. This document only explains how to talk to it. If anything here disagrees with what the
engine does or returns, the engine is right.

## Objective
Achieve the scenario objective (V0.1: *a reliable long-range communication system within 12 turns*) before
turns run out, using as few resources as you can. There is **no predefined correct solution**. The
conventional solution is deliberately unaffordable for at least one country, so you are expected to find
alternatives (reuse, substitution, simplification, combining technologies, partial or novel designs, trade).

## Roles
| Role | Job |
|---|---|
| King | Final decision: allocates resources, approves projects, manages risk, answers intelligence, may trade. |
| Engineer 1 - Inventor | Proposes approaches; searches for cheap, unconventional or combined solutions. |
| Engineer 2 - Evaluator | Criticises proposals: cost, risk, technical flaws, feasibility; suggests modifications. |
| Spy | Chooses where to look; reports **uncertain** intelligence with a confidence level. |

One model may play all four roles in sequence (Inventor -> Evaluator -> King), or each role may be a
different agent. Roles never share information except through the documented hand-offs.

## What you can know
`GET /simulation/observation/{country}` returns everything you are allowed to know:
- your own resources, income, technologies, project progress and **lessons** from past attempts
- the public rules: technology graph, standard-solution cost, strategy tags (cost / risk / progress effects)
- other countries only as **ranges** (e.g. money 50-80) with a confidence, plus uncertain observations
- public events (e.g. a country completed the project)

You will **never** see another country's exact state, the hidden per-world risk biases, or the random seed.
Do not guess hidden values and treat them as fact. Public risk figures are *estimates*; the true risk differs
by an unknown amount, so learn from the `lessons` you receive.

## Resources and rules (enforced by the engine, not by you)
- Three finite resources: `money`, `materials`, `research`. Income arrives at the start of each turn.
- Every action costs resources. The engine **rejects** any action you cannot afford and spends nothing.
- You cannot use a technology you do not own. Technologies have prerequisites; research is acquired at the
  end of the turn in which it succeeds. Research can fail.
- Resources are never created by actions. They move only through trade, or are destroyed by shocks.
- You may submit at most 4 actions per turn; extras are rejected.

## Allowed actions (JSON, `type` is required)
```json
{"type": "research_tech", "tech_id": "radio_systems"}
{"type": "attempt_project", "proposal": {"name": "...", "tags": ["simplify_design"], "uses_techs": ["radio_systems"]}}
{"type": "trade", "partner": "D", "give": {"money": 30}, "receive": {"materials": 10}}
{"type": "pass"}
```
- `proposal.tags` are strategy tags from the rules (no tags = the standard, expensive solution).
- `uses_techs` must be technologies you already own; advanced ones give a small discount.
- A `trade` happens only if the partner's king accepts; otherwise nothing moves.
- Anything else (inventing action types, editing state) is rejected. You cannot modify the world directly.

## Decision process
1. Read your observation. Note `turns_remaining`, resources, owned techs, `own.lessons`.
2. **Inventor**: list 2-5 distinct approaches, at least one unconventional. Do not repeat an approach your
   lessons show failing for a reason you have not addressed.
3. **Evaluator**: price each with `POST /simulation/quote/{country}` (public rules + your techs). Flag missing
   technologies, unaffordable cost, and risk. Adjust risk upward for tags that already failed for you.
4. **King**: choose actions that fit your *spendable* budget and risk tolerance. If the best approach is
   blocked by a technology, research it only if the whole path is reachable before the deadline. If it is
   short on one resource, consider a trade.
5. **Spy**: choose a focus country; read ranges and confidence honestly. Low confidence means low weight.
6. Submit with `POST /simulation/action`, then the operator calls `POST /simulation/advance`.

## Expected output
Return only JSON the API accepts: `{"country": "A", "actions": [ ... ]}`. Put reasoning in a separate
free-text field if your framework needs it; the engine ignores it.

## Failure behaviour
- A rejected action costs nothing; read the reason in `own_events` (`action_rejected`) and adapt.
- A failed attempt costs its full price, gives no progress, and adds a **lesson** to your memory.
- If you cannot afford anything useful, `pass` and save; do not submit impossible actions repeatedly.
- Invalid payloads are rejected by the API (HTTP 422) and nothing is queued. If you queue nothing for a turn,
  the country's built-in team (rule-based by default) plays that turn for you.
