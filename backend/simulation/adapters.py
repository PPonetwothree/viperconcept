"""Sensor adapter interface.

The simulation reads every sensor through a ``SensorAdapter``. Only the
simulated adapter exists in this build. A real deployment would add adapters
that implement the same ``read()`` contract — for example an MQTT subscriber
for ESP32 nodes, an ONVIF/RTSP analytics client for cameras, or a Modbus RTU
poller for RS-485 fence processors — without touching the fusion engine.
"""
from __future__ import annotations

import math
from typing import Any, Protocol


class SensorAdapter(Protocol):
    """Contract: return the sensor's current reading and the entities/conditions
    it detects. ``detections`` items are dicts with at least ``entity``,
    ``distance`` and ``quality``."""

    def read(self, sensor: dict[str, Any], world: Any) -> dict[str, Any]: ...


class HardwareAdapterTemplate:
    """Placeholder showing where a physical integration plugs in.

    Deliberately NOT implemented: this build has no hardware attached and must
    not pretend otherwise. Implement ``read`` against a real transport (e.g.
    paho-mqtt topic ``viper/<node>/<sensor>``) and register it in
    ``SimulationEngine.adapters`` for the sensor types it serves.
    """

    def read(self, sensor: dict[str, Any], world: Any) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError("No hardware adapter is configured in this demonstrator.")


def angle_diff(a: float, b: float) -> float:
    return (a - b + 180) % 360 - 180


def in_coverage(sensor: dict[str, Any], x: float, y: float) -> tuple[bool, float]:
    dx, dy = x - sensor["x"], y - sensor["y"]
    d = math.hypot(dx, dy)
    if d > sensor["range"]:
        return False, d
    if sensor["fov"] >= 360 or d < 1e-6:
        return True, d
    bearing = math.degrees(math.atan2(dy, dx))
    return abs(angle_diff(bearing, sensor["dir"])) <= sensor["fov"] / 2, d


def dist_to_segment(px: float, py: float, seg: list[float]) -> float:
    x1, y1, x2, y2 = seg
    vx, vy = x2 - x1, y2 - y1
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * vx + (py - y1) * vy) / L2))
    return math.hypot(px - (x1 + t * vx), py - (y1 + t * vy))


IMAGING = {"optical", "lowlight", "ptz", "thermal"}
MOTION = {"pir", "microwave", "radar"}
# Thermal contrast against background (°C) per entity kind — illustrative.
HEAT_DT = {"personnel": 9.0, "intruder": 9.5, "animal": 4.5, "vehicle": 18.0}


class SimulatedAdapter:
    """Computes readings from the simulated world model. All values are synthetic."""

    def read(self, s: dict[str, Any], world: Any) -> dict[str, Any]:
        t = s["type"]
        if t in IMAGING or t in MOTION:
            return self._coverage(s, world)
        if t == "fence":
            return self._fence(s, world)
        if t == "contact":
            return self._contact(s, world)
        return self._environmental(s, world)

    def _coverage(self, s, world):
        dets = []
        for e in world.entities:
            if s["type"] in ("pir", "microwave", "radar") and not e.moving and e.kind != "intruder":
                continue
            ok, d = in_coverage(s, e.x, e.y)
            if not ok:
                continue
            q = self._quality(s, world, d)
            # Optical cameras in low light only detect intermittently.
            if s["type"] == "optical" and world.light < 0.3 and world.rng.random() > 0.35:
                continue
            dets.append({"entity": e, "distance": d, "quality": q})
        if s["type"] == "thermal":
            fire = max((a.heat_at(s["x"], s["y"], s["range"]) for a in world.anomalies), default=0.0)
            v = max([HEAT_DT.get(x["entity"].kind, 5.0) for x in dets] + [fire, 0.0])
            return {"value": round(v, 1), "unit": "ΔT °C", "detections": dets, "text": f"max ΔT {v:.1f} °C"}
        if s["type"] == "radar":
            near = min((x["distance"] for x in dets), default=None)
            return {"value": len(dets), "unit": "tracks", "detections": dets,
                    "text": f"{len(dets)} track(s)" + (f", nearest {near:.0f} m" if near else "")}
        if s["type"] in ("pir", "microwave"):
            return {"value": 1 if dets else 0, "unit": "motion", "detections": dets,
                    "text": "MOTION" if dets else "idle"}
        return {"value": len(dets), "unit": "objects", "detections": dets,
                "text": f"{len(dets)} object(s) · light {world.light:.2f}"}

    def _quality(self, s, world, d):
        frac = d / max(1.0, s["range"])
        if s["type"] == "thermal":
            return round(0.9 * (1 - 0.3 * frac), 3)
        if s["type"] == "optical":
            base = 0.92 if world.light >= 0.3 else 0.5
            return round(base * (1 - 0.4 * frac), 3)
        if s["type"] in ("lowlight", "ptz"):
            base = 0.9 if world.light >= 0.3 else 0.78
            return round(base * (1 - 0.3 * frac), 3)
        return {"pir": 0.7, "microwave": 0.72, "radar": 0.8}.get(s["type"], 0.6)

    def _fence(self, s, world):
        g = world.wind * 0.035 * (0.4 + world.rng.random() * 0.6)
        touching = None
        for e in world.entities:
            if dist_to_segment(e.x, e.y, s["segment"]) <= 4.0:
                if e.kind == "intruder" and e.state == "climbing":
                    g = max(g, 1.2 + world.rng.random() * 0.8)
                    touching = e
                elif e.kind == "animal" and e.state == "touching":
                    g = max(g, 0.35 + world.rng.random() * 0.25)
                    touching = e
        return {"value": round(g, 3), "unit": "g", "touching": touching, "text": f"{g:.2f} g"}

    def _contact(self, s, world):
        gate = world.gate_open.get(s.get("gate"), None)
        state = 1 if gate else 0
        return {"value": state, "unit": "open", "authorized": bool(gate and gate.get("authorized")),
                "text": "OPEN" if state else "closed"}

    def _environmental(self, s, world):
        t = s["type"]
        if t == "temperature":
            v = world.ambient_temp + sum(a.temp_at(s["x"], s["y"]) for a in world.anomalies)
            v += world.rng.gauss(0, 0.08)
            rh = max(5.0, min(100.0, world.humidity - (v - world.ambient_temp) * 1.2))
            return {"value": round(v, 2), "unit": "°C", "rh": round(rh, 1), "text": f"{v:.1f} °C · {rh:.0f} %RH"}
        if t == "smoke":
            v = 0.05 + abs(world.rng.gauss(0, 0.02)) + sum(a.smoke_at(s["x"], s["y"]) for a in world.anomalies)
            return {"value": round(v, 2), "unit": "%obs/m", "text": f"{v:.2f} %obs/m"}
        wet = any(a.kind == "leak" and math.hypot(a.x - s["x"], a.y - s["y"]) <= s["range"] for a in world.anomalies)
        return {"value": 1 if wet else 0, "unit": "wet", "text": "WET" if wet else "dry"}
