"""deletion_rules.csv -> treatment; finding / remediation / verification selection (DESIGN §7.2).

The required action of each data category comes from dataset/deletion_rules.csv. Only the condition
evaluators (retention still running, legacy copy, opt-in contact lookup) and the exposure columns live in code.
Rules: H-STP-01 (finding -> remediation -> verification pairing), H-STP-04 (one verification per resource),
H-STP-06 (retained audit records: VERIFY_RECORD_PRESENT only), H-STP-07 (finding operation follows the
treatment; a retained backup is verified as BLOCKED, never PRESENT), G-POL-01, G-POL-03 (legal holds),
W-POL-01 (opt-in contact lookup is DELETE), X-POL-03 / OQ-2 (expired retention), OQ-3, X-POL-01.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import catalog
from .config import Flags
from .facts import Fact
from .loaders import Rule, parse_ts
from .state import (ABSENT, BAD, CategorySpec, EXPOSED, FLOW_ACTIVE, KIND_BACKUP, KIND_FLOW, KIND_RECORD, KIND_RETAIN,
                    KIND_SENSITIVE, PRESENT, RESTORABLE, Assessment)
from .steps import Step

_REDACT_COLS = frozenset({"email", "phone", "name", "email_hash"})  # the stable reference is allowed (rule_15)
_ANON_COLS = _REDACT_COLS | {"user_id", "customer_reference"}
_BACKUP, _FLOW = "BACKUP_ARCHIVE", catalog.DATA_FLOW
_RETAIN_RECORDS = {"SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD"}
LEGACY_COPY = "LEGACY_COPY"  # support_replica copy whose deletion marker is missing: DELETE (G-POL-01)


@dataclass
class Decision:
    resource_id: str
    system_id: str
    category: str
    kind: str
    action: str
    assessment: Assessment
    steps: list[Step] = field(default_factory=list)  # evidence ids are filled by citations
    violating: bool = False
    rule_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class Policy:
    def __init__(self, rules: list[Rule], flags: Flags):
        self.flags = flags
        self.rules = {r.data_category: r for r in rules}

    def action_of(self, category: str) -> str:
        if category == _FLOW:
            return "PROCESS"
        r = self.rules.get(category)
        return r.required_action if r else "DELETE"  # unseen category: delete (X-POL-01 rule default)

    def spec(self, category: str, action: str | None = None) -> CategorySpec:
        a = action or self.action_of(category)
        if category == _FLOW:
            return CategorySpec(category, KIND_FLOW)
        if category == _BACKUP:
            return CategorySpec(category, KIND_BACKUP)
        if category in _RETAIN_RECORDS and a == "RETAIN":
            return CategorySpec(category, KIND_RETAIN)
        if a == "REDACT":
            return CategorySpec(category, KIND_SENSITIVE, _REDACT_COLS)
        if a == "ANONYMIZE":
            return CategorySpec(category, KIND_SENSITIVE, _ANON_COLS)
        return CategorySpec(category, KIND_RECORD)

    def resolve(self, resource_id: str, category: str, facts: list[Fact], audit_at: datetime) -> tuple[str, str, list[str]]:
        """-> (effective category, action, rule ids). Applies the condition evaluators."""
        action = self.action_of(category)
        rule_ids = [self.rules[category].rule_id] if category in self.rules else []
        sig = [f.signals for f in facts if f.fact_time <= audit_at]
        if category == "SUPPORT_MESSAGE" and any(s.get("marker_found") is not None for s in sig):
            return LEGACY_COPY, "DELETE", rule_ids + ["G-POL-01"]  # review item 4: marker_found=false -> copy remains
        if category == "ANALYTICS_PROFILE" and self.flags.analytics_contact_delete \
                and any(s.get("email_opt_in") is True for s in sig):
            return "MARKETING_PROFILE", "DELETE", ["rule_10", "W-POL-01"]  # opt-in contact lookup
        if category in _RETAIN_RECORDS and action == "RETAIN" and self.flags.expired_retention_delete:
            until = self._latest_until(facts, audit_at)
            if until is not None and until < audit_at:  # retention / hold expired before audit_at (OQ-2)
                return category, "DELETE", rule_ids + ["X-POL-03"]
        return category, action, rule_ids

    @staticmethod
    def _latest_until(facts: list[Fact], audit_at: datetime) -> datetime | None:
        best = None
        for f in facts:
            if f.fact_time > audit_at:
                continue
            v = f.signals.get("retention_until") or f.signals.get("retained_until")
            if v:
                try:
                    t = parse_ts(str(v))
                except ValueError:
                    continue
                best = t if best is None or t > best else best
        return best

    # ---- treatment ---------------------------------------------------------------------------------------
    def decide(self, resource_id: str, system_id: str, category: str, action: str, spec: CategorySpec,
               assessment: Assessment, rule_ids: list[str]) -> Decision:
        d = Decision(resource_id, system_id, category, spec.kind, action, assessment, rule_ids=rule_ids)
        state = assessment.state
        bad = state in BAD[spec.kind]
        d.violating = bad
        mk = lambda phase, op, st: Step(phase, system_id, resource_id, op, st)  # noqa: E731
        k = spec.kind
        if k == KIND_RECORD:
            if bad:
                d.steps += [mk("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"), mk("REMEDIATION", "DELETE_RECORD", "ABSENT")]
            d.steps.append(mk("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"))
        elif k == KIND_SENSITIVE:
            redact = action == "REDACT"
            if bad:
                d.steps += [mk("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
                            mk("REMEDIATION", "REDACT_RECORD" if redact else "ANONYMIZE_RECORD", "REDACTED" if redact else "ANONYMIZED")]
            d.steps.append(mk("VERIFICATION", "VERIFY_RECORD_REDACTED" if redact else "VERIFY_RECORD_ANONYMIZED",
                              "REDACTED" if redact else "ANONYMIZED"))
        elif k == KIND_RETAIN:
            d.steps.append(mk("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"))  # H-STP-06, G-POL-03
            if state == ABSENT:
                d.notes.append("retained record not observed (OQ-3): verification only, no finding")
        elif k == KIND_BACKUP:
            if bad:
                d.steps += [mk("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"), mk("REMEDIATION", "BLOCK_RESTORE", "BLOCKED")]
            d.steps.append(mk("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"))  # H-STP-07
        elif k == KIND_FLOW:
            if bad:
                d.steps += [mk("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"), mk("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED")]
            d.steps.append(mk("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"))
        return d
