from datetime import datetime, timezone

import pytest

from ghost import catalog, config
from ghost.evidence import json_parser, log_parser, sql_parser, txt_parser
from ghost.evidence.normalize import ident_fields, signals_from
from ghost.facts import ABSENT, FLOW_ACTIVE, PRESENT, RESTORABLE, RESTORE_BLOCKED, Fact, derive_states
from ghost.loaders import EvidenceFile, parse_ts

CAP = datetime(2026, 9, 1, tzinfo=timezone.utc)
F = EvidenceFile("evidence_x", "evidence/x", "origin", CAP)


def by_resource(parsed):
    return {r.fields.get("resource_id"): r for r in parsed.records}


# ---- logs: the styles in DESIGN §5 -------------------------------------------------------------------
KV = """2026-09-26T08:57:37Z level=DEBUG service=account_service trace_id=rb-1 event=profile_lookup_started resource_id=account_7566 lookup_key=l.fontaine46@yahoo.com
2026-09-26T08:57:38Z level=INFO service=account_service trace_id=rb-1 event=profile_lookup_completed resource_id=account_7566 rows=0 http_status=404
2026-09-26T09:54:09Z level=INFO service=analytics_platform trace_id=rb-2 event=analytics_profile_read_completed resource_id=analytics_9406 customer_reference=null email=null
"""
BRACKET = '2026-07-28T05:51:18Z [DEBUG] [account_service] [tr-6074163] profile_lookup_started: lookup_key="l.nascimento40@gmail.com" attempt="1"\n' \
          '2026-07-28T05:51:21Z [INFO] [account_service] [tr-6074163] profile_lookup_completed: resource_id="account_7947" rows="0" http_status="404"\n'
PIPE = '2026-02-03T05:51:23Z | DEBUG | security_service | tr-1 | audit_record_query_started | subject_ref="user_517" attempt="1"\n' \
       '2026-02-03T05:51:30Z | DEBUG | security_service | tr-1 | audit_record_read_completed | resource_id="audit_record_4027" rows="1"\n'
SYSLOG = '2026-03-25T08:51:15Z <15>1 node-1 support_platform tr-7 - - level=DEBUG event="message_scan_started" subject_key="silva.mariana@icloud.com"\n' \
         '2026-03-25T08:51:23Z <12>1 node-1 support_platform tr-7 - - level=WARN resource_id="support_9464" event="message_pii_scan" matched_value="silva.mariana@icloud.com"\n'
JSONL = '2026-04-19T06:51:13Z {"service":"search_service","trace_id":"tr-9","event":"index_query_started","match_key":"dubois.ines94@icloud.com"}\n' \
        '2026-04-19T06:51:20Z {"service":"search_service","trace_id":"tr-9","resource_id":"search_55","event":"index_query_completed","result":"hit"}\n'
CLOUD = '2026-09-30T11:51:03Z requestId=tr-22 level=DEBUG function=profile_service message="resource_id=\\"account_66777\\" event=\\"profile_lookup_completed\\" rows=\\"1\\" http_status=\\"200\\" correlation_key=\\"a.watanabe06@yahoo.com\\""\n'
SOLO = '2026-03-15T07:00:00Z INFO service=downstream_delivery_service event=record_lookup seq=1 system="account_service" resource_id="account_022" record_type="USER_PROFILE" result="NOT_FOUND" subject_reference="zofia-novak@gmail.com"\n'


def test_kv_style_groups_by_trace_and_links_identifier_to_resource():  # H-LNK-03
    p = log_parser.parse(F, KV)
    rec = by_resource(p)["account_7566"]
    assert rec.fields["lookup_key"] == "l.fontaine46@yahoo.com"
    assert rec.fields["rows"] == "0" and rec.fields["http_status"] == "404"
    assert rec.fact_time == parse_ts("2026-09-26T08:57:38Z")  # latest line of the trace (D3)
    assert rec.line_span == (1, 2)
    assert by_resource(p)["analytics_9406"].fields["email"] is None  # null -> None


@pytest.mark.parametrize("text,rid,key,value", [
    (BRACKET, "account_7947", "lookup_key", "l.nascimento40@gmail.com"),
    (PIPE, "audit_record_4027", "subject_ref", "user_517"),
    (SYSLOG, "support_9464", "subject_key", "silva.mariana@icloud.com"),
    (JSONL, "search_55", "match_key", "dubois.ines94@icloud.com"),
    (CLOUD, "account_66777", "correlation_key", "a.watanabe06@yahoo.com"),
    (SOLO, "account_022", "subject_reference", "zofia-novak@gmail.com"),
])
def test_log_styles(text, rid, key, value):
    rec = by_resource(log_parser.parse(F, text))[rid]
    assert rec.fields[key] == value


