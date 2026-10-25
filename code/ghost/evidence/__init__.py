"""Evidence dispatch by extension, then content sniffing (DESIGN §5).

Every file in evidence_files.csv is parsed; nothing is skipped by name. Parsers yield `RawRecord`s that
`normalize.py` turns into Facts. PNG screenshots are registered as unparsed (M5, D5).
Rules: H-LNK-03, H-TIM-02 (record-level time), G-SYS-01.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..loaders import EvidenceFile, read_text


@dataclass
class RawRecord:
    locator: str
    fields: dict[str, Any]  # flattened scalars (nested keys joined with '.')
    text: str  # text searched by the identifier matcher
    fact_time: datetime | None = None  # record-level time; None -> file/capture time
    system_hint: str | None = None  # own `system` field or parent key
    collection: str | None = None
    topology: str = "primary"
    capture_time: datetime | None = None
    label_category: str | None = None  # explicit category label in the evidence (trusted)
    event: str | None = None
    events: tuple[str, ...] = ()
    line_span: tuple[int, int] | None = None


@dataclass
class ScopeInfo:
    system_id_hint: str
    topology: str
    captured_at: datetime


@dataclass
class ParsedFile:
    fmt: str
    records: list[RawRecord] = field(default_factory=list)
    capture_time: datetime | None = None
    scopes: list[ScopeInfo] = field(default_factory=list)
    unparsed_reason: str | None = None


def flatten(value: Any, prefix: str = "", out: dict[str, Any] | None = None, max_items: int = 50) -> dict[str, Any]:
    """Flatten nested dict/list into dotted scalar keys (lists indexed)."""
    out = {} if out is None else out
    if isinstance(value, dict):
        for k, v in value.items():
            flatten(v, f"{prefix}.{k}" if prefix else str(k), out, max_items)
    elif isinstance(value, list):
        for i, v in enumerate(value[:max_items]):
            flatten(v, f"{prefix}.{i}", out, max_items)
    else:
        out[prefix] = value
    return out


def parse_file(f: EvidenceFile, dataset_dir: Path | None = None) -> ParsedFile:
    from . import json_parser, log_parser, pdf_parser, sql_parser, txt_parser
    from .image_parser import parse_image

    path = f.abs_path(dataset_dir)
    suffix = f.suffix
    if suffix == ".png" or suffix in (".jpg", ".jpeg"):
        return parse_image(f, path)
    if suffix == ".pdf":
        return pdf_parser.parse(f, path)
    text = read_text(path)
    if suffix == ".sql":
        return sql_parser.parse(f, text)
    if suffix == ".json":
        return json_parser.parse(f, text)
    if suffix == ".log":
        return log_parser.parse(f, text)
    if suffix == ".txt":
        return txt_parser.parse(f, text)
    # content sniffing for unknown extensions
    s = text.lstrip()
    if s.startswith(("{", "[")):
        try:
            json.loads(s)
            return json_parser.parse(f, text)
        except ValueError:
            pass
    if "CREATE TABLE" in text.upper():
        return sql_parser.parse(f, text)
    if text.count(" | ") >= 4:
        return txt_parser.parse(f, text)
    return log_parser.parse(f, text)
