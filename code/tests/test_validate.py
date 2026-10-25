from datetime import datetime, timezone

from ghost.loaders import DeletionRequest, EvidenceFile
from ghost.steps import Step, order_steps, serialize_steps, write_output
from ghost.validate import validate_output, validate_steps

AUDIT = datetime(2026, 5, 1, tzinfo=timezone.utc)
EV = {"evidence_1": datetime(2026, 4, 30, tzinfo=timezone.utc), "evidence_late": datetime(2026, 5, 2, tzinfo=timezone.utc)}


def d(steps):
    return [s.to_dict() for s in order_steps(steps)]


def V(phase, op, state, sys_, res, ev=""):
    return Step(phase, sys_, res, op, state, ev)


GOOD_COMPLETE = [V("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT", "account_service", "account_1", "evidence_1")]
GOOD_INCOMPLETE = [
    V("FINDING", "REPORT_REMAINING_RECORD", "PRESENT", "account_service", "account_1", "evidence_1"),
    V("REMEDIATION", "DELETE_RECORD", "ABSENT", "account_service", "account_1"),
    V("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT", "account_service", "account_1"),
]


def codes(status, steps):
    return {i.code for i in validate_steps("c", status, steps, AUDIT, EV)}


def test_good_fixtures_pass():
    assert codes("COMPLETE", d(GOOD_COMPLETE)) == set()
    assert codes("INCOMPLETE", d(GOOD_INCOMPLETE)) == set()
    assert codes("NOT_APPLICABLE", []) == set()


def test_not_applicable_must_be_empty():
    assert "NA_STEPS" in codes("NOT_APPLICABLE", d(GOOD_COMPLETE))


def test_bad_status_and_not_array():
    assert "STATUS" in codes("DONE", [])
    assert "JSON" in {i.code for i in validate_steps("c", "COMPLETE", {"a": 1}, AUDIT, EV)}


def test_extra_key_and_bad_pair():
    steps = d(GOOD_COMPLETE)
    steps[0]["extra"] = 1
    assert "KEYS" in codes("COMPLETE", steps)
    steps = d(GOOD_COMPLETE)
    steps[0]["state"] = "PRESENT"
    assert "PAIR" in codes("COMPLETE", steps)


def test_step_numbering_and_order():
    steps = d(GOOD_INCOMPLETE)
    steps[0]["step_no"] = 2
    assert "STEP_NO" in codes("INCOMPLETE", steps)
    steps = d(GOOD_INCOMPLETE)
    steps.reverse()
    for n, s in enumerate(steps, 1):
        s["step_no"] = n
    assert {"ORDER", "PHASE_ORDER"} <= codes("INCOMPLETE", steps)


def test_complete_rules():
    assert "COMPLETE_PHASES" in codes("COMPLETE", d(GOOD_INCOMPLETE))
    steps = d(GOOD_COMPLETE)
    steps[0]["evidence_id"] = ""
    assert "COMPLETE_EVIDENCE" in codes("COMPLETE", steps)


def test_incomplete_rules():
    steps = d(GOOD_INCOMPLETE)
    steps[2]["evidence_id"] = "evidence_1"
    assert "FUTURE_EVIDENCE" in codes("INCOMPLETE", steps)
    steps = d(GOOD_INCOMPLETE)
    steps[0]["evidence_id"] = ""
    assert "FINDING_EVIDENCE" in codes("INCOMPLETE", steps)
    assert "INCOMPLETE_NO_FINDING" in codes("INCOMPLETE", d(GOOD_COMPLETE))


def test_verification_count_per_resource():  # H-STP-04
    steps = d(GOOD_INCOMPLETE[:2])
    assert "VERIFY_COUNT" in codes("INCOMPLETE", steps)


def test_citation_must_exist_and_not_be_late():
    steps = d(GOOD_COMPLETE)
    steps[0]["evidence_id"] = "evidence_late"
    assert "CITE_LATE" in codes("COMPLETE", steps)
    steps[0]["evidence_id"] = "nope"
    assert "CITE_UNKNOWN" in codes("COMPLETE", steps)


def test_citation_inclusive_cutoff():  # H-TIM-03
    ev = {"evidence_1": AUDIT}
    assert not validate_steps("c", "COMPLETE", d(GOOD_COMPLETE), AUDIT, ev)


def _req(cid):
    return DeletionRequest(cid, "a@b.c", AUDIT, "COMPLETE", AUDIT, AUDIT, "x")


def test_validate_output_file(tmp_path):
    reqs = [_req("case_2"), _req("case_10")]
    files = [EvidenceFile("evidence_1", "x", "o", AUDIT)]
    p = tmp_path / "o.csv"
    write_output([("case_2", "NOT_APPLICABLE", "[]"), ("case_10", "COMPLETE", serialize_steps(order_steps(GOOD_COMPLETE)))], p)
    assert validate_output(p, reqs, files, [], []) == []
    write_output([("case_10", "NOT_APPLICABLE", "[]"), ("case_2", "NOT_APPLICABLE", "[]")], p)  # wrong order
    assert {i.code for i in validate_output(p, reqs, files, [], [])} == {"ROW_ORDER"}
    write_output([("case_2", "NOT_APPLICABLE", "[]")], p)
    assert "ROW_COUNT" in {i.code for i in validate_output(p, reqs, files, [], [])}
    p.write_text("case_id,status,steps_json\n", encoding="utf-8")
    assert [i.code for i in validate_output(p, reqs, files, [], [])] == ["HEADER"]
    write_output([("case_2", "NOT_APPLICABLE", "{bad"), ("case_10", "NOT_APPLICABLE", "[]")], p)
    assert "JSON" in {i.code for i in validate_output(p, reqs, files, [], [])}
