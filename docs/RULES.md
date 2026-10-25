# Rules Register (running)

Planning document, not a deliverable. It lists every rule the solution relies on, with its status and the evidence behind it. When planning is finalised it is converted to `rules.json`, keeping the same rule IDs.

## How this file works
- **Status bands**
  - **SPEC**: stated in `problem_statement.md`, `README.md` or `AGENTS.md`. Hard by definition, and only the organisers can change it.
  - **HARD**: observed and verified, 100% support with adequate coverage and no counterexample.
  - **GOOD**: fully consistent so far, but coverage is low or not yet cross-checked against evidence files.
  - **WEAK**: seen in places, but sparse, ambiguous, or with at least one counterexample.
  - **GAP**: a rule we need, but the sample data shows nothing.
- **Promotion and demotion** happen only with numbers. One counterexample demotes a rule immediately.
- **Support notation**: `n/N` = holds in n of N applicable cases, followed by the case ids or the probe reference.
- **Probes**: when code is needed to test a rule, it goes in `docs/probes/Pxx_<name>.py` and gets an entry in the probe log at the bottom.
- **IDs are stable.** A rule is never renumbered. A retired rule is marked RETIRED, not deleted.

Prefixes: `ORD` ordering and serialisation, `STA` case status, `STP` step construction, `CIT` citation, `IDN` identity, `INT` intent, `TIM` time cut-off, `EVD` evidence interpretation, `POL` policy (deletion_rules), `SYS` system_id mapping, `FLW` data flows and restore.

---

## SPEC — contract rules
| ID | Rule | Source |
|---|---|---|
| S-ORD-01 | Output columns are exactly `case_id,deletion_status,steps_json`. There are exactly 518 data rows, one per request. | problem_statement Required Output |
| S-ORD-02 | Steps are ordered by phase FINDING → REMEDIATION → VERIFICATION, then by operation-table order, then by `system_id` ascending, then by `resource_id` ascending. | problem_statement Rules |
| S-ORD-03 | `step_no` starts at 1 and increases consecutively. Array order is significant, while JSON key order and whitespace are ignored. | problem_statement |
| S-STP-01 | Each step has exactly 7 keys: `step_no, phase, system_id, resource_id, operation, state, evidence_id`. Only the 15 listed operation/state pairs are allowed. | AGENTS §6.3–6.4 |
| S-STA-01 | `NOT_APPLICABLE` means the request does not authorise deletion, and `steps_json` = `[]`. | problem_statement |
| S-STA-02 | `COMPLETE` contains only VERIFICATION steps, each citing evidence. | problem_statement |
| S-STA-03 | `INCOMPLETE` contains findings (cited), the complete remediation plan and post-remediation verification. Remediation and verification steps have `evidence_id` = `""`. | problem_statement |
| S-STA-04 | COMPLETE requires all of: every copy treated per the rules; no active sync, import or restore path; retained records hold only permitted identifiers; required retained records are still present. | problem_statement |
| S-TIM-01 | Use only information at or before `audit_at`. Never cite evidence captured after `audit_at`. | AGENTS §6.2, §6.6 |
| S-CIT-01 | `evidence_id` may be a `file_id`, an `activity_id` or an `audit_id`. | problem_statement |
| S-EVD-01 | `reported_status` and `reported_result` are claims, not proof. | problem_statement |
| S-IDN-01 | Resolve current and historical identifiers. The request email may be either. | AGENTS §6.5 |
| S-POL-01 | An ACCOUNT_TOMBSTONE keeps the stable `user_id`. Name, email, phone and email_hash are removed (REDACT). | problem_statement, rule_15 |
| S-POL-02 | Do not delete records that policy requires to be retained, redacted, anonymized or kept as a tombstone. | AGENTS §6.5 |
| S-FLW-01 | Within remediation, disable flows and block restores **before** changing dependent records. Process downstream copies before their source when a dependency requires it. | AGENTS §6.5. **Subordinate to S-ORD-02 (D2):** satisfied only through operation-table order (DISABLE and BLOCK precede record changes). Never reorders steps outside the sort. |
| S-FLW-02 | Verification must cover the required final state of every remediated record or process. | AGENTS §6.5 |

