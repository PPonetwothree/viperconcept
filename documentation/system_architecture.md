# VIPER — System Architecture & Requirements

**VIPER — Vigilant Infrastructure Protection & Emergency Response**
Research & development demonstrator. **Every sensor reading, entity and incident in this build is simulated.** No physical hardware is connected.

---

## 1. Project overview

Defence-linked civil assets (airports, fuel depots, substations, water treatment plants, logistics hubs) are protected today mostly by static CCTV, manual monitoring and patrols. Weak points: detection delay, operator fatigue, fragmented monitoring (each subsystem has its own console), and slow escalation.

VIPER is a modular platform that fuses heterogeneous sensors at the edge, correlates their observations centrally with transparent rules, and puts every resulting incident through a **human-verified**, timestamped lifecycle. This demonstrator proves the software architecture end-to-end with simulated device adapters, structured so real adapters (MQTT, RTSP/ONVIF, Modbus/RS-485) can replace them later.

### 1.1 Scope of this build

| Real (implemented and working) | Simulated (stand-in for hardware) |
|---|---|
| Event engine, fusion rules, lifecycle state machine | All sensors, cameras, edge nodes |
| SQLite persistence, REST API, WebSocket push | Network links (latency, loss, outages) |
| Operator workflow, exports, reports | People, vehicles, intruders, animals, weather |
| Metrics computation from recorded events | Mains power, UPS battery |
| Scenario test harness, automated tests | Clock skew of edge nodes |

### 1.2 Assumptions

1. Single site per running instance; one operator console (multi-operator is a roadmap item).
2. Map units are metres; layouts are **generic and conceptual**, not modelled on any real facility.
3. Edge nodes run detection/tracking locally and transmit *observations*, not raw video, to the centre.
4. Access control (badge readers, work permits) is available as context: the centre knows whether authorised personnel are present in a zone.
5. Edge node clocks drift; offsets are estimated from NTP-style heartbeats and corrected at ingest.
6. A Windows laptop with Python 3.10+ is the only runtime requirement. No cloud services.

## 2. System requirements

| ID | Requirement |
|---|---|
| SR-1 | Runs locally on Windows 10/11, Python ≥ 3.10, any evergreen browser. |
| SR-2 | One command starts backend + UI on one URL (`http://127.0.0.1:8000`). |
| SR-3 | No mandatory internet access at runtime (no CDN, no cloud APIs). |
| SR-4 | Data persists in a local SQLite file (`backend/data/viper.db`). |

## 3. Functional requirements

| ID | Requirement | Module |
|---|---|---|
| FR-01 | Select between ≥ 3 infrastructure environments with distinct layouts. | D |
| FR-02 | Show zones, perimeter, sensors, camera coverage, checkpoints, command centre. | D |
| FR-03 | Animate personnel, authorised vehicles, unauthorised movement, animals, environmental anomalies, all driven by simulation state. | D/H |
| FR-04 | Each sensor exposes live simulated readings and a device profile. | B/D |
| FR-05 | Interactive architecture diagram with clickable layers and live data-flow animation. | A |
| FR-06 | Seven interactive SVG engineering schematics with tooltips. | C |
| FR-07 | Rule-based fusion engine: validation, timestamp sync, correlation, classification, confidence, severity, alert. | E |
| FR-08 | Every event has the full Module F schema and a unique ID `VIPER-YYYY-NNNN`. | F |
| FR-09 | Live timeline with filtering (severity/sensor/zone), ID search, acknowledge, false positive, close. | F |
| FR-10 | Incident detail page showing the complete lifecycle with timestamps. | F |
| FR-11 | Export history to CSV and JSON. | F |
| FR-12 | Simulation controls: start/pause/resume/reset, speed 1×/2×/5×, inject test event, equipment failure, comms failure, environmental anomaly, power interruption. | H |
| FR-13 | Human-in-the-loop response: every response requires an operator name and explicit authorisation. No autonomous physical action. | I |
| FR-14 | Analytics computed from recorded events, with metric definitions. | J |
| FR-15 | Scenario test harness with expected vs actual, latency and pass/fail report. | L |
| FR-16 | Engineering documentation viewable inside the app. | K |

## 4. Non-functional requirements

| ID | Requirement | Target in demonstrator |
|---|---|---|
| NFR-1 | Event push latency (engine → UI) | < 250 ms on localhost |
| NFR-2 | Simulation tick rate | 5 Hz (configurable) |
| NFR-3 | Timestamp precision | millisecond, UTC ISO-8601 storage |
| NFR-4 | State consistency | All lifecycle transitions validated server-side; invalid transitions return HTTP 409 |
| NFR-5 | Extensibility | Sensor adapters behind an interface (`SensorAdapter`) |
| NFR-6 | Transparency | Every classification carries the list of rules fired and contributing observations |
| NFR-7 | Usability | Readable at 1920×1080; usable down to ~1280 px wide |

## 5. Layered architecture

```
PHYSICAL ENVIRONMENT        people, vehicles, weather, fire, water        (simulated world model)
        ↓
SENSING LAYER               optical / thermal / PIR / fence / microwave / radar / contact / env
        ↓
EDGE COMPUTING              detection, tracking, thresholds, debounce, store-and-forward
        ↓
COMMUNICATION NETWORK       Ethernet / Wi-Fi / LoRaWAN / LTE / RS-485 → MQTT-style observations
        ↓
AI PROCESSING & FUSION      validation → clock correction → zone/time correlation
        ↓
EVENT CLASSIFICATION        deterministic rules → category, evidence score, severity
        ↓
COMMAND & CONTROL CENTRE    dashboard, alerts, timeline, analytics
        ↓
HUMAN VERIFICATION          acknowledge → verify (genuine / false positive / benign)
        ↓
EMERGENCY RESPONSE          authorised notification categories → resolve → close → report
```

