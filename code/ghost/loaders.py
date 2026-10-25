"""CSV loading, typed records, UTC time parsing (DESIGN §3, §5 general rules).

Rules: H-ORD-01/D1 (input row order is the output order), H-TIM-03 (inclusive cut-off).
Text files are read with universal newlines because the build machine has CRLF files (§5).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import config


def parse_ts(value: str) -> datetime:
    """ISO-8601 (with Z or offset) -> timezone-aware UTC datetime."""
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def read_text(path: Path) -> str:
    """UTF-8 text with universal newlines (CRLF safe)."""
    with open(path, "r", encoding="utf-8", errors="replace", newline=None) as fh:
        return fh.read()


def _rows(path: Path) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


@dataclass(frozen=True)
class DeletionRequest:
    case_id: str
    email: str
    requested_at: datetime
    reported_status: str
    reported_at: datetime
    audit_at: datetime
    request_text: str


@dataclass(frozen=True)
class UserIdentity:
    user_id: str
    name: str
    email: str
    phone: str
    email_hash: str
    updated_at: datetime


@dataclass(frozen=True)
class AuditEvent:
    audit_id: str
    user_id: str
    event_time: datetime
    field_name: str
    old_value: str
    new_value: str


@dataclass(frozen=True)
class Activity:
    activity_id: str
    event_time: datetime
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str


@dataclass(frozen=True)
class Rule:
    rule_id: str
    data_category: str
    condition: str
    required_action: str


@dataclass(frozen=True)
class EvidenceFile:
    file_id: str
    file_path: str
    origin: str
    captured_at: datetime

    def abs_path(self, dataset_dir: Path | None = None) -> Path:
        return (dataset_dir or config.DATASET_DIR) / self.file_path

    @property
    def suffix(self) -> str:
        return Path(self.file_path).suffix.lower()


def load_requests(dataset_dir: Path | None = None, name: str = "deletion_requests.csv") -> list[DeletionRequest]:
    """Requests in file order (D1: numeric case order, identical to the input order)."""
    d = dataset_dir or config.DATASET_DIR
    return [
        DeletionRequest(
            r["case_id"], r["email"], parse_ts(r["requested_at"]), r["reported_status"],
            parse_ts(r["reported_at"]), parse_ts(r["audit_at"]), r["request_text"],
        )
        for r in _rows(d / name)
    ]


def load_identities(dataset_dir: Path | None = None) -> list[UserIdentity]:
    d = dataset_dir or config.DATASET_DIR
    return [
        UserIdentity(r["user_id"], r["name"], r["email"], r["phone"], r["email_hash"], parse_ts(r["updated_at"]))
        for r in _rows(d / "user_identities.csv")
    ]


def load_audit_log(dataset_dir: Path | None = None) -> list[AuditEvent]:
    d = dataset_dir or config.DATASET_DIR
    return [
        AuditEvent(r["audit_id"], r["user_id"], parse_ts(r["event_time"]), r["field_name"], r["old_value"], r["new_value"])
        for r in _rows(d / "user_audit_log.csv")
    ]


def load_activity(dataset_dir: Path | None = None) -> list[Activity]:
    d = dataset_dir or config.DATASET_DIR
    return [
        Activity(r["activity_id"], parse_ts(r["event_time"]), r["event_type"], r["source_system"],
                 r["target_system"], r["resource_id"], r["reported_result"], r["details"])
        for r in _rows(d / "system_activity.csv")
    ]


def load_rules(dataset_dir: Path | None = None) -> list[Rule]:
    d = dataset_dir or config.DATASET_DIR
    return [Rule(r["rule_id"], r["data_category"], r["condition"], r["required_action"]) for r in _rows(d / "deletion_rules.csv")]


def load_evidence_manifest(dataset_dir: Path | None = None) -> list[EvidenceFile]:
    d = dataset_dir or config.DATASET_DIR
    return [
        EvidenceFile(r["file_id"], r["file_path"], r["origin"], parse_ts(r["captured_at"]))
        for r in _rows(d / "evidence_files.csv")
    ]