## HARD — verified observations
| ID | Rule | Support | History |
|---|---|---|---|
| H-ORD-01 | `output.csv` rows are in numeric `case_id` order, which equals the input file row order. | Input and sample files both numeric (EDA §1). Decision D1 | 2026-10-24 adopted (Discord question pending) |
| H-STP-01 | Finding → remediation → verification pairing per resource: REMAINING_RECORD → DELETE_RECORD → VERIFY_RECORD_ABSENT; EXPOSED_PII → REDACT_RECORD → VERIFY_RECORD_REDACTED, **or** → ANONYMIZE_RECORD → VERIFY_RECORD_ANONYMIZED; ACTIVE_DATA_FLOW → DISABLE_DATA_FLOW → VERIFY_DATA_FLOW_DISABLED; RESTORE_RISK → BLOCK_RESTORE → VERIFY_RESTORE_BLOCKED. | 41/41 finding triplets in samples, 0 deviations (EDA §2.1) | 2026-10-24 |
| H-ORD-02 | Inside every phase the S-ORD-02 sort is absolute. Dependency ordering (S-FLW-01) never overrides it. | Spec authority (D2) plus samples: 11/11 multi-system remediations, 2/2 direct conflicts (case_16, case_24: `account_service` DELETE before `search_service` DELETE) | 2026-10-24 G-ORD-01 → HARD (D2) |
| H-STA-02 | State is decided from evidence, never from `reported_status` or `reported_result`. | Counterexamples to activity claims: case_02 (PARTIAL→absent), case_10, 16 and 24 (SUCCESS→present), case_25 (FAILED→absent) | 2026-10-24 P02; absorbs H-STA-01 (reported_status wrong in 22/32), restates S-EVD-01 with evidence |
| H-STP-02 | Every case has exactly one `account_service` resource: VERIFY_ABSENT, or a REMAINING finding if evidence shows it present. | 32/32 | 2026-10-24 P02 |
| H-TIM-02 | **Knowledge time = record-level timestamp** (inner snapshot `captured_at`, `observed_at`, log-line time). Facts timestamped ≤ `audit_at` may be used for discovery even if the file was captured later. Such files are **never cited**. | case_09 (evidence_06 lines 08:52 < audit 09:00), case_23 and case_24 (evidence_02 inner snapshot 09-15T12:00) | 2026-10-24 G→HARD by decision D3 |
| H-STP-05 | **At most one resource per type per case** (account exactly one). Usable as an elimination constraint. | 32/32 sample cases, every type n=1 | 2026-10-25 sweep: G→HARD (32/32, every type n=1) |
| H-STP-06 | Retained SECURITY_AUDIT_LOG records produce `VERIFY_RECORD_PRESENT` (security_service, `audit_record_*`) with **no** finding or remediation, in both COMPLETE and INCOMPLETE cases. | 24/24 VERIFY_PRESENT are security_service | 2026-10-25 24/24; sweep G→HARD |
| H-LNK-02 | Security audit records are discovered from evidence via `user_NN` (`subject_reference`, `correlation_key`, `lookup_key`, handover line) and are always VERIFY_RECORD_PRESENT (`retention_until` in the future). | 22/24 discoverable; 2 unreachable (W-CEIL-01) | 2026-10-25 22/22 discoverable all PRESENT; sweep G→HARD |
| H-LNK-03 | In logs, link per `trace_id`: the `*_started` line carries an identifier (lookup_key, subject_key, subject_ref, correlation_key), and the `*_completed`/event line carries `resource_id` + state. Historical identifiers count (old email: case_10; old email hash: case_12). | cases 03, 09, 10, 12, 15, 17, 18, 19, 20 | 2026-10-25 9 cases, 0 counterexamples; sweep G→HARD |
| H-STP-04 | **Every case resource gets exactly one VERIFICATION step** (remediated or already compliant), and at most one FINDING. In INCOMPLETE cases **all** verification steps have `evidence_id=""`, including already-compliant ones. | 32/32 cases: each resource exactly 1 verify; 0 resources with >1 finding; incomplete_future_blank 22/22 | 2026-10-25 sweep: G-STP-02 → HARD, criterion sharpened |
| H-TIM-03 | The `audit_at` cut-off is **inclusive** (≤): a file captured exactly at `audit_at` is usable and citable. | 15 sample citations have `captured_at == audit_at` (evidence_03, 05, 51) | 2026-10-25 sweep |
| H-STP-07 | The finding operation follows from the required treatment: DELETE → REPORT_REMAINING_RECORD; REDACT or ANONYMIZE → REPORT_EXPOSED_PII; active flow → REPORT_ACTIVE_DATA_FLOW; restorable backup → REPORT_RESTORE_RISK. A retained backup gets only VERIFY_RESTORE_BLOCKED, never VERIFY_RECORD_PRESENT. | 41/41 findings; 6/6 backups verified as BLOCKED, 0 as PRESENT | 2026-10-25 sweep |
| ~~H-IDN-01~~ | Email matching is case-insensitive and whitespace-trimmed. | 20 uppercase eval emails resolve only when lowercased. All 550 resolve. | RETIRED 2026-10-25: merged into H-IDN-04 (case-insensitive exact validation) |
| H-IDN-04 | **Two-stage identifier matching** (user refinement 2026-10-25). Stage 1 *candidate retrieval*: loose, case-insensitive substring or regex search (e.g. email local part, digits of a phone), tuned for recall. Stage 2 *mandatory exact validation*: extract the full token around the hit (whole email, 64-hex hash, normalised phone digits, `\buser_NN\b`) and accept only if it **equals** an identifier in the subject's identity set (current **and** historical). Outcomes: exact → link; same user's other identifier → link (that identifier also validates); a different known user → reject (look-alike); unknown → reject (decoy) and log it. Only stage-2 links create facts. | P12 over all text evidence × all users' emails: 2,339 substring candidates → 1,958 exact, **353 same user's other email** (would be lost by single-email matching), **24 unknown decoys** (`*.jr@`, `jonas.berglund`), **4 different-user look-alikes** (`thandiwe.n5276` = user_413 vs `thandiwe.n` = user_04) | 2026-10-25 |
| H-IDN-02 | `email_hash` = sha256(lowercase(email)). This holds for current and historical emails. | 850/850 current, 107/107 historical pairs | 2026-10-24 |
| H-IDN-03 | An email belongs to exactly one user over its whole history (no reuse). Historical email changes always precede the request. | 0 reuse; 100/100 changes precede the request | 2026-10-24 |
| ~~H-TIM-01~~ | (cited `captured_at` ≤ `audit_at`) | 75/75 | RETIRED 2026-10-25: duplicate of S-TIM-01; evidence kept as confirmation |
| ~~H-STA-01~~ | (`reported_status` does not predict status) | 22/32 wrong | RETIRED 2026-10-25: merged into H-STA-02 |

