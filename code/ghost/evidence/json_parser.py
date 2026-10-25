"""JSON evidence: generic record walker (DESIGN §5, JSON row).

Any dict carrying `resource_id` is a record. Record time = own observed_at/recorded_at/updated_at/captured_at,
else the innermost ancestor captured_at/observed_at/exported_at (H-TIM-02, D3). System = the record's own
`system`, else the parent key (service_exports.<system>) or `data_store`; the catalog prefix decides in
normalize.py (G-SYS-01).
"""
from __future__ import annotations

import json
from typing import Any

from .. import catalog
from ..loaders import EvidenceFile, parse_ts
from . import ParsedFile, RawRecord, ScopeInfo, flatten

_OWN_TIME = ("observed_at", "recorded_at", "updated_at", "captured_at")
_CTX_TIME = ("captured_at", "observed_at", "exported_at", "recorded_at")


def _ts(v: Any):
    try:
        return parse_ts(v) if isinstance(v, str) else None
    except ValueError:
        return None


def parse(f: EvidenceFile, text: str) -> ParsedFile:
    data = json.loads(text)
    out = ParsedFile("json")
    counter = {"n": 0}

    def walk(node: Any, ctx: dict, path: str) -> None:
        if isinstance(node, dict):
            if "resource_id" in node and isinstance(node["resource_id"], str):
                counter["n"] += 1
                own = next((t for k in _OWN_TIME if (t := _ts(node.get(k)))), None)
                label = node.get("record_type") if isinstance(node.get("record_type"), str) else None
                out.records.append(RawRecord(
                    locator=f"{path}#{node['resource_id']}",
                    fields=flatten(node), text=json.dumps(node, ensure_ascii=False, sort_keys=True),
                    fact_time=own or ctx.get("time"), system_hint=node.get("system") or ctx.get("system"),
                    collection=ctx.get("collection"), capture_time=ctx.get("time"), label_category=label,
                ))
                return
            sub = dict(ctx)
            for k in _CTX_TIME:
                if (t := _ts(node.get(k))):
                    sub["time"] = t
                    break
            if isinstance(node.get("data_store"), str):
                sub["system"] = node["data_store"]
                st = sub.get("time")
                if st is not None and isinstance(node.get("records"), list):  # bundle snapshot: covers the system
                    out.scopes.append(ScopeInfo(node["data_store"], "primary", st))
            if isinstance(node.get("collection"), str):
                sub["collection"] = node["collection"]
            for k, v in node.items():
                child = dict(sub)
                if catalog.normalize_system(k):  # service_exports.<system>
                    child["system"] = k
                elif isinstance(v, list) and isinstance(k, str) and "collection" not in node and ctx.get("system"):
                    child["collection"] = child.get("collection") or k
                walk(v, child, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, ctx, f"{path}[{i}]")

    walk(data, {}, "$")
    # the file-level time (root captured_at / exported_at) is the capture time
    root = data if isinstance(data, dict) else {}
    out.capture_time = next((t for k in ("captured_at", "exported_at") if (t := _ts(root.get(k)))), None)
    return out
