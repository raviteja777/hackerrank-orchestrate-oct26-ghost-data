# Review: Claude Code sessions 1–2 (M0, M1, M2)

Planning-chat review, 2026-10-25 09:44 IST. Everything below was re-run independently in the review VM (Linux, Python 3.10), not taken from the log.

## Verdict: both milestones accepted
| Check | Claimed | Re-run result |
|---|---|---|
| Unit tests | 48 passed | **48 passed** (3.7 s) |
| M1 / P12 reproduction | 1958 / 353 / 24 / 4; 550/550 | **exact=1958 same_user=353 unknown_decoys=24 other_user=4; 550/550** |
| M2 acceptance | PASS | **PASS**: 86/87 non-audit sample resources (72 facts + 14 run-only accounts); missing account_004 (ceiling); audit 22/24 (ceiling pair); dossiers 03 9/9, 09 8/8, 24 15/15 |
| Validator on the official `sample_output.csv` | — | **0/32 rows rejected** (no false positives) |
| Hard-coded case/resource/evidence ids in `code/ghost` | none | none (only in docstrings) |
| Log entries | SESSION START + per turn | present, `tool=Claude Code`, `model=claude-sonnet-5-5` ✓ |
| Code quality | — | clear modules, rule IDs cited, deterministic manifest order, broken files reported not fatal, decoys logged |

## Findings to carry into M3/M4 (state signals not yet mapped)
M2 keeps all raw fields, so nothing is lost; M4's state derivation must use these (DESIGN §6 updated):
1. `direct_identifiers` = 0/1 on `analytics_profile_read` log lines (35 facts) → ANONYMIZED / IDENTIFIABLE.
2. `decision=deny` on `restore_authorization_completed` (5 facts, e.g. backup_3933) → RESTORE_BLOCKED.
3. Support exposure: `event=message_pii_scan`, `detector=direct_identifier`, `matched_value` (51 facts, e.g. support_9553 in case_19), and identifiers inside free text (`message_text`, `message_excerpt`). `ident_fields` only checks column names, so M4 must also treat a validated identifier inside free text as exposure for REDACT/ANONYMIZE categories.
4. `marker_found=false` (legacy support replica) → copy still present (case_10). Captured as a signal but not yet in `derive_states`.
5. **Legal holds exist** in evidence (`legal_hold_*`, `legal_service`, `retained_until` 2033, 8 subjects), so new rule G-POL-03 applies: VERIFY_RECORD_PRESENT.
6. Facts with no `resource_id` (the PDF register evidence_27, account history evidence_18) are kept for linking but must **never** produce a step (G-POL-02).

## Process issues (fix now)
- **Nothing is committed.** `git log` still ends at the starter commit, and all of `code/`, `docs/`, `log.txt` and `output.csv` are untracked. Commit now (`git add -A && git commit -m "M0-M2: skeleton, identity, evidence parsers"`) and after every session.
- `.idea/` was untracked → added to `.gitignore`.
- Make sure both sessions were `/export`ed into `agent-trace/claude-code/`.

## Open questions
| ID | Answer |
|---|---|
| OQ-7 | Already answered by you. |
| OQ-8 | Accepted: account_004 joins the W-CEIL-01 ceiling. |
| OQ-9 | Accepted: the extra shapes are handled generically; DESIGN §5 now lists seven log layouts. |
| OQ-1…OQ-6 | Defaults stand; nothing new. OQ-6 still waits on Discord. |

## Schedule (≈3 h behind plan, 8 h 15 m left)
| Session | Scope | Revised target | Notes |
|---|---|---|---|
| 3 | M3 | 11:15 | port P13/P14 directly |
| 4 | M4 + evaluation harness | 13:45 | first real `output.csv`, committed |
| 5 | M5 lean | 15:45 | priority: intent (rules + local LLM), then screenshot OCR path, vision only if time allows |
| 6 | M6 | 17:00 | final run, reports, zip; **request the claude.ai export at ~15:30** |
| — | buffer | 17:00–18:00 | submission |

## Addendum (11:03): bracket / pipe / syslog log layouts
User question after OQ-11. Verified per file with the M2 `log_parser.parse_line`:
| Layout | Files | Lines | Trace id extracted |
|---|---|---|---|
| bracket `[LEVEL] [service] [tr-…] event:` | application_trace_* (2) | 218 | **218 (100%)** |
| pipe `\| LEVEL \| service \| tr-… \| event \|` | operations_stream_* (2) | 231 | **231 (100%)** |
| syslog `<15>1 node service tr-… - -` | syslog_archive_* (2) | 232 | **232 (100%)** |
| cloud runtime (`requestId`, nested `message=`) | cloud_runtime_* (2) | 433 | 433 (100%) |
| key=value / JSON | the rest | — | all data lines; the untraced lines are infrastructure noise (log_router, dns_cache, queue_consumer, secret_agent…) or self-contained single-line records (support_replica `contact_query_completed`, record_lookup) |
Conclusion: the gap was only in the **planning probes** (P04/P13/P14 used a `trace_id=` regex), which is why M3 finds 83 more hard links than P13. The production parser is correct. Sample precision was re-measured on the full parser in M3, so the probe gap does not affect any decision.
Hardening for unseen layouts (added to the Session 4 prompt, small):
1. Fallback trace detection: when no layout matches and no `trace_id/requestId/request_id` key exists, take a bare token matching `\b(?:tr|rb|req)-[A-Za-z0-9-]+\b`.
2. Parser self-check in the run report: per log file, the share of lines carrying a `resource_id` or identifier that received a trace id; warn when < 90%.
3. One unit test per layout (bracket, pipe, syslog, cloud runtime, JSON, key=value, legacy replica).
