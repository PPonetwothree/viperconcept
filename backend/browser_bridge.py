"""In-browser backend for static hosting (Netlify, GitHub Pages, ...).

When the frontend finds no VIPER server it loads Pyodide (CPython compiled to
WebAssembly) and runs *this same Python code* inside the visitor's browser
tab. This module stands in for ``main.py`` + ``api/routes.py`` + ``api/ws.py``:
it exposes ``handle()`` (one REST request) and ``tick()`` (one simulation
step), and pushes WebSocket-style messages to a JavaScript callback.

The simulation, fusion rules, lifecycle state machine and SQLite store are the
unmodified modules used by the server, so both deployments behave the same.
History lives in an in-memory SQLite database and resets when the tab reloads.
FastAPI/pydantic are not used here; request validation mirrors routes.py.
"""
from __future__ import annotations

import csv
import io
import json
import re
import time
from typing import Any, Callable
from urllib.parse import parse_qs

import config
from api.reports import incident_report_md
from database.store import EXPORT_FIELDS, EventStore, export_rows
from devices.catalog import DEVICES, SELECTION_RATIONALE
from event_engine.lifecycle import TransitionError
from event_engine.models import CATEGORIES, LIFECYCLE_STAGES, RESPONSE_CATEGORIES, SEVERITIES, \
    VERIFICATION_OUTCOMES
from simulation.environments import LINKS, NODE_MODELS, get_environment, list_environments
from simulation.runtime import Runtime
from simulation.scenarios import SCENARIOS, run_scenarios

INJECT_KINDS = {"test_intrusion", "equipment_failure", "comm_failure", "env_anomaly", "fire", "leak",
                "power_interruption", "animal", "wind_gust", "vehicle"}
VERIFY_OUTCOMES = {"verified_genuine", "false_positive", "verified_benign"}
RESPOND_CATS = {"security_team", "infrastructure_ops", "technical_maintenance", "emergency_services", "escalation"}
ACTIONS = {"acknowledge": "acknowledge", "verify": "verify", "false-positive": "false_positive",
           "respond": "respond", "resolve": "resolve", "close": "close"}


class HTTPError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


