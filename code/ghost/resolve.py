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
from datetime import datetime, timedelta

from . import catalog
from .config import Flags
from .edgelog import EdgeLog, IN_CHAIN, IN_SLOT
from .identity import IdentityIndex
from .loaders import DeletionRequest
from .runs import RunIndex

TIER_HARD, TIER_SINGLE, TIER_ELIM, TIER_CHAIN, TIER_EVIDENCE = "1", "1s", "3", "3b", "ev"
TIER_LLM, TIER_TIEBREAK, TIER_COOC = "4", "5", "4b"
LOW_CONFIDENCE_TIERS = {TIER_CHAIN, TIER_LLM, TIER_TIEBREAK}  # OQ-11 (2): reported as low confidence


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
    queue: list[dict] = field(default_factory=list)  # ambiguity queue rows (D12)

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


def _case_num(case_id: str) -> int:
    tail = case_id.rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else 10**9


_TEXT_KEYS = {"message_text", "message_excerpt", "note", "notes", "comment", "body", "text", "excerpt", "ocr_text"}


def residual_snippets(store, rid: str, limit: int = 3) -> list[str]:
    """Unstructured content about a parked resource (screenshot / PDF text, free-text fields) that carries no
    validated identifier: the only residuals tier 4 may hand to an LLM (DESIGN §8.3 step 5)."""
    out = []
    for f in store.for_resource(rid):
        if f.mentions:
            continue
        txt = " ".join(str(v) for k, v in f.fields.items() if v and (f.fmt in ("png", "pdf") or k.rsplit(".", 1)[-1] in _TEXT_KEYS))
        if txt.strip():
            out.append(f"{f.file_id}: {txt.strip()[:500]}")
    return out[:limit]


