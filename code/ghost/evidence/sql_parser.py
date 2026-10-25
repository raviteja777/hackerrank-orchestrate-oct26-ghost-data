"""SQL snapshot evidence via sqlite3 in-memory executescript (DESIGN §5, SQL row).

Rules: G-SYS-01 (replica tables map to the base system), G-EVD-01 (snapshot_scope gives the systems a
capture covers, for proof of absence), H-TIM-02 (row updated_at is the record time; the header
"Captured at" is the snapshot time). Topology comes from the table name and the header comment.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from .. import catalog
from ..loaders import EvidenceFile, parse_ts
from . import ParsedFile, RawRecord, ScopeInfo, flatten

_HDR_CAPTURED = re.compile(r"^--\s*Captured at:\s*(\S+)", re.M)
_HDR_TOPOLOGY = re.compile(r"^--\s*Database topology:\s*(\S+)", re.M)
_ROW_TIME = ("updated_at", "indexed_at", "recorded_at", "observed_at")


def topology_of(table: str) -> str:
    t = table.lower()
    if t.endswith("_primary") or "_primary" in t:
        return "primary"
    m = re.search(r"(failover|read|reporting)_replica", t)
    if m:
        return f"replica:{m.group(1)}"
    m = re.search(r"replica_(\w+)$", t)
    if m:
        return f"replica:regional:{m.group(1)}"
    return "primary"  # inventory tables are snapshots of the system itself


def collection_of(table: str) -> str:
    return re.sub(r"_(?:primary|failover_replica|read_replica|reporting_replica)$", "", table)


def _ts(v: Any):
    try:
        return parse_ts(v) if isinstance(v, str) else None
    except ValueError:
        return None


def parse(f: EvidenceFile, text: str) -> ParsedFile:
    out = ParsedFile("sql")
    m = _HDR_CAPTURED.search(text)
    out.capture_time = _ts(m.group(1)) if m else None
    con = sqlite3.connect(":memory:")
    try:
        con.executescript(text)
    except sqlite3.Error as exc:  # keep partial content parseable; surfaced via unparsed_reason
        out.unparsed_reason = f"sqlite error: {exc}"
    con.row_factory = sqlite3.Row
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    for tb in tables:
        rows = con.execute(f'SELECT * FROM "{tb}"').fetchall()
        if tb == "snapshot_scope":
            for r in rows:
                t = _ts(r["captured_at"])
                if t:
                    out.scopes.append(ScopeInfo(r["origin_system"], "primary", t))
            continue
        topo = topology_of(tb)
        coll_default = collection_of(tb)
        seen_systems: set[str] = set()
        for r in rows:
            d = {k: r[k] for k in r.keys()}
            fields = {k: v for k, v in d.items() if k != "record_json"}
            collection = d.get("collection_name") or coll_default
            if isinstance(d.get("record_json"), str):
                try:
                    inner = json.loads(d["record_json"])
                except ValueError:
                    inner = {}
                for k, v in flatten(inner).items():
                    fields.setdefault(k, v)
                body = json.dumps(inner, ensure_ascii=False, sort_keys=True)
            else:
                body = json.dumps(fields, ensure_ascii=False, sort_keys=True, default=str)
            rid = d.get("resource_id")
            origin = d.get("origin_system")
            if origin:
                seen_systems.add(origin)
            row_t = next((t for k in _ROW_TIME if (t := _ts(d.get(k)))), None)
            out.records.append(RawRecord(
                locator=f"{tb}#{rid}", fields=fields, text=body, fact_time=row_t,
                system_hint=origin or catalog.normalize_system(tb), collection=collection, topology=topo,
                capture_time=out.capture_time,
            ))
        if not rows or not any(s for s in seen_systems):
            # Table-level coverage for typed tables (e.g. customer_profiles_primary -> account_service).
            base = catalog.normalize_system(tb)
            if base is None and tb.startswith("customer_profiles"):
                base = "account_service"
            if base and out.capture_time:
                out.scopes.append(ScopeInfo(base, topo, out.capture_time))
        if out.capture_time:
            for s in sorted(seen_systems):
                out.scopes.append(ScopeInfo(s, topo, out.capture_time))
    con.close()
    return out
