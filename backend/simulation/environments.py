"""Conceptual site layouts for the three simulated environments.

All layouts are generic and illustrative (1 map unit = 1 m on a 1000 × 620 m
canvas). They are NOT modelled on any real facility and deliberately omit
anything that would describe a real site's security configuration.
"""
from __future__ import annotations

import copy
from typing import Any

W, H = 1000, 620

# Sensor type → default geometry (range m, field of view deg) and device catalog id.
SENSOR_DEFAULTS = {
    "optical":     {"range": 420, "fov": 46, "device": "hik-ds2cd2043g2-i", "bus": "PoE Ethernet (RTSP/ONVIF)"},
    "lowlight":    {"range": 160, "fov": 90, "device": "hik-ds2cd2047g2-l", "bus": "PoE Ethernet (RTSP/ONVIF)"},
    "ptz":         {"range": 300, "fov": 60, "device": "hik-ds2de4425iw-de", "bus": "PoE+ Ethernet (RTSP/ONVIF)"},
    "thermal":     {"range": 420, "fov": 40, "device": "thermal-bullet-generic", "bus": "PoE Ethernet (RTSP/ONVIF)"},
    "pir":         {"range": 12, "fov": 110, "device": "hc-sr501", "bus": "GPIO dry contact"},
    "microwave":   {"range": 40, "fov": 120, "device": "rcwl-0516", "bus": "GPIO digital out"},
    "fence":       {"range": 0, "fov": 0, "device": "adxl355-fence", "bus": "RS-485 Modbus RTU"},
    "radar":       {"range": 260, "fov": 110, "device": "ti-iwr6843", "bus": "Ethernet / UART"},
    "contact":     {"range": 0, "fov": 0, "device": "mc38-reed", "bus": "GPIO dry contact (EOL resistor)"},
    "temperature": {"range": 70, "fov": 360, "device": "sht31", "bus": "I²C → ESP32, LoRaWAN uplink"},
    "smoke":       {"range": 70, "fov": 360, "device": "photo-smoke-en54", "bus": "Conventional loop → ESP32 input"},
    "leak":        {"range": 30, "fov": 360, "device": "leak-cable", "bus": "Analog/dry contact → ESP32"},
}
PREFIX = {"optical": "CAM", "lowlight": "LLC", "ptz": "PTZ", "thermal": "TH", "pir": "PIR",
          "microwave": "MW", "fence": "FV", "radar": "RAD", "contact": "MC",
          "temperature": "TMP", "smoke": "SMK", "leak": "WL"}
TYPE_LABEL = {"optical": "Optical (IP CCTV)", "lowlight": "Low-light wide-angle camera", "ptz": "PTZ camera",
              "thermal": "Thermal", "pir": "PIR motion", "microwave": "Microwave motion",
              "fence": "Fence vibration", "radar": "Perimeter radar", "contact": "Magnetic contact",
              "temperature": "Temperature / humidity", "smoke": "Smoke detection", "leak": "Water / liquid leak"}

# Edge node models → catalog id, edge processing latency range (ms).
NODE_MODELS = {
    "jetson": {"device": "nvidia-jetson-orin-nano", "label": "Jetson Orin Nano", "edge_ms": (22, 45)},
    "rpi5": {"device": "rpi-5", "label": "Raspberry Pi 5", "edge_ms": (6, 15)},
    "esp32": {"device": "esp32-wroom-32e", "label": "ESP32 + SX1276", "edge_ms": (2, 6)},
}
# Uplink type → one-way latency range (ms) and packet loss probability.
LINKS = {
    "fiber": {"label": "Fibre Ethernet", "latency": (1, 3), "loss": 0.0},
    "ethernet": {"label": "Ethernet (Cat6)", "latency": (1, 4), "loss": 0.0},
    "wifi": {"label": "Wi-Fi PtP bridge", "latency": (4, 25), "loss": 0.005},
    "lte": {"label": "4G LTE", "latency": (40, 140), "loss": 0.01},
    "lorawan": {"label": "LoRaWAN IN865", "latency": (400, 1600), "loss": 0.02},
}


