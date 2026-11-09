"""REST API. All endpoints are ``async`` so they run on the same event loop as
the simulation (no cross-thread access to engine state or SQLite)."""
from __future__ import annotations

import csv
import io
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

import config
from database.store import EXPORT_FIELDS, export_rows
from devices.catalog import DEVICES, SELECTION_RATIONALE
from event_engine.lifecycle import TransitionError
from event_engine.models import CATEGORIES, LIFECYCLE_STAGES, RESPONSE_CATEGORIES, SEVERITIES, \
    VERIFICATION_OUTCOMES
from simulation.environments import LINKS, NODE_MODELS, get_environment, list_environments
from simulation.scenarios import SCENARIOS, run_scenarios

from .reports import incident_report_md

router = APIRouter(prefix="/api")


def rt(request: Request):
    return request.app.state.runtime


# --------------------------------------------------------------------- models
class ControlBody(BaseModel):
    action: Literal["start", "pause", "resume", "reset"]
    clear_history: bool = False


class SpeedBody(BaseModel):
    speed: Literal[1, 2, 5]


class EnvBody(BaseModel):
    environment_id: str = Field(min_length=1, max_length=32)


class InjectBody(BaseModel):
    kind: Literal["test_intrusion", "equipment_failure", "comm_failure", "env_anomaly", "fire", "leak",
                  "power_interruption", "animal", "wind_gust", "vehicle"]
    target: str | None = Field(default=None, max_length=32)


class OperatorBody(BaseModel):
    operator: str = Field(min_length=1, max_length=64)
    note: str = Field(default="", max_length=500)


class VerifyBody(OperatorBody):
    outcome: Literal["verified_genuine", "false_positive", "verified_benign"]


class RespondBody(OperatorBody):
    category: Literal["security_team", "infrastructure_ops", "technical_maintenance",
                      "emergency_services", "escalation"]
    authorized: bool = Field(description="Operator explicitly confirms human authorisation")


class TestRunBody(BaseModel):
    scenarios: list[str] | None = None


# ---------------------------------------------------------------- system/meta
@router.get("/health")
async def health(request: Request):
    r = rt(request)
    return {"status": "ok", "mode": "SIMULATION", "hardware_connected": False,
            "sim": r.sim_status(), "db_path": str(config.DB_PATH)}


@router.get("/meta")
async def meta():
    return {"severities": SEVERITIES, "categories": CATEGORIES, "response_categories": RESPONSE_CATEGORIES,
            "verification_outcomes": VERIFICATION_OUTCOMES, "lifecycle_stages": LIFECYCLE_STAGES,
            "links": LINKS, "node_models": NODE_MODELS,
            "config": {"tick_hz": config.TICK_HZ, "correlation_window_s": config.CORRELATION_WINDOW_S,
                       "heartbeat_interval_s": config.HEARTBEAT_INTERVAL_S,
                       "heartbeat_timeout_s": config.HEARTBEAT_TIMEOUT_S,
                       "ambient_events_per_min": config.AMBIENT_EVENTS_PER_MIN}}


@router.get("/environments")
async def environments():
    return list_environments()


@router.get("/environments/{env_id}")
async def environment(env_id: str):
    try:
        return get_environment(env_id)
    except KeyError:
        raise HTTPException(404, f"Unknown environment '{env_id}'")


@router.get("/devices")
async def devices():
    return {"devices": DEVICES, "selection_rationale": SELECTION_RATIONALE}


# ----------------------------------------------------------------- simulation
@router.get("/sim/state")
async def sim_state(request: Request):
    return rt(request).snapshot()


@router.post("/sim/control")
async def sim_control(body: ControlBody, request: Request):
    r = rt(request)
    if body.action == "reset" and body.clear_history:
        r.store.clear()
    return r.control(body.action)


@router.post("/sim/speed")
async def sim_speed(body: SpeedBody, request: Request):
    return rt(request).set_speed(body.speed)


