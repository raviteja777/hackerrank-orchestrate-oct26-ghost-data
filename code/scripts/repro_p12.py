"""Reproduce probe P12 (H-IDN-04): substring candidates vs exact validation over all text evidence.

Expected on the dataset: 1,958 exact / 353 same-user other id / 24 unknown decoys / 4 other-user
look-alikes (emails), and all request emails (518 eval + 32 sample) resolve.
Scope (confirmed by the user): text evidence formats only (json, sql, log, txt). PDFs and PNGs
are deliberately excluded from this baseline (PDFs would add 2 exact emails); they are handled in M2.
Usage: python code/scripts/repro_p12.py
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ghost import config, loaders  # noqa: E402
from ghost.identity import IdentityIndex, Outcome  # noqa: E402

TEXT_SUFFIXES = {".json", ".sql", ".log", ".txt"}


def run(dataset_dir: Path | None = None) -> dict:
    d = dataset_dir or config.DATASET_DIR
    index = IdentityIndex.from_dataset(d)
    counts: Counter = Counter()
    for f in loaders.load_evidence_manifest(d):
        if f.suffix not in TEXT_SUFFIXES:
            continue
        for m in index.scan(loaders.read_text(f.abs_path(d)), f.file_id):
            if m.kind == "email":
                counts[m.outcome.value] += 1
    unresolved = [
        r.case_id
        for name in ("deletion_requests.csv", "sample_deletion_requests.csv")
        for r in loaders.load_requests(d, name)
        if index.user_for_email(r.email) is None
    ]
    n_requests = sum(len(loaders.load_requests(d, n)) for n in ("deletion_requests.csv", "sample_deletion_requests.csv"))
    return {"counts": dict(counts), "requests": n_requests, "unresolved": unresolved}


if __name__ == "__main__":
    res = run()
    c = res["counts"]
    print(f"exact={c.get(Outcome.EXACT.value, 0)} same_user={c.get(Outcome.SAME_USER_OTHER_ID.value, 0)} "
          f"unknown_decoys={c.get(Outcome.UNKNOWN_DECOY.value, 0)} other_user={c.get(Outcome.OTHER_USER.value, 0)}")
    print(f"request emails resolved: {res['requests'] - len(res['unresolved'])}/{res['requests']}")
