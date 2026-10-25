"""M2 acceptance checks (DESIGN §14).

1. Every non-audit resource in dataset/sample_output.csv is found as a fact or a run candidate (a resource in
   system_activity), except the W-CEIL-01 list.
2. For sample cases 03, 09 and 24, every evidence hit in the P02 dossier (docs/probes/out/P02_case_NN.txt) is
   matched by a fact from the same file that carries the hit key (resource id or validated identifier); for
   line-based formats (logs, txt) the fact's line span must also contain the dossier line.
Usage: python code/scripts/m2_acceptance.py
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ghost import config, loaders  # noqa: E402
from ghost.evidence import parse_file  # noqa: E402
from ghost.evidence.normalize import build_fact_store  # noqa: E402
from ghost.facts import FactStore  # noqa: E402
from ghost.identity import IdentityIndex, normalize_phone  # noqa: E402

DOSSIER_DIR = config.REPO_ROOT / "docs" / "probes" / "out"
# W-CEIL-01: answer resources that appear in no participant-facing file (activity or evidence).
# account_004 (case_04) is the third: it occurs only in sample_output.csv (OQ-8, informational).
CEILING = {"audit_record_6645", "audit_record_5569", "account_004"}
_FILE_RE = re.compile(r"^\[(evidence_\d+)\]")
_HIT_RE = re.compile(r"^\s+L(\d+):.*<-\s*(\[.*\])\s*$")


def sample_resources() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    with open(config.DATASET_DIR / "sample_output.csv", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["case_id"]] = {(s["system_id"], s["resource_id"]) for s in json.loads(r["steps_json"])}
    return out


def resource_coverage(store: FactStore, activity_resources: set[str]) -> dict:
    found_fact, found_run, missing = [], [], []
    total = 0
    for case, res in sorted(sample_resources().items()):
        for system, rid in sorted(res):
            if system == "security_service":
                continue  # audit records are checked separately (H-LNK-02)
            total += 1
            if store.for_resource(rid):
                found_fact.append((case, rid))
            elif rid in activity_resources:
                found_run.append((case, rid))
            else:
                missing.append((case, rid))
    return {"total": total, "fact": found_fact, "run": found_run, "missing": missing}


def audit_coverage(store: FactStore) -> dict:
    found, missing = [], []
    for case, res in sorted(sample_resources().items()):
        for system, rid in sorted(res):
            if system == "security_service":
                (found if store.for_resource(rid) else missing).append((case, rid))
    return {"found": found, "missing": missing}


def parse_dossier(case_id: str) -> list[tuple[str, int, list[str]]]:
    """-> [(file_id, line, keys)] from the EVIDENCE HITS section."""
    n = case_id.split("_")[1]
    path = DOSSIER_DIR / f"P02_case_{n}.txt"
    hits, cur = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("--- ACTIVITY"):
            break
        m = _FILE_RE.match(line)
        if m:
            cur = m.group(1)
            continue
        m = _HIT_RE.match(line)
        if m and cur:
            hits.append((cur, int(m.group(1)), eval(m.group(2))))  # noqa: S307 - own dossier files
    return hits


def _norm(key: str) -> str:
    if key.startswith("+") or re.fullmatch(r"[\d\s()\-]{7,}", key):
        return normalize_phone(key)
    return key.lower()


def dossier_check(case_id: str, store: FactStore) -> dict:
    ok, bad = 0, []
    for file_id, line, keys in parse_dossier(case_id):
        facts = store.for_file(file_id)
        for key in keys:
            k = _norm(key)
            hit = False
            for f in facts:
                toks = {f.resource_id, *(t for _, _, t in f.mentions)}
                if k not in toks and not (f.resource_id and k == f.resource_id.lower()):
                    continue
                if f.fmt in ("log", "txt") and f.line_span and not (f.line_span[0] <= line <= f.line_span[1]):
                    continue
                hit = True
                break
            if hit:
                ok += 1
            else:
                bad.append((file_id, line, key))
    return {"ok": ok, "missing": bad}


def main() -> int:
    index = IdentityIndex.from_dataset()
    store = build_fact_store(index=index)
    activity = {a.resource_id for a in loaders.load_activity()}
    print(f"facts={len(store.facts)} unparsed={len(store.unparsed)} (png TODO M5) noise_dropped={store.dropped_noise} "
          f"decoys_logged={len(store.decoys)}")
    cov = resource_coverage(store, activity)
    print(f"non-audit sample resources: {cov['total']}  as fact: {len(cov['fact'])}  run-only: {len(cov['run'])}  "
          f"missing: {len(cov['missing'])}")
    for c, r in cov["run"]:
        print(f"   run-only: {c} {r}")
    for c, r in cov["missing"]:
        print(f"   MISSING: {c} {r}")
    aud = audit_coverage(store)
    print(f"audit records: found {len(aud['found'])}, missing {len(aud['missing'])}: "
          f"{[r for _, r in aud['missing']]} (W-CEIL-01 list: {sorted(CEILING)})")
    bad_audit = [r for _, r in aud["missing"] if r not in CEILING]
    for case in ("case_03", "case_09", "case_24"):
        d = dossier_check(case, store)
        print(f"{case}: dossier hit keys matched {d['ok']}, unmatched {len(d['missing'])} {d['missing'][:5]}")
    unexpected = [(c, r) for c, r in cov["missing"] if r not in CEILING]
    ok = not unexpected and not bad_audit
    print("ACCEPTANCE:", "PASS" if ok else "CHECK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