## GOOD — consistent, needs more confirmation
| ID | Rule | Support | Open question / next check |
|---|---|---|---|
| G-CIT-01 | Citations use evidence **file ids**, never activity or audit ids. | 75/75 sample citations | The spec allows activity and audit ids. When would those be the *only* proof? Check in the sample deep-dive. |
| G-EVD-01 | Absence is proven by citing a snapshot of the relevant system in which the record is **missing**. | case_01/02/04 cite evidence_54 (failover replica without `account_00N`); case_31 cites evidence_51 (account collection with 0 records). The account need not be mentioned (SAMPLE_DEEP_DIVE §5.2) | How to choose *which* snapshot proves absence, e.g. latest before audit_at, or same system. **Amended 2026-10-25 (OQ-12a):** a snapshot's scope is not completeness; scope proves absence only when the resource has no explicit observation in the window. |
| G-INT-01 | Exactly 10 eval requests are non-deletion (`case_533`–`case_542`). All 62 non-English requests are deletion requests. | Intent templates (EDA §3), matches 10 CLASSIFY_REQUEST activities | Confirm that the CLASSIFY_REQUEST resources map to these 10 users. |
| G-LNK-01 | **Case inventory = deletion run ∪ evidence-only resources** (security audit records, replica copies, attachments, legacy copies). *(Merged with G-EVD-02 in the sweep, 2026-10-25: "run is the inventory" and "activity is not the inventory" read as contradictory; 26/111 sample resources are evidence-only.)* Each case has a deletion_worker run tied to its `reported_at`. Generated family: `submitted primary profile <account>` at −45…−75 min, successful policy actions at −28/−21/−14/−7 min, failures and checks at +40…+115 min. All non-audit answer resources come from the run, except attachments and copies found only in evidence. | 31/32 accounts, 85/87 non-audit resources (misses: account_004, support_001). **Window criteria (P10, all 1466 deletion_worker events):** anchor −80…−40 fits 532/532, all to a unique `reported_at` slot; policy action −35…0 fits 248/248, all unique; final result +30…+125 fits 557/558 (429 unique); checks +30…+125 fit 116/117 (81 unique); scenario style −10…+15 fits 11/11. | Bands come from the samples and are validated on the full stream. Remaining slot overlap only for final and check events (hourly slots, ~95-min band). Within-slot sharing → X-LNK-01 |
| G-POL-01 | Category → treatment mapping (see SAMPLE_DEEP_DIVE §3.7): search, export, account → DELETE; analytics with an identifier → ANONYMIZE; support message with requester identifiers → REDACT; support attachment or legacy copy → DELETE; flow enabled → DISABLE; backup restorable → BLOCK; tombstone with PII → REDACT. Compliant counterparts → matching VERIFY. | 87 non-audit resources, 0 contradictions | Categories never seen: cache, marketing, email delivery, legal hold (X-POL-01). |
| G-CIT-02 | A finding cites the file showing the violating state. A COMPLETE verification cites the file proving the compliant state, preferring one capture covering all resources, close to `audit_at`. | 75/75 citations | Absorbs W-TIM-01 (latest capture ≤ audit) and links to G-EVD-06 (audit-capture file) and G-EVD-01 (absence snapshot). Tie-break → X-CIT-01. |
| G-EVD-05 | PDF/PNG evidence belongs to single-subject "scenario" cases (eval cases 33–63, users 03–22). All of them are alone at their `reported_at`, so binary evidence is needed for their records but not for run disambiguation. | 12/12 eval cases with binary evidence have group size 1 | Confirm evidence_42/46 subjects with the vision path. |
| G-POL-02 | Evidence with **no resource id** produces no step (e.g. the finance disputed-order register). It is not treated as a LEGAL_HOLD_RECORD. | 6/6 users in the register have no legal-hold step in their sample answers (08, 12, 17, 21, 24, 29) | Real legal_hold_* resources exist in activity (10 RETAIN events), unseen in samples → X-POL-01. |
| G-EVD-06 | **Audit-capture file.** For almost every case exactly one evidence file is captured shortly before `audit_at` (median 16 min, p90 24 min) and mentions the subject. It is the primary state source and the citation for that case. Older files (incl. the 24 SQL snapshots Feb–Sep) only supply history, e.g. pre-deletion links. | eval: 488/518 cases have exactly 1 such file (30 have none); samples: 28/32 cite it (exceptions 04, 05 cite older absence snapshots, 31/32 cite the bundle) | The 30 eval cases with none → scenario cases (binary evidence) or absence-only captures; check. |
| G-POL-03 | `legal_hold_*` records exist in evidence (system `legal_service`, `retained_until` 2033, `subject_reference` user_NN; 8 users) → LEGAL_HOLD_RECORD → RETAIN → VERIFY_RECORD_PRESENT (same pattern as H-STP-06). | Found in M2 review (evidence_21/24/36/40/43/45/47); unseen in samples | Partly closes X-POL-01. |
| G-LNK-06 | **Contrary-link exclusion** (OQ-10): a resource whose validated owner at `audit_at` is another user, and not also the case's own user, is removed from that case's candidates. | M3: sample precision 78/84 → 79/80. Audit: 1,808 exclusions, 98% within-slot competition, 40 scenario/non-requester resources; all exact-validated | Shared-context records stay (own user also linked). |
| G-STP-08 | **Observation required to emit** (candidate for M4): a non-account resource produces a step only if it has a state observation with `fact_time` between the case's run anchor and `audit_at`. Catalog-only links (LINK_RESOURCE_IDENTITY) and pre-run snapshots are history. Accounts are always emitted (H-STP-02). | Explains sample case_17 (tombstone_17: link only, not in the answer) and case_07 (object_19: not in the answer) | Verify on all 32 samples in M4 before relying on it. |
| G-SEC-01 | All LLM inputs are untrusted data: delimited, never followed as instructions; LLM outputs are schema-bounded and validated; a regex detector flags instruction-like input and routes it to the deterministic fallback (DESIGN §11.3). | Scan 2026-10-25: 0 injection-like hits in requests, text evidence, PDF text and OCR | Defence in depth for unseen data; custom eval case. |
| G-EVD-04 | Screenshot **detail panel / title bar** carries the record of interest and may set state (presence + label cues) within the G-STP-08 window; header and table rows only link (OQ-15). | M5: 44/44 geometry; detail-panel subject consistent on the parsed screens; gate fired on 2 screens with no ids | Promoted from W-EVD-04 on 2026-10-25. |
| G-SYS-01 | A record found in a replica or failover copy of the account DB is reported under `system_id = account_service`, not the replica name. | case_05 (failover replica), case_16 (read replica) → account_service, same resource_id | Sweep: same pattern for support: legacy `support_replica` log → `support_platform` (case_10). Regional and reporting replicas not yet seen. **Amended 2026-10-25 (OQ-12b):** state is judged per copy (topology); a violating copy is cleared only by a later-or-equal compliant observation of the same copy; ties → violation. |

