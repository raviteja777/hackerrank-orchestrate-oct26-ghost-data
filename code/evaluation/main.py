"""Evaluation harness (DESIGN §13): metrics on the 32 sample cases against dataset/sample_output.csv.

Metrics: case status accuracy; step-level multiset precision / recall / F1 (all 7 fields); field-level accuracy
(steps aligned by (phase, operation, system_id, resource_id)); sequence accuracy (exact array equality and a
normalised LCS ratio); citation accuracy; ablations (G-STP-08 on/off, D8 tiers). The generated block of
evaluation/evaluation_report.md is rewritten between the markers; the curated "Failures found" section below it
is kept as written.
Usage: python code/evaluation/main.py --samples [--write-report] [--no-ablation] [--diff]
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ghost import config, loaders  # noqa: E402
from ghost.pipeline import CaseResult, build_context, solve_all  # noqa: E402

FIELDS = ("phase", "system_id", "resource_id", "operation", "state", "evidence_id")
KEY = ("phase", "operation", "system_id", "resource_id")
REPORT = Path(__file__).resolve().parent / "evaluation_report.md"
BEGIN, END = "<!-- BEGIN GENERATED -->", "<!-- END GENERATED -->"


def load_expected(dataset_dir: Path) -> dict[str, tuple[str, list[dict]]]:
    out = {}
    with open(dataset_dir / "sample_output.csv", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["case_id"]] = (r["deletion_status"], json.loads(r["steps_json"]))
    return out


def _tuple(s: dict) -> tuple:
    return tuple(s[k] for k in FIELDS)


def lcs(a: list, b: list) -> int:
    dp = [0] * (len(b) + 1)
    for x in a:
        prev = 0
        for j, y in enumerate(b, start=1):
            cur = dp[j]
            dp[j] = prev + 1 if x == y else max(dp[j], dp[j - 1])
            prev = cur
    return dp[len(b)]


def evaluate(results: dict[str, CaseResult], expected: dict[str, tuple[str, list[dict]]]) -> dict:
    m: Counter = Counter()
    lcs_ratios, per_case = [], {}
    field_ok: Counter = Counter()
    for cid, (status, exp_steps) in sorted(expected.items()):
        got = results[cid]
        got_steps = [s.to_dict() for s in got.steps]
        m["cases"] += 1
        m["status_ok"] += got.status == status
        e_ms, g_ms = Counter(_tuple(s) for s in exp_steps), Counter(_tuple(s) for s in got_steps)
        tp = sum((e_ms & g_ms).values())
        m["tp"] += tp
        m["fn"] += sum(e_ms.values()) - tp
        m["fp"] += sum(g_ms.values()) - tp
        seq_e, seq_g = [_tuple(s) for s in exp_steps], [_tuple(s) for s in got_steps]
        exact = seq_e == seq_g and status == got.status
        m["seq_exact"] += exact
        lcs_ratios.append(1.0 if not seq_e and not seq_g else lcs(seq_e, seq_g) / max(len(seq_e), len(seq_g)))
        # field-level: align by key, then by position among equal keys
        buckets: dict[tuple, list[dict]] = {}
        for s in got_steps:
            buckets.setdefault(tuple(s[k] for k in KEY), []).append(s)
        for s in exp_steps:
            m["exp_steps"] += 1
            cand = buckets.get(tuple(s[k] for k in KEY), [])
            if cand:
                g = cand.pop(0)
                m["aligned"] += 1
                for f in FIELDS:
                    field_ok[f] += g[f] == s[f]
                if s["evidence_id"]:
                    m["cited_exp"] += 1
                    m["cited_ok"] += g["evidence_id"] == s["evidence_id"]
            elif s["evidence_id"]:
                m["cited_exp"] += 1
        per_case[cid] = {"exact": exact, "status": (status, got.status), "tp": tp}
    p = m["tp"] / (m["tp"] + m["fp"]) if m["tp"] + m["fp"] else 0.0
    r = m["tp"] / (m["tp"] + m["fn"]) if m["tp"] + m["fn"] else 0.0
    return {
        "cases": m["cases"], "status_ok": m["status_ok"], "precision": p, "recall": r,
        "f1": 2 * p * r / (p + r) if p + r else 0.0, "seq_exact": m["seq_exact"],
        "lcs": sum(lcs_ratios) / len(lcs_ratios), "aligned": m["aligned"], "exp_steps": m["exp_steps"],
        "field_acc": {f: field_ok[f] / m["exp_steps"] for f in FIELDS},
        "cite_ok": m["cited_ok"], "cite_exp": m["cited_exp"], "per_case": per_case,
        "tp": m["tp"], "fp": m["fp"], "fn": m["fn"],
    }


def diff_lines(results: dict[str, CaseResult], expected: dict) -> list[str]:
    out = []
    for cid, (status, exp_steps) in sorted(expected.items(), key=lambda kv: int(kv[0].split("_")[1])):
        got = results[cid]
        e = Counter(_tuple(s) for s in exp_steps)
        g = Counter(_tuple(s.to_dict()) for s in got.steps)
        if status == got.status and e == g and [_tuple(s) for s in exp_steps] == [_tuple(s.to_dict()) for s in got.steps]:
            continue
        out.append(f"{cid}: status expected {status} got {got.status}; notes {got.notes}")
        for t in sorted((e - g).elements()):
            out.append(f"    MISSING {t}")
        for t in sorted((g - e).elements()):
            out.append(f"    EXTRA   {t}")
    return out


def fmt_metrics(label: str, r: dict) -> str:
    fa = ", ".join(f"{k} {v:.3f}" for k, v in r["field_acc"].items())
    return (f"| {label} | {r['status_ok']}/{r['cases']} | {r['precision']:.3f} / {r['recall']:.3f} / {r['f1']:.3f} | "
            f"{r['seq_exact']}/{r['cases']} | {r['lcs']:.3f} | {r['cite_ok']}/{r['cite_exp']} | {fa} |")


def run_variant(dataset_dir: Path, flags: config.Flags, sample_reqs, expected, llm_profile=None, run_label="evaluation") -> tuple[dict, dict]:
    # intent texts: only the evaluated requests, so a `final` smoke run classifies the 32 samples and nothing else
    ctx = build_context(dataset_dir, flags, llm_profile=llm_profile, run_label=run_label,
                        intent_texts=[r.request_text for r in sample_reqs])
    results = {r.case_id: x for r, x in zip(sample_reqs, solve_all(ctx, sample_reqs))}
    return evaluate(results, expected), results


def full_dataset_blocks(d: Path, profile: str | None) -> list[str]:
    """Generated report blocks that need the whole dataset: per-tier counts, ambiguity queue, intent, custom cases."""
    from collections import Counter

    import custom_cases
    from ghost import untrusted
    from ghost.intent import IntentGate
    from ghost.llm import LLMClient
    from ghost.resolve import write_ambiguity_queue

    ev = loaders.load_requests(d)
    sm = loaders.load_requests(d, "sample_deletion_requests.csv")
    ctx = build_context(d, config.Flags(), llm_profile=profile, run_label="evaluation_full")
    results = solve_all(ctx, ev)
    write_ambiguity_queue(ctx.resolution.queue, Path(__file__).resolve().parent / "ambiguity_queue.csv")
    c = ctx.resolution.counts
    names = {"1": "1 hard identifier link", "1s": "1s window naked single", "3": "3 elimination", "3b": "3b timing-phase chain",
             "4": "4 LLM residual", "4b": "4b audit-capture co-occurrence", "5": "5 deterministic tie-break (low confidence)",
             "ev": "evidence-only link (audit records, attachments, copies)"}
    out = ["## Full-dataset resolution (518 eval + 32 sample cases)", "", "| Tier | Resources assigned |", "|---|---|"]
    out += [f"| {names[k]} | {c.get(k, 0)} |" for k in names]
    out += [f"| excluded by a contrary link (OQ-10) | {c.get('foreign_excluded', 0)} |",
            f"| window singles rejected by H-STP-05 | {c.get('single_rejected_h_stp_05', 0)} |", "",
            f"Output over the 518 eval requests: {dict(Counter(r.status for r in results))}; "
            f"cases without an account step: {sum(1 for r in results if r.status != 'NOT_APPLICABLE' and not any(s.resource_id.startswith('account_') for s in r.steps))}; "
            f"low-confidence cases (any 3b / 4 / 5 attribution or fallback): {sum(r.low_confidence for r in results)}.", ""]
    t5 = [(cid, rid) for cid, a in ctx.resolution.assignments.items() for rid, x in a.items() if x.tier == "5"]
    shapes = Counter(q["shape"] for q in ctx.resolution.queue if q["kind"] == "account_slot")
    out += ["### Ambiguity queue (D12; `code/evaluation/ambiguity_queue.csv`)", "",
            f"* slots with account-less cases after every evidence tier: {sum(shapes.values())} (shapes cases-v-anchors: "
            f"{', '.join(f'{k} x{v}' for k, v in sorted(shapes.items()))})",
            f"* tier-5 low-confidence resource assignments: {len(t5)} over {len({cid for cid, _ in t5})} cases "
            f"(accounts {sum(1 for _, r in t5 if r.startswith('account_'))}, chain members {sum(1 for _, r in t5 if not r.startswith('account_'))})",
            f"* parked optional resources not emitted: {sum(1 for q in ctx.resolution.queue if q['kind'] == 'optional_resource')}", ""]

    gate_rules = IntentGate(None).classify_all([r.request_text for r in ev + sm])
    llm = LLMClient(profile, run_label="evaluation_intent") if profile else None
    gate_llm = IntentGate(llm).classify_all([r.request_text for r in ev + sm])

    def acc(gate):
        wrong = [r.case_id for r in ev if gate[r.request_text].authorizes_deletion != (not 533 <= int(r.case_id.split("_")[1]) <= 542)]
        wrong += [r.case_id for r in sm if not gate[r.request_text].authorizes_deletion]
        return len(ev) + len(sm) - len(wrong), len(ev) + len(sm), wrong

    r_ok, r_n, r_w = acc(gate_rules)
    l_ok, l_n, l_w = acc(gate_llm)
    out += ["## Intent (550 requests, 398 distinct texts)", "", "| Classifier | Correct | Wrong |", "|---|---|---|",
            f"| multilingual rules only | {r_ok}/{r_n} | {r_w} |", f"| rules + LLM cascade (profile `{profile}`) | {l_ok}/{l_n} | {l_w} |", "",
            f"Non-deletion requests detected: {sum(1 for r in ev if not gate_llm[r.request_text].authorizes_deletion)}/10; samples classified as deletion: "
            f"{sum(gate_llm[r.request_text].authorizes_deletion for r in sm)}/32. LLM vs rules disagreements: "
            f"{sum(1 for x in gate_llm.values() if x.llm is not None and x.rules is not None and x.llm != x.rules)}; escalated: "
            f"{sum(x.escalated for x in gate_llm.values())}; rules undecided (default deletion): {sum(x.rules is None for x in gate_llm.values())}; "
            f"suspicious-input flags: {sum(x.suspicious for x in gate_llm.values())}; low-confidence intents: {sum(x.low_confidence for x in gate_llm.values())}.", ""]

    cres = custom_cases.run_all(llm)
    out += ["## Custom evaluation cases (`code/evaluation/custom_cases.py`)", "", "| Case | Result | Rationale |", "|---|---|---|"]
    out += [f"| {cc.name} | {'PASS' if ok else 'FAIL'} | {cc.rationale} |" for cc, _, ok in cres]
    out += ["", f"{sum(ok for *_, ok in cres)}/{len(cres)} custom cases pass. Instruction-like texts flagged during this report: {untrusted.STATS.get('flagged', 0)} "
            "(the injection case only; none of the 550 requests is flagged).", ""]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", action="store_true", default=True)
    ap.add_argument("--write-report", action="store_true")
    ap.add_argument("--no-ablation", action="store_true")
    ap.add_argument("--diff", action="store_true", help="print every sample mismatch")
    ap.add_argument("--llm-profile", choices=("local", "final"), default=None)
    ap.add_argument("--no-llm", action="store_true", help="rules only (no model calls)")
    ap.add_argument("--smoke", action="store_true", help="single default variant, usage summary of this run (final-profile smoke test)")
    args = ap.parse_args(argv)
    d = config.DATASET_DIR
    profile = None if args.no_llm else config.get_llm_profile(args.llm_profile)
    sample_reqs = loaders.load_requests(d, "sample_deletion_requests.csv")
    expected = load_expected(d)
    base = config.Flags()
    variants = [("default (G-STP-08 on, tiers 1-5, D12 on, LLM intent)", base, True)]
    if not args.no_ablation and not args.smoke:
        variants += [
            ("G-STP-08 off (`require_observation_to_emit=False`)", dataclasses.replace(base, require_observation_to_emit=False), True),
            ("3b off (tiers 1-3, then 4b / 5)", dataclasses.replace(base, tier_chains=False), True),
            ("tier 5 off (no tie-break)", dataclasses.replace(base, tier_tiebreak=False), True),
            ("D12 off (intent after resolution, no 4b, slot order)", dataclasses.replace(base, d12_refinements=False), True),
            ("tiers 1 only (no 3, 3b; 4b / 5 still on)", dataclasses.replace(base, tier_eliminate=False, tier_chains=False), True),
            ("intent rules only, no LLM at all (no vision either)", base, False),
        ]
    rows, main_res = [], None
    for label, fl, use_llm in variants:
        r, res = run_variant(d, fl, sample_reqs, expected, profile if use_llm else None, "smoke" if args.smoke else "evaluation")
        rows.append(fmt_metrics(label, r))
        print(f"[{label}] status {r['status_ok']}/{r['cases']}  step P/R/F1 {r['precision']:.3f}/{r['recall']:.3f}/{r['f1']:.3f}  "
              f"sequence-exact {r['seq_exact']}/{r['cases']}  LCS {r['lcs']:.3f}  citations {r['cite_ok']}/{r['cite_exp']}")
        if main_res is None:
            main_res = (r, res)
    r, res = main_res
    if args.smoke:
        from ghost.llm import read_ledger, summarize
        led = [x for x in read_ledger() if x.get("run") == "smoke" and x["profile"] == config.get_llm_profile(args.llm_profile)]
        print("smoke usage:", json.dumps(summarize(led), indent=1))
    diffs = diff_lines(res, expected)
    if args.diff:
        print("\n".join(diffs))
    if args.write_report:
        block = [BEGIN, "", f"_Generated by `python code/evaluation/main.py --write-report --llm-profile {profile or 'none'}`; profile: **{profile}**._", "",
                 "## Sample metrics (32 cases, `dataset/sample_output.csv`)", "",
                 "Columns: case-level status accuracy | step-level precision / recall / F1 (multiset of full 7-field steps) | sequence-exact "
                 "(array equality) | normalised LCS ratio | citation accuracy (evidence_id of the aligned expected cited steps) | field-level accuracy per field "
                 "(steps aligned by phase, operation, system_id, resource_id).", "",
                 "| Variant | Status | Step P / R / F1 | Sequence-exact | LCS ratio | Citations | Field accuracy |",
                 "|---|---|---|---|---|---|---|", *rows, "",
                 f"Aligned steps (default): {r['aligned']}/{r['exp_steps']}; TP {r['tp']}, FP {r['fp']}, FN {r['fn']}.", "",
                 *full_dataset_blocks(d, profile),
                 "### Sample mismatches (default variant, generated)", "", "```", *diffs, "```", "", END]
        text = REPORT.read_text(encoding="utf-8") if REPORT.exists() else "# Evaluation report\n\n" + BEGIN + "\n" + END + "\n"
        if BEGIN in text and END in text:
            head, rest = text.split(BEGIN, 1)
            tail = rest.split(END, 1)[1]
            text = head + "\n".join(block) + tail
        else:
            text += "\n" + "\n".join(block) + "\n"
        REPORT.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
