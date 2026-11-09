# VIPER — Vigilant Infrastructure Protection & Emergency Response

An interactive engineering demonstrator for an integrated critical-infrastructure protection platform: sensing → edge computing → communication → rule-based sensor fusion → classification → command & control → human verification → emergency-response workflow.

> **This is a simulation.** Every sensor reading, entity, incident and latency figure is synthetic. No hardware is connected, and nothing in this repository has been validated in the field. Device specifications are compiled from manufacturer documentation (marked DS) or are estimates (EST); prices are estimates. Site layouts are generic and conceptual.

## Quick start (Windows)

Requirements: Python 3.10 or newer (tested on 3.14), any modern browser. No Node.js, no build step, no internet access needed at runtime.

```bat
cd VIPER
python -m pip install -r requirements.txt
python backend\main.py
```

Then open **http://127.0.0.1:8000**. (Or double-click `start.bat`.)

Run the automated tests:

```bat
cd backend
python -m pytest -q
```

(Or double-click `run_tests.bat`.) Regenerate the hardware spec, BOM and test report from the code: `python backend\tools\generate_docs.py`.

Optional configuration: copy `backend\.env.example` to `backend\.env` and edit (port, tick rate, correlation window, heartbeat timeout, random seed, ambient event rate). The database lives at `backend\data\viper.db`; delete it to start with an empty history.

## Deploying online (Netlify)

