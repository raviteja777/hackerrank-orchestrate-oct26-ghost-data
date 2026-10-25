"""CLI entry: run the pipeline and write ./output.csv (DESIGN §2, §3, §14).

Milestone M0: every case is a NOT_APPLICABLE / [] placeholder in input row order (D1, H-ORD-01).
Usage: python code/main.py [--dataset DIR] [--output FILE] [--llm-profile local|final] [--no-validate]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ghost import config, loaders, steps, validate  # noqa: E402


def build_rows(requests: list[loaders.DeletionRequest]) -> list[tuple[str, str, str]]:
    # M0 placeholder: later milestones replace this with the real pipeline.
    return [(r.case_id, "NOT_APPLICABLE", "[]") for r in requests]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ghost Data Still Exists: deletion-audit agent")
    ap.add_argument("--dataset", type=lambda p: Path(p), default=config.DATASET_DIR)
    ap.add_argument("--output", type=lambda p: Path(p), default=config.OUTPUT_PATH)
    ap.add_argument("--llm-profile", choices=("local", "final"), default=None)
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args(argv)

    profile = config.get_llm_profile(args.llm_profile)
    requests = loaders.load_requests(args.dataset)  # D1: output order = input order
    rows = build_rows(requests)
    steps.write_output(rows, args.output)
    print(f"wrote {len(rows)} rows to {args.output} (llm profile: {profile})")

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
