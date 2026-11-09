"""SQLite persistence for events, lifecycle history, system logs and test runs."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from event_engine.models import Event, local_str, now, utc_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY, year INTEGER, seq INTEGER,
  created_utc TEXT, created_epoch REAL, sim_time REAL, environment TEXT,
  sensor_id TEXT, sensor_type TEXT, zone TEXT, category TEXT, classification TEXT,
  severity TEXT, confidence REAL, description TEXT,
  processing_status TEXT, verification_status TEXT,
  acknowledgement_status TEXT, resolution_status TEXT,
  detection_latency_ms REAL, alert_epoch REAL, ack_epoch REAL, verified_epoch REAL,
  response_epoch REAL, resolved_epoch REAL, closed_epoch REAL,
  response_category TEXT, data TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_created ON events(created_epoch);
CREATE TABLE IF NOT EXISTS lifecycle (
  id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT, stage TEXT,
  ts_utc TEXT, ts_epoch REAL, actor TEXT, note TEXT
);
CREATE INDEX IF NOT EXISTS ix_lifecycle_event ON lifecycle(event_id);
CREATE TABLE IF NOT EXISTS logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts_utc TEXT, ts_epoch REAL,
  level TEXT, source TEXT, message TEXT
);
CREATE TABLE IF NOT EXISTS test_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_utc TEXT, report TEXT
);
"""

COLUMNS = ["event_id", "year", "seq", "created_utc", "created_epoch", "sim_time", "environment",
           "sensor_id", "sensor_type", "zone", "category", "classification", "severity",
           "confidence", "description", "processing_status", "verification_status",
           "acknowledgement_status", "resolution_status", "detection_latency_ms",
           "alert_epoch", "ack_epoch", "verified_epoch", "response_epoch", "resolved_epoch",
           "closed_epoch", "response_category", "data"]

EXPORT_FIELDS = ["event_id", "created_utc", "created_local", "sim_time", "environment", "sensor_id",
                 "sensor_type", "zone", "category", "classification", "severity", "confidence",
                 "description", "processing_status", "verification_status",
                 "acknowledgement_status", "resolution_status", "detection_latency_ms",
                 "response_category"]


