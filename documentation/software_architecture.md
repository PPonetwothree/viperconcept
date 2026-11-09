# VIPER — Software Architecture, API & Engineering Analysis

> Demonstrator build. All sensor data are simulated; no hardware integration exists.

## 1. Module map

| Layer | Path | Responsibility |
|---|---|---|
| Server entry | `backend/main.py` | FastAPI app, lifespan (store + runtime + 5 Hz loop), static frontend on `/` |
| Configuration | `backend/config.py`, `backend/.env.example` | Env-var configuration (host, port, DB path, tick rate, fusion window, heartbeat timeout, seed) |
| Simulation | `backend/simulation/environments.py` | Three conceptual site layouts (zones, sensors, nodes, routes, assets) |
| | `backend/simulation/adapters.py` | `SensorAdapter` interface, `SimulatedAdapter`, `HardwareAdapterTemplate` (deliberately unimplemented) |
| | `backend/simulation/engine.py` | World model, edge analytics, links, store-and-forward, power, failure injection, `VirtualClock` |
| | `backend/simulation/runtime.py` | Wires engine → fusion → store → listeners; control, injection, operator actions, KPIs, analytics |
| | `backend/simulation/scenarios.py` | Module L scenario harness (headless, virtual clock) |
| Event engine | `backend/event_engine/models.py` | `Observation`, `Event`, enums, UTC/local formatting |
| | `backend/event_engine/fusion.py` | Validation, time sync, correlation, classification rules, merging, heartbeat watchdog |
| | `backend/event_engine/lifecycle.py` | Human-in-the-loop state machine |
| Persistence | `backend/database/store.py` | SQLite: events, lifecycle, logs, test runs; query/filter/export |
| API | `backend/api/routes.py`, `ws.py`, `reports.py` | REST, WebSocket, Markdown incident reports |
| Devices | `backend/devices/catalog.py` | Module B device profiles and selection rationale |
| Tests | `backend/tests/` | pytest: unit, scenario, robustness, API |
| Frontend | `frontend/index.html`, `frontend/src/` | Vanilla ES modules, no build step |

Frontend: `core/` (api, store, ws, util), `components/` (charts, incident, markdown, ui), `dashboards/` (command, fusion, incidents, analytics, testing, docs), `schematics/` (architecture, schematics), `simulation/mapView.js`, `animations/flow.js`, `devices/devices.js`, `data/architecture.js`, `styles/main.css`.

## 2. Data flow

```
SimulatedAdapter.read()  ──reading──▶  edge processing (_edge_process: tracks, thresholds, cooldowns)
      ▲                                     │ Observation(sensor_ts = true time + node skew)
      │ world model                          ▼
SimulationEngine.step()               _transmit(): link up?  ──no──▶ node store-and-forward queue
                                            │ yes: latency ~ U(link), loss → QoS1 retransmit
                                            ▼
                                     delivery queue (wall-clock release)
                                            ▼
Runtime.step(): FusionEngine.ingest()  → heartbeat? update offset/liveness
                                       → validate (V1/V2) → correct clock (T1) → snapshot access context
                                       → fault/power? immediate system event
                                       → bucket[(zone, group)]
                FusionEngine.step()    → heartbeat watchdog (H1)
                                       → close buckets (6 s or ≥3 modalities) → merge or classify → Event
                EventStore.save()      → SQLite (events + append-only lifecycle)
                Runtime.emit()         → WebSocket: event / event_update / observation / log / snapshot (5 Hz)
Operator (UI) → REST action → lifecycle transition (409 if invalid) → save → emit event_update
```

Two clocks are kept separate: **wall clock** (host time, stored as UTC with ms) stamps every observation, event and action and drives network latency and heartbeats; **simulation clock** (T+, advances `real_dt × speed`, stops when paused) drives movement, weather, fires and power drain. Both are displayed side by side in the UI and stored on each event (`created_utc` and `sim_time`).

## 3. Classification and the meaning of “confidence”

The engine is a **transparent rule engine, not a trained model**. Evidence score:

```
E = 1 − Π_m (1 − w_m · q_m)       m ∈ independent modalities present (best observation per modality)
```

`w_m` = illustrative modality weight (adjusted for wind / low light), `q_m` = edge-reported quality. E measures **corroboration**, not threat probability. The probability that an alert is genuine is

```
P(genuine | alert) = TPR·π / (TPR·π + FPR·(1 − π))
```

which depends on the base rate π and the true detection/false-alarm rates — unknown until a pilot. The Fusion view includes an explicitly illustrative calculator for this.

Rules (full text in the Fusion view): V1/V2 validation · T1 time sync · K1 correlation · M1 merge · C1 evidence · W context weights · R1 authorised presence · R2 wildlife vote · R3 wind compensation · R4 unauthorised access point · R5 single modality · R6 perimeter corroboration · R7 interior corroboration · E1–E4 environmental · F1 device fault · P1 power · H1 heartbeat.

## 4. API documentation

