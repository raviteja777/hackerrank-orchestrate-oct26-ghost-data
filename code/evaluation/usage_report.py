"""Generate evaluation/usage_report.md from the usage ledger of ONE final run (AGENTS.md §6.8).

The run is selected by its ledger label (`python code/main.py --llm-profile final --run-label final_run_1`). Cached
calls are flagged and keep their ORIGINAL token counts (they were paid for in an earlier run). Prices come from
`ghost/llm_profiles.py` (official list prices, USD per million tokens, with the date they were checked).
Usage: python code/evaluation/usage_report.py [--run final_run_1] [--requests 518]
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ghost.llm import read_ledger  # noqa: E402
from ghost.llm_profiles import PRICES_CHECKED, PRICES_USD_PER_MTOK  # noqa: E402

OUT = Path(__file__).resolve().parent / "usage_report.md"
PRICE_SOURCE = ("Anthropic models and pricing table (Claude API reference, cached 2026-10-06); "
                "https://platform.claude.com/docs/en/about-claude/pricing. Claude Haiku 5.5 is priced for prompts up to 100K tokens.")


def cost(model: str, tin: int, tout: int) -> float:
    pin, pout = PRICES_USD_PER_MTOK.get(model, (0.0, 0.0))
    return (tin * pin + tout * pout) / 1e6


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="final_run_1")
    ap.add_argument("--requests", type=int, default=518)
    args = ap.parse_args(argv)
    rows = [r for r in read_ledger() if r.get("run") == args.run and r["profile"] == "final"]
    if not rows:
        print("no ledger rows for", args.run)
        return 1
    per: dict = defaultdict(lambda: defaultdict(int))
    for r in rows:
        k = (r["provider"], r["model"])
        fresh = "cached" if r.get("cache_hit") else "fresh"
        for f in ("input_tokens", "output_tokens", "thinking_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            per[k][f"{fresh}_{f}"] += r.get(f) or 0
        per[k][f"{fresh}_calls"] += 1
        per[k]["purposes_" + r["purpose"]] += 1
    n = args.requests
    lines = [f"# Usage report", "",
             f"Final full-dataset run: `python code/main.py --llm-profile final --run-label {args.run}` (writes `output.csv`; "
             f"{n} requests). Source: `code/cache/usage_ledger.jsonl`, rows with run = `{args.run}` and profile = `final`. "
             "Development runs on the `local` profile (Ollama: llama3.1, gpt-oss:20b, gemma4:12b) cost USD 0 and are not part of this report; "
             "the earlier 32-sample smoke run, a 3-call connectivity pre-check and the second (byte-identical) reproduction run "
             "have their own ledger labels and are excluded.", "",
             "## Providers and models",
             "| Provider | Model | Role in the pipeline |", "|---|---|---|"]
    role = {"claude-haiku-5-5": "L1 intent classification (batches of <= 20 distinct request texts, structured JSON)",
            "claude-sonnet-5-5": "L2 conditional screenshot reading (vision gate D5a) and L1 escalation on disagreement",
            "claude-opus-5-5": "L3 tier-4 residuals (content only)"}
    for (prov, model) in sorted(per):
        lines.append(f"| {prov} | {model} | {role.get(model, '')} |")
    lines += ["| (none) | claude-opus-5-5 | configured for tier 4; no call was needed in this run, so it does not appear above |"
              if ("anthropic", "claude-opus-5-5") not in per else "", "",
             "No sampling parameters are sent (current models reject them); thinking is adaptive with `effort: low`; responses use structured outputs.", "",
             "## Calls and tokens per model", "",
             "| Model | Calls (fresh + cached) | Input tokens | Output tokens | of which thinking tokens | Cache-write / cache-read input tokens |",
             "|---|---|---|---|---|---|"]
    tot = defaultdict(float)
    for (prov, model), d in sorted(per.items()):
        cin, cout = d["fresh_input_tokens"] + d["cached_input_tokens"], d["fresh_output_tokens"] + d["cached_output_tokens"]
        calls = d["fresh_calls"] + d["cached_calls"]
        lines.append(f"| {model} | {calls} ({d['fresh_calls']} fresh + {d['cached_calls']} cached) | {cin:,} | {cout:,} | "
                     f"{d['fresh_thinking_tokens'] + d['cached_thinking_tokens']:,} | "
                     f"{d['fresh_cache_creation_input_tokens'] + d['cached_cache_creation_input_tokens']:,} / "
                     f"{d['fresh_cache_read_input_tokens'] + d['cached_cache_read_input_tokens']:,} |")
        tot["calls"] += calls
        tot["in"] += cin
        tot["out"] += cout
        tot["fresh_in"] += d["fresh_input_tokens"]
        tot["fresh_out"] += d["fresh_output_tokens"]
        tot["cached_calls"] += d["cached_calls"]
        tot["cached_in"] += d["cached_input_tokens"]
        tot["cached_out"] += d["cached_output_tokens"]
    lines += [f"| **All models** | {int(tot['calls'])} ({int(tot['calls'] - tot['cached_calls'])} fresh + {int(tot['cached_calls'])} cached) | "
              f"{int(tot['in']):,} | {int(tot['out']):,} | | |", "",
              "### Cached calls (flagged, original token counts)",
              "A cached call was answered from the local content-hash cache; its tokens were billed in the earlier run that created the entry "
              "(here: the `final`-profile smoke run of the 32 samples) and are listed at their original counts.", "",
              "| Model | Cached calls | Original input tokens | Original output tokens |", "|---|---|---|---|"]
    for (prov, model), d in sorted(per.items()):
        if d["cached_calls"]:
            lines.append(f"| {model} | {d['cached_calls']} | {d['cached_input_tokens']:,} | {d['cached_output_tokens']:,} |")
    lines += ["", "## Tokens per request", "",
              "| Measure | Value |", "|---|---|",
              f"| Total tokens, all calls in the ledger (input + output) | {int(tot['in'] + tot['out']):,} |",
              f"| Average tokens per request (/{n}) | {(tot['in'] + tot['out']) / n:,.1f} |",
              f"| Total tokens billed in this run (fresh calls only) | {int(tot['fresh_in'] + tot['fresh_out']):,} |",
              f"| Average billed tokens per request (/{n}) | {(tot['fresh_in'] + tot['fresh_out']) / n:,.1f} |", "",
              "## Estimated cost", "",
              f"Prices (USD per million tokens, input / output), checked {PRICES_CHECKED}. Source: {PRICE_SOURCE}", "",
              "| Model | Input $/M | Output $/M |", "|---|---|---|"]
    for m, (a, b) in sorted(PRICES_USD_PER_MTOK.items()):
        lines.append(f"| {m} | {a:.2f} | {b:.2f} |")
    lines += ["", "| Model | Cost, all calls at original counts (USD) | Cost billed in this run, fresh calls only (USD) | Per request, all calls (USD) |", "|---|---|---|---|"]
    ca = cf = 0.0
    for (prov, model), d in sorted(per.items()):
        a = cost(model, d["fresh_input_tokens"] + d["cached_input_tokens"], d["fresh_output_tokens"] + d["cached_output_tokens"])
        f = cost(model, d["fresh_input_tokens"], d["fresh_output_tokens"])
        ca, cf = ca + a, cf + f
        lines.append(f"| {model} | {a:.4f} | {f:.4f} | {a / n:.6f} |")
    lines += [f"| **Overall** | **{ca:.4f}** | **{cf:.4f}** | **{ca / n:.6f}** |", "",
              "Costs are estimates from list prices; thinking tokens are part of the output tokens. Rule-based stages (identity, evidence parsing, "
              "linkage, state, policy, citations, tie-break) make no model calls, so the per-request cost is the intent classification (20 calls for "
              "398 distinct request texts) plus two conditional screenshot readings.", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {OUT}: {int(tot['calls'])} calls, {int(tot['in'])} in / {int(tot['out'])} out, USD {ca:.4f} (billed {cf:.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
