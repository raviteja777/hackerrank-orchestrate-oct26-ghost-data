"""Append-only, time-stamped edge log and per-case graph view (DESIGN §4.2, D7).

The edge log is the source of truth; state at `audit_at` = rows with t <= audit_at (D3, H-TIM-03).
Edge types: has_identifier, mentions, about, observed, claimed, linked_by_catalog (this module) and
in_slot / in_chain / flows_to (added by runs.py / resolve.py). `users_of` answers the question the
resolver asks: which users are linked to a resource by a validated identifier path at a given time.
A networkx.MultiDiGraph can be exported per case (`to_networkx`), also as GraphML for debugging.
Rules: H-IDN-04 (only validated links), H-TIM-02 (fact_time is the edge time), H-STA-02 (activity results
are `claimed`, never `observed`), H-LNK-03.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import networkx as nx

from . import catalog
from .facts import FactStore, derive_states
from .identity import IdentityIndex, links
from .loaders import Activity

HAS_IDENTIFIER, MENTIONS, ABOUT, OBSERVED = "has_identifier", "mentions", "about", "observed"
CLAIMED, LINKED_BY_CATALOG, IN_SLOT, IN_CHAIN = "claimed", "linked_by_catalog", "in_slot", "in_chain"


@dataclass(frozen=True)
class Edge:
    src: str
    type: str
    dst: str
    t: datetime
    source_ref: str = ""
    attrs: tuple[tuple[str, str], ...] = ()


class EdgeLog:
    def __init__(self) -> None:
        self.edges: list[Edge] = []
        self._links: dict[str, list[tuple[datetime, str, str]]] = defaultdict(list)  # resource -> [(t, user, ref)]
        self._sorted = True

    # ---- writing (append only) ------------------------------------------------------------------
    def add(self, src: str, type_: str, dst: str, t: datetime, source_ref: str = "", **attrs: str) -> None:
        self.edges.append(Edge(src, type_, dst, t, source_ref, tuple(sorted(attrs.items()))))

    def add_resource_user(self, resource_id: str, user_id: str, t: datetime, ref: str) -> None:
        """Validated person -> identifier -> record -> resource path (H-IDN-04), stamped with the record time."""
        self._links[resource_id].append((t, user_id, ref))
        self._sorted = False

    # ---- reading ----------------------------------------------------------------------------------
    def _ensure_sorted(self) -> None:
        if not self._sorted:
            for v in self._links.values():
                v.sort()
            self._sorted = True

    def users_of(self, resource_id: str, audit_at: datetime) -> set[str]:
        """Users with a validated link to `resource_id` established at or before `audit_at` (D3)."""
        self._ensure_sorted()
        rows = self._links.get(resource_id, [])
        times = [r[0] for r in rows]
        return {u for _, u, _ in rows[: bisect_right(times, audit_at)]}

    def linked_resources(self, audit_at: datetime) -> dict[str, set[str]]:
        """resource -> users, as of audit_at."""
        return {r: u for r in self._links if (u := self.users_of(r, audit_at))}

    def as_of(self, audit_at: datetime) -> list[Edge]:
        return [e for e in self.edges if e.t <= audit_at]  # inclusive (H-TIM-03)

    def to_networkx(self, audit_at: datetime) -> nx.MultiDiGraph:
        g = nx.MultiDiGraph()
        for e in self.as_of(audit_at):
            g.add_edge(e.src, e.dst, key=f"{e.type}:{e.source_ref}", type=e.type, t=e.t.isoformat(),
                       **{k: v for k, v in e.attrs})
        return g

    def write_graphml(self, audit_at: datetime, path: Path) -> None:
        nx.write_graphml(self.to_networkx(audit_at), path)

    # ---- construction -----------------------------------------------------------------------------
    @classmethod
    def build(cls, index: IdentityIndex, store: FactStore, activity: list[Activity]) -> "EdgeLog":
        log = cls()
        for r in index.records:  # historical identifiers stay (DESIGN §4.2)
            log.add(f"person:{r.user_id}", HAS_IDENTIFIER, f"id:{r.kind}:{r.value}", r.t, "identities",
                    historical=str(r.historical))
        for f in store.facts:
            node = f"fact:{f.fact_id}"
            for user, kind, token in f.mentions:
                log.add(node, MENTIONS, f"id:{kind}:{token}", f.fact_time, f.fact_id, user=user)
            if not f.resource_id:
                continue  # G-POL-02: a fact without a resource id never yields a step
            res = f"res:{f.resource_id}"
            log.add(node, ABOUT, res, f.fact_time, f.fact_id)
            for st in sorted(derive_states(f)):
                log.add(node, OBSERVED, res, f.fact_time, f.fact_id, state=st)
            for user in sorted(f.users()):
                log.add_resource_user(f.resource_id, user, f.fact_time, f.fact_id)
        for a in activity:
            log.add(f"act:{a.activity_id}", CLAIMED, f"res:{a.resource_id}", a.event_time, a.activity_id,
                    result=a.reported_result, event_type=a.event_type)  # H-STA-02: claims only
            if a.event_type == "LINK_RESOURCE_IDENTITY":  # explicit catalog link between resource and identity
                users = {u for u, _, _ in links(index.scan(a.details, a.activity_id))}
                resources = set(catalog.RESOURCE_ID_RE.findall(a.details)) | {a.resource_id}
                for rid in sorted(resources):
                    for u in sorted(users):
                        log.add(f"res:{rid}", LINKED_BY_CATALOG, f"person:{u}", a.event_time, a.activity_id)
                        log.add_resource_user(rid, u, a.event_time, a.activity_id)
        log.edges.sort(key=lambda e: (e.t, e.type, e.src, e.dst))
        return log
