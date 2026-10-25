"""M5 acceptance for the screenshot pipeline (DESIGN §5.1, P09, SCREENSHOTS §6-7).

1. Region consistency (P09): every PNG x {original, 0.6x, 1.5x, inverted} labels red / green / blue / yellow like the
   original (expected 44/44).
2. Cross-check: the resource ids and validated identifiers OCR-extracted from each variant versus the original
   (the robustness custom case of the evaluation report).
Usage: python code/scripts/m5_screenshots.py [--ocr]   (--ocr runs tesseract on all 44 variants; slower)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ghost import catalog, config, loaders  # noqa: E402
from ghost.evidence import image_parser as ip  # noqa: E402
from ghost.identity import IdentityIndex, links  # noqa: E402


def variants(img):
    return [("orig", img), ("x0.6", cv2.resize(img, None, fx=.6, fy=.6, interpolation=cv2.INTER_AREA)),
            ("x1.5", cv2.resize(img, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)), ("invert", 255 - img)]


def image_paths(dataset_dir: Path | None = None) -> list[Path]:
    d = dataset_dir or config.DATASET_DIR
    return [f.abs_path(d) for f in loaders.load_evidence_manifest(d) if f.suffix == ".png"]


def region_consistency(paths=None) -> tuple[int, int, list[str]]:
    ok = tot = 0
    bad = []
    for p in paths or image_paths():
        img = ip.imread(p)
        base = None
        for name, v in variants(img):
            sig = ip.regions_signature(v)
            base = base or sig
            same = ip.same_regions(sig, base)
            tot += 1
            ok += same
            if not same:
                bad.append(f"{p.name}:{name}")
    return ok, tot, bad


def ocr_identifiers(img, index: IdentityIndex) -> set[str]:
    """Resource ids + validated identifiers of one image (header, detail, table rows, activity)."""
    ts = ip._tesseract()
    ex = ip.extract(img, ts)
    text = " ".join(ex["texts"].values()) + " " + " ".join(ex["rows"])
    ids = set(catalog.RESOURCE_ID_RE.findall(text.lower()))
    ids |= {f"{k}:{t}" for _, k, t in links(index.scan(text))}
    return ids


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ocr", action="store_true")
    args = ap.parse_args(argv)
    ok, tot, bad = region_consistency()
    print(f"region consistency (P09): {ok}/{tot} variants match the original  {bad}")
    if args.ocr:
        index = IdentityIndex.from_dataset()
        agree = total = 0
        per: dict[str, list[int]] = {}
        for p in image_paths():
            img = ip.imread(p)
            ref = None
            for name, v in variants(img):
                ids = ocr_identifiers(v, index)
                ref = ref if ref is not None else ids
                if name != "orig":
                    total += 1
                    jac = 1.0 if not (ids | ref) else len(ids & ref) / len(ids | ref)  # both empty = identical
                    agree += jac >= 0.8
                    per.setdefault(name, []).append(jac >= 0.8)
                    print(f"{p.name[:40]:<40} {name:<7} ids={len(ids):>2} vs orig {len(ref):>2} jaccard={jac:.2f}")
        print(f"identifier agreement with the original (jaccard >= 0.8): {agree}/{total}")
        print("per variant:", {k: f"{sum(v)}/{len(v)}" for k, v in per.items()})
    return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(main())
