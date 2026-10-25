"""Screenshot evidence (DESIGN §5.1, D5 / D5a; port of docs/probes/P09_region_labelling.py v3).

Two derived images per screenshot:
* geometry image: grayscale -> invert if median < 128 -> contrast stretch -> black-hat (7x7) > 3 -> long-line opening
  -> rectangles; labels are RELATIVE (green = largest, red = >=3 wide cards above green, right column top-down:
  blue = detail panel (thin title bars merged into it), yellow = activity, black = header band). No absolute pixels.
* text image: grayscale -> invert if dark -> contrast stretch -> upscale -> tesseract per region; the table is split
  into row strips at detected horizontal lines and each strip read with --psm 7.
The detail panel (+ title bar) is the subject record (W-EVD-04); header and table rows are separate records, and
identity validation filters decoy rows naturally (normalize.py runs the two-stage matcher, H-IDN-04).
Semantic pass (D5a, conditional): a vision LLM reads the whole image only when a quality gate fails (fewer than 3
regions, no resource id / identifier in header + detail, an OCR token that looks like a resource id but is not one,
or tesseract missing). Its identifiers are accepted only if they also appear in the OCR text or match a known
resource id (never the sole basis of a finding). Untrusted-input handling (§11.3): OCR text is data inside tags;
a flagged text is not sent to a model. Results are cached by the image sha256.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .. import catalog, config, untrusted
from ..loaders import EvidenceFile
from . import ParsedFile, RawRecord

REF_WIDTH = 3500  # upscale target so text height lands near tesseract's sweet spot (~30 px)
CACHE_VERSION = "v1"
VISION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["entity_header", "detail", "all_identifiers"],
    "properties": {
        "entity_header": {"type": "object", "additionalProperties": False, "required": ["title", "ids", "emails", "phones"],
                          "properties": {"title": {"type": "string"}, "ids": {"type": "array", "items": {"type": "string"}},
                                         "emails": {"type": "array", "items": {"type": "string"}},
                                         "phones": {"type": "array", "items": {"type": "string"}}}},
        "detail": {"type": "object", "additionalProperties": False, "required": ["record_id", "fields"],
                   "properties": {"record_id": {"type": "string"},
                                  "fields": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                                         "required": ["label", "value"],
                                                                         "properties": {"label": {"type": "string"}, "value": {"type": "string"}}}}}},
        "all_identifiers": {"type": "array", "items": {"type": "string"}},
    },
}
VISION_SYSTEM = ("You read screenshots of internal business dashboards. Extract only what is printed: the entity header "
                 "(title, ids, emails, phones), the record shown in the detail panel (its id and label/value fields) and every "
                 "identifier visible anywhere (emails, phone numbers, ids like account_123 or user_12). Do not guess characters. "
                 + untrusted.DATA_NOTICE)


@dataclass
class ImageContext:
    """Collaborators injected by build_fact_store (the parser itself stays dependency-free)."""

    known_resources: set[str] = field(default_factory=set)
    vision: Callable[[bytes, str], dict | None] | None = None  # (png bytes, ocr text) -> VISION_SCHEMA dict
    cache_dir: Path | None = None


# ---- geometry (P09 v3) ----------------------------------------------------------------------------------------------
def imread(path: Path) -> np.ndarray | None:
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def _prep_gray(img: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if np.median(g) < 128:
        g = 255 - g  # dark theme: invert both derived images (SCREENSHOTS §7)
    return cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX)  # contrast stretch


def rects(img: np.ndarray) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    g = _prep_gray(img)
    h, w = g.shape
    bh_ = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)))
    ink = (bh_ > 3).astype(np.uint8) * 255
    hl = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(12, w // 20), 1)))
    vl = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(12, h // 25))))
    grid = cv2.dilate(cv2.bitwise_or(hl, vl), np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(grid, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    out: list[tuple[int, int, int, int]] = []
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw > 0.08 * w and bh > 0.04 * h and bw < 0.97 * w and bh < 0.99 * h:
            if not any(abs(x - o[0]) < .01 * w and abs(y - o[1]) < .01 * h and abs(bw - o[2]) < .015 * w
                       and abs(bh - o[3]) < .015 * h for o in out):
                out.append((x, y, bw, bh))
    return w, h, out


def label(w: int, h: int, R: list[tuple[int, int, int, int]]) -> dict:
    if not R:
        return {}
    green = max(R, key=lambda r: r[2] * r[3])
    gx, gy, gw, gh = green
    above = [r for r in R if r[1] + r[3] <= gy + 5 and r[2] > r[3]]
    rows: dict[int, list] = {}
    for r in above:
        rows.setdefault(round(r[1] / (0.02 * h)), []).append(r)
    cards = max(rows.values(), key=len) if rows else []
    red = None
    if len(cards) >= 3:
        xs = [c[0] for c in cards]
        ys = [c[1] for c in cards]
        red = (min(xs), min(ys), max(c[0] + c[2] for c in cards) - min(xs), max(c[3] for c in cards))
    right = [r for r in R if r[0] >= gx + gw - 5 and r[1] >= gy - 5]
    right = [r for r in right if not any(o != r and o[1] >= r[1] - 3 and o[1] + o[3] <= r[1] + r[3] + 3 and o[3] < r[3] * 0.9 for o in right)]
    thin = [r for r in right if r[3] < 0.06 * h]  # panel title bars (fix v2): kept, merged into blue when extracting
    right = [r for r in right if r[3] >= 0.06 * h]
    right.sort(key=lambda r: r[1])
    blue = right[0] if right else None
    yellow = right[1] if len(right) > 1 else None
    black = (gx, 0, w - gx, (red[1] if red else gy))
    return {"black": black, "red": red, "green": green, "blue": blue, "yellow": yellow, "n_cards": len(cards), "thin": thin}


def norm(b, w: int, h: int):
    return None if b is None else tuple(round(v, 3) for v in (b[0] / w, b[1] / h, b[2] / w, b[3] / h))


def regions_signature(img: np.ndarray) -> dict:
    """Normalised red / green / blue / yellow boxes: what P09 compares across variants."""
    w, h, R = rects(img)
    L = label(w, h, R)
    return {k: norm(L.get(k), w, h) for k in ("red", "green", "blue", "yellow")}


def same_regions(a: dict, b: dict, tol: float = 0.015) -> bool:
    return all((a[k] is None) == (b[k] is None) and (a[k] is None or max(abs(x - y) for x, y in zip(a[k], b[k])) < tol) for k in a)


# ---- OCR ----------------------------------------------------------------------------------------------------------------
def _tesseract():
    import pytesseract

    cmd = config.resolve_tesseract()
    if not cmd:
        return None
    pytesseract.pytesseract.tesseract_cmd = cmd
    return pytesseract


def _union(a, b):
    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
    return (x0, y0, x1 - x0, y1 - y0)


def _row_strips(gray_crop: np.ndarray) -> list[tuple[int, int]]:
    """Horizontal strips of a table panel between detected row lines (y ranges)."""
    h, w = gray_crop.shape
    bh_ = cv2.morphologyEx(gray_crop, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)))
    ink = (bh_ > 3).astype(np.uint8) * 255
    hl = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(12, w // 3), 1)))
    ys = np.where(hl.sum(axis=1) > 0)[0]
    lines: list[int] = []
    for y in ys:
        if not lines or y - lines[-1] > 3:
            lines.append(int(y))
    cuts = [0] + lines + [h]
    return [(a + 2, b - 1) for a, b in zip(cuts, cuts[1:]) if b - a > max(14, 0.02 * h)]


def _ocr(ts, gray: np.ndarray, box, scale: float, psm: int) -> str:
    x, y, bw, bh = [int(v * scale) for v in box]
    crop = gray[max(0, y):y + bh, max(0, x):x + bw]
    if crop.size == 0:
        return ""
    return ts.image_to_string(crop, config=f"--psm {psm}").strip()


# ---- semantic signals from panel text ------------------------------------------------------------------------------------
_YES, _NO = r"(yes|true|on|enabled|allowed)", r"(no|false|off|disabled|blocked|denied)"


def signals_from_text(text: str) -> dict:
    """Generic label / value cues of a detail panel (not template-specific); only explicit cues are mapped."""
    t = text.lower()
    f: dict = {}
    m = re.search(rf"restore[^\n]{{0,20}}?{_YES}\b", t)
    if m and not re.search(rf"restore[^\n]{{0,20}}?{_NO}\b", t):
        f["restore_allowed"] = True
    elif re.search(rf"restore[^\n]{{0,20}}?{_NO}\b", t):
        f["restore_allowed"] = False
    if re.search(rf"\benabled\b[^\n]{{0,8}}\b{_YES}\b", t) or re.search(r"\bstatus\b[^\n]{0,8}\bactive\b", t):
        f["enabled"] = True
    elif re.search(r"\benabled\b[^\n]{0,8}\b(no|false|off)\b", t) or re.search(r"\bstatus\b[^\n]{0,8}\b(disabled|stopped)\b", t):
        f["enabled"] = False
    m = re.search(r"direct identifiers?\D{0,6}(\d)", t)
    if m:
        f["direct_identifiers"] = int(m.group(1))
    if re.search(r"\bnot found\b|\b404\b", t):
        f["result"] = "NOT_FOUND"
    elif re.search(r"\bstatus\b[^\n]{0,8}\b(found|present)\b", t):
        f["result"] = "FOUND"
    return f


# EO-7: explicit absence cues in a detail panel (the record is shown but gone / unavailable); anything else that names a
# resource in the header or detail panel is a presence observation at the file's captured_at.
_ABSENT_CUE = re.compile(r"\b(not found|deleted|removed|expired|no records)\b", re.I)


def panel_presence(region: str, body: str) -> bool | None:
    """True / False for a header or detail panel, None for other regions (table rows are mostly decoys, W-EVD-04)."""
    if region == "detail":
        return not _ABSENT_CUE.search(body)
    if region == "header":
        return True
    return None


_LOOKS_LIKE_ID = re.compile(r"\b[a-z]{2,15}_\d{2,6}\b", re.I)


def _suspect_ids(text: str, known: set[str]) -> list[str]:
    """OCR tokens shaped like a resource id that are not a valid catalog id (clipped `jport_1034`)."""
    return [t for t in _LOOKS_LIKE_ID.findall(text) if not catalog.RESOURCE_ID_RE.fullmatch(t.lower()) and not t.lower().startswith("user_")]


def repair_ids(text: str, known: set[str]) -> dict[str, str]:
    """Map a clipped / garbled id to a known resource id sharing the same number and a prefix within edit distance 3."""
    from ..tier4 import _edit_distance_le

    out = {}
    by_num: dict[str, list[str]] = {}
    for k in known:
        by_num.setdefault(k.rsplit("_", 1)[-1], []).append(k)
    for tok in _suspect_ids(text, known):
        prefix, num = tok.lower().rsplit("_", 1)
        for cand in by_num.get(num, []):
            if _edit_distance_le(prefix, cand.rsplit("_", 1)[0], 3):  # the number must match exactly and be a known id
                out[tok] = cand
                break
    return out


def make_vision(llm) -> Callable[[bytes, str], dict | None]:
    """L2 callable: whole image + OCR text (as tagged data) -> VISION_SCHEMA dict, or None on failure."""

    def vision(png: bytes, ocr_text: str) -> dict | None:
        user = "Extract the structured content of this screenshot.\n" + untrusted.wrap("ocr_text", ocr_text[:3000])
        return llm.call_json("vision", "L2", VISION_SYSTEM, user, VISION_SCHEMA, images=[png], max_tokens=4000).data

    return vision


# ---- extraction ----------------------------------------------------------------------------------------------------------
def extract(img: np.ndarray, ts) -> dict:
    """Region texts + row strips for one image. Pure function of the pixels (cached by sha256)."""
    w, h, R = rects(img)
    L = label(w, h, R)
    out = {"regions": {k: norm(L.get(k), w, h) for k in ("black", "red", "green", "blue", "yellow")}, "n_regions": sum(
        1 for k in ("red", "green", "blue", "yellow") if L.get(k)), "texts": {}, "rows": []}
    if ts is None:
        return out
    scale = max(1.0, min(5.0, REF_WIDTH / w))
    gray = cv2.resize(_prep_gray(img), None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    base = _prep_gray(img)
    detail = L.get("blue")
    if detail and L.get("thin"):  # title bar carries the record id: merge it into the detail region
        for t in L["thin"]:
            if abs((t[1] + t[3]) - detail[1]) < 0.08 * h or t[1] <= detail[1]:
                detail = _union(detail, t)
    boxes = {"header": L.get("black"), "kpi": L.get("red"), "detail": detail, "activity": L.get("yellow")}
    for name, box in boxes.items():
        if box:
            out["texts"][name] = _ocr(ts, gray, box, scale, 6)
    g = L.get("green")
    if g:
        crop = base[g[1]:g[1] + g[3], g[0]:g[0] + g[2]]
        for a, b in _row_strips(crop):
            out["rows"].append(_ocr(ts, gray, (g[0], g[1] + a, g[2], b - a), scale, 7))
        out["texts"]["table"] = _ocr(ts, gray, g, scale, 6)
    return out


def _gate(ex: dict, known: set[str], index_hits: Callable[[str], bool], have_tesseract: bool) -> list[str]:
    reasons = []
    if not have_tesseract:
        reasons.append("tesseract missing")
    if ex["n_regions"] < 3:
        reasons.append(f"only {ex['n_regions']} regions")
    key_text = " ".join(ex["texts"].get(k, "") for k in ("header", "detail"))
    if not catalog.RESOURCE_ID_RE.search(key_text.lower()) and not index_hits(key_text):
        reasons.append("no resource id or identifier in header/detail")
    if any(t.lower() not in known for t in _suspect_ids(key_text, known)) and not repair_ids(key_text, known):
        reasons.append("OCR id candidate failed validation")
    return reasons


def parse_image(f: EvidenceFile, path: Path, ctx: ImageContext | None = None, index_hits: Callable[[str], bool] | None = None) -> ParsedFile:
    ctx = ctx or ImageContext()
    img = imread(path)
    if img is None:
        return ParsedFile("png", unparsed_reason="cannot decode image")
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    cache_file = (ctx.cache_dir / f"{sha}.{CACHE_VERSION}.json") if ctx.cache_dir else None
    ts = _tesseract()
    if cache_file and cache_file.exists():
        ex = json.loads(cache_file.read_text(encoding="utf-8"))
    else:
        ex = extract(img, ts)
        ex["gate"] = _gate(ex, ctx.known_resources, index_hits or (lambda t: False), ts is not None)
        if cache_file:  # pixels-only result (OCR + gate); the model answer is cached per profile by the LLM layer
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(ex, ensure_ascii=False), encoding="utf-8")
    ex["vision"] = None
    if ex["gate"] and ctx.vision is not None:
        all_text = " ".join(ex["texts"].values()) + " " + " ".join(ex["rows"])
        if not untrusted.suspicious(all_text):  # a flagged OCR text is never sent to a model (§11.3)
            ex["vision"] = ctx.vision(raw, all_text)
    out = ParsedFile("png")
    texts = dict(ex.get("texts", {}))
    all_text = " ".join(texts.values()) + " " + " ".join(ex.get("rows", []))
    repairs = repair_ids(all_text, ctx.known_resources)
    vis_ids: list[str] = []
    v = ex.get("vision")
    if v:  # accepted iff the LLM value also appears in the OCR text or is a known resource / identity (cross-check)
        cand = list(v.get("all_identifiers", [])) + list(v.get("entity_header", {}).get("ids", [])) \
            + list(v.get("entity_header", {}).get("emails", [])) + list(v.get("entity_header", {}).get("phones", [])) \
            + [v.get("detail", {}).get("record_id", "")]
        low = all_text.lower()
        for c in cand:
            c = (c or "").strip()
            if c and (c.lower() in low or c.lower() in ctx.known_resources or (index_hits and index_hits(c))):
                vis_ids.append(c)
    n = 0

    def add(region: str, body: str, extra_ids: list[str]) -> None:
        nonlocal n
        txt = body + " " + " ".join(extra_ids) + " " + " ".join(repairs.values())
        ids = sorted(set(catalog.RESOURCE_ID_RE.findall(txt.lower())))
        sig = signals_from_text(body) if region == "detail" else {}
        base = {"region": region, "ocr_text": body, **sig}
        present = panel_presence(region, body)
        if not ids:
            out.records.append(RawRecord(locator=f"{region}#{n}", fields=base, text=txt, line_span=None))
            n += 1
            return
        for rid in ids:
            fields = {**base, "resource_id": rid, **({"present": present} if present is not None else {})}
            out.records.append(RawRecord(locator=f"{region}#{rid}", fields=fields, text=txt,
                                         label_category=None, event="attachment_document" if "attachment" in txt.lower() else None))
    add("detail", texts.get("detail", ""), vis_ids)
    add("header", texts.get("header", ""), [])
    for i, row in enumerate(ex.get("rows", [])):
        if row.strip():
            add(f"row{i}", row, [])
    out.unparsed_reason = None if out.records else "no text recovered from the screenshot"
    return out
