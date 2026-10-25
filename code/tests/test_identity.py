import hashlib
from datetime import datetime, timezone

import pytest

from ghost import config
from ghost.identity import IdentityIndex, Outcome, decoys, email_hash, links, normalize_phone, write_decoy_log
from ghost.loaders import AuditEvent, UserIdentity

T = datetime(2026, 1, 1, tzinfo=timezone.utc)


def U(uid, name, email, phone):
    return UserIdentity(uid, name, email, phone, email_hash(email), T)


@pytest.fixture
def index():
    ids = [
        U("user_04", "Thandiwe N", "thandiwe.n@gmail.com", "+27 82 111 2222"),
        U("user_413", "Thandiwe Nkosi", "thandiwe.n5276@gmail.com", "+27 82 333 4444"),
        U("user_07", "Ingrid Dahl", "ingrid.dahl@outlook.com", "+47 912 34 567"),
    ]
    audit = [
        AuditEvent("a1", "user_07", T, "email", "ingrid.dahl@gmail.com", "ingrid.dahl@outlook.com"),
        AuditEvent("a2", "user_07", T, "phone", "+47 900 00 000", "+47 912 34 567"),
    ]
    return IdentityIndex(ids, audit)


def kinds(matches, kind="email"):
    return sorted((m.token, m.searched, m.outcome.value) for m in matches if m.kind == kind)


def test_request_email_current_historical_case_insensitive(index):  # S-IDN-01
    assert index.user_for_email("  INGRID.DAHL@Outlook.com ") == "user_07"
    assert index.user_for_email("ingrid.dahl@gmail.com") == "user_07"  # historical
    assert index.user_for_email("nobody@example.com") is None


def test_hash_of_historical_email_belongs_to_user(index):  # H-IDN-02
    h = hashlib.sha256(b"ingrid.dahl@gmail.com").hexdigest()
    ms = index.scan(f"hash={h}")
    assert [(m.kind, m.outcome, m.token_users) for m in ms] == [("email_hash", Outcome.EXACT, frozenset({"user_07"}))]


def test_exact_and_same_user_other_id(index):
    ms = index.scan("seen ingrid.dahl@gmail.com today")
    assert ("ingrid.dahl@gmail.com", "ingrid.dahl@gmail.com", "EXACT") in kinds(ms)
    # the current email shares the local part: recalled, same user, still links
    assert ("ingrid.dahl@gmail.com", "ingrid.dahl@outlook.com", "SAME_USER_OTHER_ID") in kinds(ms)
    assert links(ms) == {("user_07", "email", "ingrid.dahl@gmail.com")}


def test_look_alike_other_user_is_rejected(index):
    ms = index.scan("contact thandiwe.n5276@gmail.com")
    assert ("thandiwe.n5276@gmail.com", "thandiwe.n@gmail.com", "OTHER_USER") in kinds(ms)
    assert links(ms) == {("user_413", "email", "thandiwe.n5276@gmail.com")}  # only the real owner links
    assert all(m.outcome is Outcome.OTHER_USER for m in decoys(ms))


def test_unknown_decoy_logged_not_linked(index, tmp_path):
    ms = index.scan("ingrid.dahl.jr@outlook.com")
    assert [m.outcome for m in ms] == [Outcome.UNKNOWN_DECOY, Outcome.UNKNOWN_DECOY]
    assert links(ms) == set()
    p = tmp_path / "decoys.jsonl"
    write_decoy_log(ms, p)
    assert len(p.read_text(encoding="utf-8").splitlines()) == 2


def test_names_never_link(index):  # H-IDN-04
    assert index.scan("Customer: Ingrid Dahl, thandiwe nkosi") == []


def test_unrelated_email_is_not_a_candidate(index):
    assert index.scan("staff@northstar.shop") == []


def test_phone_exact_and_decoy(index):
    ms = index.scan("tel +47 912 34 567")
    assert [(m.token, m.outcome) for m in ms if m.kind == "phone"] == [(normalize_phone("+47 912 34 567"), Outcome.EXACT)]
    ms = index.scan("tel 00 47 912 34 567")  # tail recalled, exact validation fails
    assert [m.outcome for m in ms if m.kind == "phone"] == [Outcome.UNKNOWN_DECOY]
    assert links(ms) == set()


def test_historical_phone_links(index):
    ms = index.scan("old +47 900 00 000")
    assert links(ms) == {("user_07", "phone", "4790000000")}


def test_user_reference(index):
    ms = index.scan("subject_reference=user_07 other=user_999")
    assert [(m.token, m.outcome) for m in ms] == [("user_07", Outcome.EXACT), ("user_999", Outcome.UNKNOWN_DECOY)]
    assert index.scan("xuser_07y") == []


@pytest.mark.skipif(not (config.DATASET_DIR / "user_identities.csv").exists(), reason="dataset not present")
def test_p12_reproduction_on_dataset():  # M1 acceptance
    from scripts.repro_p12 import run

    res = run()
    c = res["counts"]
    assert c["EXACT"] == 1958
    assert c["SAME_USER_OTHER_ID"] == 353
    assert c["UNKNOWN_DECOY"] == 24
    assert c["OTHER_USER"] == 4
    assert res["requests"] == 550 and res["unresolved"] == []
