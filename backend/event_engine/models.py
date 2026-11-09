"""Structured objects shared by the simulation, fusion engine, store and API."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

SEVERITIES = ["info", "low", "medium", "high", "critical"]
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}

CATEGORIES = {
    "normal_activity": "Normal activity",
    "environmental_disturbance": "Environmental disturbance",
    "unverified_movement": "Unverified movement",
    "perimeter_anomaly": "Potential perimeter anomaly",
    "equipment_malfunction": "Equipment malfunction",
    "communication_failure": "Communication failure",
}

RESPONSE_CATEGORIES = {
    "security_team": "Security team notification",
    "infrastructure_ops": "Infrastructure operations notification",
    "technical_maintenance": "Technical maintenance notification",
    "emergency_services": "Emergency services notification",
    "escalation": "Incident escalation",
}

VERIFICATION_OUTCOMES = {
    "verified_genuine": "Verified — genuine incident",
    "false_positive": "False positive",
    "verified_benign": "Verified — benign / no threat",
}

# Ordered lifecycle stages used for the incident detail view.
LIFECYCLE_STAGES = [
    "detected", "processed", "classified", "alerted",
    "acknowledged", "verified", "response_initiated", "resolved", "closed",
]


def utc_iso(epoch: float) -> str:
    """ISO-8601 UTC with millisecond precision, e.g. 2026-11-04T19:15:12.381Z."""
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def local_str(epoch: float) -> str:
    """Host local time with ms and zone abbreviation, e.g. 2026-11-05 00:45:12.381 IST."""
    try:
        dt = datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone()
    except (OSError, OverflowError, ValueError):  # Windows rejects some pre-1970-ish local conversions
        dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    name = dt.tzname() or ""
    # Windows reports long names ("India Standard Time"); abbreviate them.
    if " " in name:
        name = "".join(w[0] for w in name.split())
    return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{dt.microsecond // 1000:03d} {name}".rstrip()


def now() -> float:
    return time.time()


@dataclass
class Observation:
    """A detection emitted by an edge node after local processing.

    ``sensor_ts`` is stamped with the edge node's (skewed) clock; the fusion
    engine corrects it using the node's estimated offset to obtain ``corrected_ts``.
    """
    obs_id: str
    sensor_id: str
    sensor_type: str
    node_id: str
    zone: str
    kind: str              # motion | heat | vibration | contact | radar | smoke | temperature | leak | fault | power
    value: float
    unit: str
    quality: float         # 0..1 signal quality reported by the edge analytics
    sensor_ts: float       # epoch, edge clock (includes skew)
    edge_ts: float         # epoch, true time the edge finished processing
    sim_time: float
    edge_ms: float = 0.0
    network_ms: float = 0.0
    ingest_ts: float = 0.0
    corrected_ts: float = 0.0
    flags: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["sensor_ts_utc"] = utc_iso(self.sensor_ts)
        d["corrected_ts_utc"] = utc_iso(self.corrected_ts or self.sensor_ts)
        d["ingest_ts_utc"] = utc_iso(self.ingest_ts) if self.ingest_ts else None
        return d


@dataclass
class Event:
    event_id: str
    created_epoch: float
    sim_time: float
    environment: str
    sensor_id: str
    sensor_type: str
    zone: str
    category: str
    classification: str
    severity: str
    confidence: float
    description: str
    processing_status: str = "classified"
    verification_status: str = "awaiting_review"
    acknowledgement_status: str = "unacknowledged"
    resolution_status: str = "open"
    contributing: list[dict[str, Any]] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    latency: dict[str, float] = field(default_factory=dict)
    lifecycle: list[dict[str, Any]] = field(default_factory=list)
    response: dict[str, Any] = field(default_factory=dict)
    alert_epoch: float | None = None
    ack_epoch: float | None = None
    verified_epoch: float | None = None
    response_epoch: float | None = None
    resolved_epoch: float | None = None
    closed_epoch: float | None = None

    @property
    def created_utc(self) -> str:
        return utc_iso(self.created_epoch)

    def add_stage(self, stage: str, epoch: float, actor: str = "system", note: str = "") -> dict[str, Any]:
        entry = {"stage": stage, "ts_epoch": epoch, "ts_utc": utc_iso(epoch),
                 "ts_local": local_str(epoch), "actor": actor, "note": note}
        self.lifecycle.append(entry)
        return entry

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["created_utc"] = self.created_utc
        d["created_local"] = local_str(self.created_epoch)
        d["category_label"] = CATEGORIES.get(self.category, self.category)
        d["detection_latency_ms"] = self.latency.get("detection_ms")
        return d