def _perimeter(x0, y0, x1, y1, out=50, inner=90):
    """Four perimeter sector zones (each spans an outside strip and an inside strip)."""
    return [
        {"id": "A", "name": "Zone A — North perimeter", "kind": "perimeter", "rect": [x0 - out, y0 - out, x1 + out, y0 + inner]},
        {"id": "B", "name": "Zone B — East perimeter", "kind": "perimeter", "rect": [x1 - inner, y0 + inner, x1 + out, y1 - inner]},
        {"id": "C", "name": "Zone C — South perimeter & gate", "kind": "perimeter", "rect": [x0 - out, y1 - inner, x1 + out, y1 + out]},
        {"id": "D", "name": "Zone D — West perimeter", "kind": "perimeter", "rect": [x0 - out, y0 + inner, x0 + inner, y1 - inner]},
    ]


def _perimeter_sensors(x0, y0, x1, y1, gate_x):
    """Per side: one optical + one thermal looking along the fence from opposite ends,
    two fence-vibration segments. Two radars at opposite corners facing outward."""
    s = []
    o = 14  # inward offset of mast from fence line
    sides = [
        ("A", "N", (x0 + o, y0 + o), (x1 - o, y0 + o), 0, 180, [(x0, y0, (x0 + x1) / 2, y0), ((x0 + x1) / 2, y0, x1, y0)]),
        ("B", "E", (x1 - o, y0 + o), (x1 - o, y1 - o), 90, 270, [(x1, y0, x1, (y0 + y1) / 2), (x1, (y0 + y1) / 2, x1, y1)]),
        ("C", "S", (x1 - o, y1 - o), (x0 + o, y1 - o), 180, 0, [(x0, y1, gate_x - 20, y1), (gate_x + 20, y1, x1, y1)]),
        ("D", "W", (x0 + o, y1 - o), (x0 + o, y0 + o), 270, 90, [(x0, y0, x0, (y0 + y1) / 2), (x0, (y0 + y1) / 2, x0, y1)]),
    ]
    for zone, node, p_cam, p_th, d_cam, d_th, segs in sides:
        s.append({"type": "optical", "x": p_cam[0], "y": p_cam[1], "dir": d_cam, "zone": zone, "node": f"EN-{node}"})
        s.append({"type": "thermal", "x": p_th[0], "y": p_th[1], "dir": d_th, "zone": zone, "node": f"EN-{node}"})
        for seg in segs:
            s.append({"type": "fence", "x": (seg[0] + seg[2]) / 2, "y": (seg[1] + seg[3]) / 2,
                      "segment": list(seg), "zone": zone, "node": f"EN-{node}"})
    s.append({"type": "radar", "x": x0 + 6, "y": y0 + 6, "dir": 225, "zone": "A", "node": "EN-N"})
    s.append({"type": "radar", "x": x1 - 6, "y": y1 - 6, "dir": 45, "zone": "C", "node": "EN-S"})
    # Main gate: magnetic contact, PIR, microwave, PTZ, low-light camera.
    s.append({"type": "contact", "x": gate_x, "y": y1, "zone": "C", "node": "EN-G", "gate": "GATE-1"})
    s.append({"type": "pir", "x": gate_x + 22, "y": y1 - 10, "dir": 200, "zone": "C", "node": "EN-G"})
    s.append({"type": "microwave", "x": gate_x - 22, "y": y1 - 6, "dir": 90, "zone": "C", "node": "EN-G"})
    s.append({"type": "ptz", "x": gate_x + 40, "y": y1 - 40, "dir": 135, "zone": "C", "node": "EN-G"})
    s.append({"type": "lowlight", "x": gate_x - 40, "y": y1 - 30, "dir": 60, "zone": "C", "node": "EN-G"})
    return s