def test_noise_events_do_not_overwrite_state():
    text = ('2026-01-01T00:00:00Z level=INFO service=search_service trace_id=t1 event=index_query_started lookup_key=a@b.co\n'
            '2026-01-01T00:00:01Z level=DEBUG service=search_service trace_id=t1 event=cache_lookup result=miss\n'
            '2026-01-01T00:00:02Z level=INFO service=search_service trace_id=t1 event=index_query_completed resource_id=search_1 result=hit\n')
    assert by_resource(log_parser.parse(F, text))["search_1"].fields["result"] == "hit"


def test_two_resources_in_one_trace_split():
    text = ('2026-01-01T00:00:00Z level=INFO trace_id=t1 event=a resource_id=search_1\n'
            '2026-01-01T00:00:01Z level=INFO trace_id=t1 event=b resource_id=search_2\n')
    assert set(by_resource(log_parser.parse(F, text))) == {"search_1", "search_2"}


# ---- json ---------------------------------------------------------------------------------------------
def test_json_service_exports_inherit_system_and_own_time():
    text = '''{"exported_at":"2026-09-15T11:44:55Z","service_exports":{"account_service":{"profile_lookups":[
      {"observed_at":"2026-09-15T09:31:40Z","profile":null,"resource_id":"account_3136","status_code":404}]}}}'''
    rec = json_parser.parse(F, text).records[0]
    assert rec.system_hint == "account_service" and rec.collection == "profile_lookups"
    assert rec.fact_time == parse_ts("2026-09-15T09:31:40Z")  # record time beats file time


def test_json_bundle_snapshot_time_and_nested_search_document():
    text = '''{"exported_at":"2026-09-17T12:00:00Z","snapshots":[{"captured_at":"2026-09-15T12:00:00Z","data_store":"search_service",
      "collection":"customer_search_documents","records":[{"resource_id":"search_5577","document":{"email":"k@x.io"}}]}]}'''
    rec = json_parser.parse(F, text).records[0]
    assert rec.fact_time == parse_ts("2026-09-15T12:00:00Z")  # inner snapshot beats exported_at (D3)
    assert rec.fields["document.email"] == "k@x.io"
    assert ident_fields(rec.fields) == {"email": True}


# ---- sql ----------------------------------------------------------------------------------------------
SQL_INV = """-- Captured at: 2026-09-16T08:37:39Z
CREATE TABLE snapshot_scope (origin_system TEXT PRIMARY KEY, captured_at TEXT NOT NULL);
CREATE TABLE backup_restore_entries (resource_id TEXT, customer_reference TEXT, customer_email TEXT, archive_key TEXT, restore_allowed INTEGER, updated_at TEXT);
INSERT INTO snapshot_scope VALUES ('backup_service', '2026-09-16T08:37:39Z');
INSERT INTO backup_restore_entries VALUES ('backup_4978', NULL, 'k.appiah88@gmail.com', 'a/b', '1', '2026-09-16T07:59:54Z');
"""
SQL_REPLICA = """-- Captured at: 2026-06-13T11:00:00Z
-- Database topology: read_replica
CREATE TABLE "customer_data_primary" (resource_id TEXT, origin_system TEXT, collection_name TEXT, record_json TEXT, updated_at TEXT);
CREATE TABLE "customer_data_read_replica" (resource_id TEXT, origin_system TEXT, collection_name TEXT, record_json TEXT, updated_at TEXT);
INSERT INTO "customer_data_read_replica" VALUES('account_994','account_service','customer_profiles','{"resource_id":"account_994","email":"a@b.co"}','2026-06-13T10:59:00Z');
"""


def test_sql_inventory_row_time_scope_and_header():
    p = sql_parser.parse(F, SQL_INV)
    rec = p.records[0]
    assert rec.fields["resource_id"] == "backup_4978" and rec.fields["restore_allowed"] == 1  # INTEGER affinity
    assert rec.fact_time == parse_ts("2026-09-16T07:59:54Z") and rec.capture_time == parse_ts("2026-09-16T08:37:39Z")
    assert [(s.system_id_hint, s.captured_at) for s in p.scopes if s.system_id_hint == "backup_service"][0][1] == parse_ts("2026-09-16T08:37:39Z")


def test_sql_replica_topology_and_json_payload():  # G-SYS-01
    rec = sql_parser.parse(F, SQL_REPLICA).records[0]
    assert rec.topology == "replica:read" and rec.system_hint == "account_service"
    assert rec.fields["email"] == "a@b.co" and rec.collection == "customer_profiles"


def test_sql_crlf_script_runs():
    assert len(sql_parser.parse(F, SQL_INV.replace("\n", "\r\n")).records) == 1


