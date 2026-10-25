"""End-to-end pipeline: evidence -> facts -> edge log -> case resources -> state -> policy -> citations -> steps.

Glue between the modules of DESIGN §2. `build_context` is the expensive part (parse, link, resolve);
`solve_case` is cheap and deterministic.
Rules: H-STP-02 (an account step for every case whose account is resolved), G-STP-08 (observation required to
emit a non-account resource), H-STP-04, S-STA-01..04, OQ-4 (unresolvable email), OQ-11 (3b is low confidence).
"""
from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import catalog, config, loaders
from .citations import Citer
from .edgelog import EdgeLog
from .evidence.image_parser import ImageContext, make_vision
from .evidence.normalize import build_fact_store
from .facts import FactStore
from .identity import IdentityIndex
from .intent import IntentGate
from .llm import LLMClient
from .tier4 import make_decider
from .loaders import DeletionRequest
from .policy import Decision, Policy
from .resolve import Case, LOW_CONFIDENCE_TIERS, Resolution, TIER_EVIDENCE, make_cases, resolve
from .runs import ANCHOR, RunIndex, run_events
from .state import assess
from .steps import Step, order_steps, serialize_steps


@dataclass
class CaseResult:
    case_id: str
    status: str
    steps: list[Step] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    low_confidence: bool = False

    def steps_json(self) -> str:
        return serialize_steps(self.steps)


@dataclass
class Context:
    dataset_dir: Path
    flags: config.Flags
    index: IdentityIndex
    store: FactStore
    edges: EdgeLog
    runs: RunIndex
    cases: list[Case]
    case_by_id: dict[str, Case]
    requests: dict[str, DeletionRequest]
    resolution: Resolution
    policy: Policy
    citer: Citer
    intent_gate: IntentGate | None = None
    llm: LLMClient | None = None
    events_by_resource: dict[str, list] = field(default_factory=dict)


def build_context(dataset_dir: Path | None = None, flags: config.Flags | None = None, llm_profile: str | None = None,
                  run_label: str = "", intent_texts: list[str] | None = None) -> Context:
    """llm_profile None = rules only (no model calls): fast, used by unit tests."""
    d = dataset_dir or config.DATASET_DIR
    flags = flags or config.FLAGS
    index = IdentityIndex.from_dataset(d)
    manifest = loaders.load_evidence_manifest(d)
    activity = loaders.load_activity(d)
    llm = LLMClient(llm_profile, run_label=run_label) if llm_profile else None
    image_ctx = ImageContext({a.resource_id for a in activity}, make_vision(llm) if llm else None, config.CACHE_DIR / "images")
    store = build_fact_store(d, index, manifest, image_ctx)
    reqs = loaders.load_requests(d)
    samples = loaders.load_requests(d, "sample_deletion_requests.csv")
    cases = make_cases(index, reqs, samples)
    gate = IntentGate(llm)
    gate.classify_all(intent_texts if intent_texts is not None else [r.request_text for r in reqs + samples])
    text_of = {r.case_id: r.request_text for r in reqs + samples}
    # D12 (a): intent is applied BEFORE resolution, so NOT_APPLICABLE cases never compete for anchors
    in_play = [c for c in cases if not flags.d12_refinements or text_of[c.case_id] not in gate.results
               or gate.results[text_of[c.case_id]].authorizes_deletion]
    slots: dict[datetime, list[str]] = defaultdict(list)
    for c in in_play:
        slots[c.reported_at].append(c.case_id)
    edges = EdgeLog.build(index, store, activity)
    runs = RunIndex(run_events(activity), dict(slots), flags.chain_policy_band, flags.chain_final_band)
    by_id = {c.case_id: c for c in cases}
    decider = make_decider(llm, index, lambda cid: by_id[cid].user_id) if llm else None
    resolution = resolve(in_play, runs, edges, flags, store, decider)
    ev: dict[str, list] = defaultdict(list)
    for e in runs.events:
        ev[e.resource_id].append(e)
    return Context(
        d, flags, index, store, edges, runs, cases, {c.case_id: c for c in cases},
        {r.case_id: r for r in reqs + samples}, resolution, Policy(loaders.load_rules(d), flags),
        Citer(store, {f.file_id: f.captured_at for f in manifest}), gate, llm, dict(ev))


