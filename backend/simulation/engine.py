"""Simulation engine: world model, sensors, edge nodes, network links and power.

Two clocks exist and are kept separate on purpose:

* **Wall clock** (``self.clock()``, epoch seconds, UTC) — stamps every observation
  and event, drives network latency, heartbeats and timeouts.
* **Simulation clock** (``self.sim_time``) — advances by ``real_dt × speed`` and
  drives movement, weather, fires, power drain. Pausing stops it.

Every value produced here is synthetic.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from event_engine.models import Observation, utc_iso

from .adapters import IMAGING, SimulatedAdapter, dist_to_segment
from .environments import LINKS, NODE_MODELS, get_environment

TRACK_COOLDOWN_S = 30.0      # edge re-reports the same track after this (sim s)
FENCE_THRESHOLD_G = 0.30     # edge alarm threshold for fence vibration
FENCE_COOLDOWN_S = 6.0
TEMP_ALARM_C = 55.0
SMOKE_ALARM = 2.0
STORE_FORWARD_MAX = 500


class VirtualClock:
    """Deterministic clock for headless scenario runs and tests."""

    def __init__(self, start: float | None = None):
        self.t = start if start is not None else time.time()

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


@dataclass
class Entity:
    id: str
    kind: str                       # personnel | vehicle | intruder | animal
    x: float
    y: float
    path: list[list[float]]
    speed: float
    authorized: bool
    loop: bool = False
    idx: int = 0
    state: str = "moving"           # moving | climbing | touching | dwell | done
    pause_until: float = 0.0
    ttl: float = 1e9                # sim time at which entity is removed
    label: str = ""
    climb_at: int | None = None     # path index where an intruder climbs the fence
    touch_at: int | None = None     # path index where an animal brushes the fence
    obj_class: str = "person"
    moving: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "x": round(self.x, 1), "y": round(self.y, 1),
                "authorized": self.authorized, "state": self.state, "label": self.label}


@dataclass
class Anomaly:
    id: str
    kind: str                       # fire | leak
    x: float
    y: float
    start: float
    until: float
    intensity: float = 0.0          # 0..1, grows for fires
    sim_time: float = 0.0

    def _growth(self) -> float:
        return self.intensity

    def temp_at(self, x, y):
        if self.kind != "fire":
            return 0.0
        d = math.hypot(self.x - x, self.y - y)
        return self._growth() * 75.0 * max(0.0, 1 - d / 70.0)

    def smoke_at(self, x, y):
        if self.kind != "fire":
            return 0.0
        d = math.hypot(self.x - x, self.y - y)
        return self._growth() * 14.0 * max(0.0, 1 - d / 80.0)

    def heat_at(self, x, y, rng):
        if self.kind != "fire":
            return 0.0
        d = math.hypot(self.x - x, self.y - y)
        return self._growth() * 120.0 if d <= rng else 0.0

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "x": self.x, "y": self.y,
                "intensity": round(self.intensity, 2)}


class SimulationEngine:
    def __init__(self, env_id: str, clock: Callable[[], float] = time.time, seed: int | None = None,
                 ambient_per_min: float = 1.0, background: bool = True, heartbeat_s: float = 2.0,
                 log: Callable[[str, str, str], None] | None = None):
        self.clock = clock
        self.rng = random.Random(seed)
        self.ambient_per_min = ambient_per_min
        self.background = background
        self.heartbeat_s = heartbeat_s
        self.log = log or (lambda lvl, src, msg: None)
        self.adapter = SimulatedAdapter()
        self.load(env_id)

    # ----------------------------------------------------------------- setup
    def load(self, env_id: str) -> None:
        self.env = get_environment(env_id)
        self.env_id = env_id
        self.sensors = {s["id"]: s for s in self.env["sensors"]}
        self.nodes = {n["id"]: n for n in self.env["nodes"]}
        self.sim_time = 0.0
        self.entities: list[Entity] = []
        self.anomalies: list[Anomaly] = []
        self.ent_seq = 0
        self.obs_seq = 0
        self.wind = 2.0 + self.rng.random() * 2
        self.wind_gust_until = -1.0
        self.ambient_temp = 29.0
        self.humidity = 62.0
        self.light = 1.0
        self.gate_open: dict[str, dict[str, Any]] = {}
        self.sensor_state = {sid: {"status": "online", "reading": {}, "active_until": -1.0,
                                   "fault": None, "recover_at": None, "last_value": 0.0}
                             for sid in self.sensors}
        self.node_state = {}
        for nid, n in self.nodes.items():
            skew = self.rng.uniform(-0.8, 0.8) if n["model"] == "esp32" else self.rng.uniform(-0.3, 0.3)
            self.node_state[nid] = {"status": "online", "link_up": True, "link_down_until": None,
                                    "queue": [], "skew": skew, "next_hb": self.clock(),
                                    "last_latency_ms": 0.0, "tx": 0, "powered": True}
        self.power = {"mains": True, "source": "mains", "ups_pct": 100.0, "outage_until": None,
                      "pv_battery_pct": 86.0, "load_w": 0.0}
        self.track_seen: dict[tuple[str, str], float] = {}
        self.last_fence: dict[str, float] = {}
        self.last_env_alarm: dict[str, float] = {}
        self.prev_contact: dict[str, int] = {}
        self.delivery: list[tuple[float, Observation]] = []
        self.next_vehicle = 15.0
        self.counters = {"observations": 0, "delivered": 0, "buffered": 0, "dropped": 0,
                         "retransmits": 0, "heartbeats": 0}
        self.recent_obs: list[dict[str, Any]] = []
        if self.background:
            self._spawn_background()

    def _spawn_background(self) -> None:
        patrol = self.env["routes"]["patrol"]
        for k, start in enumerate([0, 2]):
            path = patrol[start:] + patrol[:start]
            self._add(Entity(self._eid("P"), "personnel", path[0][0], path[0][1], path, 1.4, True,
                             loop=True, label=f"Patrol {k + 1} (badge)"))
        stops = [a for a in self.env["assets"]]
        if len(stops) >= 2:
            path = [[stops[0]["x"] - 15, stops[0]["y"] + 25], [stops[1]["x"] - 15, stops[1]["y"] + 25]]
            self._add(Entity(self._eid("P"), "personnel", path[0][0], path[0][1], path, 1.1, True,
                             loop=True, label="Maintenance staff (permit)"))

    def _eid(self, p: str) -> str:
        self.ent_seq += 1
        return f"{p}{self.ent_seq:03d}"

    def _add(self, e: Entity) -> Entity:
        self.entities.append(e)
        return e

    # ------------------------------------------------------------------ step
    def step(self, real_dt: float, speed: float) -> list[Observation]:
        """Advance the world. Returns observations whose network delivery time
        has arrived (ready for fusion ingest)."""
        now = self.clock()
        dt = real_dt * speed
        self.sim_time += dt
        self._conditions(now, dt)
        self._ambient(dt)
        self._move(dt)
        self._anomalies(dt)
        self._power(dt, now)
        self._failures(now)
        self._read_sensors(now)
        self._heartbeats(now)
        return self._deliver(now)

    def _conditions(self, now: float, dt: float) -> None:
        hour = datetime.fromtimestamp(now).hour + datetime.fromtimestamp(now).minute / 60
        # Daylight from the host's actual local time: 1.0 at noon, ~0.05 at night.
        self.light = round(max(0.05, min(1.0, math.sin(math.pi * (hour - 6) / 12) * 1.3)) if 6 <= hour <= 18 else 0.05, 2)
        self.ambient_temp = 26.0 + 6.0 * math.sin(math.pi * (hour - 9) / 12)
        target = 13.0 if self.sim_time < self.wind_gust_until else 3.0
        self.wind += (target - self.wind) * min(1.0, dt * 0.25) + self.rng.gauss(0, 0.05) * dt
        self.wind = max(0.0, self.wind)

    def _ambient(self, dt: float) -> None:
        if self.background:
            self.next_vehicle -= dt
            if self.next_vehicle <= 0:
                self.next_vehicle = 80 + self.rng.random() * 60
                self.spawn_vehicle()
        if self.ambient_per_min <= 0:
            return
        if self.rng.random() < self.ambient_per_min / 60.0 * dt:
            r = self.rng.random()
            if r < 0.55:
                self.spawn_animal()
            elif r < 0.85:
                self.wind_gust()
            else:
                self.spawn_loiterer()

    def _move(self, dt: float) -> None:
        for e in list(self.entities):
            if self.sim_time >= e.ttl:
                self.entities.remove(e)
                continue
            if e.state in ("climbing", "touching", "dwell"):
                e.moving = False
                if self.sim_time >= e.pause_until:
                    if e.state == "dwell":
                        self.entities.remove(e)
                        continue
                    e.state = "moving"
                continue
            if e.idx >= len(e.path):
                e.state, e.pause_until, e.moving = "dwell", self.sim_time + 25, False
                continue
            tx, ty = e.path[e.idx]
            d = math.hypot(tx - e.x, ty - e.y)
            step = e.speed * dt
            e.moving = True
            if d <= step:
                e.x, e.y = tx, ty
                if e.climb_at is not None and e.idx == e.climb_at:
                    e.state, e.pause_until = "climbing", self.sim_time + 5.0
                if e.touch_at is not None and e.idx == e.touch_at:
                    e.state, e.pause_until = "touching", self.sim_time + 3.0
                e.idx += 1
                if e.idx >= len(e.path) and e.loop:
                    e.idx = 0
            else:
                e.x += (tx - e.x) / d * step
                e.y += (ty - e.y) / d * step
        # Gate state from vehicles at the checkpoint.
        for cp in self.env["checkpoints"]:
            near = [e for e in self.entities if e.kind == "vehicle" and math.hypot(e.x - cp["x"], e.y - cp["y"]) < 14]
            self.gate_open[cp["id"]] = {"authorized": all(v.authorized for v in near)} if near else None

    def _anomalies(self, dt: float) -> None:
        for a in list(self.anomalies):
            if self.sim_time >= a.until:
                self.anomalies.remove(a)
                self.log("info", "sim", f"Simulated {a.kind} anomaly {a.id} ended")
                continue
            if a.kind == "fire":
                a.intensity = min(1.0, a.intensity + dt / 35.0)
            else:
                a.intensity = 1.0

    def _power(self, dt: float, now: float) -> None:
        p = self.power
        if not p["mains"] and p["outage_until"] is not None and self.sim_time >= p["outage_until"]:
            p.update(mains=True, source="mains", outage_until=None)
            self.log("info", "power", "Mains restored; UPS returning to charge")
            self._send_system("UPS-1", "C2", "C", "power", {"restore": True, "state": "mains_restored",
                                                             "message": "Mains restored"}, now)
        if p["mains"]:
            p["ups_pct"] = min(100.0, p["ups_pct"] + dt * 0.15)
        else:
            p["ups_pct"] = max(0.0, p["ups_pct"] - dt * 0.35)
        powered = p["mains"] or p["ups_pct"] > 8.0
        for nid, ns in self.node_state.items():
            if nid == "EN-ENV":
                ns["powered"] = True  # solar + battery, independent of mains
                continue
            if ns["powered"] and not powered:
                self.log("error", "power", f"{nid} shut down: UPS depleted")
            ns["powered"] = powered
        n_on = sum(1 for ns in self.node_state.values() if ns["powered"])
        p["load_w"] = round(n_on * 14 + sum(1 for s in self.sensors.values() if s["type"] in IMAGING) * 7.5, 1)

    def _failures(self, now: float) -> None:
        for sid, st in self.sensor_state.items():
            if st["status"] == "fault" and st["recover_at"] is not None and self.sim_time >= st["recover_at"]:
                st.update(status="online", fault=None, recover_at=None)
                self.log("info", "device", f"{sid} self-test passed; back online")
        for nid, ns in self.node_state.items():
            if not ns["link_up"] and ns["link_down_until"] is not None and now >= ns["link_down_until"]:
                ns["link_up"], ns["link_down_until"] = True, None
                q, ns["queue"] = ns["queue"], []
                self.log("info", "network", f"{nid} uplink restored; flushing {len(q)} buffered observation(s)")
                for i, o in enumerate(q):
                    self._transmit(o, nid, now + i * 0.005)
                ns["next_hb"] = now

    # --------------------------------------------------------------- sensing
    def _read_sensors(self, now: float) -> None:
        for sid, s in self.sensors.items():
            st = self.sensor_state[sid]
            ns = self.node_state[s["node"]]
            if not ns["powered"]:
                st["reading"] = {"text": "no power", "value": None}
                continue
            if st["status"] == "fault":
                st["reading"] = {"text": f"FAULT: {st['fault']}", "value": None}
                continue
            r = self.adapter.read(s, self)
            st["reading"] = {k: v for k, v in r.items() if k not in ("detections", "touching")}
            st["last_value"] = r.get("value") or 0.0
            self._edge_process(s, r, now)

    def _edge_process(self, s: dict[str, Any], r: dict[str, Any], now: float) -> None:
        """Edge analytics: turn raw readings into discrete observations."""
        t, sid = s["type"], s["id"]
        if t in IMAGING or t in ("pir", "microwave", "radar"):
            for det in r.get("detections", []):
                e = det["entity"]
                key = (sid, e.id)
                if self.sim_time - self.track_seen.get(key, -1e9) < TRACK_COOLDOWN_S:
                    continue
                self.track_seen[key] = self.sim_time
                kind = {"thermal": "heat", "radar": "radar"}.get(t, "motion")
                if kind == "heat":
                    from .adapters import HEAT_DT
                    value, unit = HEAT_DT.get(e.kind, 5.0), "ΔT °C"
                elif kind == "radar":
                    value, unit = round(det["distance"], 1), "m"
                else:
                    value, unit = 1.0, "detection"
                details = {"track": f"{sid}/T{e.id[1:]}"}
                zone = None
                if t in IMAGING or t == "radar":
                    # Calibrated cameras / radar localise the object on the ground plane, so the
                    # observation is attributed to the zone the object is in, not the mast's zone.
                    details["position"] = [round(e.x, 1), round(e.y, 1)]
                    zone = self.zone_of(e.x, e.y)
                if t in IMAGING:
                    details.update(self._object_class(e, t))
                self._emit(s, kind, value, unit, det["quality"], now, details, zone=zone)
        elif t == "fence":
            if r["value"] >= FENCE_THRESHOLD_G and self.sim_time - self.last_fence.get(sid, -1e9) >= FENCE_COOLDOWN_S:
                self.last_fence[sid] = self.sim_time
                q = 0.85 if r["value"] >= 0.8 else 0.6
                self._emit(s, "vibration", r["value"], "g", q, now, {"wind_ms": round(self.wind, 1)})
        elif t == "contact":
            prev = self.prev_contact.get(sid, 0)
            self.prev_contact[sid] = r["value"]
            if r["value"] == 1 and prev == 0:
                self._emit(s, "contact", 1.0, "open", 0.95, now, {"authorized": r["authorized"],
                           "access_log": "credential accepted" if r["authorized"] else "no credential"})
        elif t in ("temperature", "smoke", "leak"):
            alarm = {"temperature": r["value"] >= TEMP_ALARM_C, "smoke": r["value"] >= SMOKE_ALARM,
                     "leak": r["value"] >= 1}[t]
            if alarm and self.sim_time - self.last_env_alarm.get(sid, -1e9) >= 30:
                self.last_env_alarm[sid] = self.sim_time
                self._emit(s, t, r["value"], r["unit"], 0.9, now, {})

    def _object_class(self, e: Entity, t: str) -> dict[str, Any]:
        """Simulated edge classifier output, with deliberate misclassification
        rates so that downstream rules cannot trust any single label."""
        true = {"personnel": "person", "intruder": "person", "vehicle": "vehicle", "animal": "animal"}[e.kind]
        r = self.rng.random()
        if t == "optical" and self.light < 0.3:
            if r < 0.25:
                return {"object_class": "unknown", "class_conf": round(0.3 + self.rng.random() * 0.2, 2)}
        if true == "animal" and r < 0.10:
            return {"object_class": "person", "class_conf": round(0.4 + self.rng.random() * 0.2, 2)}
        if true == "person" and r < 0.05:
            return {"object_class": "animal", "class_conf": round(0.4 + self.rng.random() * 0.2, 2)}
        return {"object_class": true, "class_conf": round(0.7 + self.rng.random() * 0.25, 2)}

    def _emit(self, s, kind, value, unit, quality, now, details, zone=None) -> None:
        ns = self.node_state[s["node"]]
        lo, hi = NODE_MODELS[self.nodes[s["node"]]["model"]]["edge_ms"]
        edge_ms = round(self.rng.uniform(lo, hi), 1)
        self.obs_seq += 1
        o = Observation(obs_id=f"OBS-{self.obs_seq:06d}", sensor_id=s["id"], sensor_type=s["type"],
                        node_id=s["node"], zone=zone or s["zone"], kind=kind, value=float(value), unit=unit,
                        quality=round(float(quality), 3), sensor_ts=now + ns["skew"],
                        edge_ts=now + edge_ms / 1000, sim_time=round(self.sim_time, 3),
                        edge_ms=edge_ms, details=details)
        self.counters["observations"] += 1
        self.sensor_state[s["id"]]["active_until"] = self.sim_time + 2.5
        self._transmit(o, s["node"], o.edge_ts)

    def _transmit(self, o: Observation, node_id: str, at: float) -> None:
        ns = self.node_state[node_id]
        if not ns["powered"]:
            self.counters["dropped"] += 1
            return
        if not ns["link_up"]:
            if o.kind == "heartbeat":
                return
            if len(ns["queue"]) < STORE_FORWARD_MAX:
                ns["queue"].append(o)
                self.counters["buffered"] += 1
            else:
                self.counters["dropped"] += 1
            return
        link = LINKS[self.nodes[node_id]["link"]]
        lat = self.rng.uniform(*link["latency"])
        if self.rng.random() < link["loss"]:
            lat = lat * 2 + 50   # MQTT QoS 1: lost publish is retransmitted after a timeout
            self.counters["retransmits"] += 1
        o.network_ms = round(lat, 1)
        ns["last_latency_ms"] = o.network_ms
        ns["tx"] += 1
        self.delivery.append((at + lat / 1000.0, o))

    def _heartbeats(self, now: float) -> None:
        for nid, ns in self.node_state.items():
            if now < ns["next_hb"]:
                continue
            ns["next_hb"] = now + self.heartbeat_s
            if not ns["powered"]:
                continue
            o = Observation(obs_id=f"HB-{nid}-{int(now * 1000)}", sensor_id=nid, sensor_type="edge_node",
                            node_id=nid, zone=self.nodes[nid]["zone"], kind="heartbeat", value=1.0, unit="",
                            quality=1.0, sensor_ts=now + ns["skew"], edge_ts=now, sim_time=self.sim_time,
                            details={"buffered": len(ns["queue"])})
            self.counters["heartbeats"] += 1
            self._transmit(o, nid, now)

    def _deliver(self, now: float) -> list[Observation]:
        ready = [o for t, o in self.delivery if t <= now]
        self.delivery = [(t, o) for t, o in self.delivery if t > now]
        ready.sort(key=lambda o: o.edge_ts + o.network_ms / 1000)
        for o in ready:
            if o.kind != "heartbeat":
                self.counters["delivered"] += 1
                self.recent_obs.append({"obs_id": o.obs_id, "sensor_id": o.sensor_id, "node_id": o.node_id,
                                        "kind": o.kind, "zone": o.zone})
        self.recent_obs = self.recent_obs[-40:]
        return ready

    def _send_system(self, sensor_id, node_id, zone, kind, details, now) -> None:
        self.obs_seq += 1
        o = Observation(obs_id=f"OBS-{self.obs_seq:06d}", sensor_id=sensor_id, sensor_type=kind,
                        node_id=node_id, zone=zone, kind=kind, value=1.0, unit="", quality=0.95,
                        sensor_ts=now, edge_ts=now + 0.002, sim_time=self.sim_time, edge_ms=2.0,
                        network_ms=1.0, details=details)
        self.delivery.append((now + 0.003, o))

    def shift_time(self, delta: float) -> None:
        """After a pause, shift wall-clock deadlines so no false timeouts occur."""
        self.delivery = [(t + delta, o) for t, o in self.delivery]
        for ns in self.node_state.values():
            ns["next_hb"] += delta
            if ns["link_down_until"]:
                ns["link_down_until"] += delta

    # -------------------------------------------------------------- injection
    def spawn_vehicle(self) -> Entity:
        path = [list(p) for p in self.env["routes"]["vehicle_in"]]
        back = list(reversed(path[:-1]))
        return self._add(Entity(self._eid("V"), "vehicle", path[0][0], path[0][1], path + back, 7.0, True,
                                label="Authorised vehicle (permit)", obj_class="vehicle"))

    def _side_geometry(self, zone: str):
        (x0, y0), _, (x1, y1), _ = self.env["perimeter"]
        gx = self.env["checkpoints"][0]["x"]
        if zone == "A":
            return (x0 + x1) / 2, y0, 0, -1
        if zone == "B":
            return x1, (y0 + y1) / 2, 1, 0
        if zone == "C":
            cx = (x0 + gx) / 2 if gx - x0 > x1 - gx else (gx + x1) / 2
            return cx, y1, 0, 1
        return x0, (y0 + y1) / 2, -1, 0

    def spawn_intruder(self, zone: str | None = None) -> Entity:
        zone = zone if zone in ("A", "B", "C", "D") else self.rng.choice(["A", "B", "D"])
        fx, fy, nx, ny = self._side_geometry(zone)
        off = self.rng.uniform(-25, 25)
        fx, fy = fx + off * abs(ny), fy + off * abs(nx)
        target = min(self.env["assets"], key=lambda a: math.hypot(a["x"] - fx, a["y"] - fy))
        path = [[fx + nx * 130, fy + ny * 130], [fx + nx * 3, fy + ny * 3], [fx - nx * 3, fy - ny * 3],
                [fx - nx * 50, fy - ny * 50], [target["x"] + 20, target["y"] + 20]]
        e = Entity(self._eid("X"), "intruder", path[0][0], path[0][1], path, 1.7, False,
                   label="SIMULATED unauthorised person", climb_at=1, ttl=self.sim_time + 260)
        self.log("warn", "sim", f"Injected simulated intrusion scenario toward zone {zone}")
        return self._add(e)

    def spawn_animal(self, zone: str | None = None) -> Entity:
        zone = zone if zone in ("A", "B", "C", "D") else self.rng.choice(["A", "B", "C", "D"])
        fx, fy, nx, ny = self._side_geometry(zone)
        along = self.rng.uniform(-150, 150)
        tx, ty = abs(ny), abs(nx)
        p0 = [fx + nx * 60 + tx * along, fy + ny * 60 + ty * along]
        p1 = [fx + nx * 2 + tx * (along + 20), fy + ny * 2 + ty * (along + 20)]
        p2 = [fx + nx * 70 + tx * (along + 60), fy + ny * 70 + ty * (along + 60)]
        e = Entity(self._eid("A"), "animal", p0[0], p0[1], [p0, p1, p2], 1.2, False,
                   label="Animal (stray dog / wildlife)", touch_at=1, obj_class="animal",
                   ttl=self.sim_time + 200)
        return self._add(e)

    def spawn_loiterer(self) -> Entity:
        zone = self.rng.choice(["A", "B", "D"])
        fx, fy, nx, ny = self._side_geometry(zone)
        tx, ty = abs(ny), abs(nx)
        path = [[fx + nx * 35 - tx * 120, fy + ny * 35 - ty * 120], [fx + nx * 35 + tx * 120, fy + ny * 35 + ty * 120]]
        return self._add(Entity(self._eid("L"), "intruder", path[0][0], path[0][1], path, 1.1, False,
                                label="SIMULATED unidentified person outside fence", ttl=self.sim_time + 260))

    def wind_gust(self, duration: float = 25.0) -> None:
        self.wind_gust_until = self.sim_time + duration
        self.log("info", "sim", f"Simulated wind gust for {duration:.0f} s (sim)")

    def env_anomaly(self, kind: str | None = None, asset: str | None = None) -> Anomaly:
        kind = kind if kind in ("fire", "leak") else self.rng.choice(["fire", "leak"])
        a = next((x for x in self.env["assets"] if x["id"] == asset), None) or self.rng.choice(self.env["assets"])
        if kind == "leak":
            # place at the nearest leak sensor so the scenario is observable
            leaks = [s for s in self.sensors.values() if s["type"] == "leak"]
            sx = min(leaks, key=lambda s: math.hypot(s["x"] - a["x"], s["y"] - a["y"]))
            a = {"x": sx["x"] + 5, "y": sx["y"] + 5, "id": a["id"]}
        an = Anomaly(f"ANOM-{len(self.anomalies) + 1}-{int(self.sim_time)}", kind, a["x"], a["y"],
                     self.sim_time, self.sim_time + (140 if kind == "fire" else 150))
        self.anomalies.append(an)
        self.log("warn", "sim", f"Injected simulated {kind} anomaly near {a['id']}")
        return an

    def equipment_failure(self, sensor_id: str | None = None) -> str:
        candidates = [sid for sid, st in self.sensor_state.items() if st["status"] == "online"]
        sid = sensor_id if sensor_id in self.sensors else self.rng.choice(candidates)
        s = self.sensors[sid]
        fault = {"optical": "video loss (no frames for 3 s)", "lowlight": "video loss", "ptz": "PTZ motor fault",
                 "thermal": "FPA temperature out of range / shutter fault", "fence": "RS-485 processor CRC errors",
                 "radar": "RF self-test failed", "pir": "tamper switch open", "microwave": "tamper",
                 "contact": "end-of-line resistor out of tolerance (cut/short)", "temperature": "I²C NACK",
                 "smoke": "chamber contamination fault", "leak": "cable open-circuit"}[s["type"]]
        st = self.sensor_state[sid]
        st.update(status="fault", fault=fault, recover_at=self.sim_time + 120)
        self._emit_fault(s, fault)
        self.log("error", "device", f"{sid} fault: {fault}")
        return sid

    def _emit_fault(self, s, fault) -> None:
        now = self.clock()
        self.obs_seq += 1
        o = Observation(obs_id=f"OBS-{self.obs_seq:06d}", sensor_id=s["id"], sensor_type=s["type"],
                        node_id=s["node"], zone=s["zone"], kind="fault", value=1.0, unit="", quality=0.95,
                        sensor_ts=now + self.node_state[s["node"]]["skew"], edge_ts=now + 0.004,
                        sim_time=self.sim_time, edge_ms=4.0,
                        details={"fault": fault, "severity": "medium",
                                 "message": f"{s['id']} ({s['type_label']}) reports fault: {fault}"})
        self._transmit(o, s["node"], o.edge_ts)

    def comm_failure(self, node_id: str | None = None, duration_s: float = 25.0) -> str:
        cands = [n for n, ns in self.node_state.items() if ns["link_up"]]
        nid = node_id if node_id in self.nodes else self.rng.choice(cands or list(self.nodes))
        ns = self.node_state[nid]
        ns["link_up"], ns["link_down_until"] = False, self.clock() + duration_s
        self.log("error", "network", f"Simulated uplink loss on {nid} ({LINKS[self.nodes[nid]['link']]['label']}) "
                                     f"for {duration_s:.0f} s wall-clock")
        return nid

    def power_interruption(self, duration_sim_s: float = 90.0) -> None:
        if not self.power["mains"]:
            return
        self.power.update(mains=False, source="UPS battery", outage_until=self.sim_time + duration_sim_s)
        self.log("error", "power", f"Simulated mains failure; site on UPS for {duration_sim_s:.0f} s (sim)")
        self._send_system("UPS-1", "C2", "C", "power",
                          {"state": "mains_lost", "severity": "high",
                           "message": "Mains power lost — critical loads transferred to UPS-1 (battery)"},
                          self.clock())

    # --------------------------------------------------------------- queries
    def zone_of(self, x: float, y: float) -> str | None:
        hit = None
        for z in self.env["zones"]:
            x0, y0, x1, y1 = z["rect"]
            if x0 <= x <= x1 and y0 <= y <= y1:
                hit = z["id"] if hit is None or z["kind"] == "interior" else hit
        return hit

    def authorized_present(self, zone: str) -> bool:
        return any(e.authorized and self.zone_of(e.x, e.y) == zone for e in self.entities)

    def sensor_online(self, sid: str) -> bool:
        s = self.sensors[sid]
        ns = self.node_state[s["node"]]
        return self.sensor_state[sid]["status"] == "online" and ns["powered"] and ns["link_up"]

    def snapshot(self) -> dict[str, Any]:
        sensors = {}
        for sid, st in self.sensor_state.items():
            s = self.sensors[sid]
            ns = self.node_state[s["node"]]
            status = st["status"]
            if not ns["powered"]:
                status = "unpowered"
            elif not ns["link_up"] and status == "online":
                status = "unreachable"
            sensors[sid] = {"status": status, "reading": st["reading"],
                            "active": self.sim_time < st["active_until"]}
        nodes = {nid: {"status": "online" if ns["powered"] and ns["link_up"] else
                       ("unpowered" if not ns["powered"] else "link_down"),
                       "link": self.nodes[nid]["link"], "queue": len(ns["queue"]),
                       "latency_ms": ns["last_latency_ms"], "skew_ms": round(ns["skew"] * 1000),
                       "tx": ns["tx"]} for nid, ns in self.node_state.items()}
        return {"entities": [e.to_dict() for e in self.entities],
                "anomalies": [a.to_dict() for a in self.anomalies],
                "sensors": sensors, "nodes": nodes,
                "power": dict(self.power, ups_pct=round(self.power["ups_pct"], 1)),
                "conditions": {"wind_ms": round(self.wind, 1), "light": self.light,
                               "ambient_c": round(self.ambient_temp, 1), "humidity": self.humidity,
                               "gust": self.sim_time < self.wind_gust_until},
                "gates": {k: (v is not None) for k, v in self.gate_open.items()},
                "counters": dict(self.counters), "recent_obs": self.recent_obs[-12:],
                "wall_utc": utc_iso(self.clock())}
