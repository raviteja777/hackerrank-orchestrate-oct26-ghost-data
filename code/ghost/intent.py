"""Request intent gate (DESIGN §10, §11.3).

Does the request authorise deletion? Access, export, correction, contact change, login help, invoice copy,
marketing opt-out and explicit "not asking for deletion" requests are NOT_APPLICABLE (S-STA-01, G-INT-01).
Check / verify / finish / audit a deletion counts as a deletion request.

Pipeline: distinct texts are classified once (cache). A multilingual rule lexicon always runs; the LLM (L1, batched
20 texts per call, strict JSON) is the primary reader and the rules are the cross-check. Cascade: primary model
first; on disagreement with the rules or invalid output the text is re-asked to the escalation model, whose answer
stands. Untrusted-input handling (§11.3): texts sit inside <request_text> tags, an instruction-like text is flagged
(`suspicious`), the rules decide it (judging only the unflagged sentences) and the LLM answer is advisory; text is
never rewritten. No LLM output can set anything but this boolean.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from . import untrusted
from .llm import LLMClient

REQUEST_TYPES = ["DELETE_ACCOUNT", "DELETE_DATA", "VERIFY_DELETION", "ACCESS", "EXPORT", "CORRECTION", "CONTACT_CHANGE",
                 "LOGIN_HELP", "INVOICE_COPY", "MARKETING_OPT_OUT", "OTHER"]
BATCH_SIZE = 20
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["results"],
    "properties": {"results": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "authorizes_deletion", "request_type", "language", "reason"],
        "properties": {"id": {"type": "integer"}, "authorizes_deletion": {"type": "boolean"},
                       "request_type": {"type": "string", "enum": REQUEST_TYPES},
                       "language": {"type": "string"}, "reason": {"type": "string"}}}}},
}
SYSTEM = (
    "You classify customer privacy requests for a commerce platform. For each request decide whether the person is "
    "asking for their account or personal data to be deleted or erased. "
    "authorizes_deletion = true for: delete / erase / close / remove the account or personal data, permanent deletion, "
    "and also for requests to check, verify, audit, investigate or finish a deletion they already asked for or were told "
    "was done. authorizes_deletion = false for: access to data, export or portability, correction of details, changing an "
    "email or phone number, login help, an invoice or data copy, marketing or promotional opt-out ('marketing lists only'), "
    "and any request that says they are NOT asking for deletion or want the account kept. Requests may be in any language. "
    "Answer with JSON only, one entry per request id, with a short reason. " + untrusted.DATA_NOTICE
)

# ---- deterministic multilingual rules ---------------------------------------------------------------------------
_DELETE = [re.compile(p, re.I) for p in [
    r"\bdelet(e|ed|es|ing|ion)\b", r"\berase[ds]?\b", r"\berasure\b", r"\bremove (my|the|this|all)\b.{0,25}\b(account|profile|data|details|information)",
    r"\bclos(e|ed|ing|ure)\b.{0,40}\baccount", r"\baccount\b.{0,40}\bclos(e|ed|ure)\b", r"\bno longer (use|need)\b",
    r"\bdisconnected my account", r"\baccount\b.{0,20}\b(is|was) gone", r"\bstill existed\b", r"privacy page", r"my request failed",
    r"eliminar|eliminaci|borrar|exclus|excluir|apagar|supprim|suppression|effac|supprimer|löschen|elimin|cancellare",
    r"削除|消去|退会|삭제|탈퇴|永久|영구",
]]
_NEG = [re.compile(p, re.I) for p in [
    r"\bnot (asking|requesting) (for )?(a )?(deletion|erasure|removal|delet)", r"\bnot a request to (erase|delete|remove)\b",
    r"\bnot (asking|requesting|wanting) (you )?to (delete|erase|remove|close)\b",
    r"\b(do not|don't|do n't|please don't|never) (want you to )?(delete|close|remove|erase)\b", r"\bwithout (removing|deleting)\b",
    r"\bmarketing lists? only\b", r"\bkeep (the|my) (account|profile)\b", r"\bleave (the|my) (account|profile)\b",
    r"\bleave .{0,40}\bin place\b", r"\bleave the account active\b", r"\bnot asking for deletion\b",
]]
_NONDEL = [re.compile(p, re.I) for p in [
    r"promotional emails?", r"\bdownload my\b", r"portable format", r"\bcopy of\b", r"personal information you hold",
    r"information held on", r"\bmisspelled\b", r"\bout of date\b", r"resetting the login", r"can't access my profile",
    r"change the email address", r"send me a copy",
]]
_SENT = re.compile(r"(?<=[.!?。])\s+|\n+")


@dataclass
class IntentResult:
    authorizes_deletion: bool
    request_type: str = "OTHER"
    language: str = ""
    reason: str = ""
    source: str = "rules"  # rules | llm | cascade | rules(suspicious) | default
    suspicious: bool = False
    escalated: bool = False
    rules: bool | None = None
    llm: bool | None = None
    notes: list[str] = field(default_factory=list)


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def split_flagged(text: str) -> tuple[list[str], list[str]]:
    clean, flagged = [], []
    for s in _SENT.split(text):
        if not s.strip():
            continue
        (flagged if untrusted.suspicious(s) else clean).append(s)
    return clean, flagged


def rules_decide(text: str) -> bool | None:
    """True / False / None (undecided). Instruction-like sentences are ignored (they are data, not requests)."""
    clean, _ = split_flagged(_norm(text))
    body = " ".join(clean)
    if any(r.search(body) for r in _NEG):
        return False
    if any(r.search(body) for r in _DELETE):
        return True
    if any(r.search(body) for r in _NONDEL):
        return False
    return None


# ---- gate -------------------------------------------------------------------------------------------------------------
class IntentGate:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm
        self.results: dict[str, IntentResult] = {}

    def classify_all(self, texts: list[str]) -> dict[str, IntentResult]:
        distinct = sorted(set(texts))
        pending: list[str] = []
        for t in distinct:
            if t in self.results:
                continue
            sus = untrusted.suspicious(_norm(t))
            r = rules_decide(t)
            res = IntentResult(authorizes_deletion=True if r is None else r, rules=r, suspicious=sus, source="rules")
            if r is None:
                res.source, res.notes = "default", ["rules undecided"]
            self.results[t] = res
            if self.llm is not None:
                pending.append(t)
        if self.llm is not None and pending:
            normal = [t for t in pending if not self.results[t].suspicious]
            flagged = [t for t in pending if self.results[t].suspicious]
            for i in range(0, len(normal), BATCH_SIZE):
                self._batch(normal[i:i + BATCH_SIZE], "intent")
            for t in flagged:  # isolated advisory call; the rules decide (§11.3)
                self._batch([t], "intent", advisory=True)
        return {t: self.results[t] for t in distinct}

    def _ask(self, texts: list[str], role: str, purpose: str) -> dict[int, dict]:
        user = "Classify each request.\n" + "\n".join(untrusted.wrap("request_text", t, id=str(i)) for i, t in enumerate(texts))
        resp = self.llm.call_json(role, purpose, SYSTEM, user, SCHEMA, max_tokens=8000)
        if not resp.data:
            return {}
        out = {}
        for item in resp.data.get("results", []):
            if isinstance(item, dict) and isinstance(item.get("id"), int) and 0 <= item["id"] < len(texts) \
                    and isinstance(item.get("authorizes_deletion"), bool):
                out[item["id"]] = item
        return out

    def _batch(self, texts: list[str], role: str, advisory: bool = False) -> None:
        answers = self._ask(texts, role, "L1")
        redo = []
        for i, t in enumerate(texts):
            res, a = self.results[t], answers.get(i)
            if advisory:
                res.llm = a["authorizes_deletion"] if a else None
                res.source = "rules(suspicious)" if res.rules is not None else "default"
                res.notes.append("suspicious input: LLM advisory only")
                continue
            if a is None:
                redo.append(t)
                continue
            res.llm, res.request_type, res.language, res.reason = a["authorizes_deletion"], a["request_type"], a["language"], a["reason"]
            if res.rules is not None and res.rules != res.llm:
                redo.append(t)  # disagreement with the rules -> escalation model decides
            else:
                res.authorizes_deletion, res.source = res.llm, "llm"
        if redo:
            esc = self._ask(redo, "intent_escalation", "L1-escalation")
            for i, t in enumerate(redo):
                res, a = self.results[t], esc.get(i)
                res.escalated = True
                if a is not None:
                    res.authorizes_deletion, res.source = a["authorizes_deletion"], "cascade"
                    res.request_type, res.language, res.reason = a["request_type"], a["language"], a["reason"]
                    res.notes.append(f"escalated (rules={res.rules}, primary={res.llm}) -> {a['authorizes_deletion']}")
                elif res.rules is not None:
                    res.authorizes_deletion, res.source = res.rules, "rules"
                    res.notes.append("escalation failed: rules stand")

    def authorizes_deletion(self, text: str) -> bool:
        if text not in self.results:
            self.classify_all([text])
        return self.results[text].authorizes_deletion
