"""Step objects, ordering, numbering and JSON/CSV serialisation (DESIGN §12).

Rules: S-ORD-01/02/03 (columns, sort, numbering), S-STP-01 (7 keys, 15 operation/state pairs),
H-ORD-02 (the sort is absolute; dependency ordering never overrides it), D1 (row order).
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, replace
from pathlib import Path

OUTPUT_COLUMNS = ("case_id", "deletion_status", "steps_json")
STATUSES = ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE")
PHASES = ("FINDING", "REMEDIATION", "VERIFICATION")
PHASE_RANK = {p: i for i, p in enumerate(PHASES)}

# Operation table in the order of problem_statement / AGENTS §6.4: (phase, operation, state).
OPERATION_TABLE: tuple[tuple[str, str, str], ...] = (
    ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"),
    ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
    ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
    ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"),
    ("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED"),
    ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED"),
    ("REMEDIATION", "DELETE_RECORD", "ABSENT"),
    ("REMEDIATION", "REDACT_RECORD", "REDACTED"),
    ("REMEDIATION", "ANONYMIZE_RECORD", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"),
    ("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"),
    ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"),
    ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
    ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),
)
OPERATION_RANK = {op: i for i, (_, op, _) in enumerate(OPERATION_TABLE)}
ALLOWED_PAIRS = {(phase, op, state) for phase, op, state in OPERATION_TABLE}
STEP_KEYS = ("step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id")


@dataclass(frozen=True)
class Step:
    phase: str
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str = ""
    step_no: int = 0

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in STEP_KEYS}
        return d


def sort_key(step: Step | dict) -> tuple:
    """(phase rank, operation-table rank, system_id, resource_id); strings compare plainly (S-ORD-02, H-ORD-02)."""
    g = (lambda k: step[k]) if isinstance(step, dict) else (lambda k: getattr(step, k))
    return (PHASE_RANK[g("phase")], OPERATION_RANK[g("operation")], g("system_id"), g("resource_id"))


def order_steps(steps: list[Step]) -> list[Step]:
    """Sort per S-ORD-02 and number consecutively from 1 (S-ORD-03)."""
    return [replace(s, step_no=i) for i, s in enumerate(sorted(steps, key=sort_key), start=1)]


def serialize_steps(steps: list[Step]) -> str:
    """Compact JSON array with keys in spec order (DESIGN §12)."""
    return json.dumps([s.to_dict() for s in steps], ensure_ascii=False, separators=(",", ":"))


def write_output(rows: list[tuple[str, str, str]], path: Path) -> None:
    """rows = (case_id, deletion_status, steps_json) in the caller's (input) order. UTF-8, \\n endings."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w.writerow(OUTPUT_COLUMNS)
        w.writerows(rows)
