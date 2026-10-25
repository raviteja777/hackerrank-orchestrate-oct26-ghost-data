"""Output contract validator (DESIGN §12). Runs at the end of main.py; non-zero exit on failure.

Rules: S-ORD-01/02/03, S-STP-01, S-STA-01/02/03, S-TIM-01, S-CIT-01, H-STP-04, H-ORD-01.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .loaders import Activity, AuditEvent, DeletionRequest, EvidenceFile
from .steps import ALLOWED_PAIRS, OUTPUT_COLUMNS, PHASE_RANK, STATUSES, STEP_KEYS, sort_key


@dataclass(frozen=True)
class Issue:
    case_id: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.case_id}: {self.message}"


def _evidence_times(
    files: list[EvidenceFile], activity: list[Activity], audit: list[AuditEvent]
) -> dict[str, datetime]:
    """evidence_id (file_id | activity_id | audit_id) -> time that must be <= audit_at (S-CIT-01, S-TIM-01)."""
    times: dict[str, datetime] = {f.file_id: f.captured_at for f in files}
    times.update({a.activity_id: a.event_time for a in activity})
    times.update({a.audit_id: a.event_time for a in audit})
    return times


def validate_steps(case_id: str, status: str, steps: object, audit_at: datetime | None,
                   ev_times: dict[str, datetime]) -> list[Issue]:
    issues: list[Issue] = []

    def bad(code: str, msg: str) -> None:
        issues.append(Issue(case_id, code, msg))

    if status not in STATUSES:
        bad("STATUS", f"invalid deletion_status {status!r}")
    if not isinstance(steps, list):
        bad("JSON", "steps_json is not a JSON array")
        return issues
    if status == "NOT_APPLICABLE" and steps:
        bad("NA_STEPS", "NOT_APPLICABLE must have steps_json = []")  # S-STA-01
    well_formed = True
    for i, s in enumerate(steps, start=1):
        if not isinstance(s, dict) or set(s) != set(STEP_KEYS):
            bad("KEYS", f"step {i} must have exactly the keys {list(STEP_KEYS)}")  # S-STP-01
            well_formed = False
            continue
        if not isinstance(s["step_no"], int) or isinstance(s["step_no"], bool):
            bad("STEP_NO", f"step {i}: step_no is not an integer")
            well_formed = False
        if any(not isinstance(s[k], str) for k in STEP_KEYS if k != "step_no"):
            bad("TYPES", f"step {i}: non-string field")
            well_formed = False
            continue
        if (s["phase"], s["operation"], s["state"]) not in ALLOWED_PAIRS:
            bad("PAIR", f"step {i}: disallowed phase/operation/state {s['phase']}/{s['operation']}/{s['state']}")
            well_formed = False
    if not well_formed:
        return issues

    if [s["step_no"] for s in steps] != list(range(1, len(steps) + 1)):
        bad("STEP_NO", "step_no is not consecutive from 1")  # S-ORD-03
    keys = [sort_key(s) for s in steps]
    if keys != sorted(keys):
        bad("ORDER", "steps are not in (phase, operation, system_id, resource_id) order")  # S-ORD-02
    phases = [PHASE_RANK[s["phase"]] for s in steps]
    if phases != sorted(phases):
        bad("PHASE_ORDER", "phases are not FINDING -> REMEDIATION -> VERIFICATION")

    by_phase = defaultdict(list)
    for s in steps:
        by_phase[s["phase"]].append(s)
    if status == "COMPLETE":
        if by_phase["FINDING"] or by_phase["REMEDIATION"]:
            bad("COMPLETE_PHASES", "COMPLETE must contain only VERIFICATION steps")  # S-STA-02
        if any(not s["evidence_id"] for s in steps):
            bad("COMPLETE_EVIDENCE", "COMPLETE verification steps must cite evidence")
    if status == "INCOMPLETE":
        if not by_phase["FINDING"]:
            bad("INCOMPLETE_NO_FINDING", "INCOMPLETE needs at least one finding")
        if any(not s["evidence_id"] for s in by_phase["FINDING"]):
            bad("FINDING_EVIDENCE", "findings must cite evidence")
        if any(s["evidence_id"] for s in by_phase["REMEDIATION"] + by_phase["VERIFICATION"]):
            bad("FUTURE_EVIDENCE", "remediation and verification steps must have evidence_id = ''")  # S-STA-03, H-STP-04

    # H-STP-04: every resource in the case has exactly one verification step.
    resources = {(s["system_id"], s["resource_id"]) for s in steps}
    verifs = defaultdict(int)
    for s in by_phase["VERIFICATION"]:
        verifs[(s["system_id"], s["resource_id"])] += 1
    for r in sorted(resources):
        if verifs[r] != 1:
            bad("VERIFY_COUNT", f"{r[0]}/{r[1]} has {verifs[r]} verification steps (expected exactly 1)")

    # S-TIM-01 / S-CIT-01: every cited id exists and is not later than audit_at (inclusive, H-TIM-03).
    for s in steps:
        eid = s["evidence_id"]
        if not eid:
            continue
        if eid not in ev_times:
            bad("CITE_UNKNOWN", f"step {s['step_no']}: evidence_id {eid!r} is not a known file/activity/audit id")
        elif audit_at is not None and ev_times[eid] > audit_at:
            bad("CITE_LATE", f"step {s['step_no']}: {eid} is dated after audit_at")
    return issues


def validate_output(path: Path, requests: list[DeletionRequest], files: list[EvidenceFile],
                    activity: list[Activity], audit: list[AuditEvent]) -> list[Issue]:
    issues: list[Issue] = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    if not rows or tuple(rows[0]) != OUTPUT_COLUMNS:
        return [Issue("-", "HEADER", f"header must be exactly {','.join(OUTPUT_COLUMNS)}")]  # S-ORD-01
    body = rows[1:]
    if len(body) != len(requests):
        issues.append(Issue("-", "ROW_COUNT", f"{len(body)} rows, expected {len(requests)}"))
    if any(len(r) != 3 for r in body):
        issues.append(Issue("-", "COLUMNS", "every row must have exactly 3 columns"))
        return issues
    out_ids = [r[0] for r in body]
    want_ids = [r.case_id for r in requests]
    if len(set(out_ids)) != len(out_ids):
        issues.append(Issue("-", "DUPLICATE", "duplicate case_id rows"))
    if sorted(out_ids) != sorted(want_ids):
        issues.append(Issue("-", "CASE_IDS", "case_id set differs from deletion_requests.csv"))
    elif out_ids != want_ids:
        issues.append(Issue("-", "ROW_ORDER", "rows are not in input (numeric case) order"))  # H-ORD-01
    ev_times = _evidence_times(files, activity, audit)
    audit_at = {r.case_id: r.audit_at for r in requests}
    for case_id, status, steps_json in body:
        try:
            steps = json.loads(steps_json)
        except json.JSONDecodeError as exc:
            issues.append(Issue(case_id, "JSON", f"invalid JSON: {exc}"))
            continue
        issues.extend(validate_steps(case_id, status, steps, audit_at.get(case_id), ev_times))
    return issues
