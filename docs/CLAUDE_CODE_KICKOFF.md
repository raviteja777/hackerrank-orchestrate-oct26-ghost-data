# Claude Code kick-off prompts

Start Claude Code **from the repository root** (so `CLAUDE.md` → `AGENTS.md` load and `log.txt` is used), with Sonnet 5.5 selected. Paste one prompt per session or milestone. Each prompt ends at a checkpoint, so you can review before continuing.

---

## Session 1: M0 + M1 (paste as is)
```
Read AGENTS.md, docs/DESIGN.md (all sections), docs/DECISIONS.md and docs/RULES.md before doing anything.
Append the SESSION START entry to log.txt as AGENTS.md requires (exact tool= and model= values), and log every turn.

Goal for this session: milestones M0 and M1 from docs/DESIGN.md §14. Nothing beyond M1.

M0:
1. Create .venv at the repo root (python -m venv .venv). Write code/requirements.txt with pinned versions for:
   pandas, numpy, networkx, opencv-python-headless, pytesseract, pypdf, anthropic, python-dotenv, pytest.
   Install and confirm every package imports on this Python (3.14.5). If any fails, stop and record it in docs/OPEN_QUESTIONS.md (DESIGN §18).
2. Create the module skeleton from DESIGN §3 (empty modules with docstrings naming their DESIGN section and rule IDs).
3. Implement config.py, loaders.py, steps.py (ordering + serialisation, DESIGN §12), validate.py (all checks in §12) and main.py,
   writing output.csv at the repo root with every case NOT_APPLICABLE / [] as a placeholder, in the input row order (D1).
4. Unit tests: ordering key, serialisation, validator (good and bad fixtures).
Acceptance: python code/main.py writes output.csv; the validator passes the format checks; pytest passes.

M1:
5. identity.py per DESIGN §8.1 and rule H-IDN-04 (two-stage matcher with exact validation against the full identity set; names never link; decoy log).
6. Tests + a small script or test that reproduces probe P12 on the dataset: 1,958 exact / 353 same-user / 24 unknown decoys / 4 other-user look-alikes, and all 550 request emails resolve.
Acceptance: the numbers above reproduce (report them in your log entry).

Rules: do not deviate from DESIGN/DECISIONS; cite rule IDs in comments; no hard-coded case or resource IDs in logic; no secrets in code or logs.
If anything is unclear, follow DESIGN §15.1: record it in docs/OPEN_QUESTIONS.md with a default, implement the default behind a flag, tell me, and continue.
At the end: summarise what was built, the acceptance results, and any open questions. Then stop.
```

## Session 2: M2 (evidence parsers and facts)
```
Read docs/DESIGN.md §4–§6 and docs/SAMPLE_DEEP_DIVE.md §2–§3. Log per AGENTS.md.
Implement milestone M2 (DESIGN §14): evidence parsers for json, sql (sqlite3 in-memory), logs (format-agnostic, grouped by trace id; six styles listed in §5), txt, pdf (pypdf), plus normalize.py and facts.py with record-level fact_time (D3) and catalog.py (§7.1).
Acceptance: every non-audit resource in dataset/sample_output.csv is found as a fact or a run candidate except the W-CEIL-01 list; facts for cases 03, 09 and 24 match the dossiers in docs/probes/out/P02_case_03/09/24.txt; parser unit tests pass.
Screenshots (png) come in M5: for now register them as unparsed with a TODO. Record any new evidence shape in docs/OPEN_QUESTIONS.md. Stop after M2.
```

## Session 3: M3 (edge log, runs, D8 tiers 1–4)
```
Read docs/DESIGN.md §4.2, §8 and docs/SAMPLE_DEEP_DIVE.md §5–§6, plus docs/probes/P04, P13, P14. Log per AGENTS.md.
Before coding, read docs/REVIEW_S1_S2.md and run `git status`; commit any uncommitted work first.
Implement M3: edgelog.py (D7), runs.py (windows and phase chains), resolve.py (tiers 1, 2, 3, 3b; tiers 4 and 5 stubbed), each tier switchable in config.
Acceptance: sample-side precision of case-resource assignment >= 38/39 (P14) and no regression on the M2 acceptance; eval accounts resolved >= 361/518 and hard links ≈ 927 (P13). The probes used their own simpler fact index, so counts within ±5% are fine. Explain any larger gap (e.g. M2 parses more formats → more hard links) instead of tuning to the number. Report the per-tier counts and the 3b ablation (tiers 1–3 vs 1–3+3b). Stop after M3.
```

