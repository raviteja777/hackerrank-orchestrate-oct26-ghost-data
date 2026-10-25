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
Acceptance: reproduce P13 (927 hard links) and P14 (eval accounts resolved >= 361/518; sample precision >= 38/39). Report the per-tier counts. Stop after M3.
```

## Session 4: M4 (state, policy, citations, steps, first scored output)
```
Read docs/DESIGN.md §6, §7, §9, §12, §13 and docs/RULES.md (HARD + GOOD). Log per AGENTS.md.
Before coding, read docs/REVIEW_S1_S2.md "Findings to carry into M3/M4" (items 1–6) and DESIGN §6 (updated): they are mandatory for state derivation.
Implement M4: state.py, policy.py (driven by dataset/deletion_rules.csv), citations.py, steps, status; then code/evaluation/main.py with the §13 metrics on the 32 samples.
Acceptance: status >= 30/32, step F1 >= 0.85, sequence-exact >= 22/32; validator passes on the full 518-row output.
For every sample mismatch, write a one-line diagnosis (rule ID involved) into code/evaluation/evaluation_report.md under "Failures found". Do not change rules to fit samples. Record proposals in OPEN_QUESTIONS. Stop after M4.
```

## Session 5: M5 (intent LLM, screenshots, tier 5)
```
Read docs/DESIGN.md §5.1, §10, §11 and docs/SCREENSHOTS.md §5–§7; port docs/probes/P09_region_labelling.py. Log per AGENTS.md.
Implement M5 using the `local` LLM profile (DESIGN §11.2, D11): intent.py (LLM + multilingual rules, cascade, cached), image_parser.py (D5 geometry + OCR + vision LLM + cross-check, cached by sha256), llm.py (providers, cache, usage ledger), resolve tier 4 (LLM for content residuals only).
Acceptance (local profile): 10/10 non-deletion eval requests detected (case_533..542), all samples classified as deletion; P09 44/44 region consistency on original/0.6x/1.5x/inverted variants; cross-check summary in the evaluation report. Then ONE `final`-profile smoke run on the 32 samples only, and report its token usage. Stop after M5.
```

## Session 6: M6 (final run, reports, packaging)
```
Read docs/DESIGN.md §13, §14 (M6), §18 and README.md (packaging). Log per AGENTS.md.
Run the full pipeline with `--llm-profile final` (D11); generate code/evaluation/evaluation_report.md (metrics, ablations, >=6 custom cases, failures and fixes) and code/evaluation/usage_report.md (from the usage ledger of this final run).
Add the "Solution" section to README.md (setup, run, architecture, limitations incl. W-CEIL-01 and D8 tie-breaks).
Build code.zip with the README command (no dataset, no .venv, no __pycache__, no nested archives, no secrets). Run the validator one last time and stop.
```

---
### Notes for the user
- Between sessions, glance at `docs/OPEN_QUESTIONS.md`; bring OPEN items back to the planning chat.
- Keep `.env` (copy of `.env.example` with your key) out of git; `.gitignore` already excludes it.
- After the final session: export each Claude Code session with `/export` and collect `~/.claude/projects/` JSONL files into `agent-trace/claude-code/` (see `agent_trace_instructions.md`); export this planning chat via claude.ai Settings → Privacy → Export data.
