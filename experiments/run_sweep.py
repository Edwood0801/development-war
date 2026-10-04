"""Run every condition over several seeds with rule-based agents and print raw per-country numbers.

    python experiments/run_sweep.py --seeds 20

This is a smoke-level harness, not an analysis. The full event history (see Simulator.export_history)
holds the data for real analysis.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `python experiments/run_sweep.py` work from the repo root (script dir is not the repo root).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments.conditions import CONDITIONS, make_config
from development_war.engine.simulator import Simulator


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    args = ap.parse_args()
    print(f"{'condition':26} {'country':7} {'completed':>9} {'attempts':>8} {'failures':>8} {'approaches':>10}")
    for name in CONDITIONS:
        agg: dict[str, list] = {}
        for seed in range(args.seeds):
            summ = Simulator(config=make_config(name, seed)).run()
            for cid, c in summ["countries"].items():
                agg.setdefault(cid, []).append(c)
        for cid, rows in sorted(agg.items()):
            n = len(rows)
            done = sum(r["completed_turn"] is not None for r in rows)
            print(f"{name:26} {cid:7} {done:>6}/{n:<2} {sum(r['project_attempts'] for r in rows)/n:8.1f} "
                  f"{sum(r['project_failures'] for r in rows)/n:8.1f} {sum(len(r['distinct_approaches_tried']) for r in rows)/n:10.1f}")


if __name__ == "__main__":
    main()
