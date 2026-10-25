"""Identity sets and the two-stage identifier matcher (DESIGN §8.1).

Rules: H-IDN-02 (email_hash = sha256(lowercase email)), H-IDN-03 (an email belongs to one user),
H-IDN-04 (stage 1 loose recall, stage 2 mandatory exact validation against the full identity set;
decoys are logged, names never link), S-IDN-01 (request email may be current or historical),
X-IDN-01 resolved (phones link only after exact normalised validation; names never link).

Stage 1 (recall): a token is a candidate when it contains the local part of a known email
(emails), a 64-hex run (hashes), a digit run containing the last 8 digits of a known phone
(phones) or matches user_<n> (user references).
Stage 2 (validation): the full token is compared with the identity set. Outcomes
EXACT | SAME_USER_OTHER_ID | OTHER_USER | UNKNOWN_DECOY; only the first two link (`links`).
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from .loaders import AuditEvent, UserIdentity

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
HASH_RE = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])")
PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{6,}\d")
USER_RE = re.compile(r"\buser_\d+\b", re.IGNORECASE)
PHONE_TAIL = 8  # stage-1 recall key for phones
MIN_PHONE_DIGITS = 8


class Outcome(str, Enum):
    EXACT = "EXACT"
    SAME_USER_OTHER_ID = "SAME_USER_OTHER_ID"
    OTHER_USER = "OTHER_USER"
    UNKNOWN_DECOY = "UNKNOWN_DECOY"


LINKING = (Outcome.EXACT, Outcome.SAME_USER_OTHER_ID)


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    return re.sub(r"\D", "", value)


def email_hash(email: str) -> str:
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()  # H-IDN-02


@dataclass(frozen=True)
class Match:
    """One validated-or-rejected candidate: a token occurrence paired with the identifier that recalled it."""

    kind: str  # email | email_hash | phone | user_id
    token: str  # normalised token as found in the text
    outcome: Outcome
    searched: str  # identifier whose stage-1 search recalled the token
    searched_users: frozenset[str]
    token_users: frozenset[str]  # owners of the token (empty for decoys)
    source_ref: str = ""
    start: int = 0
    end: int = 0

    @property
    def links(self) -> bool:
        return self.outcome in LINKING


@dataclass
class IdentitySet:
    user_id: str
    name: str = ""  # reference only: names never link (H-IDN-04)
    emails: set[str] = field(default_factory=set)  # current + historical, lowercased
    hashes: set[str] = field(default_factory=set)
    phones: set[str] = field(default_factory=set)  # digits only


@dataclass(frozen=True)
class IdentifierRecord:
    """History row for the edge log (`has_identifier`, DESIGN §4.2)."""

    user_id: str
    kind: str
    value: str
    t: datetime
    historical: bool


class IdentityIndex:
    def __init__(self, identities: list[UserIdentity], audit_log: list[AuditEvent]):
        self.sets: dict[str, IdentitySet] = {}
        self.records: list[IdentifierRecord] = []
        for u in identities:
            s = self.sets.setdefault(u.user_id, IdentitySet(u.user_id, u.name))
            self._add(s, "email", u.email, u.updated_at, historical=False)
            self._add(s, "email_hash", u.email_hash, u.updated_at, historical=False)
            self._add(s, "phone", u.phone, u.updated_at, historical=False)
        for e in sorted(audit_log, key=lambda a: (a.event_time, a.audit_id)):
            s = self.sets.setdefault(e.user_id, IdentitySet(e.user_id))
            if e.field_name in ("email", "email_hash", "phone"):
                self._add(s, e.field_name, e.old_value, e.event_time, historical=True)
                self._add(s, e.field_name, e.new_value, e.event_time, historical=False)
        self._build_lookup()

    @classmethod
    def from_dataset(cls, dataset_dir: Path | None = None) -> "IdentityIndex":
        from . import loaders

        return cls(loaders.load_identities(dataset_dir), loaders.load_audit_log(dataset_dir))

    # ---- construction -------------------------------------------------
    def _add(self, s: IdentitySet, kind: str, value: str, t: datetime, historical: bool) -> None:
        if not value or not value.strip():
            return
        if kind == "email":
            v = normalize_email(value)
            s.emails.add(v)
            s.hashes.add(email_hash(v))  # H-IDN-02: hash of every email, current or historical
        elif kind == "email_hash":
            v = value.strip().lower()
            s.hashes.add(v)
        else:
            v = normalize_phone(value)
            if len(v) < MIN_PHONE_DIGITS:
                return
            s.phones.add(v)
        self.records.append(IdentifierRecord(s.user_id, kind, v, t, historical))

    def _build_lookup(self) -> None:
        self.email_owner: dict[str, set[str]] = defaultdict(set)
        self.hash_owner: dict[str, set[str]] = defaultdict(set)
        self.phone_owner: dict[str, set[str]] = defaultdict(set)
        for uid, s in self.sets.items():
            for e in s.emails:
                self.email_owner[e].add(uid)
            for h in s.hashes:
                self.hash_owner[h].add(uid)
            for p in s.phones:
                self.phone_owner[p].add(uid)
        # stage-1 recall indexes
        self._by_local: dict[str, list[str]] = defaultdict(list)
        for e in sorted(self.email_owner):
            self._by_local[e.split("@", 1)[0]].append(e)
        self._locals = sorted(self._by_local)
        self._phone_tails: dict[str, list[str]] = defaultdict(list)
        for p in sorted(self.phone_owner):
            self._phone_tails[p[-PHONE_TAIL:]].append(p)
        self._email_cache: dict[str, list[tuple[str, Outcome]]] = {}

    # ---- request resolution -------------------------------------------
    def user_for_email(self, email: str) -> str | None:
        """Exact, case-insensitive, trimmed lookup over current and historical emails (S-IDN-01, H-IDN-04)."""
        owners = self.email_owner.get(normalize_email(email))
        if not owners:
            return None
        return sorted(owners)[0]  # H-IDN-03: exactly one owner in the dataset

    def users_for_email(self, email: str) -> frozenset[str]:
        return frozenset(self.email_owner.get(normalize_email(email), ()))

    # ---- stage 1 + 2 ---------------------------------------------------
    def _classify_email(self, token: str) -> list[tuple[str, Outcome]]:
        hit = self._email_cache.get(token)
        if hit is not None:
            return hit
        owners = self.email_owner.get(token, set())
        out: list[tuple[str, Outcome]] = []
        for lp in self._locals:  # stage 1: loose substring recall on local parts
            if lp not in token:
                continue
            for searched in self._by_local[lp]:  # stage 2: exact validation of the full token
                if searched == token:
                    out.append((searched, Outcome.EXACT))
                elif owners and owners & self.email_owner[searched]:
                    out.append((searched, Outcome.SAME_USER_OTHER_ID))
                elif owners:
                    out.append((searched, Outcome.OTHER_USER))
                else:
                    out.append((searched, Outcome.UNKNOWN_DECOY))
        self._email_cache[token] = out
        return out

    def scan(self, text: str, source_ref: str = "") -> list[Match]:
        """All stage-1 candidates in `text`, each classified by stage 2 (H-IDN-04)."""
        matches: list[Match] = []
        for m in EMAIL_RE.finditer(text):
            token = m.group(0).lower()
            for searched, outcome in self._classify_email(token):
                matches.append(Match(
                    "email", token, outcome, searched,
                    frozenset(self.email_owner[searched]), frozenset(self.email_owner.get(token, ())),
                    source_ref, m.start(), m.end()))
        for m in HASH_RE.finditer(text):
            token = m.group(0).lower()
            owners = frozenset(self.hash_owner.get(token, ()))
            matches.append(Match("email_hash", token, Outcome.EXACT if owners else Outcome.UNKNOWN_DECOY,
                                 token, owners, owners, source_ref, m.start(), m.end()))
        for m in PHONE_RE.finditer(text):
            digits = normalize_phone(m.group(0))
            owners = frozenset(self.phone_owner.get(digits, ()))
            if owners:
                matches.append(Match("phone", digits, Outcome.EXACT, digits, owners, owners, source_ref, m.start(), m.end()))
                continue
            near = [p for i in range(len(digits) - PHONE_TAIL + 1) for p in self._phone_tails.get(digits[i:i + PHONE_TAIL], ())]
            if near:  # recalled by the tail, rejected by exact validation
                p = sorted(near)[0]
                matches.append(Match("phone", digits, Outcome.UNKNOWN_DECOY, p, frozenset(self.phone_owner[p]),
                                     frozenset(), source_ref, m.start(), m.end()))
        for m in USER_RE.finditer(text):
            token = m.group(0).lower()
            known = token in self.sets
            owners = frozenset({token}) if known else frozenset()
            matches.append(Match("user_id", token, Outcome.EXACT if known else Outcome.UNKNOWN_DECOY,
                                 token, owners, owners, source_ref, m.start(), m.end()))
        matches.sort(key=lambda x: (x.start, x.kind, x.searched))
        return matches


def links(matches: list[Match]) -> set[tuple[str, str, str]]:
    """(user_id, kind, token) mentions that may create edges: EXACT or SAME_USER_OTHER_ID only (H-IDN-04)."""
    return {(u, m.kind, m.token) for m in matches if m.links for u in m.token_users}


def decoys(matches: list[Match]) -> list[Match]:
    """Rejected candidates: unknown decoys and other-user look-alikes (decoy log, DESIGN §8.1)."""
    return [m for m in matches if not m.links]


def write_decoy_log(matches: list[Match], path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        for m in decoys(matches):
            fh.write(json.dumps({
                "source_ref": m.source_ref, "kind": m.kind, "token": m.token, "outcome": m.outcome.value,
                "searched": m.searched, "searched_users": sorted(m.searched_users),
            }, ensure_ascii=False, sort_keys=True) + "\n")
