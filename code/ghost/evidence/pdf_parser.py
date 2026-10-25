"""PDF evidence via pypdf (DESIGN §5, PDF row). No system dependency is needed.

One record per catalog resource id found in the document (anchored sub-records), each carrying the document
text so the identifier matcher sees the whole document; a document without resource ids yields one
resource-less record (G-POL-02: evidence with no resource id produces no step). Record time = a
"captured <date>" stamp in the text if parseable, else the file `captured_at` (applied by normalize).
Rules: W-CEIL-01 (support_001 exists only in a PDF), G-POL-02, H-IDN-04.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .. import catalog
from ..loaders import EvidenceFile
from . import ParsedFile, RawRecord

_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
# "captured 12 Sep 2026 07 30 UTC" (the colon is lost in text extraction)
_CAPTURED = re.compile(r"\bcaptured\s+(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})(?:\s+(\d{2})\D{1,3}(\d{2}))?", re.I)


def _captured(text: str) -> datetime | None:
    m = _CAPTURED.search(text)
    if not m or m.group(2).lower() not in _MONTHS:
        return None
    return datetime(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)),
                    int(m.group(4) or 0), int(m.group(5) or 0), tzinfo=timezone.utc)


def parse(f: EvidenceFile, path: Path) -> ParsedFile:
    from pypdf import PdfReader

    out = ParsedFile("pdf")
    try:
        reader = PdfReader(str(path))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as exc:  # corrupt or unreadable PDF: register as unparsed
        out.unparsed_reason = f"pypdf failed: {exc}"
        return out
    when = _captured(text)
    ids = sorted(set(catalog.RESOURCE_ID_RE.findall(text)))
    base = dict(text=text, fact_time=when)
    if not ids:
        out.records.append(RawRecord(locator="doc", fields={"document": f.file_path}, **base))
    for rid in ids:
        out.records.append(RawRecord(locator=f"doc#{rid}", fields={"resource_id": rid, "document": f.file_path}, **base))
    return out
