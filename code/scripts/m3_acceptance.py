"""M3 acceptance (DESIGN §14): tiers 1-3b of the case-resource resolution, per-tier counts, the 3b ablation.

Compares with the probes: P13 (927 hard links, +70 elimination), P14 (eval accounts 361/518, sample
precision 38/39). The probes used a simpler fact index, so +-5% is expected; larger gaps are explained, not tuned.
Usage: python code/scripts/m3_acceptance.py
"""
from __future__ import annotations

import csv
import dataclasses
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ghost import config, loaders  # noqa: E402
from ghost.edgelog import EdgeLog  # noqa: E402
from ghost.evidence.normalize import build_fact_store  # noqa: E402
from ghost.identity import IdentityIndex  # noqa: E402
from ghost.resolve import make_cases, resolve  # noqa: E402
from ghost.runs import RunIndex, run_events  # noqa: E402


def load(dataset_dir=None):
    d = dataset_dir or config.DATASET_DIR
    index = IdentityIndex.from_dataset(d)
    store = build_fact_store(d, index)
    activity = loaders.load_activity(d)
    reqs = loaders.load_requests(d)
    samples = loaders.load_requests(d, "sample_deletion_requests.csv")
    cases = make_cases(index, reqs, samples)
    slots: dict = {}
    for c in cases:
        slots.setdefault(c.reported_at, []).append(c.case_id)
    return index, store, activity, cases, slots, d


def truth(d) -> dict[str, set[str]]:
    out = {}
    with open(d / "sample_output.csv", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["case_id"]] = {s["resource_id"] for s in json.loads(r["steps_json"]) if s["system_id"] != "security_service"}
    return out


def run_config(label: str, flags: config.Flags, ctx) -> dict:
    index, store, activity, cases, slots, d = ctx
    edges = EdgeLog.build(index, store, activity)
    runs = RunIndex(run_events(activity), slots, flags.chain_policy_band, flags.chain_final_band)
    res = resolve(cases, runs, edges, flags)
    tr = truth(d)
    found = wrong = total = 0
    for c in cases:
        if not c.sample:
            continue
        got = set(res.resources_of(c.case_id, include_evidence=False))
        total += len(tr[c.case_id])
        found += len(tr[c.case_id] & got)
        wrong += len(got - tr[c.case_id])
    # evidence-only assignments for samples (non-audit part)
    ev_found = ev_wrong = 0
    for c in cases:
        if c.sample:
            got = {r for r, a in res.resources_of(c.case_id).items() if a.tier == "ev" and not r.startswith("audit_record_")}
            ev_found += len(tr[c.case_id] & got)
            ev_wrong += len(got - tr[c.case_id])
    eval_cases = [c for c in cases if not c.sample]
    acc = sum(res.case_has_account(c.case_id) for c in eval_cases)
    samp_acc = sum(res.case_has_account(c.case_id) for c in cases if c.sample)
    return {"label": label, "res": res, "eval_accounts": acc, "sample_accounts": samp_acc, "truth": total, "found": found,
            "wrong": wrong, "ev_found": ev_found, "ev_wrong": ev_wrong, "runs": runs, "n_eval": len(eval_cases)}


def show(r: dict) -> None:
    res = r["res"]
    print(f"[{r['label']}] resources/tier {dict(sorted(res.counts.items()))}  events/tier {dict(sorted(res.event_counts.items()))}")
    print(f"   eval cases with an account: {r['eval_accounts']}/{r['n_eval']}  sample cases with an account: {r['sample_accounts']}/32")
    prec = f"{r['found']}/{r['found'] + r['wrong']}"
    print(f"   sample run-resource precision {prec}  recall {r['found']}/{r['truth']}  "
          f"(evidence-only non-audit: {r['ev_found']} right, {r['ev_wrong']} not in the answer)  parked: {len(res.parked)}")


def main() -> int:
    ctx = load()
    base = config.Flags()
    configs = [
        ("tier 1 only", dataclasses.replace(base, tier_eliminate=False, tier_chains=False)),
        ("tiers 1-3", dataclasses.replace(base, tier_chains=False)),
        ("tiers 1-3 + 3b", base),
    ]
    results = []
    for label, fl in configs:
        r = run_config(label, fl, ctx)
        show(r)
        results.append(r)
    final = results[-1]
    print("notes:", final["res"].notes)
    print("3b ablation: eval accounts", results[1]["eval_accounts"], "->", final["eval_accounts"],
          "| sample precision", f"{results[1]['found']}/{results[1]['found'] + results[1]['wrong']}", "->",
          f"{final['found']}/{final['found'] + final['wrong']}")
    # band sensitivity (documented in OPEN_QUESTIONS if it matters)
    wide = dataclasses.replace(base, chain_policy_band=(8, 12), chain_final_band=(19, 23))
    show(run_config("tiers 1-3 + 3b, bands 8-12 / 19-23 (P14 probe)", wide, ctx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
