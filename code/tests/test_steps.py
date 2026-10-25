import json

from ghost.steps import OPERATION_TABLE, Step, order_steps, serialize_steps, sort_key, write_output


def S(phase, op, state, system, res, ev=""):
    return Step(phase, system, res, op, state, ev)


def test_operation_table_has_15_pairs():
    assert len(OPERATION_TABLE) == 15


def test_order_phase_then_operation_then_system_then_resource():  # S-ORD-02
    steps = [
        S("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT", "search_service", "search_1"),
        S("REMEDIATION", "DELETE_RECORD", "ABSENT", "search_service", "search_1"),
        S("REMEDIATION", "DELETE_RECORD", "ABSENT", "account_service", "account_9"),
        S("FINDING", "REPORT_REMAINING_RECORD", "PRESENT", "search_service", "search_1", "evidence_1"),
        S("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED", "integration_service", "data_flow_1"),
        S("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE", "integration_service", "data_flow_1", "evidence_1"),
    ]
    out = order_steps(steps)
    assert [s.step_no for s in out] == [1, 2, 3, 4, 5, 6]
    assert [(s.phase, s.operation, s.system_id) for s in out] == [
        ("FINDING", "REPORT_REMAINING_RECORD", "search_service"),
        ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "integration_service"),
        ("REMEDIATION", "DISABLE_DATA_FLOW", "integration_service"),
        ("REMEDIATION", "DELETE_RECORD", "account_service"),  # H-ORD-02: account before search
        ("REMEDIATION", "DELETE_RECORD", "search_service"),
        ("VERIFICATION", "VERIFY_RECORD_ABSENT", "search_service"),
    ]


def test_resource_ids_sort_as_plain_strings():
    a = S("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT", "s", "account_1000")
    b = S("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT", "s", "account_999")
    assert sort_key(a) < sort_key(b)


def test_serialisation_key_order_and_compact():
    s = order_steps([S("FINDING", "REPORT_REMAINING_RECORD", "PRESENT", "account_service", "account_005", "evidence_01")])
    text = serialize_steps(s)
    assert text == (
        '[{"step_no":1,"phase":"FINDING","system_id":"account_service","resource_id":"account_005",'
        '"operation":"REPORT_REMAINING_RECORD","state":"PRESENT","evidence_id":"evidence_01"}]'
    )
    assert json.loads(text)[0]["step_no"] == 1


def test_non_ascii_not_escaped():
    s = order_steps([S("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT", "sys", "res_é")])
    assert "é" in serialize_steps(s)


def test_write_output_lf_and_header(tmp_path):
    p = tmp_path / "o.csv"
    write_output([("case_1", "NOT_APPLICABLE", "[]")], p)
    assert p.read_bytes() == b"case_id,deletion_status,steps_json\ncase_1,NOT_APPLICABLE,[]\n"
