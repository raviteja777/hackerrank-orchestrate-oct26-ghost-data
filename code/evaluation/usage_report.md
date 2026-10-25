# Usage report

Final full-dataset run: `python code/main.py --llm-profile final --run-label final_run_1` (writes `output.csv`; 518 requests). Source: `code/cache/usage_ledger.jsonl`, rows with run = `final_run_1` and profile = `final`. Development runs on the `local` profile (Ollama: llama3.1, gpt-oss:20b, gemma4:12b) cost USD 0 and are not part of this report; the earlier 32-sample smoke run, a 3-call connectivity pre-check and the second (byte-identical) reproduction run have their own ledger labels and are excluded.

## Providers and models
| Provider | Model | Role in the pipeline |
|---|---|---|
| anthropic | claude-haiku-5-5 | L1 intent classification (batches of <= 20 distinct request texts, structured JSON) |
| anthropic | claude-sonnet-5-5 | L2 conditional screenshot reading (vision gate D5a) and L1 escalation on disagreement |
| (none) | claude-opus-5-5 | configured for tier 4; no call was needed in this run, so it does not appear above |

No sampling parameters are sent (current models reject them); thinking is adaptive with `effort: low`; responses use structured outputs.

## Calls and tokens per model

| Model | Calls (fresh + cached) | Input tokens | Output tokens | of which thinking tokens | Cache-write / cache-read input tokens |
|---|---|---|---|---|---|
| claude-haiku-5-5 | 20 (20 fresh + 0 cached) | 42,509 | 26,048 | 0 | 0 / 0 |
| claude-sonnet-5-5 | 2 (0 fresh + 2 cached) | 8,632 | 536 | 0 | 0 / 0 |
| **All models** | 22 (20 fresh + 2 cached) | 51,141 | 26,584 | | |

### Cached calls (flagged, original token counts)
A cached call was answered from the local content-hash cache; its tokens were billed in the earlier run that created the entry (here: the `final`-profile smoke run of the 32 samples) and are listed at their original counts.

| Model | Cached calls | Original input tokens | Original output tokens |
|---|---|---|---|
| claude-sonnet-5-5 | 2 | 8,632 | 536 |

## Tokens per request

| Measure | Value |
|---|---|
| Total tokens, all calls in the ledger (input + output) | 77,725 |
| Average tokens per request (/518) | 150.0 |
| Total tokens billed in this run (fresh calls only) | 68,557 |
| Average billed tokens per request (/518) | 132.3 |

## Estimated cost

Prices (USD per million tokens, input / output), checked 2026-10-06. Source: Anthropic models and pricing table (Claude API reference, cached 2026-10-06); https://platform.claude.com/docs/en/about-claude/pricing. Claude Haiku 5.5 is priced for prompts up to 100K tokens.

| Model | Input $/M | Output $/M |
|---|---|---|
| claude-haiku-5-5 | 0.10 | 0.50 |
| claude-opus-5-5 | 4.00 | 20.00 |
| claude-sonnet-5-5 | 2.00 | 10.00 |

| Model | Cost, all calls at original counts (USD) | Cost billed in this run, fresh calls only (USD) | Per request, all calls (USD) |
|---|---|---|---|
| claude-haiku-5-5 | 0.0173 | 0.0173 | 0.000033 |
| claude-sonnet-5-5 | 0.0226 | 0.0000 | 0.000044 |
| **Overall** | **0.0399** | **0.0173** | **0.000077** |

Costs are estimates from list prices; thinking tokens are part of the output tokens. Rule-based stages (identity, evidence parsing, linkage, state, policy, citations, tie-break) make no model calls, so the per-request cost is the intent classification (20 calls for 398 distinct request texts) plus two conditional screenshot readings.
