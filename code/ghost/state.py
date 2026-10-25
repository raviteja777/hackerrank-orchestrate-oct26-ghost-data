"""State of each case resource at audit_at (DESIGN §6).

A fact is classified into a condition for its category kind (see `CategorySpec`), then the latest
observations in the window [run anchor, audit_at] decide the state. Activity `reported_result` is never an
input (H-STA-02). Knowledge uses the record-level time (D3, H-TIM-02); a copy that is still bad at or after
the latest good observation wins (replica drift, G-SYS-01).
Rules: H-STA-02, H-TIM-02, H-TIM-03, G-EVD-01 (scope proof of absence), G-STP-08 (observation to emit),
review items 1-4 (direct_identifiers, decision=deny, PII scan events and free text, marker_found).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from .facts import Fact, FactStore, SnapshotScope

ABSENT, PRESENT, EXPOSED, CLEAN = "ABSENT", "PRESENT", "EXPOSED", "CLEAN"
FLOW_ACTIVE, FLOW_DISABLED = "FLOW_ACTIVE", "FLOW_DISABLED"
RESTORABLE, RESTORE_BLOCKED = "RESTORABLE", "RESTORE_BLOCKED"
UNKNOWN = "UNKNOWN"

KIND_RECORD, KIND_SENSITIVE, KIND_RETAIN, KIND_BACKUP, KIND_FLOW = "record", "sensitive", "retain", "backup", "flow"


@dataclass(frozen=True)
class CategorySpec:
    category: str
    kind: str
    prohibited: frozenset[str] = frozenset()  # identifier columns that must be null (REDACT / ANONYMIZE)


# which conditions violate the required state, per category kind (DESIGN §7.2)
BAD = {
    KIND_RECORD: {PRESENT, EXPOSED},
    KIND_SENSITIVE: {EXPOSED},
    KIND_RETAIN: set(),  # retained records produce no finding (H-STP-06, OQ-3)
    KIND_BACKUP: {RESTORABLE},
    KIND_FLOW: {FLOW_ACTIVE},
}
GOOD = {
    KIND_RECORD: {ABSENT},
    KIND_SENSITIVE: {CLEAN, ABSENT},
    KIND_RETAIN: {PRESENT},
    KIND_BACKUP: {RESTORE_BLOCKED},
    KIND_FLOW: {FLOW_DISABLED},
}


def _b(v) -> bool | None:
    if isinstance(v, bool):
        return v
    return None


def effective_time(f: Fact, audit_at: datetime) -> datetime:
    """When the state was observed: a SQL snapshot row is observed at the capture time (its updated_at is only
    the last write); everything else at its record-level time."""
    if f.fmt == "sql" and f.capture_time is not None and f.capture_time <= audit_at:
        return max(f.capture_time, f.fact_time)
    return f.fact_time


def classify(f: Fact, spec: CategorySpec, subject_user: str | None = None) -> str | None:
    """Condition shown by one fact for a category kind, or None when the fact says nothing about it."""
    s = f.signals
    http, rows = s.get("http_status"), s.get("rows")
    res = str(s.get("result") or "").upper()
    label = str(s.get("state_label") or "").upper()
    absent = http == 404 or rows == 0 or res == "NOT_FOUND" or label == "NOT_FOUND" or s.get("profile_null") \
        or s.get("available") is False
    exists = (isinstance(http, int) and http == 200) or (isinstance(rows, int) and rows >= 1) or res in ("FOUND", "HIT") \
        or label in ("FOUND", "IDENTIFIABLE") or s.get("available") is True \
        or str(s.get("account_status") or "").upper() in ("ACTIVE", "DELETION_PENDING", "DELETED")
    # a stored row/object exists; a document naming the resource id (PDF attachment, register) shows it exists too
    data_record = (f.fmt in ("sql", "json") or (f.fmt == "pdf" and spec.kind in (KIND_RECORD, KIND_RETAIN))) and not absent
    kind = spec.kind

    if kind == KIND_FLOW:
        if s.get("enabled") is True or s.get("scheduler_registered") is True or label == "ACTIVE":
            return FLOW_ACTIVE
        if s.get("enabled") is False or label == "DISABLED" or str(s.get("last_delivery_status") or "").lower() == "stopped":
            return FLOW_DISABLED
        return None
    if kind == KIND_BACKUP:
        if s.get("decision") == "deny" or s.get("restore_allowed") is False or s.get("deletion_block") is True \
                or s.get("eligible") is False or label == "BLOCKED":
            return RESTORE_BLOCKED
        if s.get("restore_allowed") is True or (s.get("eligible") is True and s.get("deletion_block") is False) \
                or s.get("decision") == "allow" or label == "ACTIVE":
            return RESTORABLE
        return None
    if kind == KIND_RECORD and s.get("marker_found") is not None:
        # legacy replica copy (review item 4): marker_found=false means the deletion never reached this copy
        return ABSENT if s["marker_found"] else PRESENT
    if absent:
        return ABSENT
    if kind == KIND_SENSITIVE:
        if label == "IDENTIFIABLE" or s.get("pii_match") or s.get("direct_identifiers") == 1:
            return EXPOSED
        if label in ("ANONYMIZED", "REDACTED") or s.get("direct_identifiers") == 0:
            return CLEAN
        cols = {c for c, nonnull in f.ident_fields.items() if nonnull}
        if cols & spec.prohibited:
            return EXPOSED
        if f.text_mentions and (subject_user is None or subject_user in f.text_mentions):
            return EXPOSED  # the subject's validated identifier inside free text (review item 3)
        if f.ident_fields or data_record or exists:  # columns present, none prohibited
            return CLEAN
        return None
    # record / retain kinds: presence
    if exists or data_record:
        return PRESENT
    return None


@dataclass
class Observation:
    fact: Fact
    cond: str
    time: datetime


@dataclass
class Assessment:
    """State of one resource at audit_at."""

    resource_id: str
    state: str  # a condition (ABSENT, PRESENT, EXPOSED, ...) or UNKNOWN
    observed: bool  # an explicit observation exists in the window (G-STP-08)
    deciding: Observation | None = None  # latest observation that decides the state
    bad: list[Observation] = field(default_factory=list)  # all observations showing a violating state
    good: list[Observation] = field(default_factory=list)  # all observations proving a compliant state
    scope_proofs: list[SnapshotScope] = field(default_factory=list)  # snapshots proving absence (G-EVD-01)
    notes: list[str] = field(default_factory=list)


def assess(resource_id: str, spec: CategorySpec, store: FactStore, audit_at: datetime, anchor: datetime | None,
           system_id: str | None, is_account: bool = False, subject_user: str | None = None) -> Assessment:
    """Latest evidence wins; a violating copy at or after the latest good observation still violates."""
    obs: list[Observation] = []
    for f in store.for_resource(resource_id):
        if f.fact_time > audit_at:  # D3: knowledge by record time, inclusive
            continue
        t = effective_time(f, audit_at)
        if anchor is not None and t < anchor:  # before the run: history, used for linking only (DESIGN §6)
            continue
        cond = classify(f, spec, subject_user)
        if cond:
            obs.append(Observation(f, cond, t))
    bad_set, good_set = BAD[spec.kind], GOOD[spec.kind]
    bad = [o for o in obs if o.cond in bad_set]
    good = [o for o in obs if o.cond in good_set]
    key = lambda o: (o.time, o.fact.file_captured_at)  # noqa: E731
    # Each copy (topology) is judged on its own: a violating copy is cleared only by a later or equal good
    # observation of the SAME copy, so a primary 404 never hides a replica that still holds the record
    # (drift, G-SYS-01); ties go to the violation.
    live_bad: list[Observation] = []
    for topo in {o.fact.topology for o in bad}:
        latest_good = max([o.time for o in good if o.fact.topology == topo], default=None)
        live_bad += [o for o in bad if o.fact.topology == topo and (latest_good is None or o.time >= latest_good)]
    if live_bad:
        top = max(live_bad, key=key)
        return Assessment(resource_id, top.cond, True, top, bad, good, [])
    if good:
        top = max(good, key=key)
        return Assessment(resource_id, top.cond, True, top, bad, good, [])
    if obs:  # observations exist but are neither good nor live-bad (e.g. retain kind with ABSENT only)
        top = max(obs, key=key)
        return Assessment(resource_id, top.cond, True, top, bad, good, [])
    # Proof of absence by snapshot scope (G-EVD-01) is a last resort for a resource with no explicit observation:
    # a covering snapshot in the window that does not mention it. It never overrides an explicit observation
    # (bundles list only a few records, so a missing record there proves nothing on its own).
    scopes: list[SnapshotScope] = []
    if spec.kind in (KIND_RECORD, KIND_SENSITIVE) and system_id:
        mentioned_in = {f.file_id for f in store.for_resource(resource_id)}
        scopes = [sc for sc in store.scopes
                  if sc.system_id == system_id and sc.captured_at <= audit_at
                  and (anchor is None or sc.captured_at >= anchor) and sc.file_id not in mentioned_in]
    if scopes:
        return Assessment(resource_id, ABSENT, False, None, [], [], scopes, ["absence by snapshot scope only"])
    return Assessment(resource_id, UNKNOWN, False, None, [], [], [])