def case_anchor(ctx: Context, case_id: str) -> datetime | None:
    """Time of the case's own run: its anchor events, else its earliest run event (DESIGN §6)."""
    rids = [r for r, a in ctx.resolution.resources_of(case_id).items() if a.tier != TIER_EVIDENCE]
    evs = [e for r in rids for e in ctx.events_by_resource.get(r, [])]
    anchors = [e.t for e in evs if e.kind == ANCHOR]
    times = anchors or [e.t for e in evs]
    return min(times) if times else None


def _category(ctx: Context, rid: str, audit_at: datetime) -> str | None:
    facts = [f for f in ctx.store.for_resource(rid) if f.fact_time <= audit_at and f.category]
    if facts:
        return max(facts, key=lambda f: (f.fact_time, f.file_captured_at)).category
    return catalog.category_for(rid)


def solve_case(ctx: Context, req: DeletionRequest) -> CaseResult:
    case = ctx.case_by_id[req.case_id]
    fl = ctx.flags
    if not ctx.intent_gate.authorizes_deletion(req.request_text):
        return CaseResult(req.case_id, "NOT_APPLICABLE")  # S-STA-01
    if case.user_id is None:  # OQ-4 / X-IDN-02
        return CaseResult(req.case_id, "COMPLETE" if fl.unresolvable_email_complete else "NOT_APPLICABLE",
                          notes=["request email resolves to no user"], low_confidence=True)
    audit_at = req.audit_at
    assigned = ctx.resolution.resources_of(case.case_id)
    anchor = case_anchor(ctx, case.case_id)
    capture = ctx.citer.audit_capture(case.user_id, audit_at)
    res = CaseResult(req.case_id, "COMPLETE")
    for rid in sorted(assigned):
        sys_id = catalog.system_for(rid)
        category = _category(ctx, rid, audit_at)
        if not sys_id or not category:  # X-SYS-01: closed vocabulary, no step for an unknown resource
            res.notes.append(f"{rid}: unknown system/category, no step")
            continue
        is_account = category == "USER_PROFILE" and rid.startswith("account_")
        facts = ctx.store.for_resource(rid)
        eff_cat, action, rule_ids = ctx.policy.resolve(rid, category, facts, audit_at)
        spec = ctx.policy.spec(eff_cat, action)
        a = assess(rid, spec, ctx.store, audit_at, anchor, sys_id, is_account, case.user_id)
        if not is_account and fl.require_observation_to_emit and not a.observed:
            res.notes.append(f"{rid}: no observation in [anchor, audit_at], no step (G-STP-08)")
            continue
        d = ctx.policy.decide(rid, sys_id, eff_cat, action, spec, a, rule_ids)
        if assigned[rid].tier in LOW_CONFIDENCE_TIERS:
            d.notes.append(f"assigned by tier {assigned[rid].tier}: low confidence")  # OQ-11 (2)
            res.low_confidence = True
        res.decisions.append(d)
    if not any(x.resource_id.startswith("account_") for x in res.decisions):
        res.notes.append("no account resolved for this case")  # H-STP-02 not satisfiable
        res.low_confidence = True
    res.status = "INCOMPLETE" if any(d.violating for d in res.decisions) else "COMPLETE"
    steps: list[Step] = []
    for d in res.decisions:
        for s in d.steps:
            ev = ""
            if s.phase == "FINDING":
                ev, low = ctx.citer.finding(d.assessment, audit_at, capture)
                res.low_confidence |= low
            elif s.phase == "VERIFICATION" and res.status == "COMPLETE":
                ev, low = ctx.citer.verification(d.assessment, audit_at, capture)
                res.low_confidence |= low
            steps.append(dataclasses.replace(s, evidence_id=ev))
    res.steps = order_steps(steps)
    return res


def solve_all(ctx: Context, requests: list[DeletionRequest]) -> list[CaseResult]:
    return [solve_case(ctx, r) for r in requests]