Base URL `http://127.0.0.1:8000`. Interactive OpenAPI UI: `/api/docs-ui`. All request bodies are validated by Pydantic (HTTP 422 on invalid input). Lifecycle violations return **409** with a reason.

### System & metadata
| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | `{status, mode:"SIMULATION", hardware_connected:false, sim, db_path}` |
| GET | `/api/meta` | Severities, categories, response categories, verification outcomes, link & node models, config |
| GET | `/api/environments` | List of environments |
| GET | `/api/environments/{id}` | Full layout (zones, sensors, nodes, structures, routes) |
| GET | `/api/devices` | Device catalogue + selection rationale |

### Simulation control
| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/api/sim/state` | — | Snapshot: entities, sensors, nodes, power, conditions, KPIs |
| POST | `/api/sim/control` | `{"action":"start\|pause\|resume\|reset","clear_history":false}` | `clear_history` only with reset |
| POST | `/api/sim/speed` | `{"speed":1\|2\|5}` | |
| POST | `/api/sim/environment` | `{"environment_id":"airport\|substation\|fuel_depot"}` | Rebuilds world |
| POST | `/api/sim/inject` | `{"kind":..., "target":null}` | kinds: `test_intrusion` (target zone A–D), `equipment_failure` (sensor id), `comm_failure` (node id), `env_anomaly`, `fire`, `leak`, `power_interruption`, `animal`, `wind_gust`, `vehicle`. 409 if not running |

### Events & incident workflow
| Method | Path | Body / query |
|---|---|---|
| GET | `/api/events` | `severity` (comma list), `sensor_id`, `zone`, `category`, `q` (ID/text search), `status` (`active`, `awaiting`, `unacknowledged`, `open`, `response_initiated`, `resolved`, `closed`), `environment`, `limit`, `offset`, `order` |
| GET | `/api/events/{id}` | Full event incl. `lifecycle`, `contributing`, `rules`, `evidence`, `latency`, `actions` (currently permitted) |
| POST | `/api/events/{id}/acknowledge` | `{"operator":"name","note":""}` |
| POST | `/api/events/{id}/verify` | `{"operator":..., "outcome":"verified_genuine\|false_positive\|verified_benign"}` |
| POST | `/api/events/{id}/false-positive` | `{"operator":...}` — verify as FP and resolve |
| POST | `/api/events/{id}/respond` | `{"operator":..., "category":"security_team\|infrastructure_ops\|technical_maintenance\|emergency_services\|escalation", "authorized":true}` — requires `verified_genuine` and `authorized:true` |
| POST | `/api/events/{id}/resolve` | `{"operator":...}` — requires response initiated, or FP/benign verification |
| POST | `/api/events/{id}/close` | `{"operator":...}` — requires resolved |
| GET | `/api/events/{id}/report?format=md\|json` | Complete incident report |
| GET | `/api/export?format=csv\|json&environment=` | History export |

### Analytics, logs, tests, docs
| Method | Path | Description |
|---|---|---|
| GET | `/api/analytics?environment=` | Events/hour, events/minute, by category/severity, FP rate, latency stats + samples, sensor availability |
| GET | `/api/logs?limit=` | System log |
| GET | `/api/tests/scenarios` | Scenario IDs |
| POST | `/api/tests/run` | `{"scenarios":null\|[ids]}` → report (stored) |
| GET | `/api/tests/latest` | Last stored report |
| GET | `/api/docs`, `/api/docs/{name}` | Documentation (path-traversal protected) |

### WebSocket `/ws`
Server → client JSON messages: `hello {sim, snapshot}`, `snapshot {snapshot}` (5 Hz), `event {event}`, `event_update {event}`, `observation {obs}`, `log {log}`, `environment {environment}`. Slow clients drop snapshots before events.

### Example

```bash
curl -X POST http://127.0.0.1:8000/api/sim/inject -H "Content-Type: application/json" -d "{\"kind\":\"test_intrusion\",\"target\":\"A\"}"
curl "http://127.0.0.1:8000/api/events?severity=high,critical&status=active"
curl -X POST http://127.0.0.1:8000/api/events/VIPER-2026-0001/acknowledge -H "Content-Type: application/json" -d "{\"operator\":\"op1\"}"
```

## 5. Database schema

See `system_architecture.md` §8. Lifecycle rows are append-only; an event row is upserted on every transition. IDs are `VIPER-<UTC year>-<sequence>` with the sequence persisted per year. All timestamps are stored as epoch seconds (REAL) **and** ISO-8601 UTC strings with milliseconds.

## 6. Failure analysis (FMEA-style, abbreviated)

| Failure mode | Effect | Detection in VIPER | Mitigation |
|---|---|---|---|
| Camera video loss / sensor fault | Blind spot | Device self-test → F1 equipment malfunction; sensor shown FAULT; its data rejected | Overlapping coverage (thermal + optical per side), maintenance response |
| Fence processor/bus failure | Fence segment blind | F1 fault; missing data | Thermal/optical still cover the side |
| Edge node uplink loss | Observations delayed | Heartbeat watchdog H1 (7 s) | Store-and-forward; late deliveries flagged and correlated by sensor time |
| Edge node crash | Side blind | H1 | Watchdog reboot; redundant node (roadmap) |
| Clock drift | Mis-ordered or uncorrelated events | Offset estimate per node; correction shown in incident | NTP/PTP; T1 correction |
| Mains failure | Possible shutdown | P1 power event (UPS SNMP) | UPS ride-through; solar for env node; nodes shed below 8 % |
| Wind/rain | Nuisance fence alarms | R3 wind compensation | Weather station feed (roadmap) |
| Wildlife | Nuisance alarms | R2 label vote | Fence mesh, vegetation management |
| Authorised activity | Nuisance alarms | R1 access-control context | Badge + localisation |
| Authorisation masking | Missed non-breaching intruder near staff | Not detected (known limitation) | Per-person tracking, two-modality rule for interior zones |
| Operator overload | Slow acknowledgement | Ack-latency KPI | Correlation, merging, rate limits, severity sort |
| Database corruption | Lost history | SQLite integrity check (manual) | WAL mode + backups (roadmap) |
| Browser disconnect | Operator blind | Status badge “backend disconnected” | Auto-reconnect with back-off |

## 7. Cybersecurity considerations

Threats for a deployed system include spoofed sensor messages, replay, denial of service on links/radio, compromise of edge nodes, insider misuse and data exfiltration of site layouts. Recommended controls (not all implemented in this demonstrator):

- **Network segmentation**: separate VLANs for cameras, sensors, management and C2; default-deny firewall; edge nodes make outbound connections only.
- **Mutual TLS for MQTT** with per-node certificates and per-topic ACLs; LoRaWAN AES-128 session keys; message sequence numbers + timestamps to reject replays (validation rule V1 already rejects future-dated observations).
- **Secure boot & disk encryption** on edge nodes (Jetson secure boot, ESP32 secure boot + flash encryption), signed updates.
- **API authentication & RBAC** (operator, supervisor, auditor), two-person rule for escalation. *This demonstrator has no authentication and binds to 127.0.0.1 by default — do not expose it on a network.*
- **Audit trail**: lifecycle table is append-only with actor and UTC time; ship logs to write-once storage.
- **Data minimisation**: no video leaves the edge unless an operator requests a clip; layouts are classified documents.
- **Supply chain**: approved-vendor list, firmware hash verification, disable unused services (Telnet/UPnP/cloud P2P on cameras).
- **Jamming / link loss** is treated as an event (H1), never as “all clear”.
- Inputs are validated server-side (Pydantic models, bounded lengths, enumerations) and the docs endpoint is protected against path traversal.

## 8. Scalability considerations

| Dimension | Demonstrator | Scaling path |
|---|---|---|
| Sensors per site | ~33 | Hundreds: per-zone fusion workers keyed by zone (fusion state is already partitioned by `(zone, group)`) |
| Sites | 1 active | One fusion service per site, central aggregation; site ID in topics and event IDs |
| Transport | in-process queue | MQTT cluster (EMQX/Mosquitto bridge), Kafka for analytics |
| Storage | SQLite | PostgreSQL/TimescaleDB with retention policies; object storage for clips |
| UI | single page, 5 Hz snapshots | Delta snapshots, tile-based maps, role-specific consoles |
| Compute | < 1 ms per tick | Event volume, not compute, is the constraint; rate limits and merging bound alert load |

## 9. Hardware adapter extension

Implement `SensorAdapter.read(sensor, world) -> {"value", "unit", "text", "detections"?}` for a physical transport (e.g. MQTT subscriber for ESP32 nodes, ONVIF analytics events for cameras, Modbus RTU poller for fence processors) and select it per sensor type in `SimulationEngine`. Observations must carry the node's own timestamp; the fusion engine already handles clock correction, validation and late delivery. No hardware adapter is implemented in this build (`HardwareAdapterTemplate` raises `NotImplementedError` by design).

## 10. Development roadmap

1. **Pilot hardware bench (Phase 1)**: one perimeter segment — 1 optical, 1 thermal (Lepton 3.5 for bench, commercial for field), 2 ADXL355 fence nodes, Jetson Orin Nano, ESP32 env node; implement MQTT and Modbus adapters.
2. **Calibration (Phase 2)**: structured walk/climb tests (day/night/weather) to measure P_d, nuisance alarm rate, detection latency; fit modality weights and thresholds; document confidence intervals.
3. **Security hardening**: authentication/RBAC, mutual TLS, audit export, secure boot.
4. **Operations**: PTZ slew-to-alarm with operator confirmation, video clip retrieval, shift handover report, multi-operator assignment.
5. **Learning components (optional, gated)**: train and evaluate a classifier on labelled pilot data; deploy only with documented performance, drift monitoring, and the rule engine as a fallback. Keep human verification mandatory.
6. **Multi-site**: PostgreSQL, site federation, central analytics.