@router.post("/sim/environment")
async def sim_environment(body: EnvBody, request: Request):
    try:
        return rt(request).set_environment(body.environment_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/sim/inject")
async def sim_inject(body: InjectBody, request: Request):
    r = rt(request)
    if r.state != "running":
        raise HTTPException(409, "Start or resume the simulation before injecting events.")
    try:
        return r.inject(body.kind, body.target)
    except (ValueError, IndexError) as e:
        raise HTTPException(400, str(e))


# --------------------------------------------------------------------- events
@router.get("/events")
async def list_events(request: Request,
                      severity: str | None = Query(None, description="comma-separated severities"),
                      sensor_id: str | None = None, zone: str | None = None, category: str | None = None,
                      q: str | None = Query(None, max_length=64), status: str | None = None,
                      environment: str | None = None, limit: int = Query(200, ge=1, le=5000),
                      offset: int = Query(0, ge=0), order: Literal["asc", "desc"] = "desc"):
    r = rt(request)
    sev = [s for s in (severity or "").split(",") if s]
    bad = [s for s in sev if s not in SEVERITIES]
    if bad:
        raise HTTPException(422, f"Unknown severity {bad}")
    evs, total = r.store.query(sev or None, sensor_id, zone, category, q, status, environment,
                               limit=limit, offset=offset, order=order)
    return {"total": total, "events": [r.event_payload(e) for e in evs]}


@router.get("/events/{event_id}")
async def get_event(event_id: str, request: Request):
    r = rt(request)
    ev = r.store.get(event_id)
    if not ev:
        raise HTTPException(404, f"{event_id} not found")
    return r.event_payload(ev)


def _act(request: Request, event_id: str, action: str, **kw):
    r = rt(request)
    try:
        return r.event_payload(r.act(event_id, action, **kw))
    except KeyError:
        raise HTTPException(404, f"{event_id} not found")
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/events/{event_id}/acknowledge")
async def acknowledge(event_id: str, body: OperatorBody, request: Request):
    return _act(request, event_id, "acknowledge", operator=body.operator, note=body.note)


@router.post("/events/{event_id}/verify")
async def verify(event_id: str, body: VerifyBody, request: Request):
    return _act(request, event_id, "verify", operator=body.operator, note=body.note, outcome=body.outcome)


@router.post("/events/{event_id}/false-positive")
async def false_positive(event_id: str, body: OperatorBody, request: Request):
    return _act(request, event_id, "false_positive", operator=body.operator, note=body.note)


@router.post("/events/{event_id}/respond")
async def respond(event_id: str, body: RespondBody, request: Request):
    return _act(request, event_id, "respond", operator=body.operator, note=body.note,
                category=body.category, authorized=body.authorized)


@router.post("/events/{event_id}/resolve")
async def resolve(event_id: str, body: OperatorBody, request: Request):
    return _act(request, event_id, "resolve", operator=body.operator, note=body.note)


@router.post("/events/{event_id}/close")
async def close(event_id: str, body: OperatorBody, request: Request):
    return _act(request, event_id, "close", operator=body.operator, note=body.note)


@router.get("/events/{event_id}/report")
async def report(event_id: str, request: Request, format: Literal["json", "md"] = "json"):
    r = rt(request)
    ev = r.store.get(event_id)
    if not ev:
        raise HTTPException(404, f"{event_id} not found")
    if format == "md":
        return PlainTextResponse(incident_report_md(ev), media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="{event_id}.md"'})
    return JSONResponse(r.event_payload(ev), headers={"Content-Disposition": f'attachment; filename="{event_id}.json"'})


@router.get("/export")
async def export(request: Request, format: Literal["csv", "json"] = "csv", environment: str | None = None):
    r = rt(request)
    evs = r.store.all_events(environment)
    if format == "json":
        body = json.dumps({"mode": "SIMULATION", "exported_utc": r.sim_status()["wall_utc"],
                           "events": [e.to_dict() for e in evs]}, indent=2)
        return Response(body, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="viper_events.json"'})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=EXPORT_FIELDS)
    w.writeheader()
    w.writerows(export_rows(evs))
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="viper_events.csv"'})


# ------------------------------------------------------------------ analytics
@router.get("/analytics")
async def analytics(request: Request, environment: str | None = None):
    return rt(request).analytics(environment)


@router.get("/logs")
async def logs(request: Request, limit: int = Query(200, ge=1, le=2000)):
    return rt(request).store.logs(limit)


# --------------------------------------------------------------------- tests
@router.get("/tests/scenarios")
async def test_scenarios():
    return list(SCENARIOS)


@router.post("/tests/run")
async def tests_run(body: TestRunBody, request: Request):
    try:
        report = run_scenarios(body.scenarios)
    except KeyError as e:
        raise HTTPException(404, f"Unknown scenario {e}")
    rt(request).store.save_test_run(report)
    return report


@router.get("/tests/latest")
async def tests_latest(request: Request):
    return rt(request).store.latest_test_run() or {}


# ---------------------------------------------------------------------- docs
@router.get("/docs")
async def docs_list():
    return sorted(p.name for p in config.DOCS_DIR.glob("*.md"))


@router.get("/docs/{name}")
async def docs_get(name: str):
    path = (config.DOCS_DIR / name).resolve()
    if path.parent != config.DOCS_DIR.resolve() or path.suffix != ".md" or not path.exists():
        raise HTTPException(404, "Document not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown")