class Bridge:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self.store = EventStore(":memory:")
        self.rt = Runtime(self.store, clock=clock)
        self.sink: Callable[[str], None] | None = None
        self.rt.listeners.append(self._forward)
        self.rt.log("info", "system", "VIPER demonstrator started in SIMULATION mode (in-browser engine, "
                                      "no server) — no hardware connected")
        if config.AUTOSTART:
            self.rt.control("start")
        self._last = clock()
        self._n = 0
        self._snap_every = max(1, round(config.TICK_HZ / config.SNAPSHOT_HZ))

    # ------------------------------------------------------------ push channel
    def _forward(self, msg: dict[str, Any]) -> None:
        if self.sink:
            self.sink(json.dumps(msg, default=str))

    def connect(self, sink: Callable[[str], None]) -> None:
        """Equivalent of a WebSocket connect: register the sink and send hello."""
        self.sink = sink
        sink(json.dumps({"type": "hello", "sim": self.rt.sim_status(), "snapshot": self.rt.snapshot()},
                        default=str))

    def tick(self) -> None:
        """One iteration of Runtime.run_forever(), driven by a JS timer."""
        now = self.clock()
        dt = min(0.5, now - self._last)
        self._last = now
        try:
            self.rt.step(dt)
            self._n += 1
            if self._n % self._snap_every == 0:
                self._forward({"type": "snapshot", "snapshot": self.rt.snapshot()})
        except Exception as exc:  # keep the loop alive, surface the error
            self.rt.log("error", "runtime", f"tick failed: {exc!r}")

    # -------------------------------------------------------------------- REST
    def handle(self, method: str, url: str, body: str | None) -> str:
        """Serve one request. Returns JSON {status, type, body} (body is text)."""
        path, _, qs = url.partition("?")
        query = {k: v[-1] for k, v in parse_qs(qs).items()}
        try:
            data = json.loads(body) if body else {}
            result = self._route(method.upper(), path, query, data)
            if isinstance(result, tuple):
                ctype, text = result
            else:
                ctype, text = "application/json", json.dumps(result, default=str)
            return json.dumps({"status": 200, "type": ctype, "body": text})
        except HTTPError as e:
            return json.dumps({"status": e.status, "type": "application/json",
                               "body": json.dumps({"detail": e.detail})})
        except Exception as e:  # unexpected: report like a 500
            return json.dumps({"status": 500, "type": "application/json",
                               "body": json.dumps({"detail": f"internal error: {e!r}"})})

    def _route(self, m: str, p: str, q: dict[str, str], b: dict[str, Any]):
        rt = self.rt
        if m == "GET":
            if p == "/api/health":
                return {"status": "ok", "mode": "SIMULATION", "hardware_connected": False,
                        "sim": rt.sim_status(), "db_path": "in-browser (memory)", "engine": "browser"}
            if p == "/api/meta":
                return {"severities": SEVERITIES, "categories": CATEGORIES,
                        "response_categories": RESPONSE_CATEGORIES,
                        "verification_outcomes": VERIFICATION_OUTCOMES, "lifecycle_stages": LIFECYCLE_STAGES,
                        "links": LINKS, "node_models": NODE_MODELS,
                        "config": {"tick_hz": config.TICK_HZ, "correlation_window_s": config.CORRELATION_WINDOW_S,
                                   "heartbeat_interval_s": config.HEARTBEAT_INTERVAL_S,
                                   "heartbeat_timeout_s": config.HEARTBEAT_TIMEOUT_S,
                                   "ambient_events_per_min": config.AMBIENT_EVENTS_PER_MIN}}
            if p == "/api/environments":
                return list_environments()
            if mt := re.fullmatch(r"/api/environments/([^/]+)", p):
                try:
                    return get_environment(mt[1])
                except KeyError:
                    raise HTTPError(404, f"Unknown environment '{mt[1]}'")
            if p == "/api/devices":
                return {"devices": DEVICES, "selection_rationale": SELECTION_RATIONALE}
            if p == "/api/sim/state":
                return rt.snapshot()
            if p == "/api/events":
                return self._events(q)
            if mt := re.fullmatch(r"/api/events/([^/]+)/report", p):
                ev = self._get(mt[1])
                if q.get("format") == "md":
                    return "text/markdown", incident_report_md(ev)
                return rt.event_payload(ev)
            if mt := re.fullmatch(r"/api/events/([^/]+)", p):
                return rt.event_payload(self._get(mt[1]))
            if p == "/api/export":
                return self._export(q)
            if p == "/api/analytics":
                return rt.analytics(q.get("environment") or None)
            if p == "/api/logs":
                return self.store.logs(self._int(q, "limit", 200, 1, 2000))
            if p == "/api/tests/scenarios":
                return list(SCENARIOS)
            if p == "/api/tests/latest":
                return self.store.latest_test_run() or {}
            if p == "/api/docs":
                return sorted(x.name for x in config.DOCS_DIR.glob("*.md"))
            if mt := re.fullmatch(r"/api/docs/([^/]+)", p):
                path = (config.DOCS_DIR / mt[1]).resolve()
                if path.parent != config.DOCS_DIR.resolve() or path.suffix != ".md" or not path.exists():
                    raise HTTPError(404, "Document not found")
                return "text/markdown", path.read_text(encoding="utf-8")
        elif m == "POST":
            if p == "/api/sim/control":
                action = b.get("action")
                if action not in ("start", "pause", "resume", "reset"):
                    raise HTTPError(422, "action: must be start, pause, resume or reset")
                if action == "reset" and b.get("clear_history"):
                    self.store.clear()
                return rt.control(action)
            if p == "/api/sim/speed":
                if b.get("speed") not in (1, 2, 5):
                    raise HTTPError(422, "speed: must be 1, 2 or 5")
                return rt.set_speed(b["speed"])
            if p == "/api/sim/environment":
                try:
                    return rt.set_environment(str(b.get("environment_id", "")))
                except ValueError as e:
                    raise HTTPError(404, str(e))
            if p == "/api/sim/inject":
                if b.get("kind") not in INJECT_KINDS:
                    raise HTTPError(422, "kind: unknown injection")
                if rt.state != "running":
                    raise HTTPError(409, "Start or resume the simulation before injecting events.")
                try:
                    return rt.inject(b["kind"], b.get("target"))
                except (ValueError, IndexError) as e:
                    raise HTTPError(400, str(e))
            if mt := re.fullmatch(r"/api/events/([^/]+)/([a-z-]+)", p):
                return self._act(mt[1], mt[2], b)
            if p == "/api/tests/run":
                try:
                    report = run_scenarios(b.get("scenarios"))
                except KeyError as e:
                    raise HTTPError(404, f"Unknown scenario {e}")
                self.store.save_test_run(report)
                return report
        raise HTTPError(404, "Not Found")

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _int(q: dict[str, str], key: str, default: int, lo: int, hi: int | None = None) -> int:
        try:
            v = int(q.get(key, default))
        except ValueError:
            raise HTTPError(422, f"{key}: must be an integer")
        if v < lo or (hi is not None and v > hi):
            raise HTTPError(422, f"{key}: out of range")
        return v

    def _get(self, event_id: str):
        ev = self.store.get(event_id)
        if not ev:
            raise HTTPError(404, f"{event_id} not found")
        return ev

    def _events(self, q: dict[str, str]):
        sev = [s for s in q.get("severity", "").split(",") if s]
        bad = [s for s in sev if s not in SEVERITIES]
        if bad:
            raise HTTPError(422, f"Unknown severity {bad}")
        order = q.get("order", "desc")
        if order not in ("asc", "desc"):
            raise HTTPError(422, "order: must be asc or desc")
        evs, total = self.store.query(sev or None, q.get("sensor_id"), q.get("zone"), q.get("category"),
                                      (q.get("q") or None) and q["q"][:64], q.get("status"),
                                      q.get("environment"), limit=self._int(q, "limit", 200, 1, 5000),
                                      offset=self._int(q, "offset", 0, 0), order=order)
        return {"total": total, "events": [self.rt.event_payload(e) for e in evs]}

    def _act(self, event_id: str, verb: str, b: dict[str, Any]):
        if verb not in ACTIONS:
            raise HTTPError(404, "Not Found")
        operator = str(b.get("operator", "")).strip()
        if not 1 <= len(operator) <= 64:
            raise HTTPError(422, "operator: required (1–64 characters)")
        kw: dict[str, Any] = {"operator": operator, "note": str(b.get("note", ""))[:500]}
        if verb == "verify":
            if b.get("outcome") not in VERIFY_OUTCOMES:
                raise HTTPError(422, "outcome: invalid verification outcome")
            kw["outcome"] = b["outcome"]
        if verb == "respond":
            if b.get("category") not in RESPOND_CATS:
                raise HTTPError(422, "category: invalid response category")
            if not isinstance(b.get("authorized"), bool):
                raise HTTPError(422, "authorized: field required")
            kw.update(category=b["category"], authorized=b["authorized"])
        try:
            return self.rt.event_payload(self.rt.act(event_id, ACTIONS[verb], **kw))
        except KeyError:
            raise HTTPError(404, f"{event_id} not found")
        except TransitionError as e:
            raise HTTPError(409, str(e))

    def _export(self, q: dict[str, str]):
        evs = self.store.all_events(q.get("environment") or None)
        if q.get("format", "csv") == "json":
            return "application/json", json.dumps({"mode": "SIMULATION", "exported_utc": self.rt.sim_status()["wall_utc"],
                                                   "events": [e.to_dict() for e in evs]}, indent=2, default=str)
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=EXPORT_FIELDS)
        w.writeheader()
        w.writerows(export_rows(evs))
        return "text/csv", buf.getvalue()
