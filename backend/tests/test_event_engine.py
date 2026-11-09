"""Core event-engine tests: classification rules, fusion pipeline, lifecycle
state machine, persistence and ID sequencing."""
from __future__ import annotations

import pytest

from database.store import EventStore
from event_engine import lifecycle
from event_engine.fusion import FusionEngine, classify, noisy_or
from event_engine.lifecycle import TransitionError
from event_engine.models import Event, Observation, utc_iso


class Ctx:
    environment = "airport"

    def __init__(self, authorized=False, wind=2.0, light=1.0, healthy=True):
        self._auth, self._wind, self._light, self._healthy = authorized, wind, light, healthy

    def sensor(self, sid):
        return {"id": sid, "zone": "A"} if not sid.startswith("UNKNOWN") else None

    def sensor_healthy(self, sid):
        return self._healthy

    def authorized_present(self, zone):
        return self._auth

    def wind_ms(self):
        return self._wind

    def light(self):
        return self._light

    def sim_time(self):
        return 12.5


def obs(sensor_type, kind, value=1.0, t=1000.0, q=0.9, zone="A", node="EN-N", **details):
    return Observation(obs_id=f"O-{sensor_type}-{t}", sensor_id=f"{sensor_type[:3].upper()}-01",
                       sensor_type=sensor_type, node_id=node, zone=zone, kind=kind, value=value, unit="",
                       quality=q, sensor_ts=t, edge_ts=t, sim_time=0.0, details=details)


# ------------------------------------------------------------------ classify
def test_noisy_or_bounds():
    assert noisy_or([]) == 0.0
    assert noisy_or([0.5, 0.5]) == pytest.approx(0.75)
    assert 0 <= noisy_or([1.2, -1]) <= 1


def test_authorised_presence_is_normal_activity():
    r = classify([obs("optical", "motion", object_class="person", class_conf=0.9)], Ctx(authorized=True), "A", "intrusion")
    assert r["category"] == "normal_activity" and r["severity"] == "info"


def test_authorisation_does_not_mask_breach():
    o = [obs("fence", "vibration", 1.5), obs("thermal", "heat", 9.0), obs("optical", "motion", object_class="person")]
    r = classify(o, Ctx(authorized=True), "A", "intrusion")
    assert r["category"] == "perimeter_anomaly"
    assert any(x.startswith("R1b") for x in r["rules"])


def test_single_modality_is_only_unverified_movement():
    r = classify([obs("thermal", "heat", 9.0)], Ctx(), "A", "intrusion")
    assert r["category"] == "unverified_movement" and r["severity"] == "medium"
    r = classify([obs("pir", "motion")], Ctx(), "A", "intrusion")
    assert r["severity"] == "low"


def test_multi_modal_perimeter_escalates():
    o = [obs("fence", "vibration", 1.6, q=0.85), obs("thermal", "heat", 9.0),
         obs("optical", "motion", object_class="person", class_conf=0.9)]
    r = classify(o, Ctx(), "A", "intrusion")
    assert r["category"] == "perimeter_anomaly" and r["severity"] == "critical"
    two = classify(o[:2], Ctx(), "A", "intrusion")
    assert two["severity"] == "high"


def test_wind_only_fence_is_environmental():
    r = classify([obs("fence", "vibration", 0.45, q=0.6, wind_ms=13.0)], Ctx(wind=3.0), "A", "intrusion")
    assert r["category"] == "environmental_disturbance" and r["severity"] == "low"


def test_wildlife_vote_tolerates_one_mislabel():
    o = [obs("thermal", "heat", 4.5, object_class="animal", class_conf=0.9),
         obs("optical", "motion", object_class="animal", class_conf=0.85),
         obs("lowlight", "motion", object_class="person", class_conf=0.45),
         obs("fence", "vibration", 0.4)]
    r = classify(o, Ctx(), "B", "intrusion")
    assert r["category"] == "environmental_disturbance"


def test_confidence_is_not_probability_label():
    r = classify([obs("thermal", "heat", 9.0), obs("fence", "vibration", 1.2)], Ctx(), "A", "intrusion")
    assert "evidence score" in r["rules"][0]


