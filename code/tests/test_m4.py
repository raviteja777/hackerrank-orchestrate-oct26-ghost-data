import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from ghost import config, loaders
from ghost.citations import Citer
from ghost.config import Flags
from ghost.evidence import log_parser
from ghost.facts import Fact, FactStore, SnapshotScope
from ghost.loaders import EvidenceFile, Rule
from ghost.policy import Policy
from ghost.state import (ABSENT, CLEAN, EXPOSED, FLOW_ACTIVE, FLOW_DISABLED, PRESENT, RESTORABLE, RESTORE_BLOCKED,
                         UNKNOWN, assess, classify)

T = lambda h, m=0, day=10: datetime(2026, 9, day, h, m, tzinfo=timezone.utc)  # noqa: E731
AUDIT = T(12)
RULES = [Rule("rule_01", "USER_PROFILE", "Always", "DELETE"), Rule("rule_05", "SUPPORT_MESSAGE", "x", "REDACT"),
         Rule("rule_07", "ANALYTICS_PROFILE", "x", "ANONYMIZE"), Rule("rule_12", "SECURITY_AUDIT_LOG", "x", "RETAIN"),
         Rule("rule_14", "BACKUP_ARCHIVE", "x", "RETAIN")]
POL = Policy(RULES, Flags())


def fact(rid, hour, signals=None, fmt="log", topology="primary", file_id="evidence_1", captured=None, category=None,
         ident=None, text_mentions=frozenset(), minute=0, capture_time=None):
    return Fact(f"{file_id}#{rid}{hour}{minute}{topology}", file_id, captured or T(hour, minute), T(hour, minute), fmt, "loc",
                resource_id=rid, category=category, topology=topology, signals=signals or {}, ident_fields=ident or {},
                text_mentions=text_mentions, capture_time=capture_time)


def store_of(*facts, scopes=()):
    s = FactStore()
    for f in facts:
        s.add(f)
    s.scopes.extend(scopes)
    return s


def spec(cat):
    return POL.spec(cat)


# ---- classify: review items 1-4 --------------------------------------------------------------------------------
def test_analytics_direct_identifiers_flag():  # review item 1
    sp = spec("ANALYTICS_PROFILE")
    assert classify(fact("analytics_1", 9, {"direct_identifiers": 1}), sp) == EXPOSED
    assert classify(fact("analytics_1", 9, {"direct_identifiers": 0}), sp) == CLEAN
    assert classify(fact("analytics_1", 9, {}, ident={"email": True}), sp) == EXPOSED
    assert classify(fact("analytics_1", 9, {}, ident={"email": False, "phone": False}), sp) == CLEAN
    # the stable reference is NOT allowed for analytics (ANONYMIZE) but is for support (REDACT)
    assert classify(fact("analytics_1", 9, {}, ident={"customer_reference": True}), sp) == EXPOSED
    assert classify(fact("support_1", 9, {}, ident={"customer_reference": True, "email": False}), spec("SUPPORT_MESSAGE")) == CLEAN


def test_restore_decision_deny_is_blocked():  # review item 2
    sp = spec("BACKUP_ARCHIVE")
    assert classify(fact("backup_1", 9, {"decision": "deny"}), sp) == RESTORE_BLOCKED
    assert classify(fact("backup_1", 9, {"restore_allowed": True}), sp) == RESTORABLE
    assert classify(fact("backup_1", 9, {"eligible": True, "deletion_block": False}), sp) == RESTORABLE
    assert classify(fact("backup_1", 9, {"eligible": True, "deletion_block": True}), sp) == RESTORE_BLOCKED
    assert classify(fact("backup_1", 9, {"state_label": "ACTIVE"}), sp) == RESTORABLE


def test_support_exposure_by_scan_and_free_text():  # review item 3
    sp = spec("SUPPORT_MESSAGE")
    assert classify(fact("support_1", 9, {"pii_match": True}), sp) == EXPOSED
    f = fact("support_1", 9, {}, text_mentions=frozenset({"user_1"}))
    assert classify(f, sp, "user_1") == EXPOSED
    assert classify(f, sp, "user_2") != EXPOSED  # someone else's identifier in the text is shared context


