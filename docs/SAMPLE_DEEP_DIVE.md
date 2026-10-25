# Sample-by-sample evidence deep-dive (P02/P03)

Planning document, not a deliverable. Generated from `docs/probes/P02_sample_dossiers.py`. The per-case dossiers are in `docs/probes/out/P02_case_XX.txt`, and the PDF/OCR text is in `docs/probes/out/ocr/`.

## 1. Two families of sample cases
| Family | Cases | Shape |
|---|---|---|
| **Scenario** (hand-written texts with hints) | 01–10 | Small. `account_00N` numbering, deletion run around `reported_at` ±10 min. Mostly no security audit record. |
| **Generated** (template texts) | 11–32 | Account submitted at `reported_at` −45…−75 min, successful policy actions at −28/−21/−14/−7 min, failed actions and checks at +40…+115 min, plus a security audit record. **The eval set is all this family.** |

## 2. Per-case summary
Legend: **Run** = resources found in the case's deletion_worker run in `system_activity`. **Ev** = evidence that links or decides them.

| Case | Status | Resources in answer (state) | How linked / decided | Cited |
|---|---|---|---|---|
| 01 | COMPLETE | account_001 absent | Run DELETE SUCCESS. Absent from failover replica + primary tables | evidence_54 |
| 02 | COMPLETE | account_002 absent | Run DELETE **PARTIAL**, still absent in evidence_54 | evidence_54 |
| 03 | COMPLETE | account_7566 absent; audit_record_2016 present; analytics_9406 anonymized | Lookup trace: email → account 404; `lookup_key=user_43` → audit with `retention_until` 2034; analytics all-null (linked only by run) | evidence_94 |
| 04 | COMPLETE | account_004 absent; analytics_901 anonymized | account_004 **not in activity**; analytics all-null in report | evidence_54, evidence_56 |
| 05 | INCOMPLETE | account_005 **present in failover replica only** → finding under `account_service` | Run DELETE SUCCESS + SYNC to failover replica; replica row still ACTIVE | evidence_54 |
| 06 | INCOMPLETE | search_001 present; account_006 absent | Search doc in primary search DB with email + `account_006` ref; run DELETE search FAILED | evidence_57 |
| 07 | INCOMPLETE | support_001 attachment present (PDF); account_007 absent | PDF has `support_001` + name/email/phone. Activity LINK says object_19 belongs only to subject | evidence_58 (PDF) |
| 08 | INCOMPLETE | export_001 present; account_008 absent | Export job JSON with `owner_email` | evidence_59 |
| 09 | INCOMPLETE | backup_4978 restore risk; account_3960 absent; audit_record_4902 present | Inventory SQL backup row `restore=1` + run CHECK_RESTORE_ACCESS. Audit and account known **only from evidence_06 (file captured after audit, lines timestamped before audit)** | evidence_93 |
| 10 | INCOMPLETE | support_002 present (legacy support replica, `marker_found=false`); account_010 absent | **Old email** lookup in support replica log; run DELETE support SUCCESS (false claim) | evidence_61 |
| 11 | INCOMPLETE | search_052 found; analytics_2034 identifiable; support_864 identifiable; data_flow_9522 active; account_4248 absent; audit_record_9394 present | Handover TXT has explicit `system | resource | CATEGORY | STATE | identifier` lines | evidence_03 |
| 12 | INCOMPLETE | analytics_9914 **REMAINING → DELETE** (contact lookup, `email_opt_in=true`, keyed by **old email hash**); account_9797 absent; audit_record_2945 present | Service log, `correlation_key` = historical email_hash | evidence_01 |
| 13 | INCOMPLETE | search_1308 found; support_4218 SUPPORT_ATTACHMENT found → DELETE; account_9335 absent; audit_record_4816 | Handover TXT | evidence_03 |
| 14 | INCOMPLETE | backup_3870 ACTIVE → restore risk; account_3677 absent; audit_record_987 | Handover TXT + run CHECK_RESTORE_ACCESS | evidence_03 |
| 15 | INCOMPLETE | data_flow_9846 enabled (heartbeat) → active; account_4745 absent; audit_record_1596 | Service log (trace_id links subject_key → resource) | evidence_01 |
| 16 | INCOMPLETE | account_994 **in read replica only** → REMAINING under account_service; search_1007 in primary; audit_record_9528 | Read-replica SQL. Run DELETE account FAILED + SYNC to replication cluster; DELETE search SUCCESS (false claim) | evidence_05 |
| 17 | INCOMPLETE | backup_3245 `eligible=true deletion_block=false` → restore risk; account_4092 absent; audit_record_1797 | Service log | evidence_01 |
| 18 | INCOMPLETE | search, analytics (email), support (requester_email), data_flow (enabled); account_5521 absent; audit_record_6645 | Lookup trace. **audit_record_6645 appears in no participant file** | evidence_94 |
| 19 | INCOMPLETE | search_6083 hit; support_9553 PII scan match → REDACT; account_9102 absent; audit_record_6793 | Service log | evidence_01 |
| 20 | INCOMPLETE | search_4262 hit; data_flow_1770 enabled; account_5037 absent; audit_record_5569 | Lookup trace. **audit_record_5569 appears in no participant file** | evidence_94 |
| 21 | COMPLETE | account_6440 404; audit_record_3737; analytics_5335 null | Service export JSON (single file proves all) | evidence_92 |
| 22 | INCOMPLETE | search_8911 + analytics_4440 (user_id, email…) in primary; account_4990 absent; audit_record_3482 | Read-replica SQL (primary table) | evidence_05 |
| 23 | INCOMPLETE | export_7364 + search_898 present; account_410 absent; audit_record_4128 | Export JSON. Audit linked only via evidence_02 inner snapshot (09-15T12:00 = audit_at) | evidence_92 |
| 24 | INCOMPLETE | account_5334 **status 200 with email** → REMAINING (run DELETE said SUCCESS); search_5577; audit_record_7095 | Export JSON; audit via evidence_02 inner snapshot | evidence_92 |
| 25 | COMPLETE | account_3136 404; audit_record_451; analytics_1895 null | Export JSON. Account and analytics linkable **only via the run** | evidence_92 |
| 26–28 | COMPLETE | account 404; audit; support (subject_reference only) **REDACTED**; analytics null; data_flow disabled; backup `restore_allowed=false` | Export JSON; run shows policy actions SUCCESS at −28…−7 min | evidence_92 |
| 29–30 | INCOMPLETE | search, analytics (email), support (requester_email), data_flow (customer_email, enabled) + account absent + audit | Export JSON; run shows FAILED at +40…+115 min | evidence_92 |
| 31 | COMPLETE | account_4857 absent; audit_record_6909; tombstone_440 (subject_reference only) **REDACTED** | Snapshot bundle (identity_service deleted_customer_references) | evidence_51 |
| 32 | INCOMPLETE | tombstone_9178 still has email/phone/hash → EXPOSED_PII → REDACT; account_8858 absent; audit_record_7068 | Same bundle | evidence_51 |