def _nodes(x0, y0, x1, y1, gate_x, cc, env_pos, links):
    return [
        {"id": "EN-N", "model": "jetson", "x": (x0 + x1) / 2, "y": y0 + 30, "zone": "A", "link": links[0]},
        {"id": "EN-E", "model": "jetson", "x": x1 - 30, "y": (y0 + y1) / 2, "zone": "B", "link": links[1]},
        {"id": "EN-S", "model": "jetson", "x": (x0 + x1) / 2 + 120, "y": y1 - 30, "zone": "C", "link": links[2]},
        {"id": "EN-W", "model": "jetson", "x": x0 + 30, "y": (y0 + y1) / 2, "zone": "D", "link": links[3]},
        {"id": "EN-G", "model": "rpi5", "x": gate_x + 60, "y": y1 - 18, "zone": "C", "link": "ethernet"},
        {"id": "EN-ENV", "model": "esp32", "x": env_pos[0], "y": env_pos[1], "zone": "E", "link": "lorawan"},
    ]


def _build(env_id, name, subtitle, rect, gate_x, interior_zones, structures, extra_sensors,
           cc, env_node_pos, links, assets, patrol_inset=45, vehicle_stops=None):
    x0, y0, x1, y1 = rect
    sensors = _perimeter_sensors(x0, y0, x1, y1, gate_x) + extra_sensors
    counters: dict[str, int] = {}
    for s in sensors:
        counters[s["type"]] = counters.get(s["type"], 0) + 1
        s["id"] = f"{PREFIX[s['type']]}-{counters[s['type']]:02d}"
        d = SENSOR_DEFAULTS[s["type"]]
        s.setdefault("range", d["range"])
        s.setdefault("fov", d["fov"])
        s.setdefault("dir", 0)
        s["device"] = d["device"]
        s["bus"] = d["bus"]
        s["type_label"] = TYPE_LABEL[s["type"]]
    i = patrol_inset
    patrol = [[x0 + i, y0 + i], [x1 - i, y0 + i], [x1 - i, y1 - i], [x0 + i, y1 - i]]
    return {
        "id": env_id, "name": name, "subtitle": subtitle, "width": W, "height": H,
        "perimeter": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
        "zones": _perimeter(x0, y0, x1, y1) + interior_zones,
        "structures": structures,
        "checkpoints": [{"id": "GATE-1", "name": "Main access gate", "x": gate_x, "y": y1,
                         "sensor": next(s["id"] for s in sensors if s["type"] == "contact")}],
        "command_centre": {"id": "C2", "name": "Command & control centre", "x": cc[0], "y": cc[1]},
        "sensors": sensors,
        "nodes": _nodes(x0, y0, x1, y1, gate_x, cc, env_node_pos, links),
        "assets": assets,
        "routes": {
            "patrol": patrol,
            "vehicle_in": [[gate_x, H + 10], [gate_x, y1 + 25], [gate_x, y1 - 25]] + (vehicle_stops or []),
        },
        "power": {"feeders": ["Mains incomer (simulated 415 V AC 3φ)"],
                  "ups": [{"id": "UPS-1", "serves": ["EN-N", "EN-E", "EN-S", "EN-W", "EN-G", "C2"]}],
                  "solar": [{"id": "PV-1", "serves": ["EN-ENV"]}]},
        "note": "Generic conceptual layout for simulation — not representative of any real facility.",
    }


