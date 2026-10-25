# Evaluation report

<!-- BEGIN GENERATED -->

## Sample metrics (32 cases, `dataset/sample_output.csv`)

| Variant | Status | Step P / R / F1 | Sequence-exact | LCS ratio | Citations | Field accuracy |
|---|---|---|---|---|---|---|
| default (G-STP-08 on, tiers 1-3b) | 32/32 | 0.995 / 0.964 / 0.979 | 26/32 | 0.950 | 71/75 | phase 0.964, system_id 0.964, resource_id 0.964, operation 0.964, state 0.964, evidence_id 0.964 |
| G-STP-08 off (`require_observation_to_emit=False`) | 32/32 | 0.984 / 0.964 / 0.974 | 24/32 | 0.939 | 71/75 | phase 0.964, system_id 0.964, resource_id 0.964, operation 0.964, state 0.964, evidence_id 0.964 |
| tiers 1-3 (no 3b) | 32/32 | 0.963 / 0.933 / 0.947 | 22/32 | 0.913 | 66/75 | phase 0.933, system_id 0.933, resource_id 0.933, operation 0.933, state 0.933, evidence_id 0.933 |
| tier 1 only | 32/32 | 0.963 / 0.933 / 0.947 | 22/32 | 0.913 | 66/75 | phase 0.933, system_id 0.933, resource_id 0.933, operation 0.933, state 0.933, evidence_id 0.933 |

Aligned steps (default): 186/193; TP 186, FP 1, FN 7.

### Sample mismatches (default variant, generated)

```
case_04: status expected COMPLETE got COMPLETE; notes ['no account resolved for this case']
    MISSING ('VERIFICATION', 'account_service', 'account_004', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_54')
case_18: status expected INCOMPLETE got INCOMPLETE; notes []
    MISSING ('VERIFICATION', 'security_service', 'audit_record_6645', 'VERIFY_RECORD_PRESENT', 'PRESENT', '')
case_20: status expected INCOMPLETE got INCOMPLETE; notes []
    MISSING ('VERIFICATION', 'security_service', 'audit_record_5569', 'VERIFY_RECORD_PRESENT', 'PRESENT', '')
case_21: status expected COMPLETE got COMPLETE; notes []
    MISSING ('VERIFICATION', 'account_service', 'account_6440', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_92')
    MISSING ('VERIFICATION', 'analytics_platform', 'analytics_5335', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED', 'evidence_92')
    EXTRA   ('VERIFICATION', 'account_service', 'account_294', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_51')
case_27: status expected COMPLETE got COMPLETE; notes []
    MISSING ('VERIFICATION', 'analytics_platform', 'analytics_4574', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED', 'evidence_92')
case_29: status expected INCOMPLETE got INCOMPLETE; notes ['no account resolved for this case']
    MISSING ('VERIFICATION', 'account_service', 'account_7012', 'VERIFY_RECORD_ABSENT', 'ABSENT', '')
```

<!-- END GENERATED -->

## Failures found (curated; one line per sample mismatch of the default variant)

| Case | Missing step(s) | Diagnosis (rule) |
|---|---|---|
| case_04 | account_004 VERIFY_RECORD_ABSENT | The id occurs in no participant file and in no activity row, so it can never be attributed (W-CEIL-01, OQ-8). Ceiling. |
| case_18 | audit_record_6645 VERIFY_RECORD_PRESENT | The audit record appears in no participant file (W-CEIL-01). Ceiling. |
| case_20 | audit_record_5569 VERIFY_RECORD_PRESENT | Same as case_18 (W-CEIL-01). Ceiling. |
| case_21 | account_6440, analytics_5335 (+ extra account_294) | Both are identifier-free in a 6-case slot; tiers 1-3b cannot attribute them (D8). Tier 5 (deterministic tie-break, OQ-14) pairs the slot's free anchor with the wrong case and emits account_294: the pairing carries no evidence (P04), a wrong attribution costs the same as a missing one. analytics_5335 stays unattributed (optional types are never forced, H-STP-05). |
| case_25 | none (exact since M5) | The 3b chain {3136, analytics_1895} could not be tied to case_25 rather than case_550; the tier-5 tie-break (numeric case order) happens to pick correctly (OQ-14: not evidence). |
| case_27 | analytics_4574 | All-null analytics record with no identifier; an optional type cannot be forced by elimination (H-STP-05 allows 0 or 1 per type, D8 tier 3); tier 4 gets no unstructured content to read, tier 5 pairs accounts only. |
| case_29 | account_7012 | No free anchor is left for the case in its slot after tiers 1-3b, so the tie-break has nothing to pair (H-STP-02 cannot be satisfied; 12 eval cases are in the same situation). |

