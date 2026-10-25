"""Format-agnostic log parser (DESIGN §5, Logs row).

Styles handled by one tokenizer: key=value, `[LEVEL] [service] [trace] event: k="v"`, JSON after the
timestamp, pipe-separated, syslog RFC5424, cloud runtime with nested escaped `message="k=\\"v\\""`, and
trace-less record_lookup lines. A leading ISO timestamp is the line time; lines are grouped by trace id
into one record per trace (H-LNK-03). The identifier lives on the `*_started` line and the resource and
state on the `*_completed` line, so grouping is what links them. Fact time = latest line time of the trace
(H-TIM-02, D3).
"""
from __future__ import annotations

import json
import re
from collections import OrderedDict
from datetime import datetime
from typing import Any

from ..loaders import EvidenceFile, parse_ts
from . import ParsedFile, RawRecord

TS_RE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:?\d\d)?)\s+(.*)$")
KV_RE = re.compile(r'([A-Za-z_][\w.\-]*)=("(?:[^"\\]|\\.)*"|[^\s"]+)')
BRACKET_RE = re.compile(r"^\[(\w+)\]\s+\[([^\]]*)\]\s+\[([^\]]*)\]\s+([\w.\-]+):\s*(.*)$")
PIPE_RE = re.compile(r"^\|?\s*(\w+)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([\w.\-]+)\s*\|\s*(.*)$")
SYSLOG_RE = re.compile(r"^<(\d+)>\d+\s+(\S+)\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s+(.*)$")
TRACE_KEYS = ("trace_id", "requestId", "request_id")
BARE_TRACE_RE = re.compile(r"\b(?:tr|rb|req)-[A-Za-z0-9-]+\b")
_IDENT_HINT = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}|\buser_\d+\b", re.I)
SELFCHECK_MIN_SHARE = 0.90
NOISE_EVENTS = {"cache_lookup", "connection_acquired", "dependency_retry"}  # infra lines: time only


def _unquote(v: str) -> Any:
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return None if v.lower() in ("null", "none", "") else v


def scan_kv(s: str) -> dict[str, Any]:
    return {k: _unquote(v) for k, v in KV_RE.findall(s)}


def parse_line(rest: str) -> tuple[dict[str, Any], str | None, str | None]:
    """-> (fields, trace_id, service). Fields include event/level/service when known."""
    fields: dict[str, Any] = {}
    trace = service = None
    s = rest.strip()
    if s.startswith("{"):
        try:
            obj = json.loads(s)
            fields.update({k: (None if v in ("null", "") else v) for k, v in obj.items()})
        except ValueError:
            pass
    else:
        m = BRACKET_RE.match(s)
        if m:
            fields.update(level=m.group(1), service=m.group(2), event=m.group(4))
            trace = m.group(3)
            s = m.group(5)
        else:
            m = PIPE_RE.match(s)
            if m and "=" not in m.group(1):
                fields.update(level=m.group(1), service=m.group(2), event=m.group(4))
                trace = m.group(3)
                s = m.group(5)
            else:
                m = SYSLOG_RE.match(s)
                if m:
                    fields["service"] = m.group(3)
                    trace = m.group(4)
                    s = m.group(5)
        kv = scan_kv(s)
        msg = kv.get("message")
        if isinstance(msg, str) and "=" in msg:  # cloud runtime: nested escaped key=value
            nested = scan_kv(msg)
            kv.pop("message")
            kv = {**kv, **nested}
            if "function" in kv and "service" not in kv:
                kv["service"] = kv["function"]
        fields.update(kv)
    for k in TRACE_KEYS:
        if fields.get(k):
            trace = str(fields[k])
            break
    if not trace:  # hardening for unseen layouts: bare trace-shaped token anywhere on the line
        m = BARE_TRACE_RE.search(rest)
        if m:
            trace = m.group(0)
    service = fields.get("service") or fields.get("logger") or service
    return fields, trace, service


def parse(f: EvidenceFile, text: str) -> ParsedFile:
    out = ParsedFile("log")
    groups: "OrderedDict[str, list[tuple[int, datetime, dict]]]" = OrderedDict()
    solo: list[tuple[int, datetime, dict]] = []
    lines = carrying = orphans = 0
    for n, raw in enumerate(text.splitlines(), start=1):
        m = TS_RE.match(raw.strip())
        if not m:
            continue
        try:
            t = parse_ts(m.group(1))
        except ValueError:
            continue
        lines += 1
        fields, trace, service = parse_line(m.group(2))
        if service and "service" not in fields:
            fields["service"] = service
        # self-check: lines carrying a resource id or an identifier must have a trace id, unless they are
        # self-contained records (resource id and identifier on the same line, e.g. record_lookup)
        has_res = bool(fields.get("resource_id"))
        has_ident = bool(_IDENT_HINT.search(m.group(2)))
        if has_res or has_ident:
            carrying += 1
            if not trace and not (has_res and has_ident):
                orphans += 1
        item = (n, t, fields)
        if trace:
            groups.setdefault(trace, []).append(item)
        else:
            solo.append(item)
    out.stats = {"lines": lines, "carrying": carrying, "orphans": orphans}

    def emit(key: str, lines: list[tuple[int, datetime, dict]], trace: str | None) -> None:
        merged: dict[str, Any] = {}
        events: list[str] = []
        for _, _, fl in lines:
            ev = fl.get("event")
            if ev:
                events.append(str(ev))
            if ev in NOISE_EVENTS:
                continue
            for k, v in fl.items():
                if v is not None or k not in merged:
                    merged[k] = v
        if trace:
            merged["trace_id"] = trace
        text_blob = " ".join(f"{k}={v}" for k, v in merged.items() if v is not None)
        out.records.append(RawRecord(
            locator=key, fields=merged, text=text_blob, fact_time=max(t for _, t, _ in lines),
            system_hint=merged.get("service"), event=events[-1] if events else None, events=tuple(events),
            label_category=merged.get("record_type") if isinstance(merged.get("record_type"), str) else None,
            line_span=(min(n for n, _, _ in lines), max(n for n, _, _ in lines)),
        ))

    for trace, lines in groups.items():
        rids = sorted({str(fl["resource_id"]) for _, _, fl in lines if fl.get("resource_id")})
        if len(rids) <= 1:
            emit(f"trace:{trace}", lines, trace)
        else:  # several resources under one trace: one record per resource, shared lines join each
            for rid in rids:
                part = [x for x in lines if x[2].get("resource_id") in (None, rid)]
                emit(f"trace:{trace}#{rid}", part, trace)
    for n, t, fl in solo:
        emit(f"L{n}", [(n, t, fl)], None)
    out.records.sort(key=lambda r: (r.line_span or (0, 0)))
    return out