def test_env_fire_corroboration():
    o = [Observation("o1", "SMK-01", "smoke", "EN-ENV", "E", "smoke", 9.0, "%", 0.9, 1000, 1000, 0),
         Observation("o2", "TMP-01", "temperature", "EN-ENV", "E", "temperature", 70.0, "C", 0.9, 1001, 1001, 0)]
    r = classify(o, Ctx(), "E", "env")
    assert r["category"] == "environmental_disturbance" and r["severity"] == "critical"


# -------------------------------------------------------------------- fusion
def make_fusion(ctx=None):
    store = EventStore(":memory:")
    return FusionEngine(ctx or Ctx(), store.next_event_id, window_s=6.0, heartbeat_timeout_s=7.0), store


def test_validation_rejects_bad_observations():
    f, _ = make_fusion()
    f.ingest(obs("fence", "vibration", 99.0, t=1000), at=1000.1)       # out of range
    f.ingest(obs("thermal", "heat", 5.0, t=1010), at=1000.1)           # future timestamp
    bad = obs("thermal", "heat", 5.0, t=1000); bad.sensor_id = "UNKNOWN-1"
    f.ingest(bad, at=1000.1)
    assert f.stats["rejected"] == 3 and not f.buckets


def test_faulted_sensor_data_excluded():
    f, _ = make_fusion(Ctx(healthy=False))
    f.ingest(obs("thermal", "heat", 9.0), at=1000.1)
    assert f.stats["rejected"] == 1


def test_clock_offset_corrected_from_heartbeat():
    f, _ = make_fusion()
    hb = Observation("hb", "EN-N", "edge_node", "EN-N", "A", "heartbeat", 1, "", 1, sensor_ts=1000.5,
                     edge_ts=1000.0, sim_time=0, network_ms=2.0)
    f.ingest(hb, at=1000.002)
    assert f.offsets["EN-N"] == pytest.approx(0.5, abs=0.01)
    o = obs("thermal", "heat", 9.0, t=1001.5)
    f.ingest(o, at=1001.01)
    assert o.corrected_ts == pytest.approx(1001.0, abs=0.01)
    assert any(fl.startswith("clock_corrected") for fl in o.flags)


def test_correlation_window_produces_one_event():
    f, store = make_fusion()
    f.ingest(obs("fence", "vibration", 1.5, t=1000.0), at=1000.05)
    f.ingest(obs("thermal", "heat", 9.0, t=1001.0), at=1001.05)
    assert f.step(at=1002) == []                      # window still open
    out = f.step(at=1006.1)
    assert len(out) == 1 and out[0][0] == "new"
    ev = out[0][1]
    assert ev.category == "perimeter_anomaly" and len(ev.contributing) == 2
    assert ev.event_id.endswith("-0001")
    stages = [s["stage"] for s in ev.lifecycle]
    assert stages == ["detected", "processed", "classified", "alerted"]
    assert ev.latency["detection_ms"] == pytest.approx(6100, abs=5)


def test_early_close_with_three_modalities():
    f, _ = make_fusion()
    for i, (st, k, v) in enumerate([("fence", "vibration", 1.5), ("thermal", "heat", 9.0), ("radar", "radar", 30.0)]):
        f.ingest(obs(st, k, v, t=1000 + i * 0.2), at=1000.1 + i * 0.2)
    out = f.step(at=1000.6)
    assert len(out) == 1


def test_follow_up_merges_into_open_incident():
    f, _ = make_fusion()
    f.ingest(obs("thermal", "heat", 9.0, t=1000), at=1000.05)
    (_, ev), = f.step(at=1006.1)
    assert ev.category == "unverified_movement"
    f.ingest(obs("fence", "vibration", 1.6, t=1010), at=1010.05)
    out = f.step(at=1016.1)
    assert out[0][0] == "update" and out[0][1] is ev
    assert ev.category == "perimeter_anomaly" and ev.lifecycle[-1]["stage"] == "updated"


def test_heartbeat_timeout_raises_comm_failure_and_restore():
    f, _ = make_fusion()
    hb = lambda t: Observation(f"hb{t}", "EN-W", "edge_node", "EN-W", "D", "heartbeat", 1, "", 1, t, t, 0, network_ms=1)
    f.ingest(hb(1000), at=1000.001)
    assert f.step(at=1005) == []
    out = f.step(at=1007.5)
    assert out[0][1].category == "communication_failure"
    f.ingest(hb(1020), at=1020.001)
    upd = f.step(at=1020.1)
    assert upd[0][0] == "update" and "restored" in upd[0][1].lifecycle[-1]["note"]