Netlify serves static files only, so the hosted build has **no server**: when the page finds no VIPER backend it downloads [Pyodide](https://pyodide.org) (CPython compiled to WebAssembly) and runs the *same* Python simulation, fusion rules, lifecycle and SQLite store inside the visitor's browser tab. Run locally with `python backend\main.py` and the page uses the real server instead — the frontend picks automatically.

The repo includes `netlify.toml`, so connecting the GitHub repo is enough:

1. Netlify → **Add new site → Import an existing project** → GitHub → this repository.
2. Leave the build settings as detected (`netlify.toml`: build `python3 backend/tools/build_static.py`, publish `dist`) → **Deploy**.

To build or check the static site yourself: `python backend\tools\build_static.py`, then `python -m http.server 8001 -d dist` and open http://127.0.0.1:8001.

Notes for the hosted build: the first visit downloads ≈10 MB (Pyodide, cached afterwards) and takes a few seconds to start; each visitor gets their own independent simulation; incident history is in memory and resets when the tab is reloaded; the simulation runs only while the tab is open; there is no authentication (it is a single-user demo).

## A 3-minute walkthrough

1. **Command** tab. Type an operator name (top bar). The simulation is already running: patrols and authorised vehicles move, and their observations are logged as *normal activity* (info). That shows that a sensor firing is not treated as a threat by default.
2. Click a thermal camera on the map (e.g. `TH-01`). The inspector shows its device profile, its edge node and uplink, its live simulated reading and a sparkline. Use **Wiring schematic ›** to see how it connects to the edge computer.
3. Press **Test event (intrusion)** (or *Test intrusion in zone X* from the sensor inspector). Set speed to 5×. A simulated person approaches, climbs the fence and enters. Amber packets show the observations travelling sensor → edge node → C2.
4. An alert appears: a **Potential perimeter anomaly**, escalating to critical as fence, thermal and optical observations correlate. Click it to see the rule trace and the contributing observations.
5. **Acknowledge → Verify genuine → Respond…** (choose a category and tick the explicit authorisation) **→ Resolve → Close**. Out-of-order actions are refused.
6. Open **Incidents** for the chronological timeline (filters, ID search, CSV/JSON export) and the full lifecycle page with UTC, local and simulation timestamps, raw vs corrected edge-clock times, and a downloadable report.
7. **Fusion engine** shows exactly how that incident was validated, time-aligned, correlated and scored, and why the evidence score is **not** a threat probability.
8. Try **Equipment failure**, **Comm. failure** (store-and-forward and heartbeat watchdog), **Env. anomaly**, **Power interruption** (UPS), **Animal** and **Wind gust** (both should stay low-severity). Then check **Analytics** and **Testing** (run all 8 scenarios).

## What's in it

| Module | Where |
|---|---|
| A · Engineering system architecture (clickable layers, live data-flow) | Architecture tab · `frontend/src/schematics/architecture.js`, `data/architecture.js` |
| B · Device & hardware inventory (32 profiles, DS/EST provenance, comparison) | Devices tab · `backend/devices/catalog.py` · `documentation/hardware_specifications.md` |
| C · Seven interactive SVG schematics (3 live) | Schematics tab · `frontend/src/schematics/schematics.js` · `documentation/engineering_schematics.md` |
| D · Infrastructure simulation (airport, substation, fuel depot) | Command map · `backend/simulation/environments.py`, `engine.py`, `frontend/src/simulation/mapView.js` |
| E · Sensor-fusion & classification engine (deterministic rules) | Fusion engine tab · `backend/event_engine/fusion.py` |
| F · Timestamp-based event engine & incident management | Incidents tab · `backend/event_engine/`, `backend/database/store.py` |
| G · Command & control dashboard with live KPIs | Command tab · `frontend/src/dashboards/command.js` |
| H · Animation & simulation controls (start/pause/resume/reset, 1×/2×/5×, injections) | Command tab |
| I · Human-in-the-loop emergency response workflow | Incident inspector / page · `backend/event_engine/lifecycle.py` |
| J · Analytics & metric definitions | Analytics tab · `Runtime.analytics()` |
| K · Engineering documentation | Docs tab · `documentation/` |
| L · Test scenarios & report | Testing tab · `backend/simulation/scenarios.py`, `backend/tests/`, `documentation/testing_report.md` |

## Project structure

```
VIPER/
├── start.bat / run_tests.bat
├── requirements.txt
├── backend/
│   ├── main.py              FastAPI app + static frontend on one URL
│   ├── config.py, .env.example
│   ├── api/                 REST routes, WebSocket, incident reports
│   ├── simulation/          environments, adapters, engine, runtime, scenarios
│   ├── event_engine/        models, fusion rules, lifecycle state machine
│   ├── database/            SQLite store
│   ├── devices/             device catalogue
│   ├── browser_bridge.py    in-browser backend for static hosting (Pyodide)
│   ├── tools/               documentation generator, static build
│   └── tests/               pytest suite (47 tests)
├── frontend/
│   ├── index.html
│   └── src/ (core, components, dashboards, schematics, simulation, animations, devices, data, styles)
└── documentation/           architecture, hardware, schematics, software/API, BOM, testing report
```

## Design decisions & trade-offs

- **FastAPI + vanilla ES modules, no bundler.** One `python backend\main.py` serves everything on one URL; there's no Node/npm toolchain to install on a Windows laptop. Charts and schematics are hand-built SVG, so the app runs fully offline. The cost is less charting convenience.
- **Backend-authoritative simulation.** The world, sensors, network and fusion run server-side at 5 Hz; the UI only renders snapshots and real messages. All animation is driven by application state.
- **Rule-based fusion, not ML.** The demonstrator has no labelled field data, so a trained model would be fabricated. Deterministic rules give a full audit trail; the architecture leaves room for a learned component once pilot data exist.
- **Separate clocks.** Wall-clock UTC (ms) for every stored timestamp; a distinct simulation clock (T+) for world time. Edge clock skew is simulated and corrected, so time synchronisation is visible.
- **Hardware adapters as an interface only.** `SensorAdapter` is the extension point. No fake hardware integration is shipped.

## Limitations

Simulated physics only (no occlusion or imaging weather model), illustrative rule weights, single operator, and no authentication. Bind only to localhost. See `documentation/testing_report.md` §5 and `documentation/software_architecture.md` §6–7.