One sample step is wrong (the tier-5 account of case_21, 1 FP); 7 steps are missing: 3 ceiling steps (W-CEIL-01) and 4 residual attributions that no evidence can resolve.

## Failures found while building M4 and fixes (first run: status 28/32, F1 0.901, sequence-exact 20/32)
Each fix corrects how a rule was applied; no rule was changed to fit a sample.

1. **case_12, case_19 (no finding emitted):** snapshot-scope absence (G-EVD-01) overrode explicit observations because a later bundle that lists only a few records "did not mention" the resource. Fix: scope proof is a last resort, used only for a resource with no explicit observation (kept for accounts such as case_01/02/31).
2. **case_05 (replica copy ignored):** a primary-side absence cleared a failover-replica copy that still held the record. Fix: each copy (topology) is judged on its own; a violating copy is cleared only by a later or equal good observation of the same copy (G-SYS-01, replica drift).
3. **case_07 (support_001 missing):** the PDF attachment carried no state signal, so it was never observed; fix: a document naming the resource id is a presence observation for record kinds, and an "attachment" cue makes it SUPPORT_ATTACHMENT (G-POL-01, W-CEIL-01 note: the id exists only in this PDF).
4. **case_11 (extra analytics_9447):** a window naked single violated H-STP-05 (the case already held a hard-linked analytics record). Fix: naked singles are assigned after all hard links and rejected on a type conflict (H-STP-05).

## G-STP-08 (`require_observation_to_emit`) on vs off
On: precision 1.000, F1 0.976, sequence-exact 25/32. Off: precision 0.989 (2 extra steps: object_19 in case_07 and tombstone_17 in case_17, both catalog-link-only resources), F1 0.971, sequence-exact 23/32. The rule removes exactly the two extras and loses nothing on the samples.

## D8 ablation (samples)
Tiers 1-3 and tier 1 alone give the same sample result (F1 0.945, sequence-exact 18/32); adding tier 3b raises it to F1 0.976 and sequence-exact 25/32 (+7 cases). Caveat (OQ-11): 3b is a probable generator artifact and its bands were derived from sample pairs, so the sample gain may overstate the eval gain; every 3b-assigned case is marked low confidence internally.


## M5 (intent, screenshots, tier 5, LLM layer)

### Outcome-level regression guard (samples, status must stay 32/32, F1 must not drop below 0.976)
| Point in M5 | Status | Step P / R / F1 | Sequence-exact | Eval cases without an account step |
|---|---|---|---|---|
| Baseline at the start (M4) | 32/32 | 1.000 / 0.953 / 0.976 | 25/32 | 71 |
| + tier-5 deterministic tie-break | 32/32 | 0.995 / 0.964 / 0.979 | 26/32 | 12 |
| + intent (rules + `local` LLM) and screenshots (OCR + conditional vision) | 32/32 | 0.995 / 0.964 / 0.979 | 26/32 | 12 |
| `final`-profile smoke run (32 samples) | 32/32 | 0.995 / 0.964 / 0.979 | 26/32 | 12 |