def test_marker_found_false_means_copy_remains():  # review item 4
    sp = POL.spec("LEGACY_COPY", "DELETE")
    assert classify(fact("support_2", 9, {"rows": 1, "marker_found": False}), sp) == PRESENT
    assert classify(fact("support_2", 9, {"rows": 1, "marker_found": True}), sp) == ABSENT
    cat, action, _ = POL.resolve("support_2", "SUPPORT_MESSAGE", [fact("support_2", 9, {"marker_found": False})], AUDIT)
    assert (cat, action) == ("LEGACY_COPY", "DELETE")


def test_flow_states():
    sp = spec("DATA_FLOW")
    assert classify(fact("data_flow_1", 9, {"enabled": True}), sp) == FLOW_ACTIVE
    assert classify(fact("data_flow_1", 9, {"enabled": False}), sp) == FLOW_DISABLED


# ---- assess: time, copies, scope --------------------------------------------------------------------------------
def test_latest_observation_wins_and_activity_claims_are_ignored():  # H-STA-02
    sp = spec("USER_PROFILE")
    s = store_of(fact("account_1", 8, {"http_status": 200, "rows": 1}), fact("account_1", 10, {"http_status": 404, "rows": 0}))
    assert assess("account_1", sp, s, AUDIT, None, "account_service").state == ABSENT
    s = store_of(fact("account_1", 8, {"http_status": 404, "rows": 0}), fact("account_1", 10, {"http_status": 200, "rows": 1}))
    assert assess("account_1", sp, s, AUDIT, None, "account_service").state == PRESENT


def test_pre_run_observation_is_history_and_late_knowledge_is_ignored():  # DESIGN §6, D3
    sp = spec("USER_PROFILE")
    s = store_of(fact("account_1", 8, {"http_status": 200, "rows": 1}), fact("account_1", 13, {"http_status": 404, "rows": 0}))
    a = assess("account_1", sp, s, AUDIT, T(9), "account_service")  # the only usable fact is before the anchor / after audit
    assert a.state == UNKNOWN and not a.observed


def test_replica_copy_is_not_cleared_by_a_primary_absence():  # G-SYS-01
    sp = spec("USER_PROFILE")
    s = store_of(fact("account_1", 10, {"rows": 1, "account_status": "ACTIVE"}, fmt="sql", topology="replica:failover"),
                 fact("account_1", 11, {"http_status": 404, "rows": 0}))
    assert assess("account_1", sp, s, AUDIT, None, "account_service").state == PRESENT
    s = store_of(fact("account_1", 10, {"rows": 1, "account_status": "ACTIVE"}, fmt="sql", topology="replica:failover"),
                 fact("account_1", 11, {"rows": 0}, fmt="sql", topology="replica:failover"))
    assert assess("account_1", sp, s, AUDIT, None, "account_service").state == ABSENT


def test_tie_goes_to_the_violation():
    sp = spec("SEARCH_INDEX_ENTRY")
    s = store_of(fact("search_1", 10, {"result": "hit"}), fact("search_1", 10, {"rows": 0}, file_id="evidence_2"))
    assert assess("search_1", sp, s, AUDIT, None, "search_service").state == PRESENT


def test_scope_proof_is_a_last_resort():  # G-EVD-01
    sp = spec("USER_PROFILE")
    scope = SnapshotScope("evidence_9", "account_service", "primary", T(11))
    a = assess("account_1", sp, store_of(scopes=[scope]), AUDIT, T(9), "account_service")
    assert a.state == ABSENT and not a.observed and a.scope_proofs == [scope]
    # an explicit observation is never overridden by a later scope (bundles list only a few records)
    s = store_of(fact("account_1", 10, {"http_status": 200, "rows": 1}), scopes=[scope])
    a = assess("account_1", sp, s, AUDIT, None, "account_service")
    assert a.state == PRESENT and a.observed
    # a snapshot that mentions the resource is not an absence proof
    s = store_of(fact("account_1", 5, {}, file_id="evidence_9"), scopes=[scope])
    assert assess("account_1", sp, s, AUDIT, T(9), "account_service").state == UNKNOWN


def test_sql_rows_are_observed_at_the_snapshot_capture_time():
    sp = spec("SEARCH_INDEX_ENTRY")
    f = fact("search_1", 7, {}, fmt="sql", capture_time=T(11))  # row last written 07:00, snapshot taken 11:00
    s = store_of(f)
    assert assess("search_1", sp, s, AUDIT, T(9), "search_service").state == PRESENT  # not before the 09:00 anchor


