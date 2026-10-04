import json

import pytest
from fastapi.testclient import TestClient

from development_war.api.server import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_state_is_public_only(client):
    body = client.get("/simulation/state").json()
    blob = json.dumps(body)
    assert body["turn"] == 1 and len(body["countries"]) == 3
    for secret in ("resources", "techs", "hidden", "risk_bias", "income"):
        assert secret not in blob


def test_observation_endpoint_isolated_per_country(client):
    obs = client.get("/simulation/observation/A").json()
    assert obs["country"] == "A" and "B" in obs["others"]
    assert "resources" not in obs["others"]["B"]
    assert "risk_bias" not in json.dumps(obs) and "hidden" not in json.dumps(obs)
    assert client.get("/simulation/observation/Z").status_code == 404


def test_action_advance_flow_and_validation(client):
    r = client.post("/simulation/action", json={"country": "A", "actions": [{"type": "research_tech", "tech_id": "radio_systems"}]})
    assert r.json()["queued"] == 1
    assert client.post("/simulation/advance").json()["turn"] == 2
    assert "radio_systems" in client.get("/simulation/observation/A").json()["own"]["techs"]
    bad = client.post("/simulation/action", json={"country": "A", "actions": [{"type": "set_resources", "money": 999}]})
    assert bad.status_code == 422  # unknown action types never reach the engine
    # an over-budget action is accepted into the queue but rejected by the engine, visible to A only
    client.post("/simulation/action", json={"country": "A", "actions": [{"type": "attempt_project", "proposal": {"name": "std"}}]})
    client.post("/simulation/advance")
    mine = client.get("/simulation/history", params={"country": "A"}).json()
    theirs = client.get("/simulation/history", params={"country": "B"}).json()
    public = client.get("/simulation/history").json()
    assert any(e["event"] == "action_rejected" for e in mine)
    assert not any(e["event"] == "action_rejected" and e.get("country") == "A" for e in theirs + public)


def test_quote_endpoint(client):
    q = client.post("/simulation/quote/B", json={"name": "std"}).json()
    assert q["cost"]["money"] == 100 and q["feasible"] is False  # B lacks the prerequisite technologies


def test_reset_with_seed_and_scale(client):
    client.post("/simulation/advance")
    client.post("/simulation/reset", json={"seed": 5, "resource_scale": 0.4})
    obs = client.get("/simulation/observation/A").json()
    assert obs["turn"] == 1 and obs["own"]["resources"]["money"] == 28


def test_admin_endpoints_disabled_by_default_and_token_gated(client, monkeypatch):
    monkeypatch.delenv("DEVWAR_ADMIN_TOKEN", raising=False)
    assert client.get("/admin/truth").status_code == 403
    monkeypatch.setenv("DEVWAR_ADMIN_TOKEN", "s3cret")
    assert client.get("/admin/truth", headers={"X-Admin-Token": "nope"}).status_code == 403
    truth = client.get("/admin/truth", headers={"X-Admin-Token": "s3cret"}).json()
    assert "hidden" in truth and "B" in truth["countries"]


def test_finished_simulation_rejects_more_turns(client):
    for _ in range(12):
        client.post("/simulation/advance")
    assert client.get("/simulation/state").json()["finished"] is True
    assert client.post("/simulation/advance").status_code == 409
