"""Paths, model names, feature flags and environment-variable keys (DESIGN §3, §11, §18).

Rules: D8 (tier switches), D10/D11 (models, profiles), OQ-1..OQ-6 defaults as flags.
Secrets are read from the environment or an uncommitted .env only.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"
EVIDENCE_DIR = DATASET_DIR / "evidence"
OUTPUT_PATH = REPO_ROOT / "output.csv"
CACHE_DIR = REPO_ROOT / "code" / "cache"
USAGE_LEDGER = CACHE_DIR / "usage_ledger.jsonl"

ENV_API_KEY = "ANTHROPIC_API_KEY"
ENV_TESSERACT = "TESSERACT_CMD"
ENV_OLLAMA_HOST = "OLLAMA_HOST"
ENV_PROFILE = "GHOST_LLM_PROFILE"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

# D10 / DESIGN §11: models used by the `final` profile (profile maps live in llm_profiles.py).
MODEL_INTENT = "claude-haiku-5-5"
MODEL_INTENT_ESCALATION = "claude-sonnet-5-5"
MODEL_VISION = "claude-sonnet-5-5"
MODEL_RESIDUAL = "claude-opus-5-5"
MAX_TIER4_CALLS = 50


@dataclass
class Flags:
    """Behaviour switches. Defaults are the documented defaults of docs/OPEN_QUESTIONS.md."""

    # D8 resolution tiers (contribution reported in the evaluation).
    tier_hard: bool = True
    tier_eliminate: bool = True
    tier_chains: bool = True  # tier 3b, W-LNK-05
    tier_llm: bool = True
    tier_tiebreak: bool = True
    require_observation_to_emit: bool = True  # G-STP-08: a non-account resource needs an observation in the window
    exclude_foreign_links: bool = True  # OQ-10: a validated link to another user excludes the case
    evidence_only_links: bool = True  # G-LNK-01: audit records, attachments and copies found only in evidence
    chain_policy_band: tuple = (9, 11)  # W-LNK-05, seconds mod 30
    chain_final_band: tuple = (20, 22)
    # Open-question defaults (DESIGN §7.2, §16).
    analytics_contact_delete: bool = True  # W-POL-01
    object_as_attachment: bool = True  # OQ-1
    expired_retention_delete: bool = True  # OQ-2 / X-POL-03
    retained_pii_finding: bool = False  # OQ-3 / X-POL-04
    unresolvable_email_complete: bool = True  # OQ-4 / X-IDN-02
    low_confidence_citation_fallback: bool = True  # OQ-5
    numeric_row_order: bool = True  # OQ-6 / D1


FLAGS = Flags()


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
    except ImportError:  # python-dotenv is optional at run time
        pass


def get_api_key() -> str | None:
    """Lookup order (DESIGN §18): ANTHROPIC_API_KEY env, then .env at the repo root."""
    _load_dotenv()
    return os.environ.get(ENV_API_KEY) or None


def get_ollama_host() -> str:
    _load_dotenv()
    return os.environ.get(ENV_OLLAMA_HOST, DEFAULT_OLLAMA_HOST)


def get_llm_profile(cli_value: str | None = None) -> str:
    """`local` (default) or `final` (D11)."""
    return cli_value or os.environ.get(ENV_PROFILE) or "local"


def resolve_tesseract() -> str | None:
    """DESIGN §18: a directory value gets the executable name appended; a file is used as is;
    otherwise fall back to `tesseract` on PATH. Returns None when unavailable."""
    _load_dotenv()
    value = os.environ.get(ENV_TESSERACT)
    if value:
        p = Path(value)
        if p.is_dir():
            for name in ("tesseract.exe", "tesseract"):
                if (p / name).is_file():
                    return str(p / name)
        elif p.is_file():
            return str(p)
    return shutil.which("tesseract")