## 3. Cross-case findings (→ rules register)
1. **The deletion run is the case's resource inventory.** 31/32 accounts and 85/87 non-audit answer resources appear as deletion_worker events tied to the case's `reported_at`. The two misses are account_004 and support_001 (the PDF attachment). Every case has **exactly one** account resource.
2. **Security audit records** (24 cases) never appear in the activity stream. They are discovered from evidence through `subject_reference` / `correlation_key` / `lookup_key` = `user_NN`, and are always `VERIFY_RECORD_PRESENT` (retention runs to 2031–2034).
3. **State comes from evidence, never from `reported_result`.** Counterexamples to the activity claims: case_02 PARTIAL → actually absent; case_24, 10 and 16 SUCCESS → actually present; case_25 FAILED → actually absent.
4. **Information time ≠ file time.** Bundles and logs contain inner timestamps (snapshot `captured_at`, `observed_at`, log-line time). The answers use facts timestamped ≤ `audit_at` even from files captured later (case_09: evidence_06; case_23/24: evidence_02). **They are never cited**, because every citation's file `captured_at` is ≤ `audit_at`.
5. **Log linkage is per `trace_id`.** The `*_started` line carries `lookup_key`/`subject_key`/`subject_ref` (an identifier), and the `*_completed` line carries `resource_id` + state. Historical identifiers matter: case_10 used the old email, case_12 the old email hash.
6. **Replica copies** (failover, read replica) of the account are reported under `system_id=account_service` with the same `resource_id` (cases 05, 16).
7. **Category → treatment** as observed:
   * search → DELETE;
   * export → DELETE;
   * account present → DELETE;
   * analytics with any direct identifier → EXPOSED_PII + ANONYMIZE, while analytics all-null → VERIFY_ANONYMIZED;
   * analytics *contact lookup with `email_opt_in`* → REMAINING + DELETE (1 case);
   * support message with requester identifiers → EXPOSED_PII + REDACT, while support with only `subject_reference` → VERIFY_REDACTED;
   * support attachment or legacy support copy → REMAINING + DELETE;
   * data flow `enabled=true` → ACTIVE + DISABLE, while `enabled=false` → VERIFY_DISABLED;
   * backup `restore_allowed=true` / `eligible=true` / `ACTIVE` → RESTORE_RISK + BLOCK, while `restore_allowed=false` / `BLOCKED` → VERIFY_BLOCKED;
   * tombstone with email/phone/hash → EXPOSED_PII + REDACT, while tombstone with reference only → VERIFY_REDACTED.
