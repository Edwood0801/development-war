# Development War

An **experimental AI reasoning environment**: a multi-agent, turn-based simulation in which countries must
solve a hard technological-development problem under **severe resource constraints, incomplete information,
uncertainty and time pressure**. Inspired by Cold War-era technological competition. It is *not* a warfare
simulator.

> **Status: V0.1 - a working testbed, not a result.** The research hypothesis below has **not** been tested
> yet, let alone proven. The bundled agents are simple rules, so nothing they do says anything about LLMs.

## Why it exists / research question
> Can constrained environments cause AI agents to discover more resource-efficient, unconventional or
> creative solutions than they would produce in an unconstrained environment?

Scarcity does not automatically produce cleverness; it may just produce failure or paralysis (see
[Known limitations](#known-limitations)). So the engine's job is to **record data** that lets the question be
answered later: original problem, normal cost, available resources, the alternative chosen, its cost and
risk, the result and the lessons learned.

## Architecture
```
scenario data -> engine (truth, rules, validation) -> information layer -> Observation -> agents / API / LLMs
```
- **Engine** (`engine/`): authoritative world, resources, technology graph, project pricing, action
  validation, 12-phase turn loop, event log. No LLM code inside.
- **Information** (`information/`): turns truth into noisy intelligence reports and per-country observations.
  The only path from hidden state to agents.
- **Agents** (`agents/`): King, Inventor, Evaluator, Spy as interfaces + rule-based implementations.
- **Models** (`models/`): `ModelProvider` interface (+ mock/scripted providers). No vendor SDKs.
- **API** (`api/`): FastAPI layer so external AI systems can play a country.
- **Scenarios** (`scenarios/`): all content (technologies, costs, countries, tags) is JSON data.

Details and the reasoning behind each choice: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Countries and agents
| | Resources | Character |
|---|---|---|
| A | limited | high risk tolerance, pressure to advance, tries unconventional approaches |
| B | best | cautious, efficiency-minded, strong science, protects civilian stability |
| D | medium | neutral, strategically cautious, strong intelligence; independence and security first |

Each country has a **King** (strategy, allocation, approval, risk, trade), **Engineer 1 - Inventor**
(generates and combines approaches), **Engineer 2 - Evaluator** (cost, risk, flaws, modifications) and a
**Spy** (limited, uncertain intelligence with confidence levels).

## Resource constraints
Money, materials and research capacity are finite integers. Income arrives each turn; actions consume
resources; the engine rejects anything unaffordable and re-checks every spend. Resources are created only by
income and moved only by trade; random shocks only destroy them.

## Information asymmetry
`World` (truth) is never given to an agent. Each country receives an `Observation`: its own state plus other
countries as **ranges with a confidence** (e.g. money 153-285, confidence 0.5) and possibly misleading
qualitative notes. Hidden per-world risk/yield biases mean public estimates can be wrong.

## First scenario: Long-Range Communication Challenge
Develop a reliable long-range communication system within 12 turns. The standard solution (100 money,
50 materials, 40 research, plus three prerequisite technologies) is out of reach for Country A even if it
saves all income. Approaches are combinations of strategy tags (`reuse_infrastructure`, `simplify_design`,
`substitute_materials`, `combine_technologies`, `partial_solution`, `novel_architecture`), each with its own
cost, risk and progress effect. Progress accumulates; 100 completes the project. No solution is predefined.

## Install
```bash
git clone <your-repo-url> development-war && cd development-war
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```
Requires Python 3.10+. No API key is needed for anything in V0.1.

## Run a simulation
```bash
python -m development_war run --seed 42                       # full 12-turn run, prints key events + summary
python -m development_war run --seed 42 --out history.jsonl   # also write the complete event log (includes ground truth)
python -m development_war run --resource-scale 0.4 --quiet    # constrained condition
python -m development_war run --country-scale A=0.5           # scale one country only
python experiments/run_sweep.py --seeds 20                    # conditions A-E x seeds, raw table
```
A saved example (seed 42) is in [`docs/example-run/`](docs/example-run/).

## Tests
```bash
pytest
```
Covers resource enforcement, technology dependencies, information isolation, intelligence uncertainty, turn
progression, failure lessons, determinism, full-scenario completion, trade, the API and experiment configs.

## API
```bash
python -m development_war serve          # http://127.0.0.1:8000/docs
```
| Endpoint | Purpose |
|---|---|
| `GET /simulation/state` | public state only (turn, scenario, who completed) |
| `GET /simulation/observation/{country}` | that country's knowledge |
| `POST /simulation/quote/{country}` | price a proposal with public rules |
| `POST /simulation/action` | queue actions for a country for the next turn |
| `POST /simulation/advance` | run one turn (queued countries are externally controlled; others use built-in agents) |
| `POST /simulation/reset` | new run: `{"seed": 1, "resource_scale": 0.4}` |
| `GET /simulation/history[?country=A]` | public events, plus that country's private events |
| `GET /admin/truth`, `/admin/history` | ground truth; disabled unless `DEVWAR_ADMIN_TOKEN` is set (`X-Admin-Token` header) |

```bash
curl -X POST localhost:8000/simulation/action -H 'content-type: application/json' \
  -d '{"country":"A","actions":[{"type":"research_tech","tech_id":"radio_systems"}]}'
curl -X POST localhost:8000/simulation/advance
```
**Security:** V0.1 has no per-country authentication; run it on localhost only. The agent-facing contract is in
[`skills/development-war/SKILL.md`](skills/development-war/SKILL.md).

## Known limitations
- **Low-resource conditions can be dead zones.** The prerequisite technology and the cheapest possible attempt
  have fixed costs. At 20% resources, Country A's whole 12-turn budget cannot pay for both, so A and D make no
  attempts at all (the sweep shows 0.0 attempts). Such a run measures paralysis, not creativity. Rescale
  costs, change which countries are scaled, or retune the scenario before drawing conclusions.
- Rule-based agents are not intelligent; any numbers they produce only test the plumbing.
- Tag effects, costs and bias ranges are hand-set, not calibrated. Hidden biases are random draws per seed.
- Country D never intervenes; diplomacy is limited to one-shot trades; no UI.
- No per-country API authentication; one global simulation per server process.
- Research capacity is modelled as a stock with income (simplification).

## Roadmap
1. LLM adapters (`OpenAI`, `Gemini`, `Anthropic`, `Ollama`, `OpenRouter`) implementing `ModelProvider`, plus
   LLM-backed agent classes that parse JSON actions with `parse_action`.
2. Calibrate or add scenarios (data-only) so every scarcity level leaves a feasible solution space.
3. Analysis tooling for the recorded metrics: resource efficiency, attempts, failure rate, time to
   breakthrough, novelty and diversity of solutions, adaptation after failure.
4. Richer diplomacy and Country D intervention; per-country API keys.

## Multi-model future
Roles are independent interfaces grouped in a `CountryTeam`, and the engine never imports a vendor SDK, so one
engine can run, say, Country A on one model, B on another and D on a third, or mix models inside one country.
The same observation, action schema and validation apply to every model, which keeps comparisons fair.

## Research direction
Planned conditions (`experiments/conditions.py`): 100%, 70%, 40%, 20% resources, and 20% with noisier
intelligence. Planned comparisons: resource efficiency, attempts, failure rate, time to breakthrough, novel
solutions, technology progression, adaptation after failure, solution diversity. Because outcomes depend on
hidden per-seed biases, comparisons need many seeds. **No conclusions have been drawn.**

## License
MIT (see `LICENSE`; the copyright holder line is a placeholder - set it to your name before publishing).
