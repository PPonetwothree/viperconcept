"""Rule-based sensor fusion and event classification.

This is a *transparent, deterministic rule engine*, not a trained ML model.
Every classification returns the ordered list of rules that fired so an operator
(or auditor) can see exactly why an alert was raised.

Pipeline per observation:
    validate  →  timestamp correction  →  zone/time correlation  →  classify  →  Event

The ``confidence`` value is an *evidence score* computed with a noisy-OR over
independent modalities. It is NOT the probability that a real threat exists —
that also depends on the base rate of genuine incidents, which can only be
estimated from pilot data (see documentation/software_architecture.md §3).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .models import CATEGORIES, SEVERITY_RANK, Event, Observation, now

# Sensor type → modality class. Types in the same class are NOT independent evidence.
MODALITY = {
    "optical": "optical", "lowlight": "optical", "ptz": "optical",
    "thermal": "thermal", "pir": "pir", "microwave": "microwave",
    "fence": "fence", "radar": "radar", "contact": "contact",
    "smoke": "smoke", "temperature": "temperature", "leak": "leak",
}
# Illustrative per-modality reliability weights (to be calibrated in a pilot).
WEIGHT = {
    "optical": 0.55, "thermal": 0.60, "pir": 0.30, "microwave": 0.40,
    "fence": 0.45, "radar": 0.50, "contact": 0.70,
    "smoke": 0.60, "temperature": 0.35, "leak": 0.80,
}
PERIMETER_CLASSES = {"fence", "contact", "radar"}
ENV_KINDS = {"smoke", "temperature", "leak"}
INTRUSION_KINDS = {"motion", "heat", "vibration", "contact", "radar"}
SYSTEM_KINDS = {"fault", "power", "heartbeat"}

# Physically plausible ranges per observation kind (validation rule V2).
PLAUSIBLE = {
    "motion": (0.0, 1.0), "heat": (0.0, 400.0), "vibration": (0.0, 10.0),
    "contact": (0.0, 1.0), "radar": (0.0, 2000.0), "smoke": (0.0, 100.0),
    "temperature": (-40.0, 150.0), "leak": (0.0, 1.0),
}
BREACH_VIBRATION_G = 0.8      # fence vibration consistent with climbing / cutting
HIGH_WIND_MS = 8.0            # above this, fence-only alarms are treated as wind-induced
LOW_LIGHT = 0.3               # ambient light fraction below which optical weight is reduced
MAX_FUTURE_S = 1.0            # corrected timestamp later than ingest by more than this → reject
LATE_S = 5.0                  # delivered later than this → flagged (store-and-forward)
MERGE_WINDOW_S = 45.0         # follow-up observations within this time update the open incident
NORMAL_RATE_LIMIT_S = 45.0    # at most one normal-activity record per zone per this period


class FusionContext(Protocol):
    environment: str

    def sensor(self, sensor_id: str) -> dict[str, Any] | None: ...
    def sensor_healthy(self, sensor_id: str) -> bool: ...
    def authorized_present(self, zone: str) -> bool: ...
    def wind_ms(self) -> float: ...
    def light(self) -> float: ...
    def sim_time(self) -> float: ...


@dataclass
class Bucket:
    zone: str
    group: str
    opened_wall: float
    obs: list[Observation] = field(default_factory=list)


def noisy_or(scores: list[float]) -> float:
    p = 1.0
    for s in scores:
        p *= (1.0 - max(0.0, min(1.0, s)))
    return 1.0 - p


def obs_wind(o: Observation, ctx: FusionContext) -> float:
    """Wind at the time of the observation (reported by the edge), else current wind."""
    return float(o.details.get("wind_ms", ctx.wind_ms()))


def label_vote(obs: list[Observation]) -> tuple[str | None, float]:
    """Confidence-weighted vote over edge object-class labels. Returns the
    winning label and its share of the total label weight."""
    votes: dict[str, float] = {}
    for o in obs:
        lab = o.details.get("object_class")
        if lab and lab != "unknown":
            votes[lab] = votes.get(lab, 0.0) + float(o.details.get("class_conf", 0.5))
    if not votes:
        return None, 0.0
    lab = max(votes, key=votes.get)
    return lab, votes[lab] / sum(votes.values())


def effective_weight(o: Observation, ctx: FusionContext) -> tuple[float, str | None]:
    cls = MODALITY.get(o.sensor_type, o.sensor_type)
    w = WEIGHT.get(cls, 0.3)
    note = None
    if cls == "fence" and obs_wind(o, ctx) >= HIGH_WIND_MS:
        w *= 0.5
        note = f"fence weight halved (wind {obs_wind(o, ctx):.1f} m/s ≥ {HIGH_WIND_MS} at observation time)"
    if o.sensor_type == "optical" and ctx.light() < LOW_LIGHT:
        w *= 0.6
        note = f"optical weight ×0.6 (low light {ctx.light():.2f})"
    return w, note


def classify(obs: list[Observation], ctx: FusionContext, zone: str, group: str) -> dict[str, Any]:
    """Pure classification of a correlated observation set. Returns category,
    severity, confidence, label, description and the rule trace."""
    rules: list[str] = []
    best: dict[str, float] = {}
    evidence: dict[str, dict[str, Any]] = {}
    for o in obs:
        cls = MODALITY.get(o.sensor_type, o.sensor_type)
        w, note = effective_weight(o, ctx)
        score = w * o.quality
        if score > best.get(cls, -1):
            best[cls] = score
            evidence[cls] = {"modality": cls, "sensor_id": o.sensor_id, "base_weight": WEIGHT.get(cls, 0.3),
                             "weight": round(w, 3), "quality": o.quality, "score": round(score, 3),
                             "adjustment": note}
        if note and f"W: {note}" not in rules:
            rules.append(f"W: {note}")
    classes = set(best)
    conf = round(noisy_or(list(best.values())), 3)
    rules.append(f"C1: evidence score = 1 − Π(1 − wᵢ·qᵢ) over {len(classes)} independent "
                 f"modalit{'y' if len(classes) == 1 else 'ies'} {sorted(classes)} → {conf:.2f}")

    res = _classify_env(obs, ctx, classes, conf, rules) if group == "env" else         _classify_intrusion(obs, ctx, zone, classes, conf, rules)
    res["evidence"] = sorted(evidence.values(), key=lambda e: -e["score"])
    return res


def _classify_intrusion(obs, ctx, zone, classes, conf, rules):

    sensors = sorted({o.sensor_id for o in obs})
    max_vib = max((o.value for o in obs if o.kind == "vibration"), default=0.0)
    unauth_contact = any(o.kind == "contact" and not o.details.get("authorized", False) for o in obs)
    label, share = label_vote(obs)
    fence_wind = max((obs_wind(o, ctx) for o in obs if o.kind == "vibration"), default=ctx.wind_ms())
    snaps = [o.details["access_ctx"] for o in obs if "access_ctx" in o.details]
    authorized = any(snaps) if snaps else ctx.authorized_present(zone)
    breach = max_vib >= BREACH_VIBRATION_G or unauth_contact

    if authorized and not breach:
        rules.append("R1: access control reported authorised personnel/vehicle in zone at observation time and no breach "
                     "indicator (no unauthorised gate opening, fence < "
                     f"{BREACH_VIBRATION_G} g) → normal activity")
        return _result("normal_activity", "info", conf, "Logged — authorised activity",
                       f"Authorised activity in {zone} observed by {', '.join(sensors)}", rules)
    if authorized and breach:
        rules.append("R1b: authorised presence in zone but a breach indicator is present → not masked")

    if label == "animal" and share >= 0.6 and not unauth_contact and max_vib < BREACH_VIBRATION_G:
        rules.append(f"R2: confidence-weighted vote of edge object labels = animal ({share:.0%} of label "
                     "weight ≥ 60 %) and no breach indicator → wildlife disturbance (downgraded)")
        return _result("environmental_disturbance", "low", conf, "Advisory — likely wildlife",
                       f"Probable wildlife activity near {zone} ({', '.join(sensors)})", rules)

    if classes == {"fence"} and fence_wind >= HIGH_WIND_MS and max_vib < BREACH_VIBRATION_G:
        rules.append(f"R3: fence vibration is the only modality, peak {max_vib:.2f} g < breach "
                     f"threshold, wind {fence_wind:.1f} m/s at observation → wind-induced disturbance")
        return _result("environmental_disturbance", "low", conf, "Advisory — review when able",
                       f"Fence vibration in {zone} consistent with wind loading", rules)

    n = len(classes)
    if n == 1:
        only = next(iter(classes))
        if only == "contact" and unauth_contact:
            rules.append("R4: access point opened without a valid credential (single modality)")
            return _result("perimeter_anomaly", "medium", conf, "Requires verification",
                           f"Access point in {zone} opened without credential", rules)
        sev = "low" if only in ("pir", "microwave") else "medium"
        rules.append(f"R5: single modality ({only}) with no corroboration and no authorisation "
                     f"→ unverified movement, severity {sev}")
        return _result("unverified_movement", sev, conf, "Requires verification",
                       f"Uncorroborated {only} detection in {zone}", rules)

    perim = classes & PERIMETER_CLASSES
    if perim:
        sev = "critical" if (n >= 3 and conf >= 0.8) or (breach and n >= 3) else "high"
        rules.append(f"R6: {n} independent modalities including perimeter sensor(s) {sorted(perim)}"
                     f"{'; breach indicator present' if breach else ''} → potential perimeter "
                     f"anomaly, severity {sev}")
        return _result("perimeter_anomaly", sev, conf, "Requires verification",
                       f"Correlated perimeter activity in {zone}: {', '.join(sensors)}", rules)

    sev = "high" if n >= 3 else "medium"
    rules.append(f"R7: {n} interior modalities corroborate movement without authorisation "
                 f"→ unverified movement, severity {sev}")
    return _result("unverified_movement", sev, conf, "Requires verification",
                   f"Corroborated unexplained movement in {zone}: {', '.join(sensors)}", rules)


def _classify_env(obs, ctx, classes, conf, rules):
    zone = obs[0].zone
    sensors = sorted({o.sensor_id for o in obs})
    smoke = max((o.value for o in obs if o.kind == "smoke"), default=0.0)
    temp = max((o.value for o in obs if o.kind == "temperature"), default=0.0)
    if "leak" in classes:
        sev = "high" if ctx.environment == "fuel_depot" else "medium"
        rules.append(f"E1: leak detection cable/probe wet → environmental anomaly, severity {sev}"
                     f"{' (fuel facility)' if sev == 'high' else ''}")
        return _result("environmental_disturbance", sev, conf, "Requires verification",
                       f"Liquid detected by {', '.join(sensors)} in {zone}", rules)
    if {"smoke", "temperature"} <= classes:
        sev = "critical" if smoke >= 8.0 and temp >= 60.0 else "high"
        rules.append(f"E2: smoke ({smoke:.1f} %obs/m) and temperature ({temp:.1f} °C) corroborate "
                     f"→ possible fire, severity {sev}")
        return _result("environmental_disturbance", sev, conf, "Requires verification",
                       f"Corroborated smoke and heat in {zone}", rules)
    if "smoke" in classes:
        rules.append("E3: single smoke detector without temperature rise → medium; dust/steam can "
                     "cause nuisance alarms")
        return _result("environmental_disturbance", "medium", conf, "Requires verification",
                       f"Smoke detected by {', '.join(sensors)} in {zone}", rules)
    rules.append("E4: temperature excursion only → low")
    return _result("environmental_disturbance", "low", conf, "Advisory — review when able",
                   f"Temperature excursion at {', '.join(sensors)} in {zone}", rules)


def _result(category, severity, conf, label, description, rules):
    return {"category": category, "severity": severity, "confidence": conf,
            "classification": label, "description": description, "rules": rules}


class FusionEngine:
    def __init__(self, ctx: FusionContext, next_id: Callable[[], str],
                 window_s: float = 6.0, heartbeat_timeout_s: float = 7.0,
                 log: Callable[[str, str, str], None] | None = None):
        self.ctx = ctx
        self.next_id = next_id
        self.window_s = window_s
        self.heartbeat_timeout_s = heartbeat_timeout_s
        self.log = log or (lambda level, src, msg: None)
        self.buckets: dict[tuple[str, str], Bucket] = {}
        self.offsets: dict[str, float] = {}          # node → estimated clock offset (s)
        self.last_heartbeat: dict[str, float] = {}
        self.comm_down: dict[str, Event] = {}
        self.open_system: dict[tuple[str, str], Event] = {}
        self.recent: dict[tuple[str, str], tuple[Event, float]] = {}
        self.last_normal: dict[str, float] = {}
        self.pending_out: list[tuple[str, Event]] = []
        self.stats = {"received": 0, "validated": 0, "rejected": 0, "late": 0,
                      "correlated_sets": 0, "events": 0, "merged": 0, "suppressed_normal": 0}

    # ------------------------------------------------------------------ ingest
    def ingest(self, o: Observation, at: float | None = None) -> None:
        t = at or now()
        o.ingest_ts = t
        self.stats["received"] += 1

        if o.kind == "heartbeat":
            self._heartbeat(o, t)
            return

        # V1 time sync: correct the edge clock with the node's estimated offset.
        off = self.offsets.get(o.node_id, 0.0)
        o.corrected_ts = o.sensor_ts - off
        if abs(off) > 0.0005:
            o.flags.append(f"clock_corrected:{off * 1000:+.0f}ms")

        reason = self._validate(o, t)
        if reason:
            o.flags.append(f"rejected:{reason}")
            self.stats["rejected"] += 1
            self.log("warn", "fusion", f"Observation {o.obs_id} from {o.sensor_id} rejected ({reason})")
            return
        self.stats["validated"] += 1
        if t - o.corrected_ts > LATE_S:
            o.flags.append("late_delivery")
            self.stats["late"] += 1

        if o.kind in ("fault", "power"):
            self._emit_system(o, t)
            return

        # Snapshot access-control context at observation time (people move on
        # before the correlation window closes).
        o.details.setdefault("access_ctx", bool(self.ctx.authorized_present(o.zone)))
        group = "env" if o.kind in ENV_KINDS else "intrusion"
        key = (o.zone, group)
        b = self.buckets.get(key)
        if b is None:
            b = self.buckets[key] = Bucket(o.zone, group, t)
        b.obs.append(o)

    def _validate(self, o: Observation, t: float) -> str | None:
        meta = self.ctx.sensor(o.sensor_id)
        if meta is None:
            return "unknown_sensor"
        if o.kind in ("fault", "power"):
            return None
        if not self.ctx.sensor_healthy(o.sensor_id):
            return "sensor_faulted"
        lo, hi = PLAUSIBLE.get(o.kind, (float("-inf"), float("inf")))
        if not (lo <= o.value <= hi):
            return f"out_of_range({o.value})"
        if o.corrected_ts - t > MAX_FUTURE_S:
            return "future_timestamp"
        if not (0.0 <= o.quality <= 1.0):
            return "bad_quality_field"
        return None

    def _heartbeat(self, o: Observation, t: float) -> None:
        # NTP-style estimate: node clock minus (arrival − one-way link delay).
        est = o.sensor_ts - (t - o.network_ms / 1000.0)
        prev = self.offsets.get(o.node_id)
        self.offsets[o.node_id] = est if prev is None else prev * 0.8 + est * 0.2
        self.last_heartbeat[o.node_id] = t
        ev = self.comm_down.pop(o.node_id, None)
        if ev is not None:
            ev.add_stage("updated", t, "system", f"Heartbeat from {o.node_id} restored "
                         f"({o.details.get('buffered', 0)} buffered observations to flush)")
            self.pending_out.append(("update", ev))
            self.log("info", "network", f"Link to {o.node_id} restored")

    # -------------------------------------------------------------------- step
    def step(self, at: float | None = None, force: bool = False) -> list[tuple[str, Event]]:
        """Finalise correlation windows and heartbeat checks. Returns
        ``[("new"|"update", Event), ...]``."""
        t = at or now()
        out, self.pending_out = self.pending_out, []

        for node, last in list(self.last_heartbeat.items()):
            if node not in self.comm_down and t - last > self.heartbeat_timeout_s:
                ev = self._system_event(
                    t, node, "edge_node", self._node_zone(node), "communication_failure", "high",
                    0.9, f"No heartbeat from edge node {node} for {t - last:.1f} s "
                         f"(timeout {self.heartbeat_timeout_s:.0f} s); sensors behind it are not reporting",
                    [f"H1: heartbeat age {t - last:.1f} s > timeout {self.heartbeat_timeout_s:.0f} s "
                     "→ communication failure"], [])
                self.comm_down[node] = ev
                out.append(("new", ev))

        for key, b in list(self.buckets.items()):
            classes = {MODALITY.get(o.sensor_type) for o in b.obs}
            age = t - b.opened_wall
            early = len(classes) >= 3
            if force or age >= self.window_s or early:
                del self.buckets[key]
                res = self._finalize(b, t, early and age < self.window_s)
                if res:
                    out.append(res)
        return out

    def _finalize(self, b: Bucket, t: float, early: bool) -> tuple[str, Event] | None:
        self.stats["correlated_sets"] += 1
        t0 = time.perf_counter()
        key = (b.zone, b.group)
        recent = self.recent.get(key)
        if recent:
            ev, last = recent
            if t - last <= MERGE_WINDOW_S and ev.resolution_status in ("open", "response_initiated") \
                    and ev.category != "normal_activity":
                return self._merge(ev, b, t, t0)

        obs = sorted(b.obs, key=lambda o: o.corrected_ts)
        res = classify(obs, self.ctx, b.zone, b.group)
        rules = self._pipeline_rules(obs, b, early) + res["rules"]
        if res["category"] == "normal_activity":
            if t - self.last_normal.get(b.zone, -1e9) < NORMAL_RATE_LIMIT_S:
                self.stats["suppressed_normal"] += 1
                return None
            self.last_normal[b.zone] = t
        fusion_ms = (time.perf_counter() - t0) * 1000
        ev = self._build_event(obs, res, rules, t, fusion_ms)
        if ev.category != "normal_activity":
            self.recent[key] = (ev, t)
        return ("new", ev)

    def _merge(self, ev: Event, b: Bucket, t: float, t0: float) -> tuple[str, Event]:
        self.stats["merged"] += 1
        known = {(c["sensor_id"], c["obs_id"]) for c in ev.contributing}
        new = [o for o in b.obs if (o.sensor_id, o.obs_id) not in known]
        ev.contributing += [o.to_dict() for o in new]
        all_obs = [_obs_from_dict(c) for c in ev.contributing]
        res = classify(all_obs, self.ctx, b.zone, b.group)
        note = f"{len(new)} follow-up observation(s) merged from {', '.join(sorted({o.sensor_id for o in new}))}"
        if SEVERITY_RANK[res["severity"]] > SEVERITY_RANK[ev.severity]:
            note += f"; escalated {ev.severity} → {res['severity']} ({CATEGORIES[res['category']]})"
            ev.severity, ev.category = res["severity"], res["category"]
            ev.description, ev.classification = res["description"], res["classification"]
            ev.rules = ev.rules + [f"M1: merged update re-evaluated → {r}" for r in res["rules"][-1:]]
        ev.confidence = max(ev.confidence, res["confidence"])
        ev.evidence = res.get("evidence", ev.evidence)
        ev.add_stage("updated", t, "system", note)
        self.recent[(b.zone, b.group)] = (ev, t)
        return ("update", ev)

    def _pipeline_rules(self, obs: list[Observation], b: Bucket, early: bool) -> list[str]:
        corr = [abs(o.sensor_ts - o.corrected_ts) * 1000 for o in obs]
        late = sum(1 for o in obs if "late_delivery" in o.flags)
        span = (obs[-1].corrected_ts - obs[0].corrected_ts) if obs else 0
        rules = [f"V1: {len(obs)} observation(s) passed validation (known sensor, healthy, "
                 f"plausible range, timestamp not in future)",
                 f"T1: edge clocks corrected, max correction {max(corr, default=0):.0f} ms"
                 + (f"; {late} late (store-and-forward) delivery" if late else ""),
                 f"K1: correlated by zone {b.zone} over {span:.2f} s "
                 + ("(window closed early: ≥3 modalities)" if early else f"(window {self.window_s:.0f} s)")]
        return rules

    def _build_event(self, obs, res, rules, t, fusion_ms) -> Event:
        first = obs[0]
        edge = [o.edge_ms for o in obs]
        net = [o.network_ms for o in obs]
        ev = Event(
            event_id=self.next_id(), created_epoch=t, sim_time=self.ctx.sim_time(),
            environment=self.ctx.environment, sensor_id=first.sensor_id,
            sensor_type=first.sensor_type, zone=first.zone, category=res["category"],
            classification=res["classification"], severity=res["severity"],
            confidence=res["confidence"], description=res["description"],
            contributing=[o.to_dict() for o in obs], rules=rules, evidence=res.get("evidence", []),
            latency={"edge_ms": round(sum(edge) / len(edge), 1),
                     "network_ms": round(max(net), 1),
                     "fusion_ms": round(fusion_ms, 3),
                     "detection_ms": round((t - first.corrected_ts) * 1000, 1)})
        self._stamp_pipeline(ev, obs, t)
        return ev

    def _stamp_pipeline(self, ev: Event, obs: list[Observation], t: float) -> None:
        first = obs[0] if obs else None
        if first:
            ev.add_stage("detected", first.corrected_ts, first.sensor_id,
                         f"First observation ({first.kind} {first.value:g} {first.unit})")
            ev.add_stage("processed", max(o.ingest_ts for o in obs), "fusion",
                         f"{len(obs)} observation(s) validated and time-aligned")
        ev.add_stage("classified", t, "fusion", f"{CATEGORIES[ev.category]} · {ev.severity} · "
                                                f"evidence {ev.confidence:.2f}")
        ev.alert_epoch = t
        self.stats["events"] += 1
        if ev.category == "normal_activity":
            ev.verification_status = "not_required"
            ev.acknowledgement_status = "not_required"
            ev.resolution_status = "closed"
            ev.closed_epoch = t
            ev.add_stage("closed", t, "system", "Authorised activity — logged, no alert raised")
        else:
            ev.add_stage("alerted", t, "system", "Alert raised on command dashboard; awaiting operator")

    def _emit_system(self, o: Observation, t: float) -> None:
        key = (o.kind, o.sensor_id)
        if o.details.get("restore"):
            ev = self.open_system.pop(key, None)
            if ev is not None:
                ev.add_stage("updated", t, "system", o.details.get("message", "Condition cleared"))
                self.pending_out.append(("update", ev))
            return
        if o.kind == "fault":
            ev = self._system_event(
                t, o.sensor_id, o.sensor_type, o.zone, "equipment_malfunction",
                o.details.get("severity", "medium"), o.quality, o.details.get("message", "Device fault"),
                [f"F1: device self-test / health report: {o.details.get('fault', 'fault')} → equipment malfunction"],
                [o])
        else:
            ev = self._system_event(
                t, o.sensor_id, "power", o.zone, "equipment_malfunction",
                o.details.get("severity", "high"), o.quality, o.details.get("message", "Power event"),
                [f"P1: power monitor reports {o.details.get('state', '?')} → equipment malfunction (power)"],
                [o])
        self.open_system[key] = ev
        self.pending_out.append(("new", ev))

    def _system_event(self, t, sensor_id, sensor_type, zone, category, severity, conf,
                      description, rules, obs) -> Event:
        ev = Event(event_id=self.next_id(), created_epoch=t, sim_time=self.ctx.sim_time(),
                   environment=self.ctx.environment, sensor_id=sensor_id, sensor_type=sensor_type,
                   zone=zone, category=category, classification="Requires verification",
                   severity=severity, confidence=round(conf, 3), description=description,
                   contributing=[o.to_dict() for o in obs], rules=rules,
                   latency={"edge_ms": obs[0].edge_ms if obs else 0.0,
                            "network_ms": obs[0].network_ms if obs else 0.0, "fusion_ms": 0.0,
                            "detection_ms": round((t - obs[0].corrected_ts) * 1000, 1) if obs
                            else round(self.heartbeat_timeout_s * 1000, 1)})
        if obs:
            self._stamp_pipeline(ev, obs, t)
        else:
            ev.add_stage("detected", t - self.heartbeat_timeout_s, "fusion", "Last heartbeat received")
            ev.add_stage("processed", t, "fusion", "Heartbeat watchdog expired")
            self._stamp_pipeline(ev, [], t)
        return ev

    def _node_zone(self, node: str) -> str:
        for s in (self.ctx.sensor(node),):
            if s:
                return s.get("zone", "-")
        return "-"

    def reset(self) -> None:
        self.__init__(self.ctx, self.next_id, self.window_s, self.heartbeat_timeout_s, self.log)


def _obs_from_dict(d: dict[str, Any]) -> Observation:
    keys = Observation.__dataclass_fields__.keys()
    return Observation(**{k: d[k] for k in keys if k in d})
