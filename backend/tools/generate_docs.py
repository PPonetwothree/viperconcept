"""Generate catalogue-driven documentation so it cannot drift from the code.

    python backend/tools/generate_docs.py

Writes documentation/hardware_specifications.md, bom.md and testing_report.md
(the latter by actually running the scenario harness and pytest).
"""
from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from devices.catalog import DEVICES, SELECTION_RATIONALE  # noqa: E402
from simulation.environments import ENVIRONMENTS, LINKS, NODE_MODELS  # noqa: E402
from simulation.scenarios import run_scenarios  # noqa: E402

DOCS = config.DOCS_DIR
BY_ID = {d["id"]: d for d in DEVICES}


def inr(n: float) -> str:
    # Indian digit grouping (e.g. ₹1,25,000)
    raw = str(int(round(n)))
    if len(raw) <= 3:
        return f"₹{raw}"
    last3, rest = raw[-3:], raw[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return "₹" + ",".join(parts + [last3])


def hardware_md() -> str:
    L = ["# VIPER — Hardware Specifications", "",
         "> Provenance key: **DS** = manufacturer-published figure compiled for this demonstrator (source documents were "
         "**not re-fetched during the build** — verify against the current datasheet revision before design-in). "
         "**EST** = illustrative engineering estimate. All INR prices are EST (ex-GST indicative ranges).", "",
         "No hardware is connected to this demonstrator. Simulated sensors reference these profiles.", "",
         "## 1. Hardware architecture", "",
         "Each site is divided into four perimeter sectors (A–D, each spanning an outside approach strip and an inside strip) "
         "and interior zones (E–F). Each perimeter side has one GPU edge node (Jetson Orin Nano) serving one optical camera, "
         "one thermal camera and two fence-vibration segments; two corner radars cover the approaches; the main gate has a "
         "Raspberry Pi 5 node with contact, PIR, microwave, PTZ and low-light cameras; environmental sensors report through a "
         "solar ESP32 LoRaWAN node. All edge nodes except the solar node are UPS-backed.", "",
         "| Edge node | Model | Uplink | Simulated edge processing |", "|---|---|---|---|"]
    for k, m in NODE_MODELS.items():
        L.append(f"| {k} | {m['label']} | per layout | {m['edge_ms'][0]}–{m['edge_ms'][1]} ms |")
    L += ["", "## 2. Communication architecture", "",
          "Edge nodes publish observations and 2 s heartbeats (MQTT QoS 1, mutual TLS in deployment). The demonstrator "
          "models each uplink with a latency range and loss probability; lost publishes are retransmitted. A heartbeat "
          "missing for 7 s raises a communication failure. During outages nodes buffer up to 500 observations "
          "(store-and-forward) and flush them on restoration with original timestamps.", "",
          "| Link | One-way latency (sim) | Loss (sim) |", "|---|---|---|"]
    for k, l in LINKS.items():
        L.append(f"| {l['label']} | {l['latency'][0]}–{l['latency'][1]} ms | {l['loss'] * 100:.1f} % |")
    L += ["", "Figures are simulation parameters chosen to be representative; they are not measurements.", "",
          "## 3. Power management", "",
          "- Mains → distribution board (MCB/RCD/SPD) → UPS-1 (line-interactive) → PDU → PoE switches, cabinet DC supplies, C2.",
          "- Cabinet DC bus with point-of-load DC-DC converters; rail telemetry via INA219.",
          "- Remote environmental node: PV panel → MPPT controller → 12 V battery → buck/LDO → ESP32 (independent of mains).",
          "- Power events: the UPS reports mains loss via SNMP → equipment-malfunction (power) incident (rule P1); restoration "
          "is appended to the same incident. Simulated UPS drain: 0.35 %/s (sim); nodes shed below 8 %.", "",
          "### Indicative power budget per perimeter side (EST)", "",
          "| Load | Qty | Typical W (EST) | Subtotal W |", "|---|---|---|---|",
          "| Optical camera (PoE) | 1 | 7 | 7 |", "| Thermal camera (PoE) | 1 | 8 | 8 |",
          "| Jetson Orin Nano (15 W mode) | 1 | 15 | 15 |", "| Fence nodes (2) + RS-485 | 2 | 0.5 | 1 |",
          "| PoE switch overhead | 1 | 10 | 10 |", "| **Total** | | | **≈ 41 W** |", "",
          "At ≈ 41 W, a 12 V 2 × 7 Ah cabinet battery (≈ 168 Wh, ≈ 50 % usable for VRLA longevity) gives ≈ 2 h ride-through "
          "before inverter losses — size per site risk assessment.", "",
          "## 4. Device profiles", ""]
    cats = []
    for d in DEVICES:
        if d["category"] not in cats:
            cats.append(d["category"])
    for c in cats:
        L += [f"### {c}", ""]
        for d in [x for x in DEVICES if x["category"] == c]:
            L += [f"#### {d['name']} — {d['manufacturer']} {d['model']}", "",
                  f"- **Category:** {d['category']} / {d['subcategory']}",
                  f"- **Working principle:** {d['working_principle']}",
                  f"- **Internal components:** {'; '.join(d['internal_components'])}",
                  f"- **Operating voltage:** {d['operating_voltage']}",
                  f"- **Power consumption:** {d['power_consumption']}",
                  f"- **Communication:** {d['communication']}",
                  f"- **Operating temperature:** {d['operating_temperature']}",
                  f"- **Environmental limitations:** {d['environmental_limitations']}",
                  f"- **Approx. price:** {inr(d['price_inr']['low'])} – {inr(d['price_inr']['high'])} (EST)" if d['price_inr']['high'] else "- **Approx. price:** open source / n/a",
                  f"- **Advantages:** {'; '.join(d['advantages'])}",
                  f"- **Disadvantages:** {'; '.join(d['disadvantages'])}",
                  f"- **Integration:** {d['integration']}",
                  f"- **Alternatives:** {'; '.join(d['alternatives'])}", "",
                  "| Specification | Value | Source |", "|---|---|---|"]
            L += [f"| {s['param']} | {s['value']} | {s['src']} |" for s in d["specifications"]]
            if d["sources"]:
                L += ["", "Sources: " + "; ".join(f"[{s['label']}]({s['url']})" for s in d["sources"])]
            L.append("")
    L += ["## 5. Selection rationale", ""]
    for t in SELECTION_RATIONALE:
        L += [f"### {t['title']}", "", "| " + " | ".join(t["columns"]) + " |", "|" + "---|" * len(t["columns"])]
        L += ["| " + " | ".join(r) + " |" for r in t["rows"]]
        L += ["", f"**Conclusion:** {t['conclusion']}", ""]
    return "\n".join(L)


INFRA = [  # site infrastructure items not represented as simulated sensors (EST quantities)
    ("poe-switch", 5, "Per-side and gate cabinets"),
    ("adm2587e", 4, "Isolated RS-485 per side bus"),
    ("rfm95w-sx1276", 1, "Env node radio"),
    ("meanwell-lrs-100-12", 6, "Cabinet DC supplies"),
    ("lm2596-buck", 2, "5 V rails"),
    ("apc-smt1500ic", 1, "Command-centre UPS"),
    ("yuasa-np7-12", 12, "Cabinet batteries (2 per cabinet)"),
    ("victron-mppt-75-15", 1, "Solar env node"),
    ("ina219", 6, "Rail monitoring per cabinet"),
    ("mqtt-mosquitto", 1, "Broker (software)"),
]


def bom_md(env_id: str = "airport") -> str:
    env = ENVIRONMENTS[env_id]
    counts = Counter(s["device"] for s in env["sensors"])
    counts.update(NODE_MODELS[n["model"]]["device"] for n in env["nodes"])
    purpose = {s["device"]: s["type_label"] for s in env["sensors"]}
    purpose.update({NODE_MODELS[k]["device"]: f"Edge node ({v['label']})" for k, v in NODE_MODELS.items()})
    rows, total_lo, total_hi, total_mid = [], 0, 0, 0
    for dev_id, qty in list(counts.items()) + [(d, q) for d, q, _ in INFRA]:
        d = BY_ID[dev_id]
        lo, hi = d["price_inr"]["low"], d["price_inr"]["high"]
        mid = (lo + hi) / 2
        why = purpose.get(dev_id) or next((p for x, _, p in INFRA if x == dev_id), d["subcategory"])
        src = d["sources"][0]["url"] if d["sources"] else "— (generic; obtain quotation)"
        rows.append(f"| {d['name']} | {qty} | {inr(mid)} | {inr(mid * qty)} | {d['manufacturer']} | {d['model']} | {why} | {src} |")
        total_lo += lo * qty; total_hi += hi * qty; total_mid += mid * qty
    L = ["# VIPER — Preliminary Bill of Materials (pilot, one site)", "",
         f"Layout basis: **{env['name']}** simulated layout ({len(env['sensors'])} sensors, {len(env['nodes'])} edge nodes).", "",
         "> **All prices are estimates (EST)** — indicative Indian market ranges, ex-GST, before integration, civil works, "
         "cabling, enclosures, licences and installation labour. Unit price shown = midpoint of the estimated range. "
         "Obtain distributor/integrator quotations before budgeting. Several entries are development-grade parts suitable "
         "for a lab pilot only (see Devices → Disadvantages); production would substitute ruggedised equivalents.", "",
         "| Component | Qty | Unit price (EST) | Total (EST) | Manufacturer | Model | Purpose | Source link |",
         "|---|---|---|---|---|---|---|---|"] + rows + [
         "", f"**Hardware subtotal (EST):** {inr(total_mid)} (range {inr(total_lo)} – {inr(total_hi)})", "",
         "### Not included (must be estimated separately)", "",
         "- Poles, enclosures (IP66), lightning/surge protection, earthing",
         "- Fibre/copper cabling, trenching, conduits",
         "- Command-centre workstation, displays, server (≈ any modern x86 PC suffices for the demonstrator software)",
         "- LoRaWAN gateway, VPN/firewall appliances, cellular data plans",
         "- Installation, commissioning, calibration walk-tests, training, AMC", ""]
    return "\n".join(L)


def testing_md() -> str:
    rep = run_scenarios()
    py = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT, capture_output=True, text=True)
    tail = "\n".join(l for l in py.stdout.strip().splitlines()[-3:] if l.strip())
    L = ["# VIPER — Testing Report", "",
         "> Functional tests of the **software** (simulation, fusion rules, lifecycle, persistence, API). They do not and "
         "cannot validate field detection performance of any hardware.", "",
         "## 1. Methodology", "",
         "- **Unit tests** (`backend/tests/test_event_engine.py`): classification rules, noisy-OR evidence score, validation, "
         "clock-offset correction, correlation window, early close, merging/escalation, heartbeat watchdog, normal-activity "
         "rate limiting, every lifecycle transition (valid and invalid), SQLite round-trip, ID sequencing, timestamp format.",
         "- **Scenario tests** (`backend/simulation/scenarios.py`, also exposed in the UI Testing view and run by pytest): "
         "isolated headless runtime, in-memory database, `VirtualClock` (fast-forwarded), fixed seeds.",
         "- **Robustness tests**: intrusion detection and wildlife non-escalation repeated over 5 random seeds each.",
         "- **API integration test**: FastAPI TestClient through start → inject → filter → full operator workflow → report → "
         "CSV/JSON export → analytics, including 409/422/404 error paths and path-traversal protection on /api/docs.",
         "- **Manual browser verification**: every view rendered at 1920×1080 with no console errors; the complete "
         "acknowledge → verify → authorise response → resolve → close workflow driven through the UI buttons.", "",
         f"## 2. Scenario results (generated {rep['run_utc']}, {rep['clock']})", "",
         f"**{rep['passed']}/{rep['total']} passed** in {rep['duration_ms']} ms wall time.", "",
         "| # | Scenario | Expected behaviour | Actual simulated behaviour | Event timestamp (UTC) | Processing latency | System status | Result |",
         "|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rep["results"], 1):
        st = r.get("system_status") or {}
        lat = f"{r['processing_latency_ms']} ms" if r.get("processing_latency_ms") is not None else "—"
        L.append(f"| {i} | {r['title']} | {r['expected']} | {str(r['actual']).replace('|', '/')} | {r.get('event_timestamp_utc') or '—'} | {lat} | "
                 f"{st.get('online_sensors', '?')}/{st.get('total_sensors', '?')} sensors, {st.get('nodes_online', '?')}/{st.get('nodes_total', '?')} nodes, {st.get('power', '?')} | **{r['result']}** |")
    L += ["", "Processing latency = first contributing observation (clock-corrected sensor time) → alert. It is dominated by "
          "the 6 s correlation window (or early close at ≥ 3 modalities) plus simulated edge and link latency.", "",
          "## 3. Automated test suite", "", "```", f"$ python -m pytest -q", tail, "```", "",
          "## 4. Findings during development (fixed)", "",
          "1. Camera detections were attributed to the camera mast's zone, so a patrol seen across a zone boundary looked "
          "unauthorised. Fix: observations from calibrated cameras/radar are attributed to the zone of the object's ground position.",
          "2. A single mislabelled frame (animal → person) could escalate wildlife to a high-severity perimeter anomaly. "
          "Fix: confidence-weighted label vote (rule R2).",
          "3. Wind was evaluated when the correlation window closed, not when the fence alarmed. Fix: edge reports wind with "
          "the observation (rule R3).",
          "4. At 5× speed, authorised staff could leave a zone before the window closed, producing spurious unverified-movement "
          "alerts. Fix: access-control state is snapshotted at ingest.", "",
          "## 5. Known limitations", "",
          "- Rule weights and thresholds are illustrative; no field data exist to calibrate them.",
          "- No line-of-sight occlusion, no weather effect on imaging beyond the light factor, no sensor drift model.",
          "- Authorisation masking: a non-breaching intruder in a zone where authorised staff are present is logged as normal "
          "activity (rule R1). A deployment needs per-person localisation (badges + tracking) to close this gap.",
          "- Single operator, no authentication/authorisation on the API in this build.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    (DOCS / "hardware_specifications.md").write_text(hardware_md(), encoding="utf-8")
    (DOCS / "bom.md").write_text(bom_md(), encoding="utf-8")
    (DOCS / "testing_report.md").write_text(testing_md(), encoding="utf-8")
    print("wrote hardware_specifications.md, bom.md, testing_report.md")
