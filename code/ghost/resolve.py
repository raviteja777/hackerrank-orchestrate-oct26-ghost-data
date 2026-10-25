"""Tiered resolution of run resources to cases (DESIGN §8.3, D8; port of docs/probes/P13 and P14).

Tier 1  hard: a run resource whose validated identifier links (edge log, fact_time <= the case's audit_at,
        D3) point at exactly one candidate case. A resource with a single candidate case (single-case
        window) is a naked single, counted separately.
Tier 2  park: everything else goes to the ambiguity table {resource -> candidate cases}.
Tier 3  eliminate to a fixpoint: at most one resource per type per case (H-STP-05) and exactly one account
        per case (H-STP-02).
Tier 3b chains by timing phase (W-LNK-05): a chain carried by an identifier link on any member assigns all
        members; then tier 3 runs again. A probable generator artifact: switchable, reported in the ablation.
Tier 4  LLM residual (stub, D10) and tier 5 deterministic tie-break (stub): M3 leaves residuals parked.
Evidence-only resources (audit records, attachments, copies) are added to a case when a validated link
exists at audit_at and the resource is not part of any run (G-LNK-01, H-LNK-02).
Rules: G-LNK-01, H-STP-02, H-STP-05, W-LNK-05, H-IDN-04, H-TIM-02, X-LNK-01 (resolved by D8).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from . import catalog
from .config import Flags
from .edgelog import EdgeLog, IN_CHAIN, IN_SLOT
from .identity import IdentityIndex
from .loaders import DeletionRequest
from .runs import RunIndex

TIER_HARD, TIER_SINGLE, TIER_ELIM, TIER_CHAIN, TIER_EVIDENCE = "1", "1s", "3", "3b", "ev"


@dataclass(frozen=True)
class Case:
    case_id: str
    user_id: str | None
    reported_at: datetime
    audit_at: datetime
    sample: bool = False


@dataclass(frozen=True)
class Assignment:
    resource_id: str
    case_id: str
    tier: str


@dataclass
class Resolution:
    assignments: dict[str, dict[str, Assignment]] = field(default_factory=lambda: defaultdict(dict))
    parked: dict[str, set[str]] = field(default_factory=dict)  # unresolved run resource -> candidate cases
    counts: Counter = field(default_factory=Counter)  # resources assigned per tier
    event_counts: Counter = field(default_factory=Counter)  # run events covered per tier
    notes: list[str] = field(default_factory=list)

    def resources_of(self, case_id: str, include_evidence: bool = True) -> dict[str, Assignment]:
        a = self.assignments.get(case_id, {})
        return dict(a) if include_evidence else {r: x for r, x in a.items() if x.tier != TIER_EVIDENCE}

    def case_has_account(self, case_id: str) -> bool:
        return any(r.startswith("account_") for r in self.assignments.get(case_id, {}))


def make_cases(index: IdentityIndex, requests: list[DeletionRequest], sample_requests: list[DeletionRequest]) -> list[Case]:
    """Sample and eval cases together: they share one activity stream (P04)."""
    out = [Case(r.case_id, index.user_for_email(r.email), r.reported_at, r.audit_at, True) for r in sample_requests]
    out += [Case(r.case_id, index.user_for_email(r.email), r.reported_at, r.audit_at, False) for r in requests]
    return out


def _type(resource_id: str) -> str:
    e = catalog.entry_for(resource_id)
    return e.prefix if e else resource_id.rsplit("_", 1)[0]


def resolve(cases: list[Case], runs: RunIndex, edges: EdgeLog, flags: Flags) -> Resolution:
    res = Resolution()
    by_id = {c.case_id: c for c in cases}
    events_of: dict[str, list] = defaultdict(list)
    for e in runs.events:
        events_of[e.resource_id].append(e)
    cand: dict[str, set[str]] = {}
    for rid, evs in events_of.items():
        c = set().union(*(runs.candidate_cases(e) for e in evs))
        if c:
            cand[rid] = c
    assigned: dict[str, str] = {}  # resource -> case
    foreign: set[str] = set()

    # Exclusion by contrary link (OQ-10, flag exclude_foreign_links): a resource validated to belong to another
    # user at the case's audit_at cannot be this case's resource, whatever the run window says (H-IDN-04, H-IDN-03).
    if flags.exclude_foreign_links:
        for rid in sorted(cand):
            keep = {cid for cid in cand[rid]
                    if not (u := edges.users_of(rid, by_id[cid].audit_at)) or by_id[cid].user_id in u}
            if keep != cand[rid]:
                if keep:
                    cand[rid] = keep
                else:
                    foreign.add(rid)
        for rid in foreign:
            del cand[rid]
        res.counts["foreign_excluded"] = len(foreign)

    def link_cases(rid: str, cases_: set[str]) -> set[str]:
        out = set()
        for cid in cases_:
            c = by_id[cid]
            if c.user_id and c.user_id in edges.users_of(rid, c.audit_at):  # D3: link time <= this case's audit_at
                out.add(cid)
        return out

    def assign(rid: str, cid: str, tier: str) -> None:
        assigned[rid] = cid
        cand[rid] = {cid}
        res.assignments[cid][rid] = Assignment(rid, cid, tier)
        res.counts[tier] += 1
        res.event_counts[tier] += len(events_of[rid])

    # ---- tier 1: hard identifier links, plus naked singles ------------------------------------------
    if flags.tier_hard:
        for rid in sorted(cand):
            linked = link_cases(rid, cand[rid])
            if len(linked) == 1:
                assign(rid, next(iter(linked)), TIER_HARD)
            elif len(linked) > 1:
                cand[rid] = linked  # multi-link: parked with the linked candidates only
            elif len(cand[rid]) == 1:
                assign(rid, next(iter(cand[rid])), TIER_SINGLE)

    def eliminate(tier: str) -> None:
        changed = True
        while changed:
            changed = False
            for rid in sorted(cand):  # C3: at most one resource per type per case (H-STP-05)
                if rid in assigned:
                    continue
                taken = {assigned[o] for o in assigned if _type(o) == _type(rid)}
                new = cand[rid] - taken
                if new != cand[rid] and new:
                    cand[rid] = new
                    changed = True
                if len(cand[rid]) == 1:
                    assign(rid, next(iter(cand[rid])), tier)
                    changed = True
            for c in sorted(by_id):  # C2: exactly one account per case (H-STP-02): hidden singles
                if res.case_has_account(c):
                    continue
                opts = [r for r in sorted(cand) if r not in assigned and r.startswith("account_") and c in cand[r]]
                if len(opts) == 1:
                    assign(opts[0], c, tier)
                    changed = True

    if flags.tier_eliminate:
        eliminate(TIER_ELIM)

    # ---- tier 3b: chains by timing phase --------------------------------------------------------------
    if flags.tier_chains:
        for slot in sorted(runs.slots):
            slot_cases = runs.slots[slot]
            chains, _parked = runs.chains(slot)
            owner: dict[str, str] = {}
            for anchor, members in sorted(chains.items()):
                hits = {cid for cid in slot_cases for m in members if link_cases(m, {cid})}
                if len(hits) == 1:
                    owner[anchor] = next(iter(hits))
            free_cases = [c for c in slot_cases if c not in owner.values() and not res.case_has_account(c)]
            free_anchors = [a for a in chains if a not in owner]
            if len(free_cases) == 1 and len(free_anchors) == 1:  # P14 elimination
                owner[free_anchors[0]] = free_cases[0]
            for anchor, cid in sorted(owner.items()):
                for m in chains[anchor]:
                    edges.add(f"res:{m}", IN_CHAIN, f"chain:{anchor}", slot, anchor)
                    if m not in assigned and cid in cand.get(m, ()):
                        assign(m, cid, TIER_CHAIN)
        if flags.tier_eliminate:
            eliminate(TIER_ELIM)

    # ---- tier 4 / 5: stubs (M3) ----------------------------------------------------------------------
    res.parked = {r: set(c) for r, c in cand.items() if r not in assigned}
    if flags.tier_llm and res.parked:
        res.notes.append(f"tier 4 (LLM residual) is a stub in M3: {len(res.parked)} resources left parked")
    if flags.tier_tiebreak and res.parked:
        res.notes.append("tier 5 (deterministic tie-break) is a stub in M3")

    # ---- slots in the edge log -------------------------------------------------------------------------
    for slot, evs in runs.by_slot.items():
        for e in evs:
            edges.add(f"act:{e.activity_id}", IN_SLOT, f"slot:{slot.isoformat()}", e.t, e.activity_id)

    # ---- evidence-only resources (G-LNK-01, H-LNK-02) ---------------------------------------------------
    run_resources = runs.resources()
    if flags.evidence_only_links:
        for c in cases:
            if not c.user_id:
                continue
            for rid, users in sorted(edges.linked_resources(c.audit_at).items()):
                if c.user_id in users and rid not in run_resources and catalog.entry_for(rid):
                    res.assignments[c.case_id][rid] = Assignment(rid, c.case_id, TIER_EVIDENCE)
                    res.counts[TIER_EVIDENCE] += 1
    return res
