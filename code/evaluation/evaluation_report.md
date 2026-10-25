# Evaluation report

<!-- BEGIN GENERATED -->

## Sample metrics (32 cases, `dataset/sample_output.csv`)

| Variant | Status | Step P / R / F1 | Sequence-exact | LCS ratio | Citations | Field accuracy |
|---|---|---|---|---|---|---|
| default (G-STP-08 on, tiers 1-3b) | 32/32 | 1.000 / 0.953 / 0.976 | 25/32 | 0.929 | 69/75 | phase 0.953, system_id 0.953, resource_id 0.953, operation 0.953, state 0.953, evidence_id 0.953 |
| G-STP-08 off (`require_observation_to_emit=False`) | 32/32 | 0.989 / 0.953 / 0.971 | 23/32 | 0.918 | 69/75 | phase 0.953, system_id 0.953, resource_id 0.953, operation 0.953, state 0.953, evidence_id 0.953 |
| tiers 1-3 (no 3b) | 32/32 | 1.000 / 0.896 / 0.945 | 18/32 | 0.867 | 63/75 | phase 0.896, system_id 0.896, resource_id 0.896, operation 0.896, state 0.896, evidence_id 0.896 |
| tier 1 only | 32/32 | 1.000 / 0.896 / 0.945 | 18/32 | 0.867 | 63/75 | phase 0.896, system_id 0.896, resource_id 0.896, operation 0.896, state 0.896, evidence_id 0.896 |

Aligned steps (default): 184/193; TP 184, FP 0, FN 9.

### Sample mismatches (default variant, generated)

```
case_04: status expected COMPLETE got COMPLETE; notes ['no account resolved for this case (tier 4/5 are stubs)']
    MISSING ('VERIFICATION', 'account_service', 'account_004', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_54')
case_18: status expected INCOMPLETE got INCOMPLETE; notes []
    MISSING ('VERIFICATION', 'security_service', 'audit_record_6645', 'VERIFY_RECORD_PRESENT', 'PRESENT', '')
case_20: status expected INCOMPLETE got INCOMPLETE; notes []
    MISSING ('VERIFICATION', 'security_service', 'audit_record_5569', 'VERIFY_RECORD_PRESENT', 'PRESENT', '')
case_21: status expected COMPLETE got COMPLETE; notes ['no account resolved for this case (tier 4/5 are stubs)']
    MISSING ('VERIFICATION', 'account_service', 'account_6440', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_92')
    MISSING ('VERIFICATION', 'analytics_platform', 'analytics_5335', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED', 'evidence_92')
case_25: status expected COMPLETE got COMPLETE; notes ['no account resolved for this case (tier 4/5 are stubs)']
    MISSING ('VERIFICATION', 'account_service', 'account_3136', 'VERIFY_RECORD_ABSENT', 'ABSENT', 'evidence_92')
    MISSING ('VERIFICATION', 'analytics_platform', 'analytics_1895', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED', 'evidence_92')
case_27: status expected COMPLETE got COMPLETE; notes []
    MISSING ('VERIFICATION', 'analytics_platform', 'analytics_4574', 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED', 'evidence_92')
case_29: status expected INCOMPLETE got INCOMPLETE; notes ['no account resolved for this case (tier 4/5 are stubs)']
    MISSING ('VERIFICATION', 'account_service', 'account_7012', 'VERIFY_RECORD_ABSENT', 'ABSENT', '')
```

<!-- END GENERATED -->

## Failures found (curated; one line per sample mismatch of the default variant)

| Case | Missing step(s) | Diagnosis (rule) |
|---|---|---|
| case_04 | account_004 VERIFY_RECORD_ABSENT | The id occurs in no participant file and in no activity row, so it can never be attributed (W-CEIL-01, OQ-8). Ceiling. |
| case_18 | audit_record_6645 VERIFY_RECORD_PRESENT | The audit record appears in no participant file (W-CEIL-01). Ceiling. |
| case_20 | audit_record_5569 VERIFY_RECORD_PRESENT | Same as case_18 (W-CEIL-01). Ceiling. |
| case_21 | account_6440, analytics_5335 | Both are identifier-free (404 lookup, all-null analytics) in a 6-case slot; tiers 1-3b cannot attribute them (D8, X-LNK-01) and tier 4/5 are stubs until M5. |
| case_25 | account_3136, analytics_1895 | The 3b chain {3136, analytics_1895} is correct but nothing ties it to case_25 rather than case_550 (SAMPLE_DEEP_DIVE §6.1, D8 tier 5 tie-break not implemented). |
| case_27 | analytics_4574 | All-null analytics record with no identifier; an optional type cannot be forced by elimination (H-STP-05 allows 0 or 1 per type, D8 tier 3). |
| case_29 | account_7012 | Account of a 4-case slot left symmetric after tiers 1-3b (H-STP-02 requires it; D8 tier 5 not implemented). |

No sample mismatch is an extra or a wrong step: precision is 1.000 (0 FP). The 9 missing steps are 3 ceiling steps (W-CEIL-01) and 6 residual attributions that tier 4/5 (M5) address.

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
