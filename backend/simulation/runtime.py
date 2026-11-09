"""Runtime: wires the simulation engine, fusion engine, event store and
broadcast listeners together. One instance drives the live server; scenario
tests create isolated headless instances with a ``VirtualClock``."""
from __future__ import annotations

import asyncio
import statistics
import time
from typing import Any, Callable

import config
from database.store import EventStore
from event_engine import lifecycle
from event_engine.fusion import FusionEngine
from event_engine.models import CATEGORIES, SEVERITIES, Event, local_str, utc_iso

from .engine import SimulationEngine
from .environments import ENVIRONMENTS

SPEEDS = (1.0, 2.0, 5.0)


class Runtime:
    def __init__(self, store: EventStore, env_id: str = config.DEFAULT_ENVIRONMENT,
                 clock: Callable[[], float] = time.time, seed: int | None = config.RANDOM_SEED,
                 ambient_per_min: float = config.AMBIENT_EVENTS_PER_MIN, background: bool = True,
                 persist_logs: bool = True):
        self.store = store
        self.clock = clock
        self.seed = seed
        self.ambient = ambient_per_min
        self.background = background
        self.persist_logs = persist_logs
        self.listeners: list[Callable[[dict[str, Any]], None]] = []
        self.running = False
        self.speed = 1.0
        self.paused_at: float | None = None
        self.state = "stopped"          # stopped | running | paused
        self._build(env_id)

    def _build(self, env_id: str) -> None:
        self.engine = SimulationEngine(env_id, clock=self.clock, seed=self.seed,
                                       ambient_per_min=self.ambient, background=self.background,
                                       heartbeat_s=config.HEARTBEAT_INTERVAL_S, log=self.log)
        self.fusion = FusionEngine(self, self.store.next_event_id, window_s=config.CORRELATION_WINDOW_S,
                                   heartbeat_timeout_s=config.HEARTBEAT_TIMEOUT_S, log=self.log)
        self.session_start = self.clock()
        self.avail_online = 0.0
        self.avail_total = 0.0
        self.sensor_uptime = {sid: [0.0, 0.0] for sid in self.engine.sensors}
        self.tick_ms: list[float] = []

    # ------------------------------------------------------- FusionContext API
    @property
    def environment(self) -> str:
        return self.engine.env_id

    def sensor(self, sensor_id: str) -> dict[str, Any] | None:
        if sensor_id in self.engine.sensors:
            return self.engine.sensors[sensor_id]
        if sensor_id in self.engine.nodes:
            return self.engine.nodes[sensor_id]
        if sensor_id in ("UPS-1", "C2"):
            return {"id": sensor_id, "zone": "C", "type": "power"}
        return None

    def sensor_healthy(self, sensor_id: str) -> bool:
        st = self.engine.sensor_state.get(sensor_id)
        return st is None or st["status"] == "online"

    def authorized_present(self, zone: str) -> bool:
        return self.engine.authorized_present(zone)

    def wind_ms(self) -> float:
        return self.engine.wind

    def light(self) -> float:
        return self.engine.light

    def sim_time(self) -> float:
        return round(self.engine.sim_time, 3)

    # ------------------------------------------------------------- messaging
    def emit(self, msg: dict[str, Any]) -> None:
        for fn in list(self.listeners):
            try:
                fn(msg)
            except Exception:  # a broken client must never stop the engine
                pass

    def log(self, level: str, source: str, message: str) -> None:
        t = self.clock()
        entry = {"ts_utc": utc_iso(t), "ts_epoch": t, "level": level, "source": source, "message": message}
        if self.persist_logs:
            self.store.log(level, source, message, t)
        self.emit({"type": "log", "log": entry})

    def event_payload(self, ev: Event) -> dict[str, Any]:
        d = ev.to_dict()
        d["actions"] = lifecycle.available_actions(ev)
        return d

    # ------------------------------------------------------------------ tick
    def step(self, real_dt: float) -> list[tuple[str, Event]]:
        if self.state != "running":
            return []
        t0 = time.perf_counter()
        observations = self.engine.step(real_dt, self.speed)
        now = self.clock()
        for o in observations:
            self.fusion.ingest(o, at=now)
            if o.kind != "heartbeat":
                self.emit({"type": "observation", "obs": {
                    "obs_id": o.obs_id, "sensor_id": o.sensor_id, "node_id": o.node_id, "zone": o.zone,
                    "kind": o.kind, "value": o.value, "unit": o.unit, "flags": o.flags,
                    "network_ms": o.network_ms, "edge_ms": o.edge_ms}})
        out = self.fusion.step(at=now)
        for kind, ev in out:
            self.store.save(ev)
            self.emit({"type": "event" if kind == "new" else "event_update", "event": self.event_payload(ev)})
            if kind == "new" and ev.severity != "info":
                self.log("warn" if ev.severity in ("low", "medium") else "error", "fusion",
                         f"{ev.event_id} {CATEGORIES[ev.category]} [{ev.severity}] {ev.description}")
        # availability accounting (time-weighted)
        for sid in self.engine.sensors:
            on = self.engine.sensor_online(sid)
            self.sensor_uptime[sid][0] += real_dt if on else 0.0
            self.sensor_uptime[sid][1] += real_dt
            self.avail_online += real_dt if on else 0.0
            self.avail_total += real_dt
        self.tick_ms.append((time.perf_counter() - t0) * 1000)
        self.tick_ms = self.tick_ms[-200:]
        return out

    async def run_forever(self) -> None:
        period = 1.0 / config.TICK_HZ
        snap_every = max(1, round(config.TICK_HZ / config.SNAPSHOT_HZ))
        last = time.time()
        n = 0
        while True:
            await asyncio.sleep(period)
            now = time.time()
            dt = min(0.5, now - last)
            last = now
            try:
                self.step(dt)
                n += 1
                if n % snap_every == 0:
                    self.emit({"type": "snapshot", "snapshot": self.snapshot()})
            except Exception as exc:  # keep the loop alive, surface the error
                self.log("error", "runtime", f"tick failed: {exc!r}")

    # --------------------------------------------------------------- control
    def control(self, action: str) -> dict[str, Any]:
        if action == "start":
            if self.state == "paused":
                return self.control("resume")
            self.state = "running"
            self.log("info", "control", "Simulation started")
        elif action == "pause":
            if self.state == "running":
                self.state, self.paused_at = "paused", self.clock()
                self.log("info", "control", "Simulation paused")
        elif action == "resume":
            if self.state == "paused":
                delta = self.clock() - (self.paused_at or self.clock())
                self.engine.shift_time(delta)
                for k in self.fusion.last_heartbeat:
                    self.fusion.last_heartbeat[k] += delta
                for b in self.fusion.buckets.values():
                    b.opened_wall += delta
                self.state, self.paused_at = "running", None
                self.log("info", "control", f"Simulation resumed after {delta:.1f} s pause")
        elif action == "reset":
            prev = self.state
            self._build(self.engine.env_id)
            self.state = "running" if prev == "running" else "stopped"
            self.log("info", "control", "Simulation reset (world state cleared; incident history kept)")
        else:
            raise ValueError(f"Unknown control action '{action}'")
        self.emit({"type": "snapshot", "snapshot": self.snapshot()})
        return self.sim_status()

    def set_speed(self, speed: float) -> dict[str, Any]:
        if float(speed) not in SPEEDS:
            raise ValueError(f"Speed must be one of {SPEEDS}")
        self.speed = float(speed)
        self.log("info", "control", f"Simulation speed set to {self.speed:g}×")
        return self.sim_status()

    def set_environment(self, env_id: str) -> dict[str, Any]:
        if env_id not in ENVIRONMENTS:
            raise ValueError(f"Unknown environment '{env_id}'")
        self._build(env_id)
        self.log("info", "control", f"Environment switched to {ENVIRONMENTS[env_id]['name']}")
        self.emit({"type": "environment", "environment": env_id})
        return self.sim_status()

    def inject(self, kind: str, target: str | None = None) -> dict[str, Any]:
        e = self.engine
        if kind == "test_intrusion":
            ref = e.spawn_intruder(target).id
        elif kind == "equipment_failure":
            ref = e.equipment_failure(target)
        elif kind == "comm_failure":
            ref = e.comm_failure(target)
        elif kind == "env_anomaly":
            ref = e.env_anomaly(target).id
        elif kind == "fire":
            ref = e.env_anomaly("fire").id
        elif kind == "leak":
            ref = e.env_anomaly("leak").id
        elif kind == "power_interruption":
            e.power_interruption()
            ref = "UPS-1"
        elif kind == "animal":
            ref = e.spawn_animal(target).id
        elif kind == "wind_gust":
            e.wind_gust()
            ref = "wind"
        elif kind == "vehicle":
            ref = e.spawn_vehicle().id
        else:
            raise ValueError(f"Unknown injection '{kind}'")
        return {"injected": kind, "ref": ref, "sim_time": self.sim_time(), "wall_utc": utc_iso(self.clock())}

    # ------------------------------------------------------- operator actions
    def act(self, event_id: str, action: str, operator: str, note: str = "",
            outcome: str | None = None, category: str | None = None, authorized: bool = False) -> Event:
        ev = self.store.get(event_id)
        if ev is None:
            raise KeyError(event_id)
        t = self.clock()
        if action == "acknowledge":
            lifecycle.acknowledge(ev, operator, note, t)
        elif action == "verify":
            lifecycle.verify(ev, operator, outcome or "", note, t)
        elif action == "false_positive":
            lifecycle.mark_false_positive(ev, operator, note, t)
        elif action == "respond":
            lifecycle.initiate_response(ev, operator, category or "", authorized, note, t)
        elif action == "resolve":
            lifecycle.resolve(ev, operator, note, t)
        elif action == "close":
            lifecycle.close(ev, operator, note, t)
        else:
            raise lifecycle.TransitionError(f"Unknown action '{action}'")
        self.store.save(ev)
        self.log("info", "operator", f"{operator.strip()} → {action} on {event_id}")
        self.emit({"type": "event_update", "event": self.event_payload(ev)})
        return ev

    # ---------------------------------------------------------------- status
    def sim_status(self) -> dict[str, Any]:
        return {"state": self.state, "speed": self.speed, "sim_time": self.sim_time(),
                "environment": self.engine.env_id, "wall_utc": utc_iso(self.clock()),
                "wall_local": local_str(self.clock()), "session_start_utc": utc_iso(self.session_start)}

    def kpis(self) -> dict[str, Any]:
        sensors = self.engine.sensors
        online = sum(1 for sid in sensors if self.engine.sensor_online(sid))
        env = self.engine.env_id
        c = self.store.conn
        active = c.execute("SELECT COUNT(*) FROM events WHERE environment=? AND severity!='info' AND "
                           "resolution_status IN ('open','response_initiated')", (env,)).fetchone()[0]
        awaiting = c.execute("SELECT COUNT(*) FROM events WHERE environment=? AND "
                             "verification_status='awaiting_review' AND resolution_status!='closed'",
                             (env,)).fetchone()[0]
        det = c.execute("SELECT AVG(detection_latency_ms) FROM events WHERE environment=? AND "
                        "category NOT IN ('communication_failure') AND created_epoch>=?",
                        (env, self.session_start)).fetchone()[0]
        ack = c.execute("SELECT AVG(ack_epoch-alert_epoch) FROM events WHERE environment=? AND "
                        "ack_epoch IS NOT NULL AND created_epoch>=?", (env, self.session_start)).fetchone()[0]
        return {"total_sensors": len(sensors), "online_sensors": online, "offline_sensors": len(sensors) - online,
                "active_incidents": active, "awaiting_verification": awaiting,
                "mean_detection_latency_ms": round(det, 1) if det is not None else None,
                "mean_ack_time_s": round(ack, 1) if ack is not None else None,
                "availability_pct": round(100 * self.avail_online / self.avail_total, 2) if self.avail_total else 100.0,
                "tick_ms": round(statistics.mean(self.tick_ms), 2) if self.tick_ms else 0.0,
                "fusion": dict(self.fusion.stats)}

    def snapshot(self) -> dict[str, Any]:
        snap = self.engine.snapshot()
        snap["sim"] = self.sim_status()
        snap["kpis"] = self.kpis()
        snap["clock_offsets_ms"] = {k: round(v * 1000) for k, v in self.fusion.offsets.items()}
        return snap

    # ------------------------------------------------------------- analytics
    def analytics(self, environment: str | None = None) -> dict[str, Any]:
        evs = self.store.all_events(environment)
        incidents = [e for e in evs if e.severity != "info"]
        now = self.clock()

        def stats(vals: list[float]) -> dict[str, Any]:
            if not vals:
                return {"n": 0, "mean": None, "p50": None, "p95": None, "max": None}
            v = sorted(vals)
            return {"n": len(v), "mean": round(statistics.mean(v), 2), "p50": round(v[len(v) // 2], 2),
                    "p95": round(v[min(len(v) - 1, int(0.95 * len(v)))], 2), "max": round(v[-1], 2)}

        per_hour = [0] * 24
        per_min = [0] * 60
        for e in evs:
            age = now - e.created_epoch
            if age < 86400:
                per_hour[23 - int(age // 3600)] += 1
            if age < 3600:
                per_min[59 - int(age // 60)] += 1
        by_cat: dict[str, int] = {}
        by_sev = {s: 0 for s in SEVERITIES}
        for e in evs:
            by_cat[e.category] = by_cat.get(e.category, 0) + 1
            by_sev[e.severity] += 1
        verified = [e for e in incidents if e.verification_status in ("verified_genuine", "false_positive", "verified_benign")]
        fp = [e for e in verified if e.verification_status == "false_positive"]
        det = [e.latency.get("detection_ms") for e in incidents
               if e.latency.get("detection_ms") is not None and e.category != "communication_failure"]
        ack = [e.ack_epoch - e.alert_epoch for e in incidents if e.ack_epoch and e.alert_epoch]
        res = [e.resolved_epoch - e.alert_epoch for e in incidents if e.resolved_epoch and e.alert_epoch]
        avail = [{"sensor_id": sid, "type": self.engine.sensors[sid]["type"],
                  "availability_pct": round(100 * on / tot, 2) if tot else 100.0, "observed_s": round(tot, 1)}
                 for sid, (on, tot) in self.sensor_uptime.items()]
        by_cat_table = []
        for cat in sorted(by_cat):
            ce = [e for e in evs if e.category == cat]
            ca = [e.ack_epoch - e.alert_epoch for e in ce if e.ack_epoch and e.alert_epoch]
            by_cat_table.append({"category": cat, "count": len(ce),
                                 "false_positive": sum(1 for e in ce if e.verification_status == "false_positive"),
                                 "mean_ack_s": round(statistics.mean(ca), 1) if ca else None,
                                 "mean_conf": round(statistics.mean(e.confidence for e in ce), 3)})
        return {"generated_utc": utc_iso(now), "environment": environment or "all",
                "total_events": len(evs), "total_incidents": len(incidents),
                "events_per_hour": per_hour, "events_per_minute": per_min,
                "by_category": by_cat, "by_severity": by_sev, "by_category_table": by_cat_table,
                "false_positive_rate": round(len(fp) / len(verified), 3) if verified else None,
                "verified_count": len(verified), "false_positive_count": len(fp),
                "detection_latency_ms": stats(det), "detection_latency_samples_ms": det[-500:],
                "ack_latency_s": stats(ack),
                "resolution_time_s": stats(res), "sensor_availability": avail,
                "session_availability_pct": self.kpis()["availability_pct"],
                "fusion_stats": dict(self.fusion.stats), "pipeline_counters": dict(self.engine.counters)}
