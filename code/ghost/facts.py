"""Fact / Observation dataclasses and baseline state derivation (DESIGN §4.1, §6).

Rules: D3 / H-TIM-02 (knowledge time = record-level `fact_time`, citability = file `captured_at`),
H-TIM-03 (inclusive cut-off), H-STA-02 (claims never set state), G-EVD-01 (snapshot scope for absence proofs).
M2 provides the raw signals and a baseline `derive_states`; policy-aware exposure (prohibited fields per
category) is decided in M4 from `Fact.ident_fields`.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Observation states (DESIGN §6).
ABSENT, PRESENT = "ABSENT", "PRESENT"
IDENTIFIABLE, ANONYMIZED, REDACTED = "IDENTIFIABLE", "ANONYMIZED", "REDACTED"
FLOW_ACTIVE, FLOW_DISABLED = "FLOW_ACTIVE", "FLOW_DISABLED"
RESTORABLE, RESTORE_BLOCKED = "RESTORABLE", "RESTORE_BLOCKED"
RETAINED = "RETAINED"


@dataclass(eq=False)
class Fact:
    """One evidence record after normalisation."""

    fact_id: str  # file_id#locator
    file_id: str
    file_captured_at: datetime  # decides citability (<= audit_at)
    fact_time: datetime  # record-level time; decides knowledge (<= audit_at)
    fmt: str  # json | sql | log | txt | pdf | png
    locator: str
    system_id: str | None = None
    resource_id: str | None = None
    category: str | None = None
    topology: str = "primary"  # primary | replica:<kind>
    collection: str | None = None
    capture_time: datetime | None = None  # snapshot capture time (header / scope), when known
    mentions: tuple[tuple[str, str, str], ...] = ()  # validated (user_id, kind, token) links (H-IDN-04)
    decoys: tuple[tuple[str, str, str], ...] = ()  # rejected (kind, token, outcome)
    signals: dict[str, Any] = field(default_factory=dict)  # canonical state signals
    ident_fields: dict[str, bool] = field(default_factory=dict)  # identifier field -> non-null?
    fields: dict[str, Any] = field(default_factory=dict)  # flattened raw record
    line_span: tuple[int, int] | None = None  # source lines (logs, txt)
    text_mentions: frozenset[str] = frozenset()  # users whose validated identifiers occur in free-text fields

    def citable(self, audit_at: datetime) -> bool:
        return self.file_captured_at <= audit_at  # S-TIM-01, H-TIM-03

    def known(self, audit_at: datetime) -> bool:
        return self.fact_time <= audit_at  # D3

    def users(self) -> frozenset[str]:
        return frozenset(u for u, _, _ in self.mentions)


@dataclass(frozen=True)
class Observation:
    fact: Fact
    state: str


@dataclass(frozen=True)
class SnapshotScope:
    """A capture that covers a system on a topology at a time: proof of absence (G-EVD-01)."""

    file_id: str
    system_id: str
    topology: str
    captured_at: datetime


class FactStore:
    def __init__(self) -> None:
        self.facts: list[Fact] = []
        self.scopes: list[SnapshotScope] = []
        self.unparsed: list[tuple[str, str, str]] = []  # (file_id, path, reason)
        self.decoys: list[tuple[str, str, str, str]] = []  # (fact_id, kind, token, outcome)
        self.dropped_noise = 0
        self.parser_report: list[dict] = []  # per log file self-check (share of carrying lines with a trace id)
        self._by_resource: dict[str, list[Fact]] = defaultdict(list)
        self._by_user: dict[str, list[Fact]] = defaultdict(list)
        self._by_file: dict[str, list[Fact]] = defaultdict(list)

    def add(self, f: Fact) -> None:
        self.facts.append(f)
        if f.resource_id:
            self._by_resource[f.resource_id].append(f)
        for u in f.users():
            self._by_user[u].append(f)
        self._by_file[f.file_id].append(f)

    def for_resource(self, resource_id: str) -> list[Fact]:
        return self._by_resource.get(resource_id, [])

    def for_user(self, user_id: str) -> list[Fact]:
        return self._by_user.get(user_id, [])

    def for_file(self, file_id: str) -> list[Fact]:
        return self._by_file.get(file_id, [])

    def resources(self) -> set[str]:
        return set(self._by_resource)


def _truthy(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes", "y"):
        return True
    if s in ("false", "0", "no", "n"):
        return False
    return None


def derive_states(f: Fact) -> set[str]:
    """Baseline observation states from signals (DESIGN §6). Activity `reported_result` is never used (H-STA-02)."""
    s = f.signals
    out: set[str] = set()
    http, rows, res = s.get("http_status"), s.get("rows"), (s.get("result") or "").upper()
    label = (s.get("state_label") or "").upper()
    if http == 404 or rows == 0 or res in ("NOT_FOUND", "MISS_ABSENT") or label == "NOT_FOUND":
        out.add(ABSENT)
    elif http == 200 or (isinstance(rows, int) and rows >= 1) or res in ("FOUND", "HIT") or label == "FOUND" \
            or str(s.get("account_status") or "").upper() in ("ACTIVE", "DELETION_PENDING"):
        out.add(PRESENT)
    elif label in ("IDENTIFIABLE",):
        out.add(PRESENT)
    if label == "IDENTIFIABLE":
        out.add(IDENTIFIABLE)
    if label == "ANONYMIZED":
        out.add(ANONYMIZED)
    if label == "REDACTED":
        out.add(REDACTED)
    enabled = _truthy(s.get("enabled"))
    if enabled is True or label == "ACTIVE" and f.category == "DATA_FLOW" or s.get("scheduler_registered") is True:
        out.add(FLOW_ACTIVE)
    if enabled is False or label == "DISABLED":
        out.add(FLOW_DISABLED)
    ra, el, blk = _truthy(s.get("restore_allowed")), _truthy(s.get("eligible")), _truthy(s.get("deletion_block"))
    if ra is True or (el is True and blk is False) or (label == "ACTIVE" and f.category == "BACKUP_ARCHIVE"):
        out.add(RESTORABLE)
    if ra is False or blk is True or label == "BLOCKED":
        out.add(RESTORE_BLOCKED)
    if s.get("retention_until") or s.get("retained_until"):
        out.add(RETAINED)
    return out
