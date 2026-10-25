"""Plain-text records (DESIGN §5, TXT row): handover pipe tables and key: value lines.

`- time | system | resource | CATEGORY | STATE | identifier` lines are records with explicit category and
state labels, which are trusted signals (H-LNK-02, G-POL-02). Other lines are key: value metadata (the
`Snapshot:` header is the capture time) and produce no record.
"""
from __future__ import annotations

import re

from ..loaders import EvidenceFile, parse_ts
from . import ParsedFile, RawRecord

_KV = re.compile(r"^\s*([A-Za-z][\w \-]*?):\s*(.+?)\s*$")


def parse(f: EvidenceFile, text: str) -> ParsedFile:
    out = ParsedFile("txt")
    meta: dict[str, str] = {}
    for n, line in enumerate(text.splitlines(), start=1):
        if line.count("|") >= 4:
            parts = [p.strip() for p in line.lstrip(" -*\t").split("|")]
            try:
                t = parse_ts(parts[0])
            except ValueError:
                t = None
            if t is None:  # not time-led: keep as an unlabelled pipe row
                continue
            system, rid, cat, state, ident = (parts + [None] * 6)[1:6]
            fields = {"time": parts[0], "system": system, "resource_id": rid, "record_type": cat,
                      "state": state, "identifier": ident}
            out.records.append(RawRecord(
                locator=f"L{n}", fields=fields, text=" ".join(p for p in parts if p), fact_time=t,
                system_hint=system, label_category=cat, line_span=(n, n)))
            continue
        m = _KV.match(line)
        if m:
            meta[m.group(1).strip().lower()] = m.group(2)
    if "snapshot" in meta:
        try:
            out.capture_time = parse_ts(meta["snapshot"])
        except ValueError:
            pass
    return out
