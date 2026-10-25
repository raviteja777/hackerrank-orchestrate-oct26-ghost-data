# Execution checklist (deadline: 2026-10-25 18:00 IST)

Planning document. Tick items as you go.

## A. Pre-flight (before Session 1)
Verified on 2026-10-25 (planning chat):
- [x] `python --version` → 3.14.5
- [x] `tesseract --version` → 5.5.3 (`TESSERACT_CMD` = folder, also on PATH; config resolves folder → exe)
- [x] `ANTHROPIC_API_KEY` set as a system env var
- [x] API probes (Postman): sonnet / haiku / opus 5.5 → 200; `temperature` → 400 "deprecated for this model" (no sampling params on Anthropic)
- [x] Ollama: `gemma4:12b` shows `vision` (also has thinking on by default and temperature 1, so calls set `think:false`, `temperature:0`, `seed`)
- [x] Billing split decided: Claude Code + planning chat on **Claude Pro**; solution LLM calls on **API credits**

Still to do right before Session 1:
- [x] Copy `.env.example` → `.env`, paste the API key (for the solution; `.env` is gitignored)
- [x] `ollama list` shows llama3.1, gpt-oss:20b, gemma4:12b, mistral; Ollama running (`http://localhost:11434`)
- [x] Open a fresh PowerShell at the repo root → `Remove-Item Env:ANTHROPIC_API_KEY` → `claude`
- [x] In Claude Code: `/status` shows the **Claude Pro** login (not an API key); model = **Sonnet 5.5**
- [x] `docs/CLAUDE_CODE_KICKOFF.md` open → paste the **Session 1** prompt
- [ ] Runs during the build use `--llm-profile local` (the default); `final` only for the M5 sample smoke run and the M6 submission run (D11)

## B. Build sessions (stop at each checkpoint, review, then continue)
| Session | Milestone | Target finish (IST) | Checkpoint passed? |
|---|---|---|---|
| 1 | M0 + M1 | 04:00 | [ ] valid placeholder `output.csv` · [ ] P12 numbers 1958/353/24/4 · [ ] 550/550 emails resolve |
| 2 | M2 parsers + facts | 06:30 | [ ] all non-ceiling sample resources found · [ ] cases 03/09/24 match dossiers |
| 3 | M3 runs + D8 tiers | 08:30 | [ ] 927 hard links · [ ] ≥361/518 eval accounts · [ ] sample precision ≥38/39 |
| 4 | M4 scored output | 11:30 | [ ] status ≥30/32 · [ ] step F1 ≥0.85 · [ ] sequence-exact ≥22/32 · [ ] 518 rows validate |
| 5 | M5 intent + screenshots | 14:00 | [ ] 10/10 non-deletion · [ ] 44/44 screenshot variants · [ ] cross-check summary |
| 6 | M6 final run + reports + zip | 16:00 | [ ] validator passes · [ ] both reports complete · [ ] `code.zip` built |
Buffer 16:00–18:00 for fixes and submission. **From M4 on, always keep a valid `output.csv` committed.**

After **every** session:
- [ ] `log.txt` has the new entries with correct `tool=` / `model=` lines
- [ ] `docs/OPEN_QUESTIONS.md` reviewed; OPEN items brought to the planning chat
- [ ] `git commit` (small, descriptive)
- [ ] `/export` the Claude Code session into `agent-trace/claude-code/`

## C. Final output checks (before submission)
- [ ] `output.csv` at repo root: header `case_id,deletion_status,steps_json`, 518 rows, numeric input order (D1; re-check Discord answer)
- [ ] Every `steps_json` is a valid JSON array; step_no consecutive from 1; only allowed phase/operation/state pairs
- [ ] COMPLETE: verification only, all cited; INCOMPLETE: findings cited, remediation/verification `""`; NOT_APPLICABLE: `[]`
- [ ] All cited files exist and have `captured_at ≤ audit_at`
- [ ] `case_533`–`case_542` are NOT_APPLICABLE
- [ ] Same run twice → byte-identical `output.csv` (determinism)
- [ ] Submitted `output.csv` produced by a `--llm-profile final` run; `usage_report.md` built from that run's ledger

## D. Deliverables
- [ ] `code.zip` = `README.md` + `code/` (incl. `code/evaluation/evaluation_report.md`, `code/evaluation/usage_report.md`); no `dataset/`, `.venv`, `__pycache__`, nested archives, secrets
- [ ] `evaluation_report.md`: status / step / field / sequence accuracy, ≥3 custom cases (target 6), failures found + improvements
- [ ] `usage_report.md`: providers + models, calls, input/output tokens, total + average per request, total + per-request cost, per-model and overall totals (final full run)
- [ ] README "Solution" section: setup, run command, architecture, limitations (W-CEIL-01, D8 tie-breaks, 3b)
- [ ] `log.txt` → **chat_transcript** upload
- [ ] `agent-trace.zip`: `agent-trace/claude-code/` (session JSONL from `%USERPROFILE%\.claude\projects\` + `/export` files) and this planning chat (claude.ai Settings → Privacy → Export data, requested by ~15:30 so the email arrives in time); secrets checked
- [ ] Submit at: https://wwww.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists

## E. AI interview prep (after submission)
- [ ] One-page story: problem → linkage chain (SVG) → D8 tiers → evidence over claims → time travel (D3)
- [ ] Be ready to explain: two-stage identity matching (P12 decoys), audit-capture file, absence proofs, 3b as a probable generator artifact (with ablation numbers), accuracy ceiling (W-CEIL-01), LLM kept narrow + cached (cost)
- [ ] Know the headline metrics and the top 3 failure modes from the evaluation report
