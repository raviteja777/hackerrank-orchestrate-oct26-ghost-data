import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from ghost import config
from ghost.edgelog import EdgeLog
from ghost.resolve import Case, resolve
from ghost.runs import ANCHOR, FINAL, POLICY, RunEvent, RunIndex, classify, in_window

T0 = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
AUDIT = T0 + timedelta(days=13)


def ev(aid, rid, minutes, kind, seconds=0):
    return RunEvent(aid, T0 + timedelta(minutes=minutes, seconds=seconds), rid, kind, "SUCCESS", "DELETE_RECORD")


def case(cid, user, reported=T0):
    return Case(cid, user, reported, AUDIT)


def link(edges, rid, user, when=T0 - timedelta(days=1)):
    edges.add_resource_user(rid, user, when, "fact")


def run(cases, events, edges, **flags):
    slots = {}
    for c in cases:
        slots.setdefault(c.reported_at, []).append(c.case_id)
    runs = RunIndex(events, slots)
    return resolve(cases, runs, edges, dataclasses.replace(config.Flags(), **{"tier_tiebreak": False, **flags}))


def test_classify_and_windows():
    assert classify("Deletion worker submitted primary profile account_1 to account_service.") == ANCHOR
    assert classify("Policy action completed for analytics_1.") == POLICY
    assert classify("Deletion worker received the final result for search_1 from search_service.") == FINAL
    assert classify("Deletion worker reported the requested operation as completed. Target resource: x_1.") == "scenario"
    assert in_window(ev("a", "account_1", -60, ANCHOR), T0)
    assert not in_window(ev("a", "account_1", -30, ANCHOR), T0)  # anchor window is -80..-40
    assert in_window(ev("a", "x_1", 125, FINAL), T0) and not in_window(ev("a", "x_1", 126, FINAL), T0)


def test_edge_log_time_cutoff_is_inclusive():  # D3, H-TIM-03
    e = EdgeLog()
    e.add_resource_user("search_1", "user_1", AUDIT, "fact")
    assert e.users_of("search_1", AUDIT) == {"user_1"}
    assert e.users_of("search_1", AUDIT - timedelta(seconds=1)) == set()
    e.add("a", "mentions", "b", AUDIT, "x")
    assert len(e.as_of(AUDIT)) == 1 and len(e.as_of(AUDIT - timedelta(seconds=1))) == 0
    assert e.to_networkx(AUDIT).number_of_edges() == 1


def test_tier1_hard_link_picks_the_linked_case():
    cases = [case("c1", "u1"), case("c2", "u2")]
    e = EdgeLog()
    link(e, "search_1", "u2")
    r = run(cases, [ev("act1", "search_1", 60, FINAL)], e)
    assert r.assignments["c2"]["search_1"].tier == "1" and "c1" not in r.assignments


def test_foreign_link_excludes_the_only_candidate():  # OQ-10
    cases = [case("c1", "u1")]
    e = EdgeLog()
    link(e, "account_9", "u_other")
    evs = [ev("act1", "account_9", -60, ANCHOR)]
    assert run(cases, evs, e).assignments.get("c1") in (None, {})
    r = run(cases, evs, e, exclude_foreign_links=False)  # without the exclusion it is a naked single
    assert r.assignments["c1"]["account_9"].tier == "1s"


def test_elimination_gives_the_remaining_account_to_the_remaining_case():  # H-STP-02
    cases = [case("c1", "u1"), case("c2", "u2")]
    e = EdgeLog()
    link(e, "account_1", "u1")
    evs = [ev("a1", "account_1", -70, ANCHOR), ev("a2", "account_2", -60, ANCHOR)]
    r = run(cases, evs, e, tier_chains=False)
    assert r.assignments["c1"]["account_1"].tier == "1"
    assert r.assignments["c2"]["account_2"].tier == "3"
    r = run(cases, evs, e, tier_eliminate=False, tier_chains=False)
    assert "c2" not in r.assignments and "account_2" in r.parked  # tier 2: parked with its candidates


def test_chain_by_timing_phase_carries_an_identifier_link():  # W-LNK-05
    cases = [case("c1", "u1"), case("c2", "u2")]
    e = EdgeLog()
    link(e, "support_1", "u2")  # the follow-up is linked to c2's user, the anchor is not linked at all
    evs = [
        ev("a1", "account_1", -70, ANCHOR, 0),
        ev("a2", "account_2", -60, ANCHOR, 5),
        ev("p1", "support_1", -28, POLICY, 5 + 10),  # (t - a2) mod 30 s == 10 s after a2... see below
    ]
    # a2 is at -60:00+5s, p1 at -28:00+15s -> difference 32 min 10 s -> 10 s mod 30: matches a2 only
    r = run(cases, evs, e, tier_eliminate=False)
    assert r.assignments["c2"]["account_2"].tier == "3b"
    assert r.assignments["c2"]["support_1"].tier == "1"
    r = run(cases, evs, e, tier_eliminate=False, tier_chains=False)
    assert "account_2" not in r.assignments.get("c2", {})


