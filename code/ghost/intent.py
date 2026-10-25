"""Request intent gate (DESIGN §10).

TODO(M5): LLM classification (Haiku, cascade to Sonnet) with a multilingual rule lexicon cross-check.
M4 stub: every request is treated as authorising deletion, so the 10 non-deletion eval requests
(G-INT-01) currently get audit steps instead of NOT_APPLICABLE.
Rules: G-INT-01, S-STA-01.
"""
from __future__ import annotations


def authorizes_deletion(request_text: str) -> bool:
    return True  # TODO(M5)
