# VIPER — Testing Report

> Functional tests of the **software** (simulation, fusion rules, lifecycle, persistence, API). They do not and cannot validate field detection performance of any hardware.

## 1. Methodology

- **Unit tests** (`backend/tests/test_event_engine.py`): classification rules, noisy-OR evidence score, validation, clock-offset correction, correlation window, early close, merging/escalation, heartbeat watchdog, normal-activity rate limiting, every lifecycle transition (valid and invalid), SQLite round-trip, ID sequencing, timestamp format.
- **Scenario tests** (`backend/simulation/scenarios.py`, also exposed in the UI Testing view and run by pytest): isolated headless runtime, in-memory database, `VirtualClock` (fast-forwarded), fixed seeds.
- **Robustness tests**: intrusion detection and wildlife non-escalation repeated over 5 random seeds each.
- **API integration test**: FastAPI TestClient through start → inject → filter → full operator workflow → report → CSV/JSON export → analytics, including 409/422/404 error paths and path-traversal protection on /api/docs.
- **Manual browser verification**: every view rendered at 1920×1080 with no console errors; the complete acknowledge → verify → authorise response → resolve → close workflow driven through the UI buttons.

## 2. Scenario results (generated 2026-11-03T20:03:14.285Z, virtual (fast-forwarded), fixed seeds)

**8/8 passed** in 603.2 ms wall time.

| # | Scenario | Expected behaviour | Actual simulated behaviour | Event timestamp (UTC) | Processing latency | System status | Result |
|---|---|---|---|---|---|---|---|
| 1 | Normal operating conditions | Patrols and an authorised vehicle generate observations that are logged as normal activity (info, auto-closed); no alert requiring an operator is raised. | 9 normal-activity record(s), 0 alert(s); 15 normal records rate-limited.  | 2026-11-03T20:03:20.082Z | 6008.8 ms | 31/31 sensors, 6/6 nodes, mains | **PASS** |
| 2 | Simulated movement event (perimeter crossing, zone A) | At least two independent modalities (fence vibration + thermal and/or optical) correlate into ONE potential perimeter anomaly (high/critical); later observations merge into it; it awaits human verification with no automatic response. | VIPER-2026-0001: perimeter_anomaly/high, modalities ['fence', 'thermal'], evidence 0.62, status awaiting_review. Follow-up merges: 3 | 2026-11-03T20:03:31.078Z | 6001.9 ms | 31/31 sensors, 6/6 nodes, mains | **PASS** |
| 3 | Environmental disturbance (wind gust + animal at fence) | Wind-induced fence vibration and wildlife are classified as low-severity environmental disturbances, not as high-severity perimeter anomalies. | 4 environmental disturbance(s), 0 high/critical perimeter anomalies. VIPER-2026-0001 environmental_disturbance/low conf 0.66 (15 obs); VIPER-2026-0002 environmental_disturbance/low conf 0.14 (8 obs); VIPER-2026-0003 environmental_disturbance/low conf 0.14 (8 obs); VIPER-2026-0004 environmental_disturbance/low conf 0.14 (8 obs) | 2026-11-03T20:03:25.540Z | 3212.2 ms | 31/31 sensors, 6/6 nodes, mains | **PASS** |
| 4 | Sensor malfunction (thermal camera TH-01) | Device fault is reported by the edge node and raised as an equipment malfunction within 2 s; sensor shows FAULT and its data are excluded from fusion. | 1 equipment event(s) for TH-01; sensor status 'fault' | 2026-11-03T20:03:22.221Z | 2.3 ms | 30/31 sensors, 6/6 nodes, mains | **PASS** |
| 5 | Network interruption (edge node EN-W uplink lost for 25 s) | Heartbeat watchdog raises a communication failure after the 7 s timeout; on restoration the incident records the link recovery and buffered observations are flushed. | 1 communication-failure event(s) for EN-W; restoration recorded: True | 2026-11-03T20:03:27.433Z | 7000.0 ms | 31/31 sensors, 6/6 nodes, mains | **PASS** |
| 6 | Power interruption (mains loss, 90 s simulated) | Power monitor raises an equipment malfunction (power); UPS carries all edge nodes so no communication failures occur; restoration is recorded on the incident. | 1 power event(s); comm failures 0; during outage 6/6 nodes online on UPS battery (93.0 %); restoration recorded: True | 2026-11-03T20:03:22.255Z | 200.0 ms | 31/31 sensors, 6/6 nodes, mains | **PASS** |
| 7 | Multiple simultaneous events (intrusion + fire + device fault) | Three independent incidents are raised with their own categories; observations from different zones/groups are not merged into one incident. | 3 event(s), categories ['environmental_disturbance', 'equipment_malfunction', 'perimeter_anomaly']. VIPER-2026-0001 equipment_malfunction/medium conf 0.95 (1 obs); VIPER-2026-0002 environmental_disturbance/critical conf 0.69 (6 obs); VIPER-2026-0003 perimeter_anomaly/critical conf 0.71 (5 obs) | 2026-11-03T20:03:22.324Z | 2.2 ms | 30/31 sensors, 6/6 nodes, mains | **PASS** |
| 8 | Human-in-the-loop response workflow | No response without verification and explicit authorisation; full lifecycle Detection → … → Closure recorded with timestamps. | respond before verification rejected ✓; response without authorisation rejected ✓; lifecycle: detected → processed → classified → alerted → updated → acknowledged → verified → response_initiated → resolved → closed | 2026-11-03T20:03:31.395Z | 6001.9 ms | 31/31 sensors, 6/6 nodes, mains | **PASS** |

Processing latency = first contributing observation (clock-corrected sensor time) → alert. It is dominated by the 6 s correlation window (or early close at ≥ 3 modalities) plus simulated edge and link latency.

## 3. Automated test suite

```
$ python -m pytest -q
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
46 passed, 1 warning in 3.41s
```

## 4. Findings during development (fixed)

1. Camera detections were attributed to the camera mast's zone, so a patrol seen across a zone boundary looked unauthorised. Fix: observations from calibrated cameras/radar are attributed to the zone of the object's ground position.
2. A single mislabelled frame (animal → person) could escalate wildlife to a high-severity perimeter anomaly. Fix: confidence-weighted label vote (rule R2).
3. Wind was evaluated when the correlation window closed, not when the fence alarmed. Fix: edge reports wind with the observation (rule R3).
4. At 5× speed, authorised staff could leave a zone before the window closed, producing spurious unverified-movement alerts. Fix: access-control state is snapshotted at ingest.

## 5. Known limitations

- Rule weights and thresholds are illustrative; no field data exist to calibrate them.
- No line-of-sight occlusion, no weather effect on imaging beyond the light factor, no sensor drift model.
- Authorisation masking: a non-breaching intruder in a zone where authorised staff are present is logged as normal activity (rule R1). A deployment needs per-person localisation (badges + tracking) to close this gap.
- Single operator, no authentication/authorisation on the API in this build.
