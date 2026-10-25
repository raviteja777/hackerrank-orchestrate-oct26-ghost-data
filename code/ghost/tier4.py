"""Tier 4 of the resolution (DESIGN §8.3 step 5, D10): LLM for content residuals only.

Called by resolve.py only for a parked resource that has unstructured content (screenshot / PDF text, free-text
fields) carrying no validated identifier, with >= 2 candidate cases. The model sees the candidates' identifiers and
the snippets (inside <evidence> tags, flagged snippets are excluded, §11.3) and must pick ONE candidate or null.
Its answer is validated twice: the choice must be a candidate, and the snippet must contain a token within edit
distance 2 of one of that candidate's identifiers (OCR noise tolerated, names never link, H-IDN-04). Anything else
is ignored and the deterministic tie-break decides. No model output reaches status, steps or citations.
"""
from __future__ import annotations

import re
from typing import Callable

from . import untrusted
from .identity import IdentityIndex
from .llm import LLMClient

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["case_id", "reason"],
          "properties": {"case_id": {"type": ["string", "null"]}, "reason": {"type": "string"}}}
SYSTEM = (
    "You attribute a deletion-audit record to one of several candidate customers. Each candidate is listed with its known "
    "identifiers (emails, phone). Choose a candidate only when the evidence text contains one of that candidate's "
    "identifiers, allowing for small OCR errors; never choose by name, and answer case_id = null when unsure. "
    "Quote the identifier you matched in the reason. " + untrusted.DATA_NOTICE
)
_TOKEN = re.compile(r"[\w.+\-@]{6,}")


def _edit_distance_le(a: str, b: str, k: int = 2) -> bool:
    if abs(len(a) - len(b)) > k:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] <= k


def make_decider(llm: LLMClient, index: IdentityIndex, user_of_case: Callable[[str], str | None]):
    def idents(case_id: str) -> list[str]:
        s = index.sets.get(user_of_case(case_id) or "")
        return sorted(s.emails | s.phones) if s else []

    def decide(resource_id: str, case_ids: list[str], snippets: list[str]) -> str | None:
        snippets = [s for s in snippets if not untrusted.suspicious(s)]  # flagged snippets never reach the prompt
        if not snippets:
            return None
        cands = "\n".join(f"- {c}: {', '.join(idents(c)) or '(none)'}" for c in case_ids)
        user = f"Candidates:\n{cands}\n\nResource: {resource_id}\n" + "\n".join(untrusted.wrap("evidence", s) for s in snippets)
        r = llm.call_json("residual", "L3", SYSTEM, user, SCHEMA, max_tokens=4000)
        choice = (r.data or {}).get("case_id")
        if choice not in case_ids:
            return None
        text = " ".join(snippets).lower()
        toks = _TOKEN.findall(text)
        if any(_edit_distance_le(t, ident.lower()) for t in toks for ident in idents(choice)):
            return choice
        return None

    return decide
