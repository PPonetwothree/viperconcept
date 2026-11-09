"""The in-browser bridge (used on static hosting) must behave like the REST API."""
import json

import time

import browser_bridge
from simulation.engine import VirtualClock


def call(b, method, path, body=None):
    r = json.loads(b.handle(method, path, json.dumps(body) if body is not None else None))
    data = json.loads(r["body"]) if "json" in r["type"] else r["body"]
    return r["status"], data


def test_bridge_endpoints_and_lifecycle():
    clock = VirtualClock(time.time())
    b = browser_bridge.Bridge(clock=clock)
    msgs = []
    b.connect(lambda t: msgs.append(json.loads(t)))
    assert msgs[0]["type"] == "hello"
    assert call(b, "GET", "/api/health")[1]["engine"] == "browser"
    for p in ["/api/meta", "/api/environments", "/api/devices", "/api/sim/state", "/api/logs?limit=5",
              "/api/analytics", "/api/tests/scenarios", "/api/docs", "/api/events?severity=high,critical"]:
        assert call(b, "GET", p)[0] == 200, p
    assert call(b, "GET", "/api/docs/bom.md")[0] == 200
    assert call(b, "GET", "/api/docs/../config.py")[0] == 404
    assert call(b, "GET", "/api/events?severity=bogus")[0] == 422
    assert call(b, "POST", "/api/sim/speed", {"speed": 3})[0] == 422
    assert call(b, "POST", "/api/sim/inject", {"kind": "test_intrusion", "target": "A"})[0] == 200
    call(b, "POST", "/api/sim/speed", {"speed": 5})
    # Drive the engine as the JS timer would.
    for _ in range(400):
        clock.advance(0.2)
        b.tick()
    assert any(m["type"] == "snapshot" for m in msgs)
    _, evs = call(b, "GET", "/api/events?category=perimeter_anomaly")
    assert evs["total"] >= 1
    eid = evs["events"][0]["event_id"]
    assert call(b, "POST", f"/api/events/{eid}/respond", {"operator": "op", "category": "security_team",
                                                          "authorized": True})[0] == 409
    assert call(b, "POST", f"/api/events/{eid}/acknowledge", {"operator": "op"})[0] == 200
    assert call(b, "POST", f"/api/events/{eid}/verify", {"operator": "op", "outcome": "verified_genuine"})[0] == 200
    assert call(b, "POST", f"/api/events/{eid}/respond", {"operator": "op", "category": "security_team",
                                                          "authorized": False})[0] == 409
    assert call(b, "POST", f"/api/events/{eid}/respond", {"operator": "op", "category": "security_team",
                                                          "authorized": True})[0] == 200
    st, md = call(b, "GET", f"/api/events/{eid}/report?format=md")
    assert st == 200 and eid in md
    st, csv_text = call(b, "GET", "/api/export?format=csv")
    assert st == 200 and eid in csv_text
