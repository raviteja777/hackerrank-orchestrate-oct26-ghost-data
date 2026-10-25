"""Raw parser records -> Facts (DESIGN §4.1, §5).

Per record: catalog lookup (system, category), identifier extraction through the two-stage matcher (only
validated links become `mentions`; decoys are logged, H-IDN-04), canonical state signals, record-level
`fact_time` (D3) and the file `captured_at` for citability. Records with neither a resource id nor a
validated identifier are noise and are dropped (counted). PNGs are registered as unparsed (M5 TODO).
Rules: H-IDN-04, H-TIM-02, G-SYS-01, X-SYS-01, G-POL-02.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import catalog, loaders
from ..facts import Fact, FactStore, SnapshotScope
from ..identity import IdentityIndex, decoys, links
from . import ParsedFile, RawRecord, parse_file

# last path segment -> canonical identifier column (exposure test input for the policy engine, M4)
_IDENT_COLUMNS = {
    "email": "email", "requester_email": "email", "owner_email": "email", "customer_email": "email",
    "phone": "phone", "requester_phone": "phone", "owner_phone": "phone",
    "full_name": "name", "name": "name", "requester_name": "name", "display_name": "name",
    "email_hash": "email_hash", "user_id": "user_id", "customer_reference": "customer_reference",
}


_FREE_TEXT_KEYS = {"message_text", "message_excerpt", "note", "notes", "comment", "body", "text", "excerpt"}


def _to_int(v: Any) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _to_bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    s = str(v).strip().lower()
    return True if s in ("true", "1", "yes") else False if s in ("false", "0", "no") else None


def ident_fields(fields: dict[str, Any]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for key, val in fields.items():
        col = _IDENT_COLUMNS.get(key.rsplit(".", 1)[-1])
        if col:
            nonnull = val is not None and str(val).strip() != ""
            out[col] = out.get(col, False) or nonnull
    return out


def signals_from(fields: dict[str, Any], event: str | None) -> dict[str, Any]:
    f = fields
    first = lambda *ks: next((f[k] for k in ks if f.get(k) is not None), None)  # noqa: E731
    s: dict[str, Any] = {}
    http = _to_int(first("http_status", "status_code"))
    if http is not None:
        s["http_status"] = http
    rows = _to_int(first("rows", "row_count"))
    if rows is not None:
        s["rows"] = rows
    if first("result") is not None:
        s["result"] = str(first("result"))
    if first("state") is not None:  # handover STATE label
        s["state_label"] = str(first("state"))
    di = _to_int(f.get("direct_identifiers"))  # analytics_profile_read / analytics_identity_scan (review item 1)
    if di is not None:
        s["direct_identifiers"] = di
    if f.get("decision") is not None:  # restore_authorization_completed: deny -> blocked (review item 2)
        s["decision"] = str(f["decision"]).lower()
    if f.get("detector") is not None or f.get("matched_value") is not None:  # *_pii_scan (review item 3)
        s["pii_match"] = f.get("matched_value") is not None
        s["detector"] = str(f.get("detector") or "")
    for key in ("enabled", "restore_allowed", "eligible", "deletion_block", "marker_found", "email_opt_in",
                "scheduler_registered", "download_available", "available"):
        b = _to_bool(f.get(key))
        if b is not None:
            s[key] = b
    for key in ("retention_until", "retained_until", "account_status", "connector_name", "last_delivery_status",
                "event_code", "audience_cohort", "heartbeat", "record_type", "source"):
        if f.get(key) is not None:
            s[key] = f[key]
    if "profile" in f and f["profile"] is None and not any(k.startswith("profile.") for k in f):
        s["profile_null"] = True
    ref = first("subject_reference", "customer_reference", "subject_ref", "subject_key")
    if ref is not None:
        s["subject_ref"] = str(ref)
    if event:
        s["event"] = event
    return s


def _record_to_fact(f: loaders.EvidenceFile, parsed: ParsedFile, rec: RawRecord, index: IdentityIndex,
                    store: FactStore, seen_ids: set[str]) -> None:
    fields = rec.fields
    rid = fields.get("resource_id")
    rid = rid.strip() if isinstance(rid, str) and rid.strip() else None
    fact_id = f"{f.file_id}#{rec.locator}"
    if fact_id in seen_ids:
        n = 2
        while f"{fact_id}~{n}" in seen_ids:
            n += 1
        fact_id = f"{fact_id}~{n}"
    seen_ids.add(fact_id)

    matches = index.scan(rec.text, fact_id)
    mentions = tuple(sorted(links(matches)))
    rejected = tuple(sorted({(m.kind, m.token, m.outcome.value) for m in decoys(matches)}))
    if rid is None and not mentions:
        store.dropped_noise += 1
        return
    for kind, token, outcome in rejected:
        store.decoys.append((fact_id, kind, token, outcome))

    # validated identifiers inside free text (message_text, message_excerpt, ...): exposure for REDACT /
    # ANONYMIZE categories (review item 3); the policy compares the users with the case's user.
    free = " ".join(str(v) for k, v in fields.items()
                    if v and k.rsplit(".", 1)[-1] in _FREE_TEXT_KEYS)
    text_mentions = frozenset(u for u, _, _ in links(index.scan(free, fact_id))) if free else frozenset()

    system = catalog.system_for(rid, rec.system_hint)
    if rid and system is None:
        system = f"unknown:{catalog.prefix_of(rid)}"  # X-SYS-01: closed vocabulary, no step later
    category = catalog.category_for(rid, rec.label_category, rec.collection, rec.event)
    when = rec.fact_time or rec.capture_time or parsed.capture_time or f.captured_at
    store.add(Fact(
        fact_id=fact_id, file_id=f.file_id, file_captured_at=f.captured_at, fact_time=when, fmt=parsed.fmt,
        locator=rec.locator, system_id=system, resource_id=rid, category=category, topology=rec.topology,
        collection=rec.collection, capture_time=rec.capture_time or parsed.capture_time,
        mentions=mentions, decoys=rejected, signals=signals_from(fields, rec.event),
        ident_fields=ident_fields(fields), fields=dict(fields), line_span=rec.line_span,
        text_mentions=text_mentions,
    ))


def build_fact_store(dataset_dir: Path | None = None, index: IdentityIndex | None = None,
                     manifest: list[loaders.EvidenceFile] | None = None, image_ctx=None) -> FactStore:
    index = index or IdentityIndex.from_dataset(dataset_dir)
    manifest = manifest if manifest is not None else loaders.load_evidence_manifest(dataset_dir)
    store = FactStore()
    for f in manifest:  # manifest order: deterministic
        try:
            parsed = parse_file(f, dataset_dir, image_ctx, lambda t: bool(links(index.scan(t))))
        except Exception as exc:  # a broken file must not stop the run; it is reported
            store.unparsed.append((f.file_id, f.file_path, f"{type(exc).__name__}: {exc}"))
            continue
        if parsed.unparsed_reason and not parsed.records:
            store.unparsed.append((f.file_id, f.file_path, parsed.unparsed_reason))
            continue
        if parsed.stats:  # log parser self-check: warn when < 90% of carrying lines are traced or self-contained
            carrying, orphans = parsed.stats["carrying"], parsed.stats["orphans"]
            share = 1.0 if carrying == 0 else 1.0 - orphans / carrying
            store.parser_report.append({"file_id": f.file_id, "path": f.file_path, "lines": parsed.stats["lines"],
                                        "carrying": carrying, "orphans": orphans, "share": round(share, 4),
                                        "warn": share < 0.90 and carrying >= 10})
        seen: set[str] = set()
        for rec in parsed.records:
            _record_to_fact(f, parsed, rec, index, store, seen)
        if not store.for_file(f.file_id) and not parsed.scopes:  # every record was noise: account for the file anyway
            store.unparsed.append((f.file_id, f.file_path, "no resource id or validated identifier recovered"
                                   + (" (screenshot: vision gate D5a applies)" if parsed.fmt == "png" else "")))
        for sc in parsed.scopes:
            sysid = catalog.normalize_system(sc.system_id_hint)
            if sysid:
                store.scopes.append(SnapshotScope(f.file_id, sysid, sc.topology, sc.captured_at))
    return store