def test_normal_activity_auto_closed_and_rate_limited():
    f, _ = make_fusion(Ctx(authorized=True))
    f.ingest(obs("optical", "motion", object_class="person"), at=1000.05)
    (_, ev), = f.step(at=1006.1)
    assert ev.resolution_status == "closed" and ev.acknowledgement_status == "not_required"
    f.ingest(obs("optical", "motion", t=1010, object_class="person"), at=1010.05)
    assert f.step(at=1016.1) == []
    assert f.stats["suppressed_normal"] == 1


# ----------------------------------------------------------------- lifecycle
def alert_event():
    ev = Event("VIPER-2026-0001", 1000.0, 1.0, "airport", "TH-01", "thermal", "A", "perimeter_anomaly",
               "Requires verification", "high", 0.7, "test")
    ev.alert_epoch = 1000.0
    return ev


def test_full_lifecycle_happy_path():
    ev = alert_event()
    lifecycle.acknowledge(ev, "op", at=1010)
    lifecycle.verify(ev, "op", "verified_genuine", at=1020)
    lifecycle.initiate_response(ev, "op", "security_team", authorized=True, at=1030)
    lifecycle.resolve(ev, "op", at=1100)
    lifecycle.close(ev, "op", at=1110)
    assert ev.resolution_status == "closed" and ev.response["authorized_by"] == "op"
    assert [s["stage"] for s in ev.lifecycle] == ["acknowledged", "verified", "response_initiated", "resolved", "closed"]
    assert lifecycle.available_actions(ev) == []


@pytest.mark.parametrize("step", ["verify", "respond", "resolve", "close"])
def test_out_of_order_transitions_rejected(step):
    ev = alert_event()
    with pytest.raises(TransitionError):
        {"verify": lambda: lifecycle.verify(ev, "op", "verified_genuine"),
         "respond": lambda: lifecycle.initiate_response(ev, "op", "security_team", True),
         "resolve": lambda: lifecycle.resolve(ev, "op"),
         "close": lambda: lifecycle.close(ev, "op")}[step]()


def test_response_requires_explicit_authorisation_and_operator():
    ev = alert_event()
    lifecycle.acknowledge(ev, "op")
    lifecycle.verify(ev, "op", "verified_genuine")
    with pytest.raises(TransitionError):
        lifecycle.initiate_response(ev, "op", "security_team", authorized=False)
    with pytest.raises(TransitionError):
        lifecycle.initiate_response(ev, "  ", "security_team", authorized=True)
    with pytest.raises(TransitionError):
        lifecycle.initiate_response(ev, "op", "launch_drone", authorized=True)


def test_false_positive_path():
    ev = alert_event()
    lifecycle.acknowledge(ev, "op")
    lifecycle.mark_false_positive(ev, "op", "cat on fence")
    assert ev.verification_status == "false_positive" and ev.resolution_status == "resolved"
    assert "close" in lifecycle.available_actions(ev)


def test_double_acknowledge_rejected():
    ev = alert_event()
    lifecycle.acknowledge(ev, "op")
    with pytest.raises(TransitionError):
        lifecycle.acknowledge(ev, "op")


# --------------------------------------------------------------- persistence
def test_store_roundtrip_and_ids(tmp_path):
    db = tmp_path / "t.db"
    s = EventStore(db)
    ids = [s.next_event_id() for _ in range(3)]
    assert len(set(ids)) == 3 and ids[0].endswith("0001")
    ev = alert_event(); ev.event_id = ids[0]
    ev.add_stage("alerted", 1000.0)
    s.save(ev)
    lifecycle.acknowledge(ev, "op", at=1001.234)
    s.save(ev)
    s2 = EventStore(db)
    back = s2.get(ids[0])
    assert back.acknowledgement_status == "acknowledged"
    assert [x["stage"] for x in back.lifecycle] == ["alerted", "acknowledged"]
    assert back.lifecycle[1]["ts_utc"] == utc_iso(1001.234) and back.lifecycle[1]["ts_utc"].endswith(".234Z")
    assert s2.next_event_id().endswith("0002")
    evs, total = s2.query(severity=["high"], q=ids[0][-4:])
    assert total == 1


def test_timestamp_format_millisecond_utc():
    assert utc_iso(0.5) == "1970-01-01T00:00:00.500Z"