def _airport():
    rect = (80, 80, 920, 540)
    return _build(
        "airport", "Airport perimeter", "Generic regional airfield — airside perimeter", rect, gate_x=640,
        interior_zones=[
            {"id": "E", "name": "Zone E — Runway & taxiway", "kind": "interior", "rect": [170, 170, 830, 360]},
            {"id": "F", "name": "Zone F — Apron & terminal (airside)", "kind": "interior", "rect": [170, 360, 830, 450]},
        ],
        structures=[
            {"shape": "rect", "x": 160, "y": 245, "w": 680, "h": 40, "label": "RWY 09/27", "cls": "runway"},
            {"shape": "rect", "x": 220, "y": 318, "w": 560, "h": 14, "label": "Taxiway", "cls": "taxiway"},
            {"shape": "rect", "x": 300, "y": 380, "w": 260, "h": 60, "label": "Apron", "cls": "apron"},
            {"shape": "rect", "x": 600, "y": 395, "w": 150, "h": 45, "label": "Terminal (airside)", "cls": "building"},
            {"shape": "rect", "x": 760, "y": 180, "w": 50, "h": 40, "label": "Fuel farm", "cls": "building"},
            {"shape": "rect", "x": 180, "y": 180, "w": 60, "h": 36, "label": "Navaid hut", "cls": "building"},
        ],
        extra_sensors=[
            {"type": "pir", "x": 620, "y": 398, "dir": 270, "zone": "F", "node": "EN-S"},
            {"type": "microwave", "x": 760, "y": 230, "dir": 90, "zone": "E", "node": "EN-E"},
            {"type": "temperature", "x": 785, "y": 200, "zone": "E", "node": "EN-ENV"},
            {"type": "smoke", "x": 770, "y": 210, "zone": "E", "node": "EN-ENV"},
            {"type": "leak", "x": 800, "y": 222, "zone": "E", "node": "EN-ENV"},
            {"type": "temperature", "x": 210, "y": 198, "zone": "E", "node": "EN-ENV"},
            {"type": "smoke", "x": 675, "y": 415, "zone": "F", "node": "EN-ENV"},
            {"type": "temperature", "x": 690, "y": 405, "zone": "F", "node": "EN-ENV"},
        ],
        cc=(560, 600), env_node_pos=(480, 300), links=["fiber", "wifi", "ethernet", "lte"],
        assets=[{"id": "fuel_farm", "x": 785, "y": 200}, {"id": "terminal", "x": 675, "y": 418},
                {"id": "navaid", "x": 210, "y": 198}],
        vehicle_stops=[[640, 420], [450, 410]],
    )


def _substation():
    rect = (170, 110, 830, 510)
    return _build(
        "substation", "Electrical substation", "Generic 220/66 kV outdoor switchyard", rect, gate_x=330,
        interior_zones=[
            {"id": "E", "name": "Zone E — Transformer bay", "kind": "interior", "rect": [260, 200, 740, 320]},
            {"id": "F", "name": "Zone F — Control building & yard", "kind": "interior", "rect": [260, 320, 740, 420]},
        ],
        structures=[
            {"shape": "rect", "x": 290, "y": 215, "w": 70, "h": 60, "label": "TX-1", "cls": "transformer"},
            {"shape": "rect", "x": 400, "y": 215, "w": 70, "h": 60, "label": "TX-2", "cls": "transformer"},
            {"shape": "rect", "x": 510, "y": 215, "w": 70, "h": 60, "label": "TX-3", "cls": "transformer"},
            {"shape": "rect", "x": 620, "y": 225, "w": 90, "h": 40, "label": "66 kV bus", "cls": "busbar"},
            {"shape": "rect", "x": 300, "y": 340, "w": 150, "h": 60, "label": "Control building", "cls": "building"},
            {"shape": "rect", "x": 520, "y": 345, "w": 160, "h": 50, "label": "Cable trench / battery room", "cls": "building"},
        ],
        extra_sensors=[
            {"type": "pir", "x": 375, "y": 338, "dir": 90, "zone": "F", "node": "EN-S"},
            {"type": "microwave", "x": 470, "y": 300, "dir": 270, "zone": "E", "node": "EN-E"},
            {"type": "temperature", "x": 325, "y": 245, "zone": "E", "node": "EN-ENV"},
            {"type": "temperature", "x": 435, "y": 245, "zone": "E", "node": "EN-ENV"},
            {"type": "temperature", "x": 545, "y": 245, "zone": "E", "node": "EN-ENV"},
            {"type": "smoke", "x": 435, "y": 290, "zone": "E", "node": "EN-ENV"},
            {"type": "smoke", "x": 375, "y": 370, "zone": "F", "node": "EN-ENV"},
            {"type": "leak", "x": 600, "y": 370, "zone": "F", "node": "EN-ENV"},
        ],
        cc=(375, 370), env_node_pos=(600, 300), links=["fiber", "ethernet", "ethernet", "wifi"],
        assets=[{"id": "tx1", "x": 325, "y": 245}, {"id": "tx2", "x": 435, "y": 245},
                {"id": "tx3", "x": 545, "y": 245}, {"id": "battery_room", "x": 600, "y": 370}],
        vehicle_stops=[[330, 420], [480, 420]],
    )


