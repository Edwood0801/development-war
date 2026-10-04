# Architecture and decisions

```
                 +-------------------------- engine (authoritative) --------------------------+
 scenario JSON ->| World: countries, hidden biases, event log, constraint records             |
                 | Simulator: 12 ordered phases | ActionValidator | project/tech rules         |
                 +--------------------------------^-------------------------------------------+
                                                  | only path from truth to agents
                                  +---------------+---------------+
                                  | information layer             |
                                  | IntelligenceService (noisy)   |
                                  | build_observation -> Observation
                                  +---------------+---------------+
                                                  v
          agents (King / Inventor / Evaluator / Spy)  or  HTTP API  or  any LLM adapter
                         they return Actions (requests), never state changes
```

## Decisions

1. **Engine owns the truth; agents get an `Observation`.** `agents/` never imports `engine.world` (a test
   greps for it). `build_observation` is the single place hidden state is converted to knowledge.
2. **Constraints are code.** `ActionValidator` checks cost against a per-turn working budget and
   `Country.spend` re-checks (defence in depth). Prompts describe rules but do not enforce them.
3. **Costs and *estimated* risk are public and deterministic; outcomes are not.** `quote_proposal` is a pure
   function. The true success chance adds a hidden per-world bias per approach, so agents can be wrong and
   must learn from lessons. The ranges of those biases live in the private part of the scenario.
4. **No predefined solution.** A proposal is a set of strategy tags (cost / risk / progress effects, data in
   the scenario). New approaches are new data, not new code. Engineers explore combinations.
5. **Determinism.** Integer resources; independent RNG streams keyed by `(seed, stream, turn, country, ...)`
   so one agent's behaviour never shifts another stream. Same seed + same actions => identical history.
6. **Phases are data.** `PHASES` is an ordered tuple of method names; reorder or drop phases without
   touching the loop. Research results apply in `technology_update`, lessons in `memory_update`.
7. **Model-agnostic.** `ModelProvider.generate(messages, tools)` is the only LLM seam. V0.1 ships rule-based
   agents plus `MockProvider` / `ScriptedProvider`. Any role of any country can be swapped independently
   (`CountryTeam`), which is how Country A -> model X, Country B -> model Y will work.
8. **Untrusted agents.** Agent exceptions are caught and logged (`agent_error`) and replaced by `pass`;
   external actions are parsed through a closed discriminated union (`parse_action`) and malformed payloads are
   rejected before they reach the engine.
9. **History is the dataset.** Every event is logged with a visibility (`public`, specific countries, or
   truth-only). `constraint_record` events capture original problem, normal cost, available resources,
   alternative, cost, risk, result and lessons - the data needed to test the research hypothesis.
10. **API exposes no hidden state.** `/simulation/state` is public; observation is per country; admin
    endpoints (`/admin/*`) need `DEVWAR_ADMIN_TOKEN`. V0.1 has no per-country authentication.

## Deliberate simplifications (V0.1)
- Research capacity is a stock with income, like money and materials.
- Trades are one-shot, resolved the same turn by the partner's king; a partner under external control is
  still answered by its internal king.
- Country D's possible intervention, diplomacy beyond trade, combat, and a UI are not implemented.
- One scenario; tag effects and costs are hand-set numbers, not calibrated to anything.
