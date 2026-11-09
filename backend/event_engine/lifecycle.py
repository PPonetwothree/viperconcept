"""Incident lifecycle state machine.

Every operator action is a validated transition. Invalid transitions raise
``TransitionError`` (mapped to HTTP 409 by the API). No transition triggers any
physical action: response categories are notifications that a named operator
must explicitly authorise.
"""
from __future__ import annotations

from .models import RESPONSE_CATEGORIES, VERIFICATION_OUTCOMES, Event, now


class TransitionError(ValueError):
    pass


def _require_operator(operator: str) -> str:
    op = (operator or "").strip()
    if not op:
        raise TransitionError("An operator name is required for every action.")
    if len(op) > 64:
        raise TransitionError("Operator name too long (max 64 characters).")
    return op


def _require_open(ev: Event) -> None:
    if ev.resolution_status == "closed":
        raise TransitionError(f"{ev.event_id} is closed.")


def acknowledge(ev: Event, operator: str, note: str = "", at: float | None = None) -> Event:
    op = _require_operator(operator)
    _require_open(ev)
    if ev.acknowledgement_status != "unacknowledged":
        raise TransitionError(f"{ev.event_id} is not awaiting acknowledgement "
                              f"(status: {ev.acknowledgement_status}).")
    t = at or now()
    ev.acknowledgement_status = "acknowledged"
    ev.ack_epoch = t
    ev.add_stage("acknowledged", t, op, note or "Alert acknowledged by operator")
    return ev


def verify(ev: Event, operator: str, outcome: str, note: str = "", at: float | None = None) -> Event:
    op = _require_operator(operator)
    _require_open(ev)
    if outcome not in VERIFICATION_OUTCOMES:
        raise TransitionError(f"Unknown verification outcome '{outcome}'.")
    if ev.acknowledgement_status != "acknowledged":
        raise TransitionError("Acknowledge the alert before verifying it.")
    if ev.verification_status != "awaiting_review":
        raise TransitionError(f"{ev.event_id} has already been verified ({ev.verification_status}).")
    t = at or now()
    ev.verification_status = outcome
    ev.verified_epoch = t
    ev.add_stage("verified", t, op, note or VERIFICATION_OUTCOMES[outcome])
    return ev


def initiate_response(ev: Event, operator: str, category: str, authorized: bool,
                      note: str = "", at: float | None = None) -> Event:
    op = _require_operator(operator)
    _require_open(ev)
    if category not in RESPONSE_CATEGORIES:
        raise TransitionError(f"Unknown response category '{category}'.")
    if not authorized:
        raise TransitionError("Response actions require explicit human authorisation.")
    if ev.verification_status != "verified_genuine":
        raise TransitionError("A response can only be initiated for an incident verified as genuine.")
    if ev.resolution_status != "open":
        raise TransitionError(f"Response already recorded ({ev.resolution_status}).")
    t = at or now()
    ev.resolution_status = "response_initiated"
    ev.response_epoch = t
    ev.response = {"category": category, "label": RESPONSE_CATEGORIES[category],
                   "authorized_by": op, "ts_epoch": t, "note": note}
    ev.add_stage("response_initiated", t, op,
                 f"{RESPONSE_CATEGORIES[category]} (authorised by {op})" + (f" — {note}" if note else ""))
    return ev


def resolve(ev: Event, operator: str, note: str = "", at: float | None = None) -> Event:
    op = _require_operator(operator)
    _require_open(ev)
    if ev.resolution_status == "resolved":
        raise TransitionError(f"{ev.event_id} is already resolved.")
    allowed = (ev.resolution_status == "response_initiated"
               or ev.verification_status in ("false_positive", "verified_benign"))
    if not allowed:
        raise TransitionError("Resolve requires either an initiated response or a "
                              "false-positive / benign verification.")
    t = at or now()
    ev.resolution_status = "resolved"
    ev.resolved_epoch = t
    ev.add_stage("resolved", t, op, note or "Incident resolved")
    return ev


def close(ev: Event, operator: str, note: str = "", at: float | None = None) -> Event:
    op = _require_operator(operator)
    if ev.resolution_status != "resolved":
        raise TransitionError("Only resolved incidents can be closed.")
    t = at or now()
    ev.resolution_status = "closed"
    ev.closed_epoch = t
    ev.add_stage("closed", t, op, note or "Incident closed")
    return ev


def mark_false_positive(ev: Event, operator: str, note: str = "", at: float | None = None) -> Event:
    """Convenience: verify as false positive and resolve in one operator action."""
    verify(ev, operator, "false_positive", note, at)
    return resolve(ev, operator, "Resolved as false positive", at)


def available_actions(ev: Event) -> list[str]:
    """Which operator actions are valid now — used by the UI to enable buttons."""
    if ev.resolution_status == "closed":
        return []
    acts: list[str] = []
    if ev.acknowledgement_status == "unacknowledged":
        acts.append("acknowledge")
    if ev.acknowledgement_status == "acknowledged" and ev.verification_status == "awaiting_review":
        acts += ["verify", "false_positive"]
    if ev.verification_status == "verified_genuine" and ev.resolution_status == "open":
        acts.append("respond")
    if ev.resolution_status == "response_initiated" or (
            ev.verification_status in ("false_positive", "verified_benign")
            and ev.resolution_status == "open"):
        acts.append("resolve")
    if ev.resolution_status == "resolved":
        acts.append("close")
    return acts
