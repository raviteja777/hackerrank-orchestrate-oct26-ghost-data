# Open questions (build-time escalation log)

Used by Claude Code during the build (DESIGN.md §15.1). The user takes each open item back to the planning chat; the answer is recorded here and, if it changes behaviour, in `docs/DECISIONS.md` / `docs/RULES.md`.

## Template
```
### OQ-<n>: <short title>
- Raised by / when: <tool, model, ISO time>
- Context: <module, case_ids, evidence ids, what was observed>
- Question: <one precise question>
- Options: (a) … (b) … (c) …
- Default implemented now: <option + config flag name>
- Impact if wrong: <which outputs / metrics change>
- Status: OPEN | ANSWERED (<date>, <answer>) | CLOSED
```

## Seeded questions (from planning, DESIGN.md §16)
| ID | Question | Default | Status |
|---|---|---|---|
| OQ-1 | `object_*` resources: system_id and category | `object_storage`, SUPPORT_ATTACHMENT, DELETE (flag `object_as_attachment`) | OPEN |
| OQ-2 | Expired retention / legal hold at audit_at | not retained → DELETE semantics (flag `expired_retention_delete`) | OPEN |
| OQ-3 | Retained record still carrying prohibited identifiers; required retained record absent | no finding; flagged (flag `retained_pii_finding=False`) | OPEN |
| OQ-4 | Request email that resolves to no user | COMPLETE with `[]`, logged | OPEN |
| OQ-5 | COMPLETE verification without any citable proof | audit-capture file, else latest citable subject file; low confidence | OPEN |
| OQ-6 | Output row order (D1) | numeric input order; awaiting organiser answer on Discord | OPEN |

### OQ-7: P12 baseline scope (informational, no behaviour change)
- Raised by / when: Claude Code, claude-sonnet-5-5, 2026-10-25
- Context: M1 reproduction of P12. The counts 1,958 / 353 / 24 / 4 reproduce exactly when the scanned text evidence is the json/sql/log/txt files (PDF and PNG excluded). Including the 4 PDFs (pypdf text) adds 2 more EXACT email occurrences (1,960); the other counts do not change.
- Question: none blocking. Confirming that P12's "1,958" meant non-PDF text evidence.
- Options: (a) keep as is (PDFs are parsed in M2 and their identifiers validated by the same matcher) (b) none
- Default implemented now: `scripts/repro_p12.py` scans non-PDF text files only (acceptance numbers); the matcher itself is format-agnostic.
- Impact if wrong: none on outputs.
- Status: ANSWERED (2026-10-25, user: yes, P12 covers the text evidence formats only; PDFs and PNGs are excluded by design)

### OQ-8: account_004 (case_04) is in no participant file (informational)
- Raised by / when: Claude Code, claude-sonnet-5-5, 2026-10-25 (M2)
- Context: `account_004` occurs only in `sample_output.csv`: not in any evidence file, not in `system_activity`. M2 acceptance finds it neither as a fact nor as a run candidate. SAMPLE_DEEP_DIVE §5.2 lists it among the accounts that cannot be tied to the case by any identifier.
- Question: none blocking. Extends the W-CEIL-01 ceiling list from {audit_record_6645, audit_record_5569} to include account_004. Eval cases may have the same pattern (a scenario-style account absent from every file); H-STP-02 still requires an account step, resolved in M3 only where the run or a tier makes it reachable.
- Options: (a) keep as ceiling (b) none
- Default implemented now: listed in `scripts/m2_acceptance.py` CEILING; never guessed.
- Impact if wrong: one sample step; no code path depends on it.
- Status: ANSWERED (2026-10-25 planning chat): accepted. account_004 joins the W-CEIL-01 ceiling list. Never guessed. For eval cases the account step is still emitted (H-STP-02) whenever the run or a D8 tier makes an account reachable.

### OQ-9: evidence shapes seen in M2 beyond the DESIGN §5 table (informational)
- Raised by / when: Claude Code, claude-sonnet-5-5, 2026-10-25 (M2)
- Context: all handled by the generic parsers, no new code path: (1) SQL snapshots that contain only `snapshot_scope` rows (e.g. evidence_90): they yield no facts, only scopes (absence proofs, G-EVD-01); (2) bundle collections `operational_record_history` under data stores `backup_restore_service` / `privacy_treatment_service` / `support_storage_service` with a per-record `system` field, so the catalog prefix decides the system and these store names are aliased; (3) trace-less `record_lookup` log lines (notification_delivery, search_index_diagnostic): one fact per line; (4) the pipe log style begins with `|` after the timestamp; (5) a seventh log layout beyond the six listed: the legacy `support_replica.log` (key=value, `trace_id=tr-rp-*`).
- Question: none.
- Default implemented now: as described; PNG files are registered as unparsed with a TODO(M5) reason.
- Impact if wrong: none for M2.
- Status: ANSWERED (2026-10-25 planning chat): accepted. DESIGN §5 updated: seven log layouts, scope-only SQL snapshots, `operational_record_history` store aliases, trace-less record_lookup lines.