### Intent (all 550 request texts, 398 distinct)
* Rules only (multilingual lexicon, negation / scope cues): 10/10 non-deletion detected (`case_533`..`case_542`), 32/32 samples deletion, 0 wrong.
* `local` profile (llama3.1 primary, gpt-oss:20b escalation, 20 texts per call): same result, 0 wrong. 20 primary calls (22,815 input / 18,013 output tokens), 397 texts agree with the rules, 1 disagreement was escalated and the escalation answer stood (1 call, 346 / 159 tokens). 466 s on the development machine, free.
* Suspicious-input detector: 0 of the 550 texts are flagged (DESIGN §11.3 scan confirmed); the injection custom case below exercises it.

### Screenshots (11 PNGs)
* P09 region consistency on original / 0.6x / 1.5x / inverted: **44/44**.
* Cross-check summary (resource ids + validated identifiers OCR-extracted per variant versus the original, Jaccard >= 0.8): 1.5x **11/11**, inverted **11/11**, 0.6x **7/11** (29/33 overall). The 0.6x losses are OCR misses on tiny text (search inspector, connector console, backup console, security explorer lose some ids); the D5a gate catches images where header/detail yield no id and asks the vision model.
* Gate on the originals: fires for 2 screenshots (evidence_42, evidence_46). The vision model (local gemma4:12b; final claude-sonnet-5-5) also finds no resource id in them, so they stay without facts: their subjects exist only as catalog links (object_19, tombstone_17), which G-STP-08 does not emit, as the samples require.

### Custom evaluation cases (code/evaluation/custom_cases.py, 8/8 pass)
| Case | Input | Expected | Rationale |
|---|---|---|---|
| RCA-1 partial snapshot vs explicit observation | search_7 PRESENT in a log; a later partial bundle scope for search_service that does not list it | INCOMPLETE: REMAINING / DELETE / VERIFY_ABSENT, cites the log file | scope proof never overrides an explicit observation (G-EVD-01 precedence) |
| RCA-2 replica present, primary 404 | account_9 in a failover replica row, a later primary lookup 404 | INCOMPLETE finding under account_service, cites the replica file | per-copy state (G-SYS-01) |
| RCA-3 same-type second resource | case_a hard-linked analytics_1, a window event analytics_2 linked to case_b | analytics_1 -> case_a, analytics_2 -> case_b | H-STP-05 / naked singles after hard links |
| RCA-4 PDF-only attachment | support_1 appears only in a PDF | INCOMPLETE REMAINING / DELETE / VERIFY_ABSENT | OQ-13.2 |
| Decoy identifiers | text with a look-alike (`thandiwe.n5276`) and a `.jr` address | only the real owner links | H-IDN-04 |
| Late-file discovery | a pre-audit fact in a file captured after audit_at | state uses it, the citation is the earlier file | D3 / S-TIM-01 |
| Expired retention | audit record with retention_until before audit_at | policy action DELETE | OQ-2 default |
| Intent: injection, negation, multilingual | injection in a deletion request and in a data request, marketing-only, "not asking you to delete", es / ja deletion, "verify my deletion" | [True, False, False, False, True, True, True]; the two injected texts flagged | DESIGN §11.3, G-INT-01 |
Screenshot robustness (0.6x / 1.5x / inverted variants) is the cross-check above (`code/scripts/m5_screenshots.py --ocr`).

### `final`-profile smoke run (32 samples only; one run, intent texts limited to the 32 sample texts)
4 model calls, 12,241 input / 2,647 output tokens, estimated USD 0.024 at list prices (checked 2026-10-06):
| Model | Calls | Input tokens | Output tokens | Est. cost (USD) |
|---|---|---|---|---|
| claude-haiku-5-5 (intent, 2 batches of <= 20 texts) | 2 | 3,609 | 2,111 | 0.0014 |
| claude-sonnet-5-5 (vision, the 2 gated screenshots) | 2 | 8,632 | 536 | 0.0226 |
No escalation and no tier-4 call were needed; no cache hits (first `final` run). A separate 3-call connectivity pre-check (216 input / 9 output tokens each, one per model) is in the ledger under run `precheck`.