## Session 4: M4 (state, policy, citations, steps, first scored output)
```
Read docs/DESIGN.md §6, §7, §9, §12, §13 and docs/RULES.md (HARD + GOOD). Log per AGENTS.md.
Before coding, read docs/REVIEW_S1_S2.md "Findings to carry into M3/M4" (items 1–6) and DESIGN §6 (updated): they are mandatory for state derivation. Also read OQ-10 / OQ-11 answers in docs/OPEN_QUESTIONS.md and implement candidate rule G-STP-08 behind a flag (`require_observation_to_emit=True`); report sample metrics with the flag on and off. Small hardening first (≤15 min): docs/REVIEW_S1_S2.md "Addendum (11:03)" items 1–3 (bare-token trace fallback, parser self-check, one test per log layout).
Implement M4: state.py, policy.py (driven by dataset/deletion_rules.csv), citations.py, steps, status; then code/evaluation/main.py with the §13 metrics on the 32 samples.
Acceptance: status >= 30/32, step F1 >= 0.85, sequence-exact >= 22/32; validator passes on the full 518-row output.
For every sample mismatch, write a one-line diagnosis (rule ID involved) into code/evaluation/evaluation_report.md under "Failures found". Do not change rules to fit samples. Record proposals in OPEN_QUESTIONS. Stop after M4.
```

## Session 5: M5 (intent LLM, screenshots, tier 5)
```
Read docs/DESIGN.md §5.1, §10, §11 and docs/SCREENSHOTS.md §5–§7; port docs/probes/P09_region_labelling.py. Log per AGENTS.md.
Start: read docs/REVIEW_S3_S4.md; run the sample evaluation and record the baseline (status 32/32, F1 0.976, sequence-exact 25/32). FIRST implement the deterministic tier-5 tie-break (DESIGN §8.3 step 6; no LLM) so every deletion case gets an account step (H-STP-02), then intent. Re-run the sample evaluation after each feature; status must stay 32/32 and F1 must not drop.
Implement M5 using the `local` LLM profile (DESIGN §11.2, D11): intent.py (LLM + multilingual rules, cascade, cached), image_parser.py (D5 geometry + OCR + vision LLM + cross-check, cached by sha256), llm.py (providers, cache, usage ledger), resolve tier 4 (LLM for content residuals only).
Acceptance (local profile): 10/10 non-deletion eval requests detected (case_533..542), all samples classified as deletion; P09 44/44 region consistency on original/0.6x/1.5x/inverted variants; cross-check summary in the evaluation report. Also add the 4 RCA custom evaluation cases (REVIEW_S3_S4 §4). Implement DESIGN §11.3 (untrusted-input handling: delimited prompts, suspicious-input detector, deterministic fallback, no text rewriting) and its injection custom case. Then ONE `final`-profile smoke run on the 32 samples only, and report its token usage. Stop after M5.
```

## Session 6: M6 (final run, reports, packaging)
```
Read AGENTS.md, docs/DESIGN.md §13, §14 (M6), §18, docs/DECISIONS.md (D12), docs/REVIEW_S3_S4.md, and README.md (packaging). Log per AGENTS.md.

PART A: small fixes (local profile). Re-run the sample evaluation after EACH; status must stay 32/32 and F1 must not drop below 0.979. Report before/after numbers.
 1. D12: apply intent before resolution (NOT_APPLICABLE cases never compete for anchors); add tier 4b (audit-capture co-occurrence: an unassigned account mentioned in a file captured <= 24 h before exactly one remaining candidate's audit_at goes to that case); write the ambiguity queue to code/evaluation/ambiguity_queue.csv; run tier 5 most-constrained slot first, with propagation after each assignment; keep the stable secondary key resource_id.
 2. OQ-16 refinement: undecided after dropping flagged sentences -> rules on the full text, low confidence, logged; add that sentence to the injection custom case.
 3. git commit.

PART B: final run. OQ-6 is closed: D1 numeric input order is final; output rows must follow the input row order exactly.
 4. python code/main.py --llm-profile final  (writes ./output.csv; the validator must pass). Run it a second time: output.csv must be byte-identical.
 5. Evaluation report code/evaluation/evaluation_report.md must explicitly contain: case-level status accuracy; step-level P/R/F1; field-level accuracy per field; sequence accuracy (exact + LCS); citation accuracy; ablations (G-STP-08 on/off, 3b on/off, tier 5 on/off, D12 before/after, intent rules vs LLM); per-tier counts and the ambiguity-queue summary (how many tier-5 low-confidence assignments); the >= 8 custom cases with results; "Failures found and improvements made" incl. the M4 RCA (docs/REVIEW_S3_S4.md §3) and OQ-10..16 outcomes; known limits (W-CEIL-01 ceiling, tier-5 guesses, 3b as a probable generator artifact). All metrics from the final-profile run.
 6. Usage report code/evaluation/usage_report.md from the usage ledger of THIS final run only: providers and model names; calls per model (cached calls flagged with original token counts); input and output tokens (incl. thinking tokens); total and average tokens per request (/518); estimated total and per-request cost per model and overall (prices in config.py, with the date and source).
 7. README.md "Solution" section: setup (Python, venv, requirements, Tesseract + TESSERACT_CMD, ANTHROPIC_API_KEY via env or .env, optional Ollama), run commands (local vs final profile), architecture summary (linkage chain, D8/D12 tiers, evidence-over-claims, time cut-off), outputs, limitations.
 8. Package: delete code/**/__pycache__, then build code.zip with the README command (README.md + code/; no dataset, no .venv, no nested archives, no .env). List the zip contents in the log and confirm no secret is inside (grep for "sk-ant").
 9. Final validator run, git commit, then stop.
```


