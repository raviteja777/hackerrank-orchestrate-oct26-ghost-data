# HackerRank Orchestrate - October 2026

## Ghost Data Still Exists

Build an AI agent that audits whether a user's personal data was actually deleted.

A deletion workflow may report **Complete** while data still exists in databases, logs, support attachments, exports, search indexes, archives, or backups. Sync and restore processes may also bring deleted data back.

For each request, the agent must first determine whether deletion was actually requested. It then returns `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`, reports any remaining data or recreation risk, and produces the ordered remediation and verification steps required to finish an authorized deletion safely.

Read [`problem_statement.md`](./problem_statement.md) for the complete challenge contract.

---

## Quick Start

Clone the repository and move into the project directory:

```bash
git clone https://github.com/interviewstreet/hackerrank-orchestrate-october26.git
cd hackerrank-orchestrate-october26
```

Start your AI coding tool from the **repository root** so it automatically reads [`AGENTS.md`](./AGENTS.md) and logs your session turns to `log.txt` in the root directory.

Build your solution in `code/main.py`, or use another language and document its setup and run command clearly in your README.

Your solution must:

- Read the input files from `dataset/`
- Generate one prediction row for every request in `dataset/deletion_requests.csv`
- Write the final predictions to `output.csv` in the repository root

Run the starter Python entry point with:

```bash
python3 code/main.py
```

The blank template at `dataset/output.csv` is provided as a reference. Your final generated file for submission must be the root-level `output.csv`.


## Dataset

All participant-facing files are in `dataset/`:

| File | Contents |
| --- | --- |
| `deletion_requests.csv` | 518 requests |
| `sample_deletion_requests.csv` | 32 sample requests |
| `sample_output.csv` | Correct sample answers |
| `user_identities.csv` | Current user identities |
| `user_audit_log.csv` | Historical identity changes |
| `system_activity.csv` | Activity across services and data processes |
| `deletion_rules.csv` | Required treatment for each data category |
| `evidence_files.csv` | Manifest of supplied evidence files |
| `output.csv` | Blank output template |

Evidence is stored under `dataset/evidence/` and may include PDFs, images, logs, JSON, plain text, or SQL snapshot exports. SQL captures may contain a primary database, regional replicas, a reporting replica, or a failover replica so replication drift can be investigated directly. The `.sql` files are readable as text and executable with SQLite.

Only `deletion_requests.csv` requires answers. The other files provide evidence and context.

---

## Output

Create `output.csv` with these columns in this exact order:

```text
case_id,deletion_status,steps_json
```

Produce exactly one row per request. `deletion_status` is `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`. `steps_json` is an ordered JSON array containing findings, remediation actions, and verification checks. Use an empty array (`[]`) for `NOT_APPLICABLE`. Evidence references may be a `file_id`, `activity_id`, or `audit_id`. Determine the resource state at `audit_at` from the available evidence; reported workflow statuses and operation results are claims. Use `dataset/sample_output.csv` as the format reference.

The final file must contain 518 data rows sorted by `case_id` (plus the header row). The grader parses `steps_json` as JSON, so object-key order and whitespace do not matter; array order does. Order findings, remediation, and verification in that phase order. Within a phase, follow the operation order in the problem statement, then sort by `system_id` and `resource_id`.

---

## Evaluation

`output.csv` will be compared with hidden canonical answers. Scoring considers:

- deletion assessment accuracy;
- current and historical identity resolution;
- discovery of remaining data and recreation risks;
- correct policy application and evidence references; and
- completeness and ordering of remediation and verification steps.

Your `code.zip` must include:

```text
code/evaluation/evaluation_report.md
code/evaluation/usage_report.md
```

- `evaluation_report.md` must cover case, row, field, and sequence accuracy, at least three additional evaluation cases created by you, failures found, and improvements made.
- `usage_report.md` must cover the final full-dataset run, including model providers and names, model calls, input and output tokens, total and average tokens per request, and estimated total and per-request cost. Include per-model and overall totals when using multiple models.

**Important:** Place `evaluation_report.md` and `usage_report.md` inside `code/evaluation/` (matching `code/evaluation/main.py` in this starter layout), write your complete evaluation metrics, custom evaluation test cases, and token/cost breakdowns directly inside those Markdown files, and keep prompts in source code or Markdown files. Automated code evaluation ignores raw data files (`.csv`, `.tsv`, `.json`, `.jsonl`, `.sql`, `.log`), so content stored only in those formats will not be visible to the code judge or AI interviewer.

---

## Chat Transcript

This repository includes [`AGENTS.md`](./AGENTS.md), which instructs compatible AI coding tools to append conversation summaries to `log.txt` in the repository root:

| Platform | Path |
| --- | --- |
| macOS / Linux | `<repo root>/log.txt` |
| Windows | `<repo root>\log.txt` |

