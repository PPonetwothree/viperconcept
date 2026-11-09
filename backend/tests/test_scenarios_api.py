"""Scenario harness and API integration tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from simulation.scenarios import SCENARIOS, Harness, run_scenarios


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario_passes(name):
    r = run_scenarios([name])
    res = r["results"][0]
    assert res["result"] == "PASS", res


@pytest.mark.parametrize("seed", [1, 2, 4, 8, 16])
def test_intrusion_detected_across_seeds(seed):
    h = Harness(background=False, seed=seed)
    h.run(8)
    h.rt.inject("test_intrusion")
    evs = h.run(110)
    assert any(e.category == "perimeter_anomaly" and e.severity in ("high", "critical") for e in evs)


@pytest.mark.parametrize("seed", [1, 2, 4, 8, 16])
def test_wildlife_not_escalated_across_seeds(seed):
    h = Harness(background=False, seed=seed)
    h.run(8)
    h.rt.inject("animal")
    evs = h.run(80)
    assert not any(e.category == "perimeter_anomaly" and e.severity in ("high", "critical") for e in evs), \
        [(e.category, e.severity, e.rules[-1]) for e in evs]


@pytest.fixture()
def client(tmp_path):
    from main import create_app
    app = create_app(db_path=tmp_path / "api.db", autostart=False, run_loop=False)
    with TestClient(app) as c:
        yield c


def test_api_flow(client):
    assert client.get("/api/health").json()["hardware_connected"] is False
    assert len(client.get("/api/environments").json()) == 3
    assert client.post("/api/sim/inject", json={"kind": "fire"}).status_code == 409   # not running
    assert client.post("/api/sim/control", json={"action": "start"}).json()["state"] == "running"
    assert client.post("/api/sim/speed", json={"speed": 3}).status_code == 422
    assert client.post("/api/sim/speed", json={"speed": 5}).json()["speed"] == 5
    rt = client.app.state.runtime
    rt.inject("equipment_failure", "CAM-01")
    import time
    for _ in range(10):
        rt.step(0.2)
        time.sleep(0.01)
    evs = client.get("/api/events", params={"severity": "medium"}).json()
    assert evs["total"] >= 1
    eid = evs["events"][0]["event_id"]
    assert client.post(f"/api/events/{eid}/resolve", json={"operator": "op"}).status_code == 409
    assert client.post(f"/api/events/{eid}/acknowledge", json={"operator": ""}).status_code == 422
    r = client.post(f"/api/events/{eid}/acknowledge", json={"operator": "op"})
    assert r.status_code == 200 and "verify" in r.json()["actions"]
    r = client.post(f"/api/events/{eid}/verify", json={"operator": "op", "outcome": "verified_genuine"})
    r = client.post(f"/api/events/{eid}/respond", json={"operator": "op", "category": "technical_maintenance",
                                                         "authorized": True})
    assert r.json()["resolution_status"] == "response_initiated"
    client.post(f"/api/events/{eid}/resolve", json={"operator": "op"})
    assert client.post(f"/api/events/{eid}/close", json={"operator": "op"}).json()["resolution_status"] == "closed"
    md = client.get(f"/api/events/{eid}/report", params={"format": "md"}).text
    assert eid in md and "SIMULATION" in md
    csv = client.get("/api/export", params={"format": "csv"}).text
    assert csv.splitlines()[0].startswith("event_id,created_utc")
    assert client.get("/api/export", params={"format": "json"}).json()["mode"] == "SIMULATION"
    an = client.get("/api/analytics").json()
    assert an["total_events"] >= 1
    assert client.get("/api/events/VIPER-1999-0001").status_code == 404
    assert client.get("/api/docs/../config.py").status_code == 404