---
### Notes for the user
- Between sessions, glance at `docs/OPEN_QUESTIONS.md`; bring OPEN items back to the planning chat.
- Keep `.env` (copy of `.env.example` with your key) out of git; `.gitignore` already excludes it.
- After the final session: export each Claude Code session with `/export` and collect `~/.claude/projects/` JSONL files into `agent-trace/claude-code/` (see `agent_trace_instructions.md`); export this planning chat via claude.ai Settings → Privacy → Export data.

## Session 7 (approved, time-boxed 60 min): EO-7 screenshot presence evidence
```
Read AGENTS.md, docs/OPEN_QUESTIONS.md EO-7, docs/DESIGN.md §5 (screenshots) and §6 (state). Log per AGENTS.md.
STEP 0: git restore code/cache/.gitkeep if missing; delete output_run1.csv / output_bkup.csv if present; commit the current state ("pre-EO-7 baseline"). Copy output.csv to output_baseline.csv (untracked, not zipped) for the diff.

Context: each of the 11 PNGs is captured about one day before audit_at of one scenario case (evidence_04 case_34, _09 case_35, _14 case_39, _19 case_50, _23 case_52, _28 case_53, _32 case_55, _37 case_45, _42 case_46, _46 case_61, _60 case_63). PNG facts carry validated mentions but empty signals, so assess() sees no observation and G-STP-08 drops the resource; 9 of these cases are COMPLETE with []. Example: evidence_23 shows export_1260, owner ingrid.dahl@outlook.com, status Ready -> case_52 should be INCOMPLETE (FINDING REPORT_REMAINING_RECORD PRESENT evidence_23, then the policy's remediation and verification, as in sample case_08). DESIGN/README already say screenshot detail panels are presence evidence; implement that, nothing else.

Change:
 1. A PNG fact whose header/detail panel names a catalog resource id gets an observation at file captured_at: present=True by default; present=False only on an explicit absence cue in that panel (not found / deleted / removed / expired / no records). Keep the existing explicit cues (restore allowed, enabled, direct identifiers).
 2. A PNG fact with a validated identifier of a case's user in header/detail links its resource to that case as evidence-only, also when the resource appears in deletion_worker runs, provided no run tier assigned it to another case.
 3. Do not guess for gate-failed images (evidence_42, evidence_46).
 4. Report only (no change): which cases the 4 PDFs relate to (user and resource ids, captured_at vs audit_at), and why output.csv cites no PDF while the sample cites one.

PHASE 1, test on cached model outputs (no new API spend): `python code/main.py --llm-profile final --run-label eo7_test` (all calls must be cache hits; if any call is fresh, report it) and `python code/main.py --no-llm --output <temp>`.
Guardrails (all must hold, else `git checkout -- .`, keep the baseline output, and go to WIND-UP):
 - sample metrics byte-identical: status 32/32, F1 0.984, sequence-exact 26/32, citations 72/75 (no sample cites a PNG);
 - output.csv diff vs output_baseline.csv touches only case_33..case_63; list every changed case with before/after status and steps;
 - validator passes; pytest passes; the --no-llm output is byte-identical to the eo7_test output.
If all hold: commit ("EO-7: screenshot presence evidence"), then STOP and tell the user to do the fresh run.

FRESH RUN (the user does it manually): caches moved aside, `python code/main.py --llm-profile final --run-label final_run_2`, repeat run, hash compare.

WIND-UP (Claude Code, after the user confirms the fresh run, or right away if Phase 1 was reverted): regenerate code/evaluation/evaluation_report.md (`python code/evaluation/main.py --write-report --llm-profile final`; add EO-7 to "Failures found and improvements made" with the before/after numbers) and code/evaluation/usage_report.md (`--run final_run_2`, or `final_run_1` if reverted); update README (usage command, EO-7 limitation: fixed or still open); validator; pytest; commit; delete __pycache__; rebuild code.zip with the README command; check the zip has no __pycache__ / .env / dataset / venv entries and no "sk-ant"; delete output_baseline.csv; stop.
```