- Always launch your AI coding agent from the repository root (or explicitly ask it to read `./AGENTS.md` first) so every turn is logged to `log.txt` with the required `User Prompt`, `Agent Response Summary`, `Actions`, and `Context` sections.
- Upload `log.txt` directly as your `chat_transcript` submission on HackerRank.
- Do not include API keys, tokens, credentials, or secrets in prompts, code, configuration, or `log.txt`.

---

## Solution: deletion-audit agent

A deterministic evidence pipeline with a narrow, cached LLM layer. Rules decide; models only *read* (request intent, screenshot meaning, content residuals) and can never set a status, a step, a citation or an ordering.

### Setup
1. Python 3.14 (tested; the code needs 3.10+ syntax, older 3.1x versions are untested). From the repository root:
   ```bash
   python -m venv .venv
   .venv/Scripts/python -m pip install -r code/requirements.txt     # Windows
   .venv/bin/python -m pip install -r code/requirements.txt         # macOS / Linux
   ```
2. **Tesseract OCR** (screenshots). Windows: `winget install UB-Mannheim.TesseractOCR`; set `TESSERACT_CMD` to the install folder or the executable if it is not on `PATH` (a folder value gets `tesseract.exe` appended). Without Tesseract the screenshot path degrades to the vision model / the committed cache.
3. **Anthropic key** (profile `final`): `ANTHROPIC_API_KEY` in the environment, or in an uncommitted `.env` at the repository root (copy `.env.example`). Keys are never written to code, logs or reports.
4. **Optional Ollama** (profile `local`, free development runs): `ollama pull llama3.1 gpt-oss:20b gemma4:12b`; `OLLAMA_HOST` defaults to `http://localhost:11434`.
5. Put the dataset in `dataset/` (it is not part of `code.zip`).

### Run
```bash
python code/main.py --llm-profile final      # submission run: Anthropic models (haiku-5-5 intent, sonnet-5-5 vision, opus-5-5 tier 4, not triggered in the final run)
python code/main.py --llm-profile local      # development run: Ollama models
python code/main.py --no-llm                 # rules only: no model calls at all
```
`main.py` writes `output.csv` at the repository root (rows in the input order of `dataset/deletion_requests.csv`, sorted by that order, 518 rows) and runs the validator (header, row count and order, JSON, 15 allowed operation/state pairs, numbering, ordering, per-status rules, one verification per resource, every cited id exists and is not later than `audit_at`); it exits non-zero on any issue. `--run-label NAME` tags the usage ledger. Model answers are cached by content hash in `code/cache/llm` (profile and model are part of the key), screenshot OCR in `code/cache/images`; the committed cache lets a run be reproduced without API access, and two runs produce a byte-identical `output.csv`. The submitted `output.csv` does not depend on model access at all: `--no-llm` (rules only) reproduces it byte for byte, verified on 2026-10-25. Without a flag the profile defaults to `local`; an unreachable model or a missing key is reported and never fatal.

Other commands: `python code/evaluation/main.py --write-report --llm-profile final` (sample metrics, ablations, full-dataset tier counts, intent table, custom cases), `python code/evaluation/usage_report.py --run final_run_2` (usage report from the ledger), `python code/evaluation/custom_cases.py`, `python -m pytest code/tests -q`.

### How it works
```
dataset CSVs ─ identities (+ audit-log history) ─┐
evidence (json, sql, logs x7 layouts, txt, pdf, png) ─ parsers ─ facts (record-level time, validated identifiers)
                                                     └─ edge log (append-only, time-stamped) ─ per-case view at audit_at
deletion_worker runs ─ slots by reported_at ─ tiers ─ case inventory ─ state ─ policy ─ citations ─ steps ─ output.csv
```
* **Linkage chain.** A person has current and historical emails, hashes, phones and a `user_NN`. A two-stage matcher (loose recall, then exact validation against the full identity set) turns evidence text into `mentions`; look-alikes and unknown addresses are logged as decoys and never link; names never link. Log lines are grouped per trace id so the identifier on the started line meets the resource on the completed line.
* **Evidence over claims.** `reported_status` and activity `reported_result` are claims. State is derived from facts only: latest observation in the window [run anchor, `audit_at`], judged per copy (primary versus replicas), explicit observations before snapshot-scope proofs of absence, documents and screenshot detail panels as presence evidence.
* **Time cut-off.** A fact is *known* if its own record time is at or before `audit_at` (inclusive), and a file is *citable* only if its `captured_at` is at or before `audit_at`; a later-captured file may reveal what was true earlier but is never cited.
* **Case inventory (D8 / D12).** Run events are attributed to cases in tiers: 1 hard identifier link (+ window singles after all hard links), 2 park, 3 elimination (one account per case, at most one resource per type), 3b timing-phase chains, 4 LLM for unstructured content only (validated against candidates and edge-distance), 4b audit-capture co-occurrence, 5 deterministic tie-break (low confidence). Intent is applied before resolution so non-deletion requests never compete for anchors; a validated link to another user excludes a case; the leftover ambiguity is written to `code/evaluation/ambiguity_queue.csv`.
* **Policy** is driven by `dataset/deletion_rules.csv` (delete, redact, anonymize, retain, tombstone); exposure is tested on the prohibited identifier columns and on identifiers inside free text. Findings, remediation and verification follow the allowed vocabulary; steps are sorted by phase, operation-table rank, `system_id`, `resource_id`; remediation and post-remediation verification in INCOMPLETE cases carry an empty `evidence_id`.
* **Untrusted input.** Request texts and OCR text are wrapped in tags and never edited; an instruction-like text is flagged, decided by the rules and answered by the model only advisorily.
* Every rule is cited by ID in the code (`docs/RULES.md`); open design questions and the decisions taken are in `docs/OPEN_QUESTIONS.md` and `docs/DECISIONS.md`.

