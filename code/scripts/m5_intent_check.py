"""M5 acceptance: intent classification on all 550 request texts (518 eval + 32 samples).

Expected (G-INT-01): case_533..case_542 are NOT deletion requests, every other eval request and every sample is.
Reports rules-only accuracy, LLM agreement, escalations and the suspicious-input count for the chosen profile.
Usage: python code/scripts/m5_intent_check.py [--profile local|final|none]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ghost import config, loaders, untrusted  # noqa: E402
from ghost.intent import IntentGate  # noqa: E402
from ghost.llm import LLMClient, read_ledger, summarize  # noqa: E402


def expected(case_id: str, sample: bool) -> bool:
    n = int(case_id.split("_")[1])
    return True if sample else not (533 <= n <= 542)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="local", choices=("local", "final", "none"))
    args = ap.parse_args(argv)
    ev = loaders.load_requests(config.DATASET_DIR)
    sm = loaders.load_requests(config.DATASET_DIR, "sample_deletion_requests.csv")
    llm = None if args.profile == "none" else LLMClient(args.profile, run_label="m5_intent")
    gate = IntentGate(llm)
    t0 = time.time()
    res = gate.classify_all([r.request_text for r in ev + sm])
    wrong, tp_nd = [], 0
    for r, sample in [(r, False) for r in ev] + [(r, True) for r in sm]:
        got = res[r.request_text].authorizes_deletion
        if got != expected(r.case_id, sample):
            wrong.append(r.case_id)
        tp_nd += (not got) and not sample
    c = Counter(x.source for x in res.values())
    print(f"profile={args.profile} distinct texts={len(res)} time={time.time() - t0:.0f}s sources={dict(c)}")
    print(f"non-deletion detected: {tp_nd}/10; samples classified as deletion: "
          f"{sum(res[r.request_text].authorizes_deletion for r in sm)}/{len(sm)}; wrong overall: {wrong}")
    print(f"escalated: {sum(x.escalated for x in res.values())}; llm vs rules disagreements: "
          f"{sum(1 for x in res.values() if x.llm is not None and x.rules is not None and x.llm != x.rules)}; "
          f"llm answered: {sum(x.llm is not None for x in res.values())}; suspicious flagged: "
          f"{sum(x.suspicious for x in res.values())}")
    if llm:
        print("usage:", summarize([r for r in read_ledger() if r.get("run") == "m5_intent" and r["profile"] == args.profile]))
    return 0 if not wrong and tp_nd == 10 else 1


if __name__ == "__main__":
    sys.exit(main())
