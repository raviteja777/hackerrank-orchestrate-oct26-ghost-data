"""LLM layer: providers (Anthropic, Ollama), content-hash cache, usage ledger (DESIGN §11).

Rules / constraints:
* Anthropic requests send NO sampling parameters (temperature / top_p / top_k are rejected on the current models)
  and no assistant prefill; JSON comes from structured outputs (`output_config.format` json_schema) and effort is
  set low for extraction / classification. Determinism = schema-constrained output + the cache.
* Ollama requests use the `format` schema, explicit temperature 0 and a fixed seed, and thinking off.
* The cache key is sha256(profile, provider, model, system, user, schema, image hashes): `local` answers never leak
  into `final`. Cached calls are ledgered with their original token counts and flagged.
* Keys come from the environment / uncommitted .env only (config.get_api_key); nothing secret is logged.
* No model output sets status, steps, citations or ordering (DESIGN §11.3, bounded authority).
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .llm_profiles import PRICES_USD_PER_MTOK, role_for

OLLAMA_SEED = 20261025


@dataclass
class LLMResponse:
    data: dict | None
    raw: str = ""
    usage: dict = field(default_factory=dict)
    cached: bool = False
    provider: str = ""
    model: str = ""
    error: str | None = None


class LLMError(RuntimeError):
    pass


def _sha(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


class LLMClient:
    def __init__(self, profile: str = "local", cache_dir: Path | None = None, ledger: Path | None = None,
                 run_label: str = "", max_retries: int = 1):
        self.profile = profile
        self.cache_dir = (cache_dir or config.CACHE_DIR / "llm")
        self.ledger = ledger or config.USAGE_LEDGER
        self.run_label = run_label
        self.max_retries = max_retries
        self._anthropic = None
        self.calls = 0
        self.cache_hits = 0

    # ---- public --------------------------------------------------------------------------------------------
    def call_json(self, role: str, purpose: str, system: str, user: str, schema: dict, images: list[bytes] | None = None,
                  max_tokens: int = 8000) -> LLMResponse:
        r = role_for(self.profile, role)
        img_hashes = [hashlib.sha256(b).hexdigest() for b in (images or [])]
        key = _sha(self.profile, r.provider, r.model, system, user, schema, img_hashes)
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            blob = json.loads(path.read_text(encoding="utf-8"))
            self.cache_hits += 1
            resp = LLMResponse(blob.get("data"), blob.get("raw", ""), blob.get("usage", {}), True, r.provider, r.model)
            self._ledger(purpose, resp, role)
            return resp
        last_err = None
        for attempt in range(self.max_retries + 1):  # one retry on parse failure (DESIGN §11)
            try:
                raw, usage, req_id = self._dispatch(r.provider, r.model, system, user, schema, images or [], max_tokens)
            except Exception as exc:  # network / API error: reported, never fatal to the pipeline
                last_err = f"{type(exc).__name__}: {exc}"
                continue
            self.calls += 1
            try:
                data = json.loads(raw)
            except ValueError:
                last_err = "invalid JSON from model"
                self._ledger(purpose, LLMResponse(None, raw, usage, False, r.provider, r.model, last_err), role, req_id)
                continue
            resp = LLMResponse(data, raw, usage, False, r.provider, r.model)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"data": data, "raw": raw, "usage": usage, "provider": r.provider, "model": r.model,
                                        "profile": self.profile}, ensure_ascii=False), encoding="utf-8")
            self._ledger(purpose, resp, role, req_id)
            return resp
        return LLMResponse(None, "", {}, False, r.provider, r.model, last_err)

    # ---- providers -------------------------------------------------------------------------------------------
    def _dispatch(self, provider, model, system, user, schema, images, max_tokens):
        if provider == "anthropic":
            return self._anthropic_call(model, system, user, schema, images, max_tokens)
        if provider == "ollama":
            return self._ollama_call(model, system, user, schema, images)
        raise LLMError(f"unknown provider {provider}")

    def _anthropic_call(self, model, system, user, schema, images, max_tokens):
        if self._anthropic is None:
            import anthropic

            key = config.get_api_key()
            if not key:
                raise LLMError("ANTHROPIC_API_KEY is not set (environment or .env)")
            self._anthropic = anthropic.Anthropic(api_key=key)
        content: list[dict] = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                              "data": base64.standard_b64encode(b).decode("ascii")}}
                               for b in images]
        content.append({"type": "text", "text": user})
        resp = self._anthropic.messages.create(  # no temperature / top_p / top_k, no prefill
            model=model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": content}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        )
        text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
        u = resp.usage
        details = getattr(u, "output_tokens_details", None)
        usage = {
            "input_tokens": getattr(u, "input_tokens", 0) or 0, "output_tokens": getattr(u, "output_tokens", 0) or 0,
            "thinking_tokens": (getattr(details, "thinking_tokens", 0) or 0) if details else 0,
            "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
            "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
            "service_tier": getattr(u, "service_tier", None), "stop_reason": getattr(resp, "stop_reason", None),
        }
        return text, usage, getattr(resp, "_request_id", None) or getattr(resp, "id", "")

    def _ollama_call(self, model, system, user, schema, images):
        host = config.get_ollama_host().rstrip("/")
        msg: dict = {"role": "user", "content": user}
        if images:
            msg["images"] = [base64.standard_b64encode(b).decode("ascii") for b in images]
        payload = {
            "model": model, "stream": False, "format": schema,
            "messages": [{"role": "system", "content": system}, msg],
            "options": {"temperature": 0, "seed": OLLAMA_SEED, "num_ctx": 8192},
            "think": "low" if model.startswith("gpt-oss") else False,
        }
        req = urllib.request.Request(f"{host}/api/chat", data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=900) as r:
            out = json.loads(r.read().decode("utf-8"))
        usage = {"input_tokens": out.get("prompt_eval_count", 0) or 0, "output_tokens": out.get("eval_count", 0) or 0,
                 "thinking_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "service_tier": None}
        return (out.get("message", {}) or {}).get("content", ""), usage, ""

    # ---- ledger ------------------------------------------------------------------------------------------------
    def _ledger(self, purpose: str, resp: LLMResponse, role: str, request_id: str | None = None) -> None:
        row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "profile": self.profile, "run": self.run_label,
               "purpose": purpose, "role": role, "provider": resp.provider, "model": resp.model, "request_id": request_id or "",
               "cache_hit": resp.cached, "error": resp.error, **{k: resp.usage.get(k) for k in (
                   "input_tokens", "output_tokens", "thinking_tokens", "cache_creation_input_tokens",
                   "cache_read_input_tokens", "service_tier")}}
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with open(self.ledger, "a", encoding="utf-8", newline="") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---- health check (local profile) ---------------------------------------------------------------------------------
def ollama_health(models: list[str], vision_model: str | None = None) -> list[str]:
    """Problems with the local Ollama setup (empty list = healthy). Lists installed models and, for the vision model,
    its capabilities (DESIGN §11.2)."""
    host = config.get_ollama_host().rstrip("/")
    problems = []
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=10) as r:
            have = {m["name"] for m in json.loads(r.read().decode("utf-8")).get("models", [])}
    except (urllib.error.URLError, OSError) as exc:
        return [f"Ollama is not reachable at {host}: {exc}"]
    for m in models:
        if m not in have and f"{m}:latest" not in have:
            problems.append(f"Ollama model not installed: {m}")
    if vision_model and not problems:
        try:
            req = urllib.request.Request(f"{host}/api/show", data=json.dumps({"model": vision_model}).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                caps = json.loads(r.read().decode("utf-8")).get("capabilities", [])
            if "vision" not in caps:
                problems.append(f"{vision_model} has no vision capability (capabilities: {caps})")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            problems.append(f"cannot inspect {vision_model}: {exc}")
    return problems


# ---- ledger summary (usage report input) ----------------------------------------------------------------------------
def read_ledger(path: Path | None = None) -> list[dict]:
    p = path or config.USAGE_LEDGER
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(rows: list[dict]) -> dict:
    """Per-model and overall calls / tokens / estimated cost. Cached calls keep their original token counts."""
    per: dict[str, dict] = {}
    for r in rows:
        m = per.setdefault(f"{r['provider']}:{r['model']}", {"calls": 0, "cache_hits": 0, "input": 0, "output": 0, "thinking": 0})
        m["calls"] += 1
        m["cache_hits"] += bool(r.get("cache_hit"))
        m["input"] += r.get("input_tokens") or 0
        m["output"] += r.get("output_tokens") or 0
        m["thinking"] += r.get("thinking_tokens") or 0
    total = {"calls": 0, "cache_hits": 0, "input": 0, "output": 0, "cost_usd": 0.0}
    for key, m in per.items():
        price = PRICES_USD_PER_MTOK.get(key.split(":", 1)[1])
        m["cost_usd"] = round((m["input"] * price[0] + m["output"] * price[1]) / 1e6, 6) if price else 0.0
        for k in ("calls", "cache_hits", "input", "output", "cost_usd"):
            total[k] += m[k]
    return {"per_model": per, "total": total}