# ---- policy -------------------------------------------------------------------------------------------------------
def d(cat, state_fact, **kw):
    sp = POL.spec(*kw.get("sa", (cat,)))
    rid = state_fact.resource_id
    a = assess(rid, sp, store_of(state_fact), AUDIT, None, "sys")
    return POL.decide(rid, "sys", cat, kw.get("action", POL.action_of(cat)), sp, a, [])


def ops(dec):
    return [(s.phase[:3], s.operation, s.state) for s in dec.steps]


def test_treatments_and_pairing():  # H-STP-01, H-STP-07
    assert ops(d("SEARCH_INDEX_ENTRY", fact("search_1", 10, {"result": "hit"}))) == [
        ("FIN", "REPORT_REMAINING_RECORD", "PRESENT"), ("REM", "DELETE_RECORD", "ABSENT"), ("VER", "VERIFY_RECORD_ABSENT", "ABSENT")]
    assert ops(d("SEARCH_INDEX_ENTRY", fact("search_1", 10, {"rows": 0}))) == [("VER", "VERIFY_RECORD_ABSENT", "ABSENT")]
    assert ops(d("ANALYTICS_PROFILE", fact("a_1", 10, {"direct_identifiers": 1}))) == [
        ("FIN", "REPORT_EXPOSED_PII", "PRESENT"), ("REM", "ANONYMIZE_RECORD", "ANONYMIZED"), ("VER", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED")]
    assert ops(d("SUPPORT_MESSAGE", fact("support_1", 10, {"pii_match": True}))) == [
        ("FIN", "REPORT_EXPOSED_PII", "PRESENT"), ("REM", "REDACT_RECORD", "REDACTED"), ("VER", "VERIFY_RECORD_REDACTED", "REDACTED")]
    assert ops(d("BACKUP_ARCHIVE", fact("backup_1", 10, {"restore_allowed": True}))) == [
        ("FIN", "REPORT_RESTORE_RISK", "ACTIVE"), ("REM", "BLOCK_RESTORE", "BLOCKED"), ("VER", "VERIFY_RESTORE_BLOCKED", "BLOCKED")]
    assert ops(d("BACKUP_ARCHIVE", fact("backup_1", 10, {"restore_allowed": False}))) == [("VER", "VERIFY_RESTORE_BLOCKED", "BLOCKED")]
    assert ops(d("DATA_FLOW", fact("data_flow_1", 10, {"enabled": True}))) == [
        ("FIN", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"), ("REM", "DISABLE_DATA_FLOW", "DISABLED"), ("VER", "VERIFY_DATA_FLOW_DISABLED", "DISABLED")]
    # retained audit record: verification only, in every case (H-STP-06)
    assert ops(d("SECURITY_AUDIT_LOG", fact("audit_record_1", 10, {"rows": 1}))) == [("VER", "VERIFY_RECORD_PRESENT", "PRESENT")]


def test_conditions_expired_retention_and_optin_contact():  # X-POL-03 / OQ-2, W-POL-01
    old = fact("audit_record_1", 10, {"retention_until": "2026-01-01T00:00:00Z", "rows": 1})
    assert POL.resolve("audit_record_1", "SECURITY_AUDIT_LOG", [old], AUDIT)[1] == "DELETE"
    live = fact("audit_record_1", 10, {"retention_until": "2031-01-01T00:00:00Z", "rows": 1})
    assert POL.resolve("audit_record_1", "SECURITY_AUDIT_LOG", [live], AUDIT)[1] == "RETAIN"
    optin = fact("analytics_1", 10, {"email_opt_in": True, "rows": 1})
    assert POL.resolve("analytics_1", "ANALYTICS_PROFILE", [optin], AUDIT)[:2] == ("MARKETING_PROFILE", "DELETE")
    off = Policy(RULES, dataclasses.replace(Flags(), analytics_contact_delete=False))
    assert off.resolve("analytics_1", "ANALYTICS_PROFILE", [optin], AUDIT)[1] == "ANONYMIZE"


# ---- citations ------------------------------------------------------------------------------------------------------
def test_citations_never_cite_a_later_file_and_prefer_the_audit_capture():  # D3, S-TIM-01, G-EVD-06
    sp = spec("SEARCH_INDEX_ENTRY")
    late = fact("search_1", 11, {"result": "hit"}, file_id="evidence_late", captured=AUDIT + timedelta(days=2))
    ok = fact("search_1", 9, {"result": "hit"}, file_id="evidence_ok", captured=T(9))
    s = store_of(late, ok)
    times = {"evidence_late": late.file_captured_at, "evidence_ok": T(9), "evidence_cap": T(11, 40)}
    c = Citer(s, times)
    a = assess("search_1", sp, s, AUDIT, None, "search_service")
    assert a.deciding.fact.file_id == "evidence_late"  # known at 11:00 (D3) ...
    assert c.finding(a, AUDIT, None) == ("evidence_ok", False)  # ... but never cited
    good = store_of(fact("search_1", 9, {"rows": 0}, file_id="evidence_a", captured=T(9)),
                    fact("search_1", 11, {"rows": 0}, file_id="evidence_cap", captured=T(11, 40)))
    c = Citer(good, times | {"evidence_a": T(9)})
    a = assess("search_1", sp, good, AUDIT, None, "search_service")
    assert c.verification(a, AUDIT, "evidence_a") == ("evidence_a", False)  # the audit-capture file proves it: preferred
    assert c.verification(a, AUDIT, None) == ("evidence_cap", False)  # otherwise the latest citable file
    # inclusive cut-off: a file captured exactly at audit_at is citable
    assert Citer(good, {"f": AUDIT}).citable("f", AUDIT)


# ---- log layouts (session 4 hardening) ---------------------------------------------------------------------------------
LEGACY = ('2026-09-17T22:00:04Z level=DEBUG service=support_replica trace_id=tr-rp-002 event=contact_query_started lookup_key=nadia.ionescu@yahoo.com source=legacy_contact_index\n'
          '2026-09-17T22:00:05Z level=INFO service=support_replica trace_id=tr-rp-002 event=contact_query_completed resource_id=support_002 rows=1\n'
          '2026-09-17T22:00:06Z level=WARN service=support_replica trace_id=tr-rp-002 event=deletion_marker_check resource_id=support_002 marker_found=false\n')


def test_legacy_replica_layout_groups_into_one_record():
    p = log_parser.parse(EvidenceFile("e", "x", "o", T(1)), LEGACY)
    assert len(p.records) == 1
    f = p.records[0].fields
    assert f["resource_id"] == "support_002" and f["marker_found"] == "false" and f["lookup_key"] == "nadia.ionescu@yahoo.com"


def test_bare_trace_token_fallback_and_selfcheck():
    text = ('2026-01-01T00:00:00Z weird layout tr-123456 lookup for a.b@c.io started\n'
            '2026-01-01T00:00:01Z weird layout tr-123456 resource_id=account_9 done\n'
            '2026-01-01T00:00:02Z orphan resource_id=search_5\n')
    p = log_parser.parse(EvidenceFile("e", "x", "o", T(1)), text)
    assert any(r.fields.get("resource_id") == "account_9" and r.locator == "trace:tr-123456" for r in p.records)
    assert p.stats == {"lines": 3, "carrying": 3, "orphans": 1}  # the untraced resource-only line is an orphan


# ---- dataset acceptance (M4) -----------------------------------------------------------------------------------------
@pytest.mark.skipif(not (config.DATASET_DIR / "sample_output.csv").exists(), reason="dataset not present")
def test_m4_acceptance_samples_and_full_validation(tmp_path):
    import sys
    sys.path.insert(0, str(config.REPO_ROOT / "code" / "evaluation"))
    import main as ev  # noqa: E402
    from ghost.pipeline import build_context, solve_all
    from ghost import steps, validate

    dd = config.DATASET_DIR
    ctx = build_context(dd)
    sample_reqs = loaders.load_requests(dd, "sample_deletion_requests.csv")
    res = dict(zip((r.case_id for r in sample_reqs), solve_all(ctx, sample_reqs)))
    m = ev.evaluate(res, ev.load_expected(dd))
    assert m["status_ok"] >= 30 and m["f1"] >= 0.85 and m["seq_exact"] >= 22
    reqs = loaders.load_requests(dd)
    results = solve_all(ctx, reqs)
    out = tmp_path / "output.csv"
    steps.write_output([(r.case_id, r.status, r.steps_json()) for r in results], out)
    assert validate.validate_output(out, reqs, loaders.load_evidence_manifest(dd), loaders.load_activity(dd), loaders.load_audit_log(dd)) == []
