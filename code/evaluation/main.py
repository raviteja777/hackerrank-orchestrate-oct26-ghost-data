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
    sample_reqs = loaders.load_requests(d, "sample_deletion_requests.csv")
    expected = load_expected(d)
    base = config.Flags()
    variants = [("default (G-STP-08 on, tiers 1-3b)", base)]
    if not args.no_ablation and not args.smoke:
        variants += [
            ("G-STP-08 off (`require_observation_to_emit=False`)", dataclasses.replace(base, require_observation_to_emit=False)),
            ("tiers 1-3 (no 3b)", dataclasses.replace(base, tier_chains=False)),
            ("tier 1 only", dataclasses.replace(base, tier_eliminate=False, tier_chains=False)),
        ]
    rows, main_res = [], None
    for label, fl in variants:
        r, res = run_variant(d, fl, sample_reqs, expected, None if args.no_llm else config.get_llm_profile(args.llm_profile),
                             "smoke" if args.smoke else "evaluation")
        rows.append(fmt_metrics(label, r))
        print(f"[{label}] status {r['status_ok']}/{r['cases']}  step P/R/F1 {r['precision']:.3f}/{r['recall']:.3f}/{r['f1']:.3f}  "
              f"sequence-exact {r['seq_exact']}/{r['cases']}  LCS {r['lcs']:.3f}  citations {r['cite_ok']}/{r['cite_exp']}")
        if main_res is None:
            main_res = (r, res)
    r, res = main_res
    if args.smoke:
        from ghost.llm import read_ledger, summarize
        rows = [x for x in read_ledger() if x.get("run") == "smoke" and x["profile"] == config.get_llm_profile(args.llm_profile)]
        print("smoke usage:", json.dumps(summarize(rows), indent=1))
    diffs = diff_lines(res, expected)
    if args.diff:
        print("\n".join(diffs))
    if args.write_report:
        block = [BEGIN, "", "## Sample metrics (32 cases, `dataset/sample_output.csv`)", "",
                 "| Variant | Status | Step P / R / F1 | Sequence-exact | LCS ratio | Citations | Field accuracy |",
                 "|---|---|---|---|---|---|---|", *rows, "",
                 f"Aligned steps (default): {r['aligned']}/{r['exp_steps']}; TP {r['tp']}, FP {r['fp']}, FN {r['fn']}.", "",
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
