"""Predefined validation scenarios (Module L).

Each scenario runs in an isolated, headless runtime with an in-memory store
and a ``VirtualClock`` so that minutes of simulated operation complete in
well under a second and results are repeatable (fixed seed). Live incident
history is never touched.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from database.store import EventStore
from event_engine.lifecycle import TransitionError
from event_engine.models import SEVERITY_RANK, Event, utc_iso

from .engine import VirtualClock
from .runtime import Runtime

DT = 0.2


class Harness:
    def __init__(self, env: str = "airport", seed: int = 7, background: bool = True):
        self.clock = VirtualClock(time.time())
        self.store = EventStore(":memory:")
        self.rt = Runtime(self.store, env, clock=self.clock, seed=seed, ambient_per_min=0.0,
                          background=background, persist_logs=False)
        self.rt.control("start")
        self.updates: list[Event] = []

    def run(self, seconds: float) -> list[Event]:
        new: list[Event] = []
        for _ in range(int(seconds / DT)):
            self.clock.advance(DT)
            for kind, ev in self.rt.step(DT):
                (new if kind == "new" else self.updates).append(ev)
        return new

    def status(self) -> dict[str, Any]:
        k = self.rt.kpis()
        return {"online_sensors": k["online_sensors"], "total_sensors": k["total_sensors"],
                "nodes_online": sum(1 for n in self.rt.engine.snapshot()["nodes"].values() if n["status"] == "online"),
                "nodes_total": len(self.rt.engine.nodes), "power": self.rt.engine.power["source"],
                "ups_pct": round(self.rt.engine.power["ups_pct"], 1)}


def _ev_summary(evs: list[Event]) -> list[str]:
    return [f"{e.event_id} {e.category}/{e.severity} conf {e.confidence:.2f} ({len(e.contributing)} obs)" for e in evs]


def _result(name, title, expected, actual, evs, h, passed, notes=""):
    first = evs[0] if evs else None
    return {"id": name, "title": title, "expected": expected, "actual": actual,
            "event_timestamp_utc": first.created_utc if first else None,
            "event_ids": [e.event_id for e in evs],
            "processing_latency_ms": first.latency.get("detection_ms") if first else None,
            "fusion_ms": first.latency.get("fusion_ms") if first else None,
            "system_status": h.status(), "result": "PASS" if passed else "FAIL", "notes": notes}


def s_normal() -> dict[str, Any]:
    h = Harness(seed=11)
    h.rt.inject("vehicle")
    evs = h.run(150)
    alerts = [e for e in evs if e.severity != "info"]
    normal = [e for e in evs if e.category == "normal_activity"]
    passed = not alerts and len(normal) >= 1 and all(e.resolution_status == "closed" for e in normal)
    return _result("normal", "Normal operating conditions",
                   "Patrols and an authorised vehicle generate observations that are logged as normal "
                   "activity (info, auto-closed); no alert requiring an operator is raised.",
                   f"{len(normal)} normal-activity record(s), {len(alerts)} alert(s); "
                   f"{h.rt.fusion.stats['suppressed_normal']} normal records rate-limited. "
                   + "; ".join(_ev_summary(alerts)[:3]), normal, h, passed,
                   "Demonstrates that sensor activations are not automatically treated as threats.")


def s_movement() -> dict[str, Any]:
    h = Harness(background=False, seed=3)
    h.run(8)
    h.rt.inject("test_intrusion", "A")
    evs = h.run(90)
    perim = [e for e in evs if e.category == "perimeter_anomaly"]
    ev = perim[0] if perim else None
    modalities = {c["sensor_type"] for c in ev.contributing} if ev else set()
    passed = bool(ev) and SEVERITY_RANK[ev.severity] >= SEVERITY_RANK["high"] and len(modalities) >= 2 \
        and ev.verification_status == "awaiting_review" and ev.resolution_status == "open"
    return _result("movement", "Simulated movement event (perimeter crossing, zone A)",
                   "At least two independent modalities (fence vibration + thermal and/or optical) correlate into "
                   "ONE potential perimeter anomaly (high/critical); later observations merge into it; it awaits "
                   "human verification with no automatic response.",
                   (f"{ev.event_id}: {ev.category}/{ev.severity}, modalities {sorted(modalities)}, "
                    f"evidence {ev.confidence:.2f}, status {ev.verification_status}. "
                    f"Follow-up merges: {sum(1 for u in h.updates if u.event_id == ev.event_id)}")
                   if ev else "No perimeter anomaly raised: " + "; ".join(_ev_summary(evs)),
                   perim, h, passed)


def s_environment() -> dict[str, Any]:
    h = Harness(background=False, seed=5)
    h.run(8)
    h.rt.inject("wind_gust")
    h.rt.inject("animal", "B")
    evs = h.run(80)
    threats = [e for e in evs if e.category == "perimeter_anomaly" and SEVERITY_RANK[e.severity] >= 3]
    env = [e for e in evs if e.category == "environmental_disturbance"]
    passed = bool(env) and not threats
    return _result("environment", "Environmental disturbance (wind gust + animal at fence)",
                   "Wind-induced fence vibration and wildlife are classified as low-severity environmental "
                   "disturbances, not as high-severity perimeter anomalies.",
                   f"{len(env)} environmental disturbance(s), {len(threats)} high/critical perimeter anomalies. "
                   + "; ".join(_ev_summary(evs)[:4]), env or evs, h, passed,
                   "Edge object classification is deliberately imperfect (10 % animal→person); a FAIL here "
                   "would reveal a rule that over-trusts a single label.")


def s_malfunction() -> dict[str, Any]:
    h = Harness(background=False, seed=9)
    h.run(8)
    sid = h.rt.inject("equipment_failure", "TH-01")["ref"]
    evs = h.run(10)
    eq = [e for e in evs if e.category == "equipment_malfunction" and e.sensor_id == sid]
    offline = h.rt.engine.snapshot()["sensors"][sid]["status"]
    passed = bool(eq) and offline == "fault" and eq[0].latency["detection_ms"] < 2000
    return _result("malfunction", "Sensor malfunction (thermal camera TH-01)",
                   "Device fault is reported by the edge node and raised as an equipment malfunction within "
                   "2 s; sensor shows FAULT and its data are excluded from fusion.",
                   f"{len(eq)} equipment event(s) for {sid}; sensor status '{offline}'", eq, h, passed)


def s_network() -> dict[str, Any]:
    h = Harness(background=False, seed=13)
    h.run(8)
    nid = h.rt.inject("comm_failure", "EN-W")["ref"]
    evs = h.run(12)
    comm = [e for e in evs if e.category == "communication_failure" and e.sensor_id == nid]
    h.run(20)
    restored = any(u.event_id == comm[0].event_id and any("restored" in s["note"] for s in u.lifecycle)
                   for u in h.updates) if comm else False
    passed = bool(comm) and restored
    return _result("network", "Network interruption (edge node EN-W uplink lost for 25 s)",
                   "Heartbeat watchdog raises a communication failure after the 7 s timeout; on restoration "
                   "the incident records the link recovery and buffered observations are flushed.",
                   f"{len(comm)} communication-failure event(s) for {nid}; restoration recorded: {restored}",
                   comm, h, passed, "Store-and-forward keeps edge observations during the outage.")


def s_power() -> dict[str, Any]:
    h = Harness(background=False, seed=17)
    h.run(8)
    h.rt.inject("power_interruption")
    evs = h.run(20)
    pw = [e for e in evs if e.sensor_id == "UPS-1"]
    comm = [e for e in evs if e.category == "communication_failure"]
    status = h.status()
    h.run(100)
    restored = any(u.sensor_id == "UPS-1" and any("restored" in s["note"].lower() for s in u.lifecycle)
                   for u in h.updates)
    passed = bool(pw) and not comm and status["nodes_online"] == status["nodes_total"] and restored
    return _result("power", "Power interruption (mains loss, 90 s simulated)",
                   "Power monitor raises an equipment malfunction (power); UPS carries all edge nodes so no "
                   "communication failures occur; restoration is recorded on the incident.",
                   f"{len(pw)} power event(s); comm failures {len(comm)}; during outage "
                   f"{status['nodes_online']}/{status['nodes_total']} nodes online on {status['power']} "
                   f"({status['ups_pct']} %); restoration recorded: {restored}", pw, h, passed)


def s_multiple() -> dict[str, Any]:
    h = Harness(background=False, seed=21)
    h.run(8)
    h.rt.inject("test_intrusion", "B")
    h.rt.inject("fire")
    h.rt.inject("equipment_failure", "FV-01")
    evs = h.run(90)
    cats = {e.category for e in evs}
    need = {"perimeter_anomaly", "environmental_disturbance", "equipment_malfunction"}
    passed = need <= cats
    return _result("multiple", "Multiple simultaneous events (intrusion + fire + device fault)",
                   "Three independent incidents are raised with their own categories; observations from "
                   "different zones/groups are not merged into one incident.",
                   f"{len(evs)} event(s), categories {sorted(cats)}. " + "; ".join(_ev_summary(evs)[:5]),
                   evs, h, passed)


def s_human_loop() -> dict[str, Any]:
    h = Harness(background=False, seed=3)
    h.run(8)
    h.rt.inject("test_intrusion", "A")
    evs = h.run(110)
    ev = next((e for e in evs if e.category == "perimeter_anomaly"), None)
    steps, ok = [], bool(ev)
    if ev:
        try:
            h.rt.act(ev.event_id, "respond", "op1", category="security_team", authorized=True)
            steps.append("respond-before-verify: ACCEPTED (unexpected)"); ok = False
        except TransitionError:
            steps.append("respond before verification rejected ✓")
        h.clock.advance(4.2)
        h.rt.act(ev.event_id, "acknowledge", "op1")
        h.rt.act(ev.event_id, "verify", "op1", outcome="verified_genuine")
        try:
            h.rt.act(ev.event_id, "respond", "op1", category="security_team", authorized=False)
            steps.append("unauthorised response ACCEPTED (unexpected)"); ok = False
        except TransitionError:
            steps.append("response without authorisation rejected ✓")
        h.rt.act(ev.event_id, "respond", "op1", category="security_team", authorized=True)
        h.rt.act(ev.event_id, "resolve", "op1")
        h.rt.act(ev.event_id, "close", "op1")
        stages = [s["stage"] for s in ev.lifecycle]
        need = ["detected", "processed", "classified", "alerted", "acknowledged", "verified",
                "response_initiated", "resolved", "closed"]
        ok = ok and all(s in stages for s in need) and stages.index("closed") > stages.index("resolved")
        steps.append(f"lifecycle: {' → '.join(dict.fromkeys(stages))}")
    return _result("human_loop", "Human-in-the-loop response workflow",
                   "No response without verification and explicit authorisation; full lifecycle "
                   "Detection → … → Closure recorded with timestamps.", "; ".join(steps) or "no event",
                   [ev] if ev else [], h, ok)


SCENARIOS: dict[str, Callable[[], dict[str, Any]]] = {
    "normal": s_normal, "movement": s_movement, "environment": s_environment,
    "malfunction": s_malfunction, "network": s_network, "power": s_power,
    "multiple": s_multiple, "human_loop": s_human_loop,
}


def run_scenarios(names: list[str] | None = None) -> dict[str, Any]:
    names = names or list(SCENARIOS)
    t0 = time.perf_counter()
    results = []
    for n in names:
        if n not in SCENARIOS:
            raise KeyError(n)
        s0 = time.perf_counter()
        try:
            r = SCENARIOS[n]()
        except Exception as exc:  # report, don't crash the harness
            r = {"id": n, "title": n, "expected": "-", "actual": f"harness error: {exc!r}",
                 "result": "ERROR", "event_ids": [], "system_status": {}}
        r["wall_runtime_ms"] = round((time.perf_counter() - s0) * 1000, 1)
        results.append(r)
    return {"run_utc": utc_iso(time.time()), "clock": "virtual (fast-forwarded), fixed seeds",
            "passed": sum(1 for r in results if r["result"] == "PASS"), "total": len(results),
            "duration_ms": round((time.perf_counter() - t0) * 1000, 1), "results": results}