8. **Citation pattern:** findings cite the file showing the violating state. COMPLETE verifications cite the file proving the compliant state, usually one capture covering all resources, close to `audit_at`.
9. **Unreachable truth:** `audit_record_6645` (case_18) and `audit_record_5569` (case_20) appear in no participant-facing file. This is an accuracy ceiling. We accept it and do not try to guess.
10. **Binary evidence:** PDFs extract cleanly with `pdftotext`. PNGs: **10 light UI + 1 dark** (`security_audit_explorer_20260905.png`). *(Corrected 2026-10-24 after the user's check; the earlier "all dark, OCR unusable" claim was wrong.)* Preprocessed OCR (crop sidebar, 2× upscale, invert dark, psm 11, see P03b) is readable but loses table structure.
11. **Observation (eval-relevant conflict):** `marketing_profile_console.png` shows `marketing_001` = *Soo-jin Park, sj.park@naver.com, +82 10-5837-9451, email opt-in Yes*. That person is not in `user_identities`. `activity_4008` (data catalog, 2026-09-16) links `marketing_001` to `kwame-mensah@proton.me` / `user_09`, who is eval **case_63** (audit 2026-09-17). Catalog link vs on-screen identity: to resolve in the design.

## 4. The main open design problem: run disambiguation
In the eval set, **363/518 cases share `reported_at` with two other cases** (121 triplets), so their deletion runs interleave in time. Resources carrying an identifier in evidence can be assigned directly. Identifier-free resources (anonymized analytics, a 404 account) cannot be assigned that way. In the samples the triplet case_24/25/26 has exactly this problem: analytics_1895 vs analytics_4566 are both all-null. Candidate disambiguators to probe on the eval set: (a) older snapshots that still show the identifier before deletion, (b) elimination once the other cases' resources are assigned, (c) run timing and sequence patterns. → Probe P04.

## 5. P04 results: run linkage on the full dataset (`docs/probes/P04_run_linkage.py`)
Method:
- **Fact index** at record granularity (JSON object with `resource_id`, SQL row, log `trace_id` group, TXT line, PDF text, data-catalog LINK events), filtered by the fact's own timestamp ≤ `audit_at` (D3).
- **Identifier → user:** current and historical emails, hashes, phones, `user_NN`.
- **Runs:** deletion_worker events in windows around `reported_at`: anchor −80…−40 min, policy actions −35…0, failures and checks +30…+125. Cases are grouped by `reported_at` **across the sample and eval sets together**, because they share one activity stream. Grouping per set produced 40 false assignments.

Results:
| Measure | Value |
|---|---|
| Group sizes (all 550 cases) | 86 singles, 37 pairs, 122 triples, 2×4, 2×5, 1×6 |
| deletion_worker events inside exactly one window | 1138/1466 (78%); 319 in 2–3 overlapping windows |
| Sample validation (non-audit resources) | precision 60/65 = **92%**, recall 60/87 = **69%** |
| Eval cases whose **account** is resolved | **231/518 (45%)**: direct identifier link 178, single-case group 45, elimination 28 (counts across all cases) |
| Run events resolved overall | direct 927, single-case 63, elimination 28; **ambiguous 664**; overlapping windows 131 |
| Does anchor order follow requested_at, case number, email or audit_at? | **No.** Agree vs disagree ≈ 50/50 on 143 known pairs, so ordering carries no signal |

Interpretation:
- Resources that carry identifiers (search, support, export, data flow, backup, tombstone, identifiable analytics) link well.
- **Accounts (usually 404 rows with no identifier left) and fully anonymised analytics are mostly unlinkable** when cases share `reported_at`. That is about 55% of eval accounts.
- The scenario-style sample cases (01–10) use different offsets (≈0 min) and are missed by these windows. The eval set has no such cases: 517/518 `reported_at` values fall on the hour.

Open decision (D6): what to emit for an ambiguous account or anonymised analytics in a shared group (omit, guess, or emit with the system known but the resource unknown).

### 5.1 Worked example: the 5-case group at `reported_at` 2026-09-02T12:00 (walkthrough for the user)
Cases: case_24, 25, 26 (sample, audit 09-15) and case_549, 550 (eval, audit 09-20).
deletion_worker events (offset from 12:00): 5 account anchors (−71.6 account_3136, −69.8 account_4842, −60.3 account_5334, −51.3 account_5684, −49.6 account_7225); policy actions (−28.9 analytics_1895, −28.6 analytics_4566, −28.2 tombstone_3963, −21.1 support_4715, −14.6 data_flow_6244, −7.1 backup_3120); failures (+47.3 tombstone_7389, +64.0 search_5577).
| Step | Result |
|---|---|
| Direct identifier links | account_5334, search_5577 → case_24 (email in evidence_92, customer_reference in evidence_02). account_5684, support_4715, data_flow_6244, backup_3120 → case_26 (`user_26`). tombstone_3963 → case_549, tombstone_7389 → case_550 (failover replica evidence_52). |
| Elimination | Fails: 3 accounts left (3136, 4842, 7225) for 3 cases (25, 549, 550). |
| Unlinked | account_3136, 4842, 7225; analytics_1895, 4566 (all-null). |
| Truth (samples) | case_25 = account_3136 + analytics_1895; case_26 also has analytics_4566. |
**New candidate signal: file-level co-occurrence.** account_3136 appears only in evidence_92, a readback export that also mentions `user_25` and neither `user_549` nor `user_550`, so it goes to case_25 (correct). That leaves 4842 and 7225 for 549 and 550, which appear in no file (50/50). analytics_1895 and 4566 both appear in files mentioning user_25 and user_26 (excluding 549 and 550), so the 2 analytics records split between 2 cases (50/50). → Candidate W-LNK-04 to be measured.

### 5.2 How the sample answers handle unlinkable accounts (user question)
16 of 32 sample accounts cannot be tied to their case by any identifier in participant data, and 11 of them appear in **no evidence file at all**. **The sample answers still name the exact account in every case (32/32).** The answers come from the organisers' private truth, and the samples show no method for choosing the account.
| Case | Group size | Account | Step | Cited | Account mentioned in any file? |
|---|---|---|---|---|---|
| 02, 04 | 1 | account_002 / 004 | VERIFY_ABSENT | evidence_54 | no; failover snapshot simply lacks it |
| 08, 10 | 1 | account_008 / 010 | VERIFY_ABSENT | "" (INCOMPLETE) | no |
| 18, 20, 22 | 3 | 5521 / 5037 / 4990 | VERIFY_ABSENT | "" | no |
| 23, 29, 32 | 6 / 4 / 5 | 410 / 7012 / 8858 | VERIFY_ABSENT | "" | no |
| 21, 25, 27, 28 | 6 / 5 / 4 / 4 | 6440 / 3136 / 3866 / 5482 | VERIFY_ABSENT | evidence_92 | yes, as a 404 lookup with no identifier |
| 31 | 5 | account_4857 | VERIFY_ABSENT | evidence_51 | **no**; the bundle's account_service collection has 0 records |
Takeaways:
1. The expected output **always** contains the account step with a specific id, so leaving it out is a guaranteed miss.
2. For COMPLETE cases, absence is proven by citing a snapshot of the account system captured at or before `audit_at` that **does not contain** the account (evidence_54, evidence_51). The account does not need to be mentioned (G-EVD-01 strengthened).
3. Single-case groups (02, 04, 08, 10) are solvable through run uniqueness once the scenario-style timing window (≈ 0 min) is added. In shared groups the samples give no rule, so the id is a best guess unless co-occurrence (W-LNK-04) or elimination resolves it.

### 5.3 Role of PDFs and screenshots in linkage (user question)
Scan of the PDF text (pdftotext) and screenshot OCR (P03b) for resource ids and identifiers:
| File | Captured | Resources | Subject → case |
|---|---|---|---|
| evidence_04 account_admin_console | 09-26 | account_5762, support_9538 | user_11 → case_34 |
| evidence_19 analytics_profile_view | 07-13 | analytics_7438 | user_20 → case_50 |
| evidence_32 backup_restore_console | 04-29 | backup_9287 (+4 decoy rows) | user_16 → case_55 |
| evidence_14 connector_management_console | 08-07 | data_flow_1121, data_flow_9846 | user_14 → case_39; user_15 → sample case_15 |
| evidence_23 customer_export_console | 06-18 | export_1260 (+3 decoy rows) | user_18 → case_52 / case_33 |
| evidence_09 search_index_inspector | 09-01 | search_428 | user_13 → case_35 |
| evidence_37 security_audit_explorer + evidence_55 security_retention_extract (PDF) | 09-05 | audit_record_001…006 / 003 | user_03 → case_45 |
| evidence_28 support_ticket_console | 05-24 | (ids not caught by OCR regex) | user_22 → case_53 |
| evidence_58 delivery_correction_attachment (PDF) | 09-12 | support_001 | user_07 → sample case_07 (and eval case_61) |
| evidence_18 account_history_report (PDF) | 07-18 | — | user_18 → case_33 / case_52 |
| evidence_60 marketing_profile_console | 09-16 | marketing_001 | on-screen identity not in identities; catalog link → user_09 → case_63 |
| evidence_42 deleted_account_reference, evidence_46 object_storage_browser | 03-10, 02-13 | (OCR found no ids) | likely user_17 / case_46 (tombstone_17) and user_07 / case_61 (object_19); to confirm with the vision path |
| evidence_27 legal_retention_register (PDF) | 05-29 | **no resource ids** | users 08, 12, 17, 21, 24, 29: disputed-order retention |
Findings:
1. **PDFs and screenshots serve the hand-made "scenario" eval cases** (users 03–22 → cases 33–63). **All 12 of those eval cases are alone at their `reported_at` (group size 1)**, so they have no run ambiguity. PDF/PNG evidence is essential for *their* records but **does not help the shared-group account ambiguity**.
2. Most screenshots carry **one subject plus decoy rows** (other customers or staff). Only the detail panel or title bar holds the subject (G-EVD-04).
3. **Legal register = no steps:** it lists retained disputed orders for users 08, 12, 17, 21, 24 and 29. Those users' sample answers (08, 12, 17, 21, 24, 29) contain **no** legal-hold step. Evidence with no resource id produces no step, and a finance retention register is not a supplied `LEGAL_HOLD_RECORD`.
4. P04 already used PDF text but **not** screenshot text. The production pipeline will feed the D5 extraction into the same fact index.

### 5.4 Walkthrough: case_09, a non-evident case (user request)
Request: k.appiah88@gmail.com → user_61 (no history). Generic template text. reported NOT_STARTED, reported_at 09-07 09:00, audit 09-16 09:00.
1. **Run:** shared with eval case_64 (same reported_at). Events: account_3960 (−64.7, FAILED), account_565 (−44.4, PARTIAL), analytics_5718 / support_6334 / data_flow_6846 / backup_3933 policy SUCCESS (−28.8…−7.3), backup_4978 CHECK_RESTORE_ACCESS "can still be restored" (+51.2).
2. **Identifier links:**
   - backup_4978: evidence_93 inventory SQL row `customer_email=k.appiah88`, `restore_allowed=1`, updated 07:59 ≤ audit → user_61.
   - account_3960: evidence_06 log `trace tr-1463969` (`lookup_key=k.appiah88` → `account_3960` rows=0, 404) at 08:57:34 ≤ audit, in a file captured 09-18 (> audit).
   - audit_record_4902: evidence_06 `trace tr-9028396` (`subject_ref=user_61` → read rows=1) at 08:52:59.
   - The other run resources belong to case_64 (by elimination: account_565 is the only account left).
3. **State at audit:** backup restorable (inventory 07:59, log 08:57 `eligible=true`, `deletion_block=false`) → violation. Account absent (404; also absent from the evidence_93 `customer_profiles` snapshot at 08:37). Audit record present (integrity passed).
4. **Treatment:** BACKUP_ARCHIVE → retain, but restore must be blocked → RESTORE_RISK + BLOCK. USER_PROFILE absent → VERIFY_ABSENT. SECURITY_AUDIT_LOG → VERIFY_PRESENT.
5. **Citation:** the finding cites evidence_93 (captured 08:37 ≤ audit). evidence_06 is never cited (captured after audit), but its pre-audit lines were needed to *find* the account and audit record (D3).
6. **Output:** INCOMPLETE, 5 steps = RESTORE_RISK backup_4978 [evidence_93] → BLOCK_RESTORE → VERIFY_ABSENT account_3960 → VERIFY_PRESENT audit_record_4902 → VERIFY_RESTORE_BLOCKED. **Matches the sample exactly.**
Non-evident points: (a) reported NOT_STARTED, yet the deletion was mostly done; (b) the only violation is a backup; (c) two of three resources are discoverable only through a later-captured file's earlier lines; (d) the activity says the account delete FAILED, but the account is in fact absent.

### 5.5 Cross-verification of account_3960 against the overlapping case (case_64, eval)
Slot 2026-09-07 09:00 is shared by case_09 (user_61, k.appiah88@gmail.com) and case_64 (user_62, zulu.lindiwe@gmail.com).
| Resource | Linking evidence (fact time ≤ audit 09-16 09:00) | Owner | State at audit |
|---|---|---|---|
| account_3960 | evidence_06 `tr-1463969`: `lookup_key=k.appiah88@gmail.com` → `account_3960` rows=0, 404 (08:57:34) | case_09 | absent |
| account_565 | evidence_06 `tr-4893151`: `lookup_key=zulu.lindiwe@gmail.com` → `account_565` rows=0, 404 (08:56:26) | case_64 | absent |
| backup_4978 | evidence_93 row `customer_email=k.appiah88`, `restore_allowed=1` | case_09 | restorable (violation) |
| support_6334 / data_flow_6846 / backup_3933 | evidence_93 rows `customer_reference=user_62`; evidence_06 traces with `subject_ref` / `subject_key=user_62` | case_64 |
| analytics_5718 | all-null, no identifier anywhere. **Genuinely ambiguous** between case_09 and case_64 *(correction 2026-10-25: earlier text said "by elimination", which is not justified, because a case may have no analytics record at all)*. The sample answer for case_09 has no analytics, so the truth gives it to case_64. | ambiguous | anonymized / redacted / disabled (0) / restore blocked (0) |
Checks:
1. **One account per case:** each slot account is linked by its own email-keyed lookup trace, so there is no double claim and no elimination needed.
2. **No action conflict:** both accounts are 404, so the step is VERIFY_RECORD_ABSENT whichever way they are assigned. Only `resource_id` would differ if swapped.
3. **Run consistency:** every other slot event resolves to user_62 (case_64), which leaves exactly backup_4978 + account_3960 for case_09. This matches the sample.
4. **Decoy noticed:** the same log contains `zulu.lindiwe.jr@gmail.com` (a different person). Raw substring matching on `zulu.lindiwe@gmail.com` would not hit it, but a fuzzy or prefix match would. Exact full-token email matching is required (H-IDN-01 extended).
General lesson: **email-keyed lookup traces resolve deleted (404) accounts**, because the lookup line carries the email and the completion line carries the resource id. This works whenever the capture log contains such a trace. It is absent for the ~236 still-ambiguous eval accounts (P11).

## 6. Tiered ambiguity resolution: user proposal tested (P13, P14)
User design: (1) hard rules → (2) park the rest in an ambiguity lookup table with applicable candidate rules → (3) elimination (resolving one record fixes the others) → (4) hand the remainder to an LLM with the candidate rules.
| Tier | Mechanism | Effect on the full dataset |
|---|---|---|
| 1 Hard | validated identifier link between a run event and exactly one case of its slot | 927 events |
| 2 Park | ambiguity table `event → candidate cases (+ candidate rules)` | 692 events parked |
| 3 Elimination | constraint propagation to a fixpoint: each event belongs to exactly one case; **exactly one account per case** (32/32); **at most one resource per type per case** (32/32 samples, every type n=1) | +70 events. Works for "exactly-one" types (accounts). **Cannot force optional types** (analytics, support…), because a case may legitimately have none (e.g. analytics_5718) |
| 3b Chain by timing phase (candidate) | `(t_event − t_anchor) mod 30 s` is 9–11 for policy actions and 20–22 for final results/checks in **39/39 true sample pairs**; wrong pairs spread uniformly over 0–29 | eval cases with a resolved account: **231 → 361 / 518**; sample precision 38/39 |
| 4 Residual | what is left for the LLM or a tie-break | ≈157 eval cases without a resolved account; analytics and other optional types partly |
Assessment:
- Tiers 1–3 are sound and deterministic. Tier 3 is exactly the user's "fix rec1 → rec2 fixed" idea, but it only propagates through **exactly-one** constraints.
- Tier 3b is powerful but most likely a **generator cadence artifact**. It is grounded in timestamps (allowed: "match evidence through … timestamps"), yet it needs an explicit decision because of the "no case-family shortcuts" rule.
- Tier 4 LLM caveat: for *symmetric* residuals (two 404 accounts with no other evidence), an LLM has no information beyond what the rules saw, so it would be guessing, non-deterministically and at a token cost. Use the LLM only where the residual depends on **interpreting unstructured content** (screenshot text, free-text notes, ambiguous categories), constrain it to choose among the parked candidates, and require a cited reason. Otherwise use a deterministic tie-break flagged low-confidence.

### 6.1 Tier 3b (timing-phase chains): step-by-step with the 09-02 12:00 slot
Steps:
1. Collect the slot's deletion_worker events (run windows, G-LNK-01).
2. Split into **anchors** ("submitted primary profile") and **follow-ups**. Classify follow-ups as *policy* ("Policy action completed") or *final* (final result / checks).
3. Phase matrix: residual = `(t_event − t_anchor) mod 30` seconds, for anchors earlier than the event.
4. Match: policy 9–11 s, final/check 20–22 s (tolerances from the 39 true sample pairs) → candidate anchors per event.
5. Chain: an event with exactly one matching anchor joins that anchor's chain. Events with several matches are parked.
6. Link chains to cases with validated identifier links on **any** member (anchor or follow-up).
7. Propagate: a linked chain takes all its members; parked events are intersected with identifier links; constraints apply (one account per case, at most one per type); repeat until stable.
8. Residual goes to tier 4/5.

Phase matrix (`*` = within tolerance):
| Event | Time | Kind | acc_3136 10:48:27 | acc_4842 10:50:09 | acc_5334 10:59:41 | acc_5684 11:08:43 | acc_7225 11:10:25 | Candidates |
|---|---|---|---|---|---|---|---|---|
| analytics_1895 | 11:31:08 | policy | 11* | 29 | 27 | 25 | 13 | 3136 |
| analytics_4566 | 11:31:24 | policy | 27 | 15 | 13 | 11* | 29 | 5684 |
| tombstone_3963 | 11:31:49 | policy | 22 | 10* | 8 | 6 | 24 | 4842 |
| support_4715 | 11:38:53 | policy | 26 | 14 | 12 | 10* | 28 | 5684 |
| data_flow_6244 | 11:45:23 | policy | 26 | 14 | 12 | 10* | 28 | 5684 |
| backup_3120 | 11:52:52 | policy | 25 | 13 | 11* | 9* | 27 | 5334 / 5684 (parked) |
| tombstone_7389 | 12:47:17 | final | 20* | 8 | 6 | 4 | 22* | 3136 / 7225 (parked) |
| search_5577 | 13:04:03 | final | 6 | 24 | 22* | 20* | 8 | 5334 / 5684 (parked) |

Resolution:
- Chains after step 5: 3136 {analytics_1895}, 4842 {tombstone_3963}, 5684 {analytics_4566, support_4715, data_flow_6244}, 5334 {}, 7225 {}.
- Step 6 (identifier links): chain 5684 → case_26 (support, data flow, `user_26`) so analytics_4566 → case_26 ✓. account_5334 + search_5577 → case_24 (email) ✓. chain 4842 → case_549 (tombstone_3963 `user_549`) → **account_4842 resolved**. backup_3120 → case_26 (`user_26`) ✓ (consistent with candidate 5684). tombstone_7389 → case_550.
- Step 7: left are accounts 3136 and 7225 for cases 25 and 550. tombstone_7389 (case_550) matches both 3136 and 7225, and analytics_1895 is in chain 3136 but has no identifier → **still ambiguous** → tier 4/5.
- Against the sample truth: case_24 ✓, case_26 ✓ (all 5), case_25 = account_3136 + analytics_1895 (the chain is right, but nothing ties chain 3136 to case_25 rather than case_550).
**Net for this slot:** before 3b, 3 of 5 accounts were resolved and both analytics records were ambiguous. After 3b, 3 accounts (+ account_4842 for case_549) and analytics_4566 are resolved, and analytics_1895 is correctly *grouped* with account_3136, which halves the residual to one symmetric pair.
