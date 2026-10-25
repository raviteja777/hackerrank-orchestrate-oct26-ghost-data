"""CLI entry: run the pipeline and write ./output.csv (DESIGN §2, §3, §14).

Pipeline (M4): evidence -> facts -> edge log -> case resources (D8 tiers) -> state -> policy -> citations ->
steps; rows in input order (D1, H-ORD-01). Intent: multilingual rules + LLM cascade (M5). Usage: python code/main.py [--dataset DIR] [--output FILE] [--llm-profile local|final] [--no-validate]
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ghost import config, loaders, steps, validate  # noqa: E402
from ghost.pipeline import build_context, solve_all  # noqa: E402
from ghost.resolve import write_ambiguity_queue  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ghost Data Still Exists: deletion-audit agent")
    ap.add_argument("--dataset", type=lambda p: Path(p), default=config.DATASET_DIR)
    ap.add_argument("--output", type=lambda p: Path(p), default=config.OUTPUT_PATH)
    ap.add_argument("--llm-profile", choices=("local", "final"), default=None)
    ap.add_argument("--no-validate", action="store_true")
    ap.add_argument("--run-label", default="main", help="label written to the usage ledger (usage_report.md filters on it)")
    ap.add_argument("--no-llm", action="store_true", help="rules only: no model calls")
    args = ap.parse_args(argv)

    profile = config.get_llm_profile(args.llm_profile)
    requests = loaders.load_requests(args.dataset)  # D1: output order = input order
    ctx = build_context(args.dataset, llm_profile=None if args.no_llm else profile, run_label=args.run_label)
    results = solve_all(ctx, requests)
    write_ambiguity_queue(ctx.resolution.queue, config.REPO_ROOT / "code" / "evaluation" / "ambiguity_queue.csv")
    rows = [(r.case_id, r.status, r.steps_json()) for r in results]
    steps.write_output(rows, args.output)
    print(f"wrote {len(rows)} rows to {args.output} (llm profile: {profile})")
    print("status counts:", dict(Counter(r.status for r in results)),
          "| low-confidence cases:", sum(r.low_confidence for r in results),
          "| cases without an account step:", sum(1 for r in results if r.status != "NOT_APPLICABLE"
                                                   and not any(s.resource_id.startswith("account_") for s in r.steps)))
    for w in (p for p in ctx.store.parser_report if p["warn"]):
        print(f"WARNING parser self-check: {w['path']} only {w['share']:.0%} of lines carrying a resource id or "
              f"identifier have a trace id ({w['orphans']}/{w['carrying']} orphans)", file=sys.stderr)

    if args.no_validate:
        return 0
    issues = validate.validate_output(
        args.output, requests, loaders.load_evidence_manifest(args.dataset),
        loaders.load_activity(args.dataset), loaders.load_audit_log(args.dataset),
    )
    if issues:
        for i in issues[:50]:
            print(i, file=sys.stderr)
        print(f"VALIDATION FAILED: {len(issues)} issue(s)", file=sys.stderr)
        return 1
    print("validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