class EventStore:
    def __init__(self, path: str | Path = ":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._cache: dict[str, Event] = {}
        self._reserved: dict[int, int] = {}

    # ---------------------------------------------------------------- ids
    def next_event_id(self) -> str:
        year = datetime.now(timezone.utc).year
        row = self.conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events WHERE year=?", (year,)).fetchone()
        seq = max(row[0], self._reserved.get(year, 0)) + 1
        self._reserved[year] = seq
        return f"VIPER-{year}-{seq:04d}"

    # ---------------------------------------------------------------- write
    def save(self, ev: Event) -> None:
        year, seq = int(ev.event_id.split("-")[1]), int(ev.event_id.split("-")[2])
        data = json.dumps({"contributing": ev.contributing, "rules": ev.rules, "evidence": ev.evidence,
                           "latency": ev.latency, "response": ev.response})
        vals = {
            "event_id": ev.event_id, "year": year, "seq": seq, "created_utc": ev.created_utc,
            "created_epoch": ev.created_epoch, "sim_time": ev.sim_time, "environment": ev.environment,
            "sensor_id": ev.sensor_id, "sensor_type": ev.sensor_type, "zone": ev.zone,
            "category": ev.category, "classification": ev.classification, "severity": ev.severity,
            "confidence": ev.confidence, "description": ev.description,
            "processing_status": ev.processing_status, "verification_status": ev.verification_status,
            "acknowledgement_status": ev.acknowledgement_status,
            "resolution_status": ev.resolution_status,
            "detection_latency_ms": ev.latency.get("detection_ms"), "alert_epoch": ev.alert_epoch,
            "ack_epoch": ev.ack_epoch, "verified_epoch": ev.verified_epoch,
            "response_epoch": ev.response_epoch, "resolved_epoch": ev.resolved_epoch,
            "closed_epoch": ev.closed_epoch, "response_category": ev.response.get("category"),
            "data": data}
        placeholders = ",".join("?" for _ in COLUMNS)
        self.conn.execute(f"INSERT OR REPLACE INTO events ({','.join(COLUMNS)}) VALUES ({placeholders})",
                          [vals[c] for c in COLUMNS])
        # Lifecycle is append-only: insert entries not yet stored.
        stored = self.conn.execute("SELECT COUNT(*) FROM lifecycle WHERE event_id=?", (ev.event_id,)).fetchone()[0]
        for entry in ev.lifecycle[stored:]:
            self.conn.execute("INSERT INTO lifecycle (event_id, stage, ts_utc, ts_epoch, actor, note) "
                              "VALUES (?,?,?,?,?,?)", (ev.event_id, entry["stage"], entry["ts_utc"],
                                                       entry["ts_epoch"], entry["actor"], entry["note"]))
        self.conn.commit()
        self._cache[ev.event_id] = ev

    def log(self, level: str, source: str, message: str, at: float | None = None) -> dict[str, Any]:
        t = at or now()
        self.conn.execute("INSERT INTO logs (ts_utc, ts_epoch, level, source, message) VALUES (?,?,?,?,?)",
                          (utc_iso(t), t, level, source, message))
        self.conn.commit()
        return {"ts_utc": utc_iso(t), "ts_epoch": t, "level": level, "source": source, "message": message}

    def save_test_run(self, report: dict[str, Any]) -> None:
        self.conn.execute("INSERT INTO test_runs (run_utc, report) VALUES (?,?)",
                          (utc_iso(now()), json.dumps(report)))
        self.conn.commit()

    def clear(self) -> None:
        self.conn.executescript("DELETE FROM events; DELETE FROM lifecycle; DELETE FROM logs;")
        self.conn.commit()
        self._cache.clear()
        self._reserved = {}

    # ---------------------------------------------------------------- read
    def get(self, event_id: str) -> Event | None:
        if event_id in self._cache:
            return self._cache[event_id]
        row = self.conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        if not row:
            return None
        ev = self._row_to_event(row)
        self._cache[event_id] = ev
        return ev

    def _row_to_event(self, row: sqlite3.Row) -> Event:
        data = json.loads(row["data"] or "{}")
        ev = Event(event_id=row["event_id"], created_epoch=row["created_epoch"], sim_time=row["sim_time"],
                   environment=row["environment"], sensor_id=row["sensor_id"],
                   sensor_type=row["sensor_type"], zone=row["zone"], category=row["category"],
                   classification=row["classification"], severity=row["severity"],
                   confidence=row["confidence"], description=row["description"],
                   processing_status=row["processing_status"],
                   verification_status=row["verification_status"],
                   acknowledgement_status=row["acknowledgement_status"],
                   resolution_status=row["resolution_status"],
                   contributing=data.get("contributing", []), rules=data.get("rules", []),
                   evidence=data.get("evidence", []),
                   latency=data.get("latency", {}), response=data.get("response", {}),
                   alert_epoch=row["alert_epoch"], ack_epoch=row["ack_epoch"],
                   verified_epoch=row["verified_epoch"], response_epoch=row["response_epoch"],
                   resolved_epoch=row["resolved_epoch"], closed_epoch=row["closed_epoch"])
        for lr in self.conn.execute("SELECT * FROM lifecycle WHERE event_id=? ORDER BY id", (ev.event_id,)):
            ev.lifecycle.append({"stage": lr["stage"], "ts_utc": lr["ts_utc"], "ts_epoch": lr["ts_epoch"],
                                 "ts_local": local_str(lr["ts_epoch"]), "actor": lr["actor"],
                                 "note": lr["note"]})
        return ev

    def query(self, severity: list[str] | None = None, sensor_id: str | None = None,
              zone: str | None = None, category: str | None = None, q: str | None = None,
              status: str | None = None, environment: str | None = None,
              since_epoch: float | None = None, limit: int = 200, offset: int = 0,
              order: str = "desc") -> tuple[list[Event], int]:
        where, args = [], []
        if severity:
            where.append(f"severity IN ({','.join('?' for _ in severity)})")
            args += severity
        if sensor_id:
            where.append("(sensor_id = ? OR data LIKE ?)")
            args += [sensor_id, f'%"sensor_id": "{sensor_id}"%']
        if zone:
            where.append("zone = ?"); args.append(zone)
        if category:
            where.append("category = ?"); args.append(category)
        if environment:
            where.append("environment = ?"); args.append(environment)
        if q:
            where.append("(event_id LIKE ? OR description LIKE ?)")
            args += [f"%{q}%", f"%{q}%"]
        if since_epoch:
            where.append("created_epoch >= ?"); args.append(since_epoch)
        if status == "active":
            where.append("resolution_status IN ('open','response_initiated')")
        elif status == "awaiting":
            where.append("verification_status = 'awaiting_review'")
        elif status == "unacknowledged":
            where.append("acknowledgement_status = 'unacknowledged' AND resolution_status != 'closed'")
        elif status in ("open", "response_initiated", "resolved", "closed"):
            where.append("resolution_status = ?"); args.append(status)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        total = self.conn.execute(f"SELECT COUNT(*) FROM events {clause}", args).fetchone()[0]
        direction = "ASC" if order == "asc" else "DESC"
        rows = self.conn.execute(f"SELECT event_id FROM events {clause} ORDER BY created_epoch {direction}, "
                                 f"seq {direction} LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
        return [self.get(r[0]) for r in rows], total

    def all_events(self, environment: str | None = None) -> list[Event]:
        evs, _ = self.query(environment=environment, limit=1_000_000, order="asc")
        return evs

    def logs(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def latest_test_run(self) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT report FROM test_runs ORDER BY id DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None


def export_rows(events: list[Event]) -> list[dict[str, Any]]:
    rows = []
    for ev in events:
        d = ev.to_dict()
        rows.append({k: d.get(k) if k != "response_category" else ev.response.get("category")
                     for k in EXPORT_FIELDS})
    return rows