The per-layer purpose, hardware, software, inputs, outputs, interfaces, power, failure modes and limitations are in the app (Architecture view) and in `frontend/src/data/architecture.js`.

## 6. Component interaction

```
 ┌──────────────── backend (FastAPI, one asyncio loop) ─────────────────┐
 │ SimulationEngine ──readings──▶ EdgeNode (debounce, tracks, queue)     │
 │        ▲                              │ observations + latency model  │
 │        │ world model                  ▼                               │
 │  Environment defs              DeliveryQueue (per-link latency/loss)  │
 │                                       │ ingest                        │
 │                                       ▼                               │
 │                     FusionEngine (validate→sync→correlate→classify)   │
 │                                       │ Event                         │
 │                                       ▼                               │
 │   EventStore (SQLite) ◀──── IncidentService (lifecycle state machine) │
 │          │                            │                               │
 │   REST /api/*                  WebSocket /ws  (snapshot 5 Hz, events) │
 └──────────┼────────────────────────────┼───────────────────────────────┘
            ▼                            ▼
       Browser UI (vanilla ES modules, SVG) — served from /, same origin
```

## 7. Event schema

| Field | Type | Notes |
|---|---|---|
| `event_id` | string | `VIPER-<UTC year>-<seq ≥4 digits>`, sequence persisted in SQLite |
| `created_utc` | string | ISO-8601 UTC with ms, e.g. `2026-11-04T19:15:12.381Z` |
| `created_local` | string | Host local time, e.g. `2026-11-05 00:45:12.381 IST` |
| `sim_time` | float | Simulation clock seconds (T+) at creation — distinct from wall clock |
| `environment` | string | `airport`, `substation`, `fuel_depot` |
| `sensor_id` / `sensor_type` | string | Primary (first) contributing sensor |
| `zone` | string | Zone ID |
| `category` | enum | `normal_activity`, `environmental_disturbance`, `unverified_movement`, `perimeter_anomaly`, `equipment_malfunction`, `communication_failure` |
| `classification` | string | Operator-facing label, e.g. "Requires verification" |
| `severity` | enum | `info`, `low`, `medium`, `high`, `critical` |
| `confidence` | float 0–1 | **Rule-based evidence score — not a probability of threat** |
| `description` | string | Human-readable summary |
| `processing_status` | enum | `received` → `validated` → `correlated` → `classified` |
| `verification_status` | enum | `not_required`, `awaiting_review`, `verified_genuine`, `false_positive`, `verified_benign` |
| `acknowledgement_status` | enum | `unacknowledged`, `acknowledged`, `not_required` |
| `resolution_status` | enum | `open`, `response_initiated`, `resolved`, `closed` |
| `contributing` | list | Observations (sensor, value, raw/corrected timestamps, quality, validation flags) |
| `rules` | list | Ordered rule trace that produced the classification |
| `latency` | object | `edge_ms`, `network_ms`, `fusion_ms`, `detection_ms` |
| `lifecycle` | list | `{stage, ts_utc, actor, note}` per transition |
| `response` | object | `{category, authorized_by, ts_utc, note}` |

## 8. Database schema (SQLite)

```sql
CREATE TABLE events (
  event_id TEXT PRIMARY KEY, year INTEGER, seq INTEGER,
  created_utc TEXT, created_epoch REAL, sim_time REAL, environment TEXT,
  sensor_id TEXT, sensor_type TEXT, zone TEXT, category TEXT, classification TEXT,
  severity TEXT, confidence REAL, description TEXT,
  processing_status TEXT, verification_status TEXT,
  acknowledgement_status TEXT, resolution_status TEXT,
  detection_latency_ms REAL, alert_epoch REAL, ack_epoch REAL,
  verified_epoch REAL, response_epoch REAL, resolved_epoch REAL, closed_epoch REAL,
  response_category TEXT, data TEXT  -- JSON: contributing, rules, latency, response
);
CREATE TABLE lifecycle (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT,
  stage TEXT, ts_utc TEXT, ts_epoch REAL, actor TEXT, note TEXT);
CREATE TABLE logs (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_utc TEXT, ts_epoch REAL,
  level TEXT, source TEXT, message TEXT);
CREATE TABLE test_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_utc TEXT, report TEXT);
```

## 9. API endpoints

See `software_architecture.md` §4 for request/response bodies. Interactive OpenAPI docs are generated at `http://127.0.0.1:8000/api/docs-ui`.

## 10. Dependencies

| Dependency | Why | Alternative |
|---|---|---|
| FastAPI | Typed REST + WebSocket on one async loop, auto OpenAPI | Flask + flask-sock |
| Uvicorn (+`websockets`) | ASGI server | Hypercorn |
| Pydantic (via FastAPI) | Request validation | — |
| sqlite3 (stdlib) | Zero-install persistence | PostgreSQL for multi-site |
| pytest, httpx | Automated tests | unittest |

The frontend uses **no third-party libraries**: charts and schematics are hand-built SVG, so the app runs fully offline and no build step (Node/Vite) is needed. This was a deliberate trade-off: less charting convenience in exchange for zero install friction on Windows.
