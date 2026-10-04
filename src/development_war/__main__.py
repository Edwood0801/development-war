"""CLI: `python -m development_war run [--seed N] [--resource-scale X] [--out FILE]` or `serve`."""
from __future__ import annotations

import argparse
import json
import sys

from .engine.simulator import Simulator
from .engine.world import WorldConfig


def _run(args: argparse.Namespace) -> int:
    cfg = WorldConfig(seed=args.seed, resource_scale=args.resource_scale, information_noise=args.information_noise)
    if args.country_scale:
        cfg.country_resource_scale = {k: float(v) for k, v in (p.split("=") for p in args.country_scale)}
    sim = Simulator(config=cfg)
    summary = sim.run()
    if args.out:
        sim.export_history(args.out, truth=True)
    if not args.quiet:
        for e in sim.world.log.all():
            if e.event in {"research_attempt", "technology_research", "trade", "project_completed", "shock"}:
                d = e.model_dump(exclude_none=True)
                d.pop("visible_to", None)
                print(json.dumps(d))
    print(json.dumps(summary, indent=2))
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("development_war.api.server:app", host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="development-war")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a full simulation with rule-based agents")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--resource-scale", type=float, default=1.0)
    r.add_argument("--country-scale", nargs="*", help="per-country override, e.g. A=0.4")
    r.add_argument("--information-noise", type=float, default=1.0)
    r.add_argument("--out", help="write full event history (JSONL, includes ground truth) to this path")
    r.add_argument("--quiet", action="store_true", help="only print the summary")
    r.set_defaults(fn=_run)
    s = sub.add_parser("serve", help="start the FastAPI server")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(fn=_serve)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
