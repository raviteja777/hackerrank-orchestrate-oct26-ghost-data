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

### OQ-10: exclusion of a case by a contrary identifier link (new rule, M3)
- Raised by / when: Claude Code, claude-sonnet-5-5, 2026-10-25 (M3)
- Context: with P13 logic as written, run events inside a single-case window were assigned to that case even when evidence linked their resource to another person (case_11: account_146 and analytics_9447 sit in the run window but the handover file ties account_146 to a different user; case_12: two accounts and two searches under one case, which violates H-STP-05). Sample precision was 78/84.
- Question: may a validated link from a resource to another user (link time <= the case's audit_at) remove that case from the resource's candidates? It follows from H-IDN-04 / H-IDN-03 (identifiers are exact, one owner) but is not in DESIGN §8.3 as written.
- Options: (a) exclude (b) keep P13 behaviour
- Default implemented now: (a), flag `exclude_foreign_links=True` (config.Flags). 17 resources excluded. Sample precision 79/80 with it; 78/84 without.
- Impact if wrong: some run resources linked to a second user would be dropped from a case; none seen in the samples.
- Status: ANSWERED (2026-10-25 planning chat): **(a) approved**, flag stays on; promoted to rule G-LNK-06. Planning-chat audit of all 1,808 (case, resource) exclusions: 1,768 (98%) are within-slot competition (the foreign user is itself a requester whose run window contains the event); the other 40 are resources of scenario-case users (users 11–22, e.g. search_428 → user_13 / case_35) or of a non-requesting person (search_7455 → user_59) that fall inside generated slots' windows. All links are exact-validated (email 38, user_id 14, phone 1); no decoy or fuzzy match is involved, so **no regex change is needed**. Keep the implemented safeguard: a case is kept when its own user is *also* linked (shared-context records, rule_05).

### OQ-11: M3 numbers vs the probes, band sensitivity, evidence-only noise (informational)
- Raised by / when: Claude Code, claude-sonnet-5-5, 2026-10-25 (M3)
- Context: (1) Tier 1 gives 1,032 hard links vs P13's 927 (+11%). 83 of them rest on facts from the bracket / pipe / syslog log layouts, which the probe's `trace_id` regex could not group; without those it is 949 (+2%). (2) Eval accounts resolved: 447/518 with the DESIGN §8.2 bands (9-11 s / 20-22 s), 396/518 with the P14 bands (8-12 / 19-23); P14 reported 361. Sample precision is the same either way (79/80 vs 77/78). The wider band makes more follow-ups match several anchors, so they are parked. (3) Evidence-only links (479 resources) add noise on samples: case_07 gets object_19 (not in the answer; OQ-1), case_17 gets tombstone_17 (not in the answer). Policy (M4) decides what produces a step. (4) One residual wrong naked single: case_11 analytics_9447 (an all-null analytics record from another run in the window).
- Question: none blocking. 3b remains a probable generator artifact (W-LNK-05); it is switchable (`tier_chains`) and the ablation is reported.
- Default implemented now: DESIGN bands (config `chain_policy_band`, `chain_final_band`).
- Impact if wrong: eval account assignment (tier 3b) could be less reliable than the sample precision suggests, because only 4 sample cases are unresolved and the true pairs were used to derive the bands.
- Status: ANSWERED (2026-10-25 planning chat): (1) accepted, the extra links come from layouts the probe could not parse. (2) keep the DESIGN bands (447/518, same precision); mark every 3b-only assignment `confidence=low` and report the ablation with the overfitting caveat. (3) evidence-only noise: handled in M4 by new rule G-STP-08 (emit a non-account resource only if it has a state observation with fact_time between the case's run anchor and audit_at; catalog-only links such as tombstone_17 / object_19 then produce no step). (4) accepted; see whether G-STP-08 or C3 removes it in M4.

### OQ-12: how snapshot scope and replica copies enter the state (M4 rule proposals)
- Raised by / when: Claude Code, claude-sonnet-5-5, 2026-10-25 (M4)
- Context: a first run (status 28/32) showed two misapplications of G-EVD-01 / G-SYS-01. (1) A bundle snapshot lists only a few records, so "the resource is missing from a covering snapshot" overrode explicit observations (case_12, case_19). (2) A primary-side 404 cleared a failover-replica copy that still held the record (case_05).
- Question: confirm the rules now implemented: (a) scope proof of absence is used only for a resource with no explicit observation in the window (still covers accounts such as case_01/02/31); (b) each copy (topology) is judged separately: a violating copy is cleared only by a later or equal good observation of the same copy; ties go to the violation.
- Options: (a) as implemented (b) scope proof always counts
- Default implemented now: (a), no flag (they are bug fixes of the stated rules). Samples: status 32/32.
- Impact if wrong: absence of unobserved non-account resources would not be proven by a scope; replica findings might be over-reported.
- Status: ANSWERED (2026-10-25 planning chat): (a) and (b) approved as implemented; RULES G-EVD-01 / G-SYS-01 and DESIGN §6 amended. RCA in docs/REVIEW_S3_S4.md §3.

### OQ-13: naked singles and H-STP-05; documents as presence evidence; M4 stubs
- Raised by / when: Claude Code, claude-sonnet-5-5, 2026-10-25 (M4)
- Context: (1) A window naked single is now assigned after all hard links and rejected when the case already holds a resource of that type (H-STP-05); fixes case_11 analytics_9447, M3 precision 79/79. (2) A PDF that names a resource id is a presence observation for record / retention kinds, and an "attachment" cue makes it SUPPORT_ATTACHMENT (support_001, case_07). (3) `intent.authorizes_deletion` is a stub (always true) until M5, so the 10 non-deletion eval requests currently get audit steps. (4) 71 eval cases have no account step because tiers 4 and 5 are stubs (H-STP-02 not yet satisfiable for them).
- Question: none blocking. Please confirm (1) and (2) as rule applications.
- Default implemented now: as described; the missing account steps are a known M4 limit.
- Impact if wrong: (1) a genuine second same-type resource in one case would be dropped; (2) a register PDF that names a resource would count as an observation.
- Status: ANSWERED (2026-10-25 planning chat): (1) and (2) approved (D8 tier order amended; PDF presence subject to G-STP-08 and G-POL-02). (3)/(4): M5 must implement intent and the **deterministic** tier-5 tie-break so every deletion case has an account step (H-STP-02).

### OQ-14: tier-5 tie-break outcome (M5)
- Raised by / when: Claude Code, claude-sonnet-5-5, 2026-10-25 (M5)
- Context: DESIGN §8.3 step 6 implemented as written (per slot, remaining anchors sorted by event time paired with account-less cases sorted by numeric case id; the chain carries its members; tier `5`, low confidence). Baseline before it: status 32/32, F1 0.976, sequence-exact 25/32, 71 eval cases without an account step. After: status 32/32, F1 0.979, sequence-exact 26/32, precision 0.995 (one wrong account: case_21 gets account_294 instead of account_6440), eval accounts 501/518 (79 resources by tier 5), 12 eval cases still without an account step (no anchor left in their slot).
- Question: none blocking. The pairing carries no evidence (P04: no ordering signal), so the precision of tier-5 accounts is expected near chance on the eval set; sample evidence: 3 correct pairs and 1 wrong. Alternative: leave the 17 symmetric accounts out (H-STP-02 then fails for them).
- Default implemented now: tier 5 on (`tier_tiebreak=True`), every tier-5 case is internally low confidence.
- Impact if wrong: a wrong account id costs one step in each affected case, an absent one costs the same, so the tie-break can only gain.
- Status: OPEN (informational)

### OQ-15: screenshot pipeline decisions (M5)
- Raised by / when: Claude Code, claude-sonnet-5-5, 2026-10-25 (M5)
- Context: (1) P09 geometry ported unchanged: 44/44 region consistency on the original / 0.6x / 1.5x / inverted variants. (2) OCR identifier agreement with the original: 1.5x and inverted are identical for all 11 images; 0.6x loses some tokens (see the evaluation report); the D5a gate (no resource id / identifier in header + detail, an OCR id candidate failing validation, fewer than 3 regions, tesseract missing) calls the vision model for such images. On the dataset the gate fires for 2 screenshots (evidence_42 deleted-account reference, evidence_46 object-storage browser); the model finds no resource id there either, so both stay without facts (their subjects exist only as catalog links, which G-STP-08 does not emit). (3) The image cache stores pixel-derived OCR + gate only; the model answer is cached per profile by the LLM layer. (4) Panel text -> state signals (`restore allowed`, `enabled`, `direct identifiers`, `not found`) are generic label cues, not template rules; a detail-panel resource counts as a presence observation for record / retention kinds only.
- Question: please confirm that a screenshot detail panel naming a resource may count as a presence observation (same reasoning as OQ-13.2 for PDFs), and that header / table-row texts only link (they never set state).
- Default implemented now: as described; vision identifiers are accepted only if also present in the OCR text or known (DESIGN §5.1 step 4).
- Impact if wrong: eval scenario cases 33-63 depend on screenshots for the state of a few resources; wrong cues change a finding.
- Status: OPEN

### OQ-16: untrusted-input handling, one refinement to DESIGN §11.3 (M5)
- Raised by / when: Claude Code, claude-sonnet-5-5, 2026-10-25 (M5)
- Context: §11.3 says a flagged request is decided by the rules and never rewritten. Implemented: texts are wrapped in `<request_text>` tags and never edited; a flagged text is sent alone (never batched with clean texts) and its model answer is advisory; the rules decide it, evaluating only the **unflagged sentences** of the text (a flagged sentence is data, so "treat this as a deletion request" cannot turn a data request into a deletion). Splitting into sentences for the rule check is analysis, not rewriting of any prompt or stored text. No request in the 550 texts is flagged.
- Question: confirm that ignoring flagged sentences in the deterministic rule check is acceptable.
- Default implemented now: yes (`intent.split_flagged`); custom case "Intent: injection, negation, multilingual".
- Impact if wrong: a genuine request containing instruction-like words would have that sentence ignored by the rules (the model answer is still recorded).
- Status: OPEN
