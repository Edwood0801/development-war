"""FastAPI layer so external AI systems can drive a country.

Hidden state never leaves this API except through the admin endpoints, which are disabled unless the
environment variable DEVWAR_ADMIN_TOKEN is set. V0.1 has NO per-country authentication: whoever can
call `/simulation/observation/A` sees country A's private view. Add API keys per country before
exposing this beyond localhost.
"""
from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from ..engine.actions import Action
from ..engine.projects import Proposal, Quote, quote_proposal
from ..engine.simulator import Simulator
from ..engine.world import WorldConfig
from ..information.intelligence import Observation, build_observation


class ActionRequest(BaseModel):
    country: str
    actions: list[Action]


class ResetRequest(BaseModel):
    seed: int = 0
    resource_scale: float = 1.0
    country_resource_scale: dict[str, float] = Field(default_factory=dict)
    information_noise: float = 1.0
    shock_probability: Optional[float] = None


def create_app(simulator: Optional[Simulator] = None) -> FastAPI:
    app = FastAPI(title="Development War", version="0.1.0")
    app.state.sim = simulator or Simulator()

    def sim() -> Simulator:
        return app.state.sim

    def check_country(country: str) -> None:
        if country not in sim().world.countries:
            raise HTTPException(404, f"unknown country '{country}'")

    def require_admin(token: Optional[str]) -> None:
        expected = os.environ.get("DEVWAR_ADMIN_TOKEN")
        if not expected:
            raise HTTPException(403, "admin endpoints are disabled (set DEVWAR_ADMIN_TOKEN to enable)")
        if token is None or not secrets.compare_digest(token, expected):
            raise HTTPException(403, "invalid admin token")

    @app.get("/")
    def root() -> dict:
        return {"name": "Development War", "docs": "/docs", "state": "/simulation/state"}

    @app.get("/simulation/state")
    def state() -> dict:
        """Public state only: no resources, technologies or hidden parameters."""
        s = sim()
        w = s.world
        return {
            "scenario": {"id": w.scenario.id, "title": w.scenario.title, "objective": w.scenario.objective},
            "turn": w.turn,
            "max_turns": w.max_turns,
            "finished": w.finished,
            "countries": [{"id": cid, "name": c.profile.name, "project_completed_turn": c.completed_turn} for cid, c in sorted(w.countries.items())],
            "submitted_actions_for": sorted(s.pending),
        }

    @app.get("/simulation/observation/{country}", response_model=Observation)
    def observation(country: str) -> Observation:
        check_country(country)
        return build_observation(sim().world, country)

    @app.post("/simulation/quote/{country}", response_model=Quote)
    def quote(country: str, proposal: Proposal) -> Quote:
        """Price a proposal using public rules and this country's own technologies."""
        check_country(country)
        w = sim().world
        return quote_proposal(w.scenario.project, w.graph, w.countries[country].techs, proposal)

    @app.post("/simulation/action")
    def submit(req: ActionRequest) -> dict:
        """Queue actions for the next turn. They are validated when the turn is advanced."""
        check_country(req.country)
        if sim().world.finished:
            raise HTTPException(409, "simulation finished")
        sim().submit_actions(req.country, list(req.actions))
        return {"queued": len(req.actions), "country": req.country, "turn": sim().world.turn}

    @app.post("/simulation/advance")
    def advance() -> dict:
        s = sim()
        if s.world.finished:
            raise HTTPException(409, "simulation finished")
        events = s.step()
        return {
            "turn": s.world.turn,
            "finished": s.world.finished,
            "public_events": [e.model_dump() for e in events if e.visible_to is None],
        }

    @app.post("/simulation/reset")
    def reset(req: ResetRequest) -> dict:
        cfg = WorldConfig(**req.model_dump())
        app.state.sim = Simulator(config=cfg)
        return {"reset": True, "seed": req.seed}

    @app.get("/simulation/history")
    def history(country: Optional[str] = None) -> list[dict]:
        """Public events, plus that country's own private events when `country` is given."""
        if country is not None:
            check_country(country)
        return sim().history(country=country)

    @app.get("/admin/truth")
    def admin_truth(x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token")) -> dict:
        require_admin(x_admin_token)
        return sim().world.truth()

    @app.get("/admin/history")
    def admin_history(x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token")) -> list[dict]:
        require_admin(x_admin_token)
        return sim().history(truth=True)

    return app


app = create_app()
