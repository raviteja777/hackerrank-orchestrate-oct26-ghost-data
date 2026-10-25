"""LLM profiles (DESIGN §11.2, D11): `local` (Ollama, development) and `final` (Anthropic, submission).

Plain data: role -> (provider, model). Same prompts and JSON schemas in both profiles; the cache key includes the
profile, provider and model so answers never leak between profiles.
Roles: intent (L1 primary), intent_escalation (L1 on disagreement), vision (L2/L4), residual (L3 tier 4).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config


@dataclass(frozen=True)
class Role:
    provider: str  # anthropic | ollama
    model: str


PROFILES: dict[str, dict[str, Role]] = {
    "local": {
        "intent": Role("ollama", "llama3.1"),
        "intent_escalation": Role("ollama", "gpt-oss:20b"),
        "vision": Role("ollama", "gemma4:12b"),
        "residual": Role("ollama", "gpt-oss:20b"),
    },
    "final": {
        "intent": Role("anthropic", config.MODEL_INTENT),
        "intent_escalation": Role("anthropic", config.MODEL_INTENT_ESCALATION),
        "vision": Role("anthropic", config.MODEL_VISION),
        "residual": Role("anthropic", config.MODEL_RESIDUAL),
    },
}

# Official list prices, USD per million tokens (input, output), checked 2026-10-06 against the Anthropic models
# table; Claude Haiku 5.5 is priced for prompts up to 100K tokens. Used only for the usage report estimate.
PRICES_USD_PER_MTOK = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
PRICES_CHECKED = "2026-10-06"


def role_for(profile: str, role: str) -> Role:
    try:
        return PROFILES[profile][role]
    except KeyError as exc:
        raise ValueError(f"unknown LLM profile/role: {profile}/{role}") from exc