### Outputs
`output.csv` (repository root), `code/evaluation/evaluation_report.md` (metrics, ablations, custom cases, failures found and improvements, limits), `code/evaluation/usage_report.md` (models, calls, tokens, cost of the final run), `code/evaluation/ambiguity_queue.csv`, `log.txt` (chat transcript).

### Limitations
Three sample answers are unreachable from participant data (`audit_record_6645`, `audit_record_5569`, `account_004`, W-CEIL-01). Attributions made by tier 5 carry no evidence and are low confidence; the timing-phase chains of tier 3b rely on the run cadence of the activity stream (verified out of sample on unlabelled eval slots, `docs/probes/P15_shortcut_diligence.py`; a dataset with another cadence would need re-validation); screenshots (no sample case cites one, so this path has no labelled example): each of the 11 PNGs is captured about a day before the `audit_at` of one scenario case; a detail panel that names a catalog resource is read as presence evidence (EO-7), which turned 5 cases from COMPLETE to INCOMPLETE (case_34, 35, 52, 63 match their screens; case_33 is doubtful, it reuses case_52's screenshot of the same user from a month earlier), while 6 cases stay COMPLETE with an empty array (case_39, 50, 55: no explicit state cue for that kind, not guessed; case_53: on-screen id not linked to the user; case_46, 61: images fail the OCR quality gate); the 267 low-confidence cases break down as 196 linked only through 3b chains, 52 tier-5 account guesses (no status effect), 11 without an account step and 8 citation fallbacks; unattributable all-null optional records are not emitted; screenshot OCR loses tokens at small scale. Details and numbers: `code/evaluation/evaluation_report.md`.

## Packaging `code.zip` and Submission

| Item | Description |
| --- | --- |
| `code.zip` | Runnable solution, prompts, configuration, `README.md`, and `evaluation/` reports |
| `output.csv` | One answer row for each of the 518 requests in `dataset/deletion_requests.csv` |
| `chat_transcript` | The root `log.txt` file generated by your coding agent |
| AI interview | Live explanation of your architecture, approach, and evaluation |

You may use any programming language, model, framework, or retrieval approach. Include clear setup and execution instructions in `README.md` inside `code.zip`.

To package `code.zip` from the repository root without bundling the dataset:

**macOS / Linux:**

```bash
zip -r code.zip README.md code -x "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store"
```

**Windows (PowerShell):**

```powershell
Compress-Archive -Path README.md, code -DestinationPath code.zip -Force
```

When packaging `code.zip`:

- Keep your evaluation reports in `code/evaluation/` so they are bundled automatically with `code` (or add `evaluation` to the archive command above if you placed them in a top-level `evaluation/` directory).
- Do **not** include `dataset/`, virtual environments (`.venv`, `venv`, `node_modules`), or build caches (`__pycache__`). On Windows, keep `.venv` at the repository root (outside `code/`) and remove any `code/__pycache__` folders before running `Compress-Archive`.
- Do **not** include nested archives (`.zip`, `.tar`, `.gz`, `.tgz`, `.7z`, `.rar`) inside `code.zip` — submissions containing nested archive files will be rejected.

Before submitting, confirm that:

- `output.csv` has the exact header `case_id,deletion_status,steps_json` and contains all 518 data rows sorted by `case_id`;
- every `steps_json` value is a valid JSON array with consecutive step numbers starting at `1`;
- findings cite valid evidence IDs, and `COMPLETE` verification steps cite evidence proving the current state;
- proposed remediation and future verification steps use an empty `evidence_id` (`""`);
- `code.zip` includes your runnable code, `README.md`, `code/evaluation/evaluation_report.md`, and `code/evaluation/usage_report.md`;
- `log.txt` follows the `AGENTS.md` turn format and is uploaded to the `chat_transcript` slot; and
- no API keys, credentials, real personal data, or sensitive configuration values are included.