def test_evidence_only_resources_are_added_when_linked():  # G-LNK-01, H-LNK-02
    cases = [case("c1", "u1")]
    e = EdgeLog()
    link(e, "audit_record_7", "u1")
    link(e, "audit_record_8", "u1", when=AUDIT + timedelta(days=1))  # later than audit_at: unknown (D3)
    r = run(cases, [], e)
    assert set(r.assignments["c1"]) == {"audit_record_7"} and r.assignments["c1"]["audit_record_7"].tier == "ev"
    assert not run(cases, [], e, evidence_only_links=False).assignments


def test_tier5_tiebreak_pairs_anchors_by_time_with_cases_by_number():  # DESIGN §8.3 step 6
    cases = [case("case_10", "u1"), case("case_9", "u2")]  # numeric order: case_9 < case_10 (not lexical)
    evs = [ev("a2", "account_2", -60, ANCHOR), ev("a1", "account_1", -70, ANCHOR)]
    r = run(cases, evs, EdgeLog(), tier_tiebreak=True, tier_eliminate=False, tier_chains=False, exclude_foreign_links=False)
    # earliest anchor (account_1) -> lowest case number (case_9), next anchor -> case_10; both low confidence
    assert r.assignments["case_9"]["account_1"].tier == "5" and r.assignments["case_10"]["account_2"].tier == "5"
    assert not run(cases, evs, EdgeLog(), tier_tiebreak=False, tier_eliminate=False, tier_chains=False).assignments


def test_tier4_llm_only_for_content_residuals_and_validated():
    from ghost.facts import Fact, FactStore
    cases = [case("c1", "u1"), case("c2", "u2")]
    evs = [ev("a1", "analytics_1", -28, POLICY), ev("a2", "analytics_2", -21, POLICY)]
    store = FactStore()
    store.add(Fact("f#1", "f", T0, T0, "png", "1", resource_id="analytics_1", fields={"ocr_text": "contact someone@x.io"}))
    calls = []

    def decider(rid, cands, snippets):
        calls.append(rid)
        return "c2" if rid == "analytics_1" else "zzz"  # an answer that is not a candidate must be ignored

    slots = {T0: ["c1", "c2"]}
    runs = RunIndex(evs, slots)
    r = resolve(cases, runs, EdgeLog(), dataclasses.replace(config.Flags(), tier_tiebreak=False, tier_chains=False), store, decider)
    assert calls == ["analytics_1"]  # analytics_2 has no unstructured content: no model call
    assert r.assignments["c2"]["analytics_1"].tier == "4"


# ---- dataset acceptance (M3) ------------------------------------------------------------------------------
@pytest.mark.skipif(not (config.DATASET_DIR / "system_activity.csv").exists(), reason="dataset not present")
def test_m3_acceptance_on_dataset():
    from scripts import m3_acceptance as acc

    ctx = acc.load()
    r = acc.run_config("full", config.Flags(), ctx)
    assert r["found"] / (r["found"] + r["wrong"]) >= 38 / 39  # P14 sample precision
    assert r["eval_accounts"] >= 361
    assert r["res"].counts["1"] >= 0.95 * 927  # P13 hard links (M2 parses more log layouts, so more is expected)
    base = acc.run_config("1-3", dataclasses.replace(config.Flags(), tier_chains=False), ctx)
    assert r["eval_accounts"] > base["eval_accounts"]  # 3b ablation


def test_d12_tier4b_cooccurrence_and_most_constrained_first_with_queue():
    from datetime import timedelta as td
    from ghost.facts import Fact, FactStore
    r1 = T0 + td(days=1)
    cases = [Case("case_5", "u1", T0, r1), Case("case_6", "u2", T0, r1 + td(days=3))]
    evs = [ev("a1", "account_1", -70, ANCHOR), ev("a2", "account_2", -60, ANCHOR)]
    store = FactStore()  # account_2 is mentioned only in a file captured 1 h before case_6's audit_at
    store.add(Fact("f#1", "f", r1 + td(days=3, hours=-1), r1 + td(days=3, hours=-1), "log", "1", resource_id="account_2"))
    flags = dataclasses.replace(config.Flags(), tier_chains=False, tier_eliminate=False)
    res = resolve(cases, RunIndex(evs, {T0: ["case_5", "case_6"]}), EdgeLog(), flags, store)
    assert res.assignments["case_6"]["account_2"].tier == "4b"  # exactly one candidate fits the 24 h window
    assert res.assignments["case_5"]["account_1"].tier == "5"  # the rest goes to the tie-break (low confidence)
    assert res.queue and res.queue[0]["shape"] == "1v1"
    off = resolve(cases, RunIndex(evs, {T0: ["case_5", "case_6"]}), EdgeLog(), dataclasses.replace(flags, d12_refinements=False), store)
    assert off.assignments["case_5"]["account_1"].tier == "5" and "4b" not in {a.tier for x in off.assignments.values() for a in x.values()}