def _fuel_depot():
    rect = (100, 90, 900, 530)
    tanks = [(250, 220), (360, 220), (470, 220), (250, 330), (360, 330), (470, 330)]
    return _build(
        "fuel_depot", "Fuel storage facility", "Generic bulk storage depot with bunded tank farm", rect, gate_x=760,
        interior_zones=[
            {"id": "E", "name": "Zone E — Bunded tank farm", "kind": "interior", "rect": [190, 180, 560, 400]},
            {"id": "F", "name": "Zone F — Loading gantry & pump house", "kind": "interior", "rect": [560, 180, 810, 440]},
        ],
        structures=[{"shape": "rect", "x": 200, "y": 170, "w": 330, "h": 215, "label": "Bund wall", "cls": "bund"}]
        + [{"shape": "circle", "x": x, "y": y, "r": 38, "label": f"T-{i + 1}", "cls": "tank"} for i, (x, y) in enumerate(tanks)]
        + [{"shape": "rect", "x": 620, "y": 230, "w": 140, "h": 60, "label": "Loading gantry", "cls": "building"},
           {"shape": "rect", "x": 620, "y": 330, "w": 80, "h": 50, "label": "Pump house", "cls": "building"},
           {"shape": "rect", "x": 160, "y": 440, "w": 120, "h": 45, "label": "Fire water tank", "cls": "building"}],
        extra_sensors=[
            {"type": "pir", "x": 660, "y": 328, "dir": 90, "zone": "F", "node": "EN-E"},
            {"type": "microwave", "x": 690, "y": 300, "dir": 180, "zone": "F", "node": "EN-E"},
            {"type": "smoke", "x": 305, "y": 275, "zone": "E", "node": "EN-ENV"},
            {"type": "smoke", "x": 415, "y": 275, "zone": "E", "node": "EN-ENV"},
            {"type": "temperature", "x": 305, "y": 285, "zone": "E", "node": "EN-ENV"},
            {"type": "temperature", "x": 415, "y": 285, "zone": "E", "node": "EN-ENV"},
            {"type": "leak", "x": 360, "y": 380, "zone": "E", "node": "EN-ENV"},
            {"type": "leak", "x": 660, "y": 380, "zone": "F", "node": "EN-ENV"},
            {"type": "smoke", "x": 690, "y": 260, "zone": "F", "node": "EN-ENV"},
            {"type": "temperature", "x": 700, "y": 270, "zone": "F", "node": "EN-ENV"},
        ],
        cc=(820, 470), env_node_pos=(560, 420), links=["ethernet", "fiber", "ethernet", "lte"],
        assets=[{"id": "tank_farm_w", "x": 305, "y": 280}, {"id": "tank_farm_e", "x": 415, "y": 280},
                {"id": "bund_south", "x": 360, "y": 385}, {"id": "gantry", "x": 690, "y": 265},
                {"id": "pump_house", "x": 660, "y": 380}],
        vehicle_stops=[[760, 400], [690, 300]],
    )


ENVIRONMENTS: dict[str, dict[str, Any]] = {e["id"]: e for e in (_airport(), _substation(), _fuel_depot())}


def get_environment(env_id: str) -> dict[str, Any]:
    if env_id not in ENVIRONMENTS:
        raise KeyError(env_id)
    return copy.deepcopy(ENVIRONMENTS[env_id])


def list_environments() -> list[dict[str, str]]:
    return [{"id": e["id"], "name": e["name"], "subtitle": e["subtitle"],
             "sensors": len(e["sensors"]), "zones": len(e["zones"])} for e in ENVIRONMENTS.values()]