## WEAK — doubtful or sparse
| ID | Rule | Support | Doubt |
|---|---|---|---|
| W-POL-01 | An analytics *contact lookup* with `email_opt_in=true` is a marketing-type record: REMAINING + DELETE, not ANONYMIZE. | 1 case (case_12) | Single example. |
| W-CEIL-01 | (D4, held as observation) Some answer resources are in **no** participant file (audit_record_6645, audit_record_5569, **account_004** per OQ-8) or only in a PDF (support_001). | 4 resources | Accept as an accuracy ceiling. Never guess them. |
| ~~W-LNK-04~~ | (P11: **weak**. Using the audit-capture file resolves only 4 accounts and 2 analytics records; 236 accounts appear in no… | — | RETIRED 2026-10-25 sweep: superseded by D8 tiers (P11 weak) |
| W-LNK-05 | **Run chain by timing phase:** `(t_event − t_anchor) mod 30 s` ∈ 9–11 (policy actions) or 20–22 (final results, checks) for the case's own events. Wrong pairs are uniform. | 39/39 true sample pairs; P14: eval accounts resolved 231 → 361; sample precision 38/39 | Probably a generator artifact. **Adopted under D8 (open to revision).** |
| ~~W-IDN-01~~ | Resource number ↔ user number (`account_005` → `user_05`).… | — | RETIRED 2026-10-25 sweep: superseded by H-IDN-04 (no number-based links) |

## GAP — needed, no sample evidence
| ID | Needed rule | Why it matters |
|---|---|---|
| ~~X-LNK-01~~ | see history | RESOLVED by D8 (2026-10-25 sweep) |
| ~~X-EVD-01~~ | see history | RESOLVED by D5 (2026-10-25 sweep) |
| X-STP-01 | A single resource with **two** violations (e.g. still present AND fed by an active flow, or retained but exposing PII). The spec allows it; the samples never show it (0/111). Emit one finding per violation type? | Ordering and step-count impact. |
| X-POL-03 | Retained records whose retention **expired** before `audit_at` (rule_12 "within retention", rule_13 "hold active") → no longer retained, so DELETE? Unseen in samples (all retention_until ≥ 2031). | Eval audits Jan–Oct: check for expired retention or holds. |
| X-POL-04 | A retained record (security audit, legal hold) that still carries direct identifiers. Only tombstones have an explicit "remove identifiers" rule (rule_15). REDACT or keep? | Spec silent. |
| X-POL-05 | rule_14 condition "restore access **can be blocked**": what if evidence shows it cannot be blocked? | Spec silent. Unseen. |
| X-IDN-02 | Request email that resolves to **no** user (robustness for unseen data): COMPLETE with no steps? NOT_APPLICABLE? | Not present in data (550/550 resolve). Needs a defined fallback. |
| X-SYS-01 | `system_id` naming for copies in non-account replicas (regional, reporting) and for object storage, marketing, email delivery, cache, legal. Only account_service, search_service, support_platform, analytics_platform, security_service, integration_service, backup_service, export_service and identity_service appear in samples. | Unseen system names must map to a fixed vocabulary. |
| X-STA-01 | Behaviour of NOT_APPLICABLE beyond `[]`. | 0 labelled samples. We must build our own eval cases. |
| X-POL-01 | Treatment and system_id for CACHE_ENTRY, MARKETING_PROFILE, EMAIL_DELIVERY_LOG, SECONDARY_IDENTIFIER, LEGAL_HOLD_RECORD, PRODUCT_TELEMETRY. | No sample step uses cache_service, marketing_platform, email_delivery_service or legal_service. |
| X-POL-02 | How to decide the conditional rules from evidence: "shared context" (r05), "belongs only to subject" (r06), "still attributable" (r07, r08), "within retention" (r12), "hold active" (r13), "restore can be blocked" (r14). | Each needs a concrete evidence signal. |
| ~~X-ORD-01~~ | RETIRED 2026-10-24 → G-ORD-01 → HARD as H-ORD-02 (D2). | — |
| X-TIM-01 | How to treat state changes between the latest snapshot and `audit_at` (activity after the snapshot). | Eval audits are earlier and sparser than the samples. |
| X-CIT-01 | Which evidence to cite when several files prove the same fact. | Affects citation accuracy scoring. |
| ~~X-IDN-01~~ | Phone or name-only matches. | RESOLVED 2026-10-25 sweep: phone counts **only** after exact normalised validation (H-IDN-04); names **never** link (3 name collisions in identities, look-alike decoys in evidence). |

---

## Sweep log
- **2026-10-25 12:18 M4 review**: amended G-EVD-01, G-SYS-01; D8 tier order (naked singles after hard links, H-STP-05 check); PDF naming a resource = presence observation (OQ-13.2). RCA → docs/REVIEW_S3_S4.md.
- **2026-10-25 00:57 sweep** (user-requested): retired as redundant H-IDN-01, H-TIM-01, H-STA-01, W-IDN-01, W-LNK-04, W-TIM-01, G-EVD-02 (merged); resolved X-EVD-01 (D5), X-LNK-01 (D8) and X-IDN-01 (phones only after exact validation, names never); promoted to HARD G-STP-01→H-STP-06, G-LNK-02→H-LNK-02, G-LNK-03→H-LNK-03, G-STP-02→H-STP-04, G-STP-05→H-STP-05; demoted G-EVD-04→W-EVD-04; new HARD H-TIM-03 (inclusive cut-off), H-STP-07 (finding op from treatment; backups verify BLOCKED only); new gaps X-STP-01, X-POL-03, X-POL-04, X-POL-05, X-IDN-02, X-SYS-01; fixed GOOD rules misfiled under WEAK.

## Probe log
| Probe | File | Purpose | Result → rule impact |
|---|---|---|---|
| P15 | inline sweep checks on sample_output | Verify-per-resource, findings per resource, finding→remediation, verify op by type, inclusive cut-off | 32/32; 0 multi-finding; 41/41; backups BLOCKED 6/6; 15 citations at captured_at == audit_at |
| P14 | `docs/probes/P14_chain_phase.py` | Timing-phase run chains + elimination | eval accounts 361/518; sample precision 38/39 |
| P13 | `docs/probes/P13_tiered_resolution.py` | User's tiered resolution (hard → park → elimination) | 927 hard, 692 parked, +70 by elimination; optional types not forcible |
| P12 | inline (substring candidates vs exact validation, all users × all text evidence) | Precision of loose matching | 2,339 → 1,958 exact + 353 same-user + 24 decoys + 4 look-alikes rejected |
| P11 | inline (files captured ≤24h before audit_at that mention the subject; capture-file co-occurrence for ambiguous resources) | Which evidence file (incl. SQL) is relevant for a request | 1 audit-capture file per case for 488/518 eval; matches the cited file in 28/32 samples; does not resolve D6 ambiguity |
| P10 | inline (offsets of all deletion_worker events to every `reported_at` within ±200 min) | Justify the run-window bands | Kind-specific bands fit 1464/1466 events; anchors and policy actions map to a unique slot 100% |
| P04 | `docs/probes/P04_run_linkage.py` | Run-linkage ambiguity on the full dataset | See SAMPLE_DEEP_DIVE §5: eval accounts resolved 231/518; sample precision 92%, recall 69% |
| P09 | `docs/probes/P09_region_labelling.py` (v3) | Geometric labelling of the 5 regions (user heuristics) across 11×4 variants | v2: 43/44 after the title-bar fix. **v3** (conditional invert + contrast stretch + black-hat line detection): **44/44**; yellow = 'Activity' 21/22 |
| P08 | inline (row-strip OCR on detected table row lines) | Recover cells missed by P06 | 6/6 strips correct incl. the subject's email in row 2 |
| P07 | `docs/probes/P07_cv_segmentation.py` | User's CV segmentation (grayscale, contrast, threshold, edges) generalised; robustness on 0.6×/1.5×/inverted | Stable panels for orig/1.5×/inverted in 10/10 light images; 0.6× adds row boxes; dark image fails at 0.6× |
| P06 | inline trial (region crop + TSV) on customer_export_console | Feasibility of template-region OCR | ~95% of cells right; dropped the subject's owner email in row 2 and one KPI value → silent-miss risk |
| P05 | `docs/probes/P05_screenshot_layout.py` | Layout uniformity of the 11 PNGs | 10 share one template (identical borders; one narrower width), 1 dark different template → SCREENSHOTS.md |
| P03b | `docs/probes/out/ocr_v2/` (crop sidebar, 2× upscale, invert dark, psm 11) | Re-OCR of PNGs after the user's correction | Readable text for all 11; table structure lost → X-EVD-01 pending |
| P03 | `docs/probes/out/ocr/` (pdftotext, tesseract default) | Extract PDF and PNG text | PDFs clean; naive PNG OCR poor (superseded by P03b) |
| P02 | `docs/probes/P02_sample_dossiers.py` → `out/P02_*.txt` | Per-case evidence dossiers for all 32 samples | → SAMPLE_DEEP_DIVE.md; added H-STA-02, H-STP-02, G-LNK-01..03, G-TIM-02, G-POL-01, G-CIT-02, W-POL-01, W-CEIL-01, X-LNK-01, X-EVD-01 |
| P01 | inline query (sample_output.csv) | Multi-system remediation order in samples | case_16/24 show source before downstream under alphabetical sort → X-ORD-01 retired, G-ORD-01 added |
| P00 | `docs/EDA_ghost_data.ipynb` | Baseline EDA across all CSVs | Seeded H-STP-01, H-IDN-01..03, H-TIM-01, H-STA-01, G-*, W-IDN-01 |