def resolve(cases: list[Case], runs: RunIndex, edges: EdgeLog, flags: Flags, store=None, llm_decider=None) -> Resolution:
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
        # naked singles (single-case window) come after all hard links so that H-STP-05 (at most one resource per
        # type per case) can reject a window event whose case already holds a hard-linked resource of that type
        for rid in sorted(cand):
            if rid in assigned or len(cand[rid]) != 1:
                continue
            cid = next(iter(cand[rid]))
            if any(_type(o) == _type(rid) and assigned[o] == cid for o in assigned):
                res.counts["single_rejected_h_stp_05"] += 1
                cand[rid] = set()
                continue
            assign(rid, cid, TIER_SINGLE)
        for rid in [r for r, c in cand.items() if not c]:
            del cand[rid]

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

    # ---- tier 4: LLM, content residuals only (DESIGN §8.3 step 5, D10) ----------------------------------------
    if flags.tier_llm and llm_decider is not None and store is not None:
        calls = 0
        for rid in sorted(cand):
            if rid in assigned or len(cand[rid]) < 2:
                continue
            snippets = residual_snippets(store, rid)
            if not snippets or calls >= flags.max_tier4_calls:
                continue  # structurally symmetric residuals are not an LLM job: no information to add
            calls += 1
            choice = llm_decider(rid, sorted(cand[rid]), snippets)
            if choice in cand[rid] and not any(_type(o) == _type(rid) and assigned[o] == choice for o in assigned):
                assign(rid, choice, TIER_LLM)  # validated: must be one of the parked candidates
        res.counts["tier4_calls"] = calls
        if flags.tier_eliminate:
            eliminate(TIER_ELIM)

    # ---- tier 4b: audit-capture co-occurrence (D12) ---------------------------------------------------------------
    # An unassigned account mentioned in a file captured <= 24 h before exactly ONE remaining candidate's audit_at
    # goes to that case (G-EVD-06: the audit-capture file is the case's own capture).
    chain_of: dict[str, list[str]] = {}
    for slot in runs.slots:
        for anchor, members in runs.chains(slot)[0].items():
            chain_of.setdefault(anchor, members)

    def assign_chain(a: str, cid: str, tier: str) -> None:
        assign(a, cid, tier)
        for m in chain_of.get(a, []):  # the chain carries its members (3b)
            if m not in assigned and cid in cand.get(m, ()):
                assign(m, cid, tier)

    if flags.d12_refinements and flags.tier_4b and store is not None:
        window = timedelta(hours=24)
        for rid in sorted(cand):
            if rid in assigned or not rid.startswith("account_"):
                continue
            files = {f.file_id: f.file_captured_at for f in store.for_resource(rid)}
            hits = [cid for cid in sorted(cand[rid]) if not res.case_has_account(cid)
                    and any(by_id[cid].audit_at - window <= t <= by_id[cid].audit_at for t in files.values())]
            if len(hits) == 1:
                assign_chain(rid, hits[0], TIER_COOC)
        if flags.tier_eliminate:
            eliminate(TIER_ELIM)

    # ---- ambiguity queue (D12): what is left after every evidence-based tier --------------------------------------
    def anchor_time(a: str):
        evs = events_of[a]
        return min([e.t for e in evs if e.kind == "anchor"] or [e.t for e in evs])

    def slot_state(slot):
        free = sorted((c for c in runs.slots[slot] if not res.case_has_account(c)), key=_case_num)
        chains, _ = runs.chains(slot)
        anchors = sorted((a for a in chains if a not in assigned and a in cand and cand[a] & set(free)),
                         key=lambda a: (anchor_time(a), a))
        return free, anchors

    queue: dict[datetime, dict] = {}
    for slot in sorted(runs.slots):
        free, anchors = slot_state(slot)
        if free:
            queue[slot] = {"kind": "account_slot", "slot": slot.isoformat(), "cases": " ".join(free),
                           "anchors": " ".join(anchors), "shape": f"{len(free)}v{len(anchors)}",
                           "outcome": "unresolved (no anchor left)" if not anchors else ""}
    res.queue = [queue[k] for k in sorted(queue)]
    res.counts["queue_slots"] = len(queue)

    # ---- tier 5: deterministic tie-break (DESIGN §8.3 step 6, D12) --------------------------------------------
    # No ordering signal links cases and anchors (P04), so within a slot the remaining anchors, sorted by event
    # time (stable secondary key: resource id), are paired with the remaining account-less cases, sorted
    # numerically by case id. D12: most-constrained slot first, constraint propagation after each assignment.
    # Low confidence. Optional types left unresolved are NOT emitted; only accounts are always emitted (H-STP-02).
    if flags.tier_tiebreak:
        done: set[datetime] = set()
        while True:
            options = []
            for slot in sorted(runs.slots):
                if slot in done:
                    continue
                free, anchors = slot_state(slot)
                if free and anchors:
                    options.append((len(free) * len(anchors) if flags.d12_refinements else 0, slot, free, anchors))
            if not options:
                break
            _, slot, free, anchors = (min(options, key=lambda o: (o[0], o[1])) if flags.d12_refinements else options[0])
            done.add(slot)
            pairs = []
            for a, cid in zip(anchors, free):
                if cid in cand.get(a, ()) and a not in assigned and not res.case_has_account(cid):
                    assign_chain(a, cid, TIER_TIEBREAK)
                    pairs.append(f"{cid}={a}")
            if slot in queue:
                queue[slot]["outcome"] = ("tier 5: " + " ".join(pairs)) if pairs else "unresolved"
            if flags.d12_refinements and flags.tier_eliminate:
                eliminate(TIER_ELIM)  # propagation after each assignment

    res.parked = {r: set(c) for r, c in cand.items() if r not in assigned}
    for r, c in sorted(res.parked.items()):
        res.queue.append({"kind": "optional_resource", "slot": "", "cases": " ".join(sorted(c)), "anchors": r,
                          "shape": f"1v{len(c)}", "outcome": "not emitted"})
    if res.parked:
        res.notes.append(f"{len(res.parked)} optional resources left unattributed (not emitted)")

    # ---- slots in the edge log -------------------------------------------------------------------------
    for slot, evs in runs.by_slot.items():
        for e in evs:
            edges.add(f"act:{e.activity_id}", IN_SLOT, f"slot:{slot.isoformat()}", e.t, e.activity_id)

    # ---- evidence-only resources (G-LNK-01, H-LNK-02) ---------------------------------------------------
    run_resources = runs.resources()
    # EO-7: a screenshot header / detail panel that shows a catalog resource together with a validated identifier of a
    # case's user links the resource to that case as evidence-only, also when the resource appears in a deletion_worker
    # run, provided no run tier assigned it to another case.
    png_links: dict[str, list[tuple[str, datetime]]] = defaultdict(list)
    if store is not None:
        for f in store.facts:
            if f.fmt == "png" and f.resource_id and f.fields.get("region") in ("header", "detail") and f.fields.get("present") is not None:
                for u in f.users():
                    png_links[u].append((f.resource_id, f.fact_time))
    if flags.evidence_only_links:
        for c in cases:
            if not c.user_id:
                continue
            for rid, t in sorted(png_links.get(c.user_id, [])):
                if rid in run_resources and t <= c.audit_at and catalog.entry_for(rid) and assigned.get(rid) in (None, c.case_id) \
                        and rid not in res.assignments[c.case_id]:
                    res.assignments[c.case_id][rid] = Assignment(rid, c.case_id, TIER_EVIDENCE)
                    res.counts[TIER_EVIDENCE] += 1
            for rid, users in sorted(edges.linked_resources(c.audit_at).items()):
                if c.user_id in users and rid not in run_resources and catalog.entry_for(rid):
                    res.assignments[c.case_id][rid] = Assignment(rid, c.case_id, TIER_EVIDENCE)
                    res.counts[TIER_EVIDENCE] += 1
    return res


def write_ambiguity_queue(rows: list[dict], path) -> None:
    """code/evaluation/ambiguity_queue.csv (D12): one row per slot with account-less cases and per parked resource."""
    import csv

    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["kind", "slot", "cases", "anchors", "shape", "outcome"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