# ---- txt ----------------------------------------------------------------------------------------------
def test_txt_handover_lines():
    text = "CUSTOMER PLATFORM - SHIFT HANDOVER\nSnapshot: 2026-10-01T12:00:00Z\n\n" \
           "- 2026-10-01T12:00:00Z | analytics_platform | analytics_2034 | ANALYTICS_PROFILE | IDENTIFIABLE | novak@x.io\n" \
           "- 2026-10-01T12:00:00Z | backup_service | backup_706 | BACKUP_ARCHIVE | BLOCKED | user_39\n"
    p = txt_parser.parse(F, text)
    assert p.capture_time == parse_ts("2026-10-01T12:00:00Z")
    assert [(r.fields["resource_id"], r.fields["state"], r.label_category) for r in p.records] == [
        ("analytics_2034", "IDENTIFIABLE", "ANALYTICS_PROFILE"), ("backup_706", "BLOCKED", "BACKUP_ARCHIVE")]
    assert p.records[0].line_span == (4, 4)


# ---- catalog / signals / states -----------------------------------------------------------------------
def test_catalog_prefixes_and_replica_mapping():  # G-SYS-01, X-SYS-01
    assert catalog.system_for("data_flow_12") == "integration_service"
    assert catalog.system_for("audit_record_9") == "security_service"
    assert catalog.system_for("tombstone_3") == "identity_service"
    assert catalog.normalize_system("customer_data_failover_replica") is None
    assert catalog.normalize_system("account_service_failover_replica") == "account_service"
    assert catalog.system_for("zzz_1") is None
    assert catalog.category_for("support_1", collection="ticket_attachments") == "SUPPORT_ATTACHMENT"
    assert catalog.category_for("support_1", label="support_message") == "SUPPORT_MESSAGE"


def test_signals_and_states():
    s = signals_from({"rows": "0", "http_status": "404", "enabled": "0"}, None)
    f = Fact("a#b", "a", CAP, CAP, "log", "b", signals=s)
    assert ABSENT in derive_states(f)
    f = Fact("a#b", "a", CAP, CAP, "sql", "b", signals=signals_from({"restore_allowed": "1"}, None))
    assert RESTORABLE in derive_states(f) and RESTORE_BLOCKED not in derive_states(f)
    f = Fact("a#b", "a", CAP, CAP, "json", "b", signals=signals_from({"restore_allowed": False}, None))
    assert RESTORE_BLOCKED in derive_states(f)
    f = Fact("a#b", "a", CAP, CAP, "log", "b", signals=signals_from({"eligible": "true", "deletion_block": "false"}, None))
    assert RESTORABLE in derive_states(f)
    f = Fact("a#b", "a", CAP, CAP, "json", "b", signals=signals_from({"enabled": True}, None))
    assert FLOW_ACTIVE in derive_states(f)
    f = Fact("a#b", "a", CAP, CAP, "log", "b", signals=signals_from({"rows": "1", "http_status": "200"}, None))
    assert PRESENT in derive_states(f)


def test_fact_time_and_citability_are_separate():  # D3, H-TIM-03
    audit = datetime(2026, 9, 16, 9, 0, tzinfo=timezone.utc)
    late_file = Fact("f#1", "f", datetime(2026, 9, 18, tzinfo=timezone.utc), datetime(2026, 9, 16, 8, 57, tzinfo=timezone.utc), "log", "1")
    assert late_file.known(audit) and not late_file.citable(audit)
    exact = Fact("f#2", "f", audit, audit, "log", "2")
    assert exact.known(audit) and exact.citable(audit)


# ---- dataset-level ------------------------------------------------------------------------------------
@pytest.mark.skipif(not (config.DATASET_DIR / "evidence_files.csv").exists(), reason="dataset not present")
def test_every_manifest_file_is_accounted_for_and_pngs_unparsed():
    from ghost.evidence.normalize import build_fact_store
    from ghost import loaders

    store = build_fact_store()
    manifest = loaders.load_evidence_manifest()
    parsed_files = {f.file_id for f in store.facts} | {s.file_id for s in store.scopes}  # scope-only snapshots count
    unparsed = {u[0] for u in store.unparsed}
    pngs = {f.file_id for f in manifest if f.suffix == ".png"}
    assert unparsed == pngs  # only screenshots are deferred to M5
    assert {f.file_id for f in manifest} - unparsed - parsed_files == set()  # nothing else vanished
    assert all(u[2].startswith("TODO(M5)") for u in store.unparsed)


@pytest.mark.skipif(not (config.DOSSIER_DIR_EXISTS if hasattr(config, "DOSSIER_DIR_EXISTS") else (config.REPO_ROOT / "docs" / "probes" / "out" / "P02_case_03.txt").exists()),
                    reason="dossiers not present")
def test_m2_acceptance_dossiers_and_resource_coverage():
    from scripts import m2_acceptance as acc
    from ghost import loaders
    from ghost.evidence.normalize import build_fact_store

    store = build_fact_store()
    cov = acc.resource_coverage(store, {a.resource_id for a in loaders.load_activity()})
    assert [r for _, r in cov["missing"] if r not in acc.CEILING] == []
    assert [r for _, r in acc.audit_coverage(store)["missing"] if r not in acc.CEILING] == []
    for case in ("case_03", "case_09", "case_24"):
        assert acc.dossier_check(case, store)["missing"] == []
