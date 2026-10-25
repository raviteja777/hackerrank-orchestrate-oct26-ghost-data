# Review: Claude Code sessions 3–4 (M3, M4) + RCA of the M4 rule-application bugs

Planning-chat review, 2026-10-25 12:18 IST. All numbers re-run independently in the review VM.

## 1. Verification
| Check | Claimed | Re-run |
|---|---|---|
| pytest | 73 passed | **73 passed** |
| Sample evaluation (G-STP-08 on) | status 32/32, F1 0.976, sequence-exact 25/32, citations 69/75 | **identical** |
| Full output validator | passes | **0 issues**; 518 rows (339 INCOMPLETE / 179 COMPLETE) |
| Remaining sample misses | 3 ceiling + 6 attribution | confirmed: account_004, audit_record_6645/5569 (W-CEIL-01); accounts of case_21/25/29 (tier 5 stub) + 4 optional all-null analytics (case_21/25/27, by design not emitted when unattributable) |
| Known M5 gaps | intent stub, 71 eval cases without account | confirmed: case_533–542 currently get audit steps; 71 cases lack the account step |

## 2. Decisions on the open questions (all approved)
| OQ | Fix | Verdict | Guard / note |
|---|---|---|---|
| OQ-12a | Snapshot-scope proof of absence only when the resource has **no explicit observation** in the window | **Approved** → amends G-EVD-01 | Scope still proves absence for unobserved accounts (cases 01/02/31) |
| OQ-12b | State judged **per copy (topology)**; a violating copy is cleared only by a later-or-equal good observation of the **same** copy; ties → violation | **Approved** → amends G-SYS-01 / DESIGN §6 | Matches case_05 (failover) and case_16 (read replica) |
| OQ-13.1 | Naked singles assigned **after** all hard links and rejected if the case already has that type (H-STP-05) | **Approved** → amends D8 tier order | Sample precision 79/79 |
| OQ-13.2 | A PDF naming a resource id = presence observation; an "attachment" cue → SUPPORT_ATTACHMENT | **Approved** | Subject to G-STP-08 window; register PDFs without resource ids still produce no step (G-POL-02) |
| OQ-13.3/4 | Intent stub; tier 4/5 stubs | **M5 must close both** | Tier 5 is **deterministic, not an LLM** (DESIGN §8.3 step 6): implement it first, then the account step exists for all cases (H-STP-02) |

## 3. RCA: why these four were missed in planning
| # | Bug (first M4 run: status 28/32, F1 0.901) | Root cause | Where it entered | Category |
|---|---|---|---|---|
| 1 | A partial bundle snapshot "proved" absence and overrode explicit present/identifiable observations (case_12, case_19) | G-EVD-01 was derived only from cases where **no** explicit observation existed (01/02/04/31). The design treated a snapshot's *scope* (which systems it covers) as *completeness* (every record of that system is listed). Bundle collections are partial extracts. | RULES G-EVD-01 → DESIGN §6 "ABSENT … or resource missing from a snapshot whose scope covers its system" (no precedence stated) | Rule induced from positive examples only, with no counter-example search |
| 2 | A primary 404 cleared a still-present failover copy (case_05) | DESIGN §6 said "latest observation wins" **per resource**. G-SYS-01 (report replica copies under the base system and id) was written for *naming*. The abstraction dropped the topology dimension, so copies of one resource collapsed into one state. The deep-dive itself had case_05 right. | DESIGN §4.1/§6 (topology kept on the Fact but not in the state key) | Abstraction lost a dimension |
| 3 | A window naked single was assigned before hard links of the same type, so case_11 got a second analytics record | Inherited from my probe P13 (tier 1 assigned naked singles immediately; the type constraint ran only in tier 3). DESIGN said "port, don't reinvent", so the bug was ported. P13 was validated on aggregate precision (17 wrong) without triaging each wrong assignment. | probes P13/P14 → DESIGN §8.3 | Reference implementation not error-triaged |
| 4 | The only evidence for support_001 (case_07) is a PDF, which was not treated as a state observation or as an attachment | The PDF path was specified as "one record per document" for linking. Binary evidence was scoped as scenario-only (G-EVD-05) with one sample, so no state or category rule was written. | DESIGN §5 PDF row / §7.1 catalog refinements | Single-example path under-specified |

**Common root causes**
1. **Positive-only rule induction.** Rules were promoted on n/N support without searching for cases where the rule should *not* fire (1, 3).
2. **Milestone checks measured discovery, not outcome.** M2/M3 accepted "found / linked" counts. State, precedence and step errors could only appear at M4 scoring, the first end-to-end metric (1, 2, 4).
3. **Design abstraction dropped evidence dimensions** (snapshot completeness, copy topology) that the deep-dive had observed (1, 2).
4. **Probes reused as references without per-error triage** (3).

**What worked:** Claude Code triaged every mismatch and fixed rule *applications* without tuning to samples. The escalation protocol surfaced each change as an OQ.

## 4. Corrective actions
- Rules updated: G-EVD-01 (precedence), G-SYS-01 (per-copy state), D8 tier order (naked singles after hard links), PDF presence (OQ-13.2). See RULES.md and DESIGN §6 / §8.3.
- **Regression guard (M5/M6):** after every change, rerun the sample evaluation. Status must stay 32/32 and F1 must not drop below 0.976. Include the M2/M3 acceptance.
- **Custom evaluation cases from this RCA** (they also satisfy the "failures found" part of the report): (1) partial snapshot vs explicit observation; (2) replica copy present while primary is 404; (3) same-type second resource in a window; (4) PDF-only attachment.
- **Outcome-level check earlier:** M5 must report the sample metrics at its start and its end, not only feature checks.
