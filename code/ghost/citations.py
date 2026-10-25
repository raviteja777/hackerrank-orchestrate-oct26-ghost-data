"""Evidence selection for findings and verifications (DESIGN §9).

Only file ids are cited (G-CIT-01) and only files captured at or before audit_at (S-TIM-01, inclusive H-TIM-03);
a file captured later may supply knowledge (D3) but is never cited. A finding cites the latest citable file
showing the violating state; a COMPLETE verification prefers the case's audit-capture file when it proves
the compliant state (G-EVD-06, G-CIT-02), and absence may be proven by a covering snapshot that does not list the
resource (G-EVD-01). Ties: latest captured_at, then the audit-capture file, then the lowest file_id (X-CIT-01).
Rule OQ-5: with no citable proof, fall back to the audit-capture file, else the latest citable file that mentions
the subject, and flag low confidence.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .facts import FactStore
from .state import Assessment

CAPTURE_WINDOW = timedelta(hours=24)  # G-EVD-06: median 16 min, p90 24 min before audit_at; 24 h is a safe bound


class Citer:
    def __init__(self, store: FactStore, file_times: dict[str, datetime]):
        self.store = store
        self.file_times = file_times

    def citable(self, file_id: str, audit_at: datetime) -> bool:
        t = self.file_times.get(file_id)
        return t is not None and t <= audit_at  # S-TIM-01, H-TIM-03

    def audit_capture(self, user_id: str | None, audit_at: datetime) -> str | None:
        """The evidence file captured shortly before audit_at that mentions the subject (G-EVD-06)."""
        if not user_id:
            return None
        files = {f.file_id for f in self.store.for_user(user_id)}
        cands = [(self.file_times[fid], fid) for fid in files
                 if fid in self.file_times and audit_at - CAPTURE_WINDOW <= self.file_times[fid] <= audit_at]
        return max(cands)[1] if cands else None

    def _pick(self, files: set[str], capture: str | None, prefer_capture: bool) -> str | None:
        if not files:
            return None
        if prefer_capture and capture in files:
            return capture
        # latest captured_at, then the audit-capture file, then the lowest file_id (X-CIT-01)
        return sorted(files, key=lambda fid: (-self.file_times[fid].timestamp(), fid != capture, fid))[0]

    def finding(self, a: Assessment, audit_at: datetime, capture: str | None) -> tuple[str, bool]:
        """-> (file_id, low_confidence)."""
        files = {o.fact.file_id for o in a.bad if self.citable(o.fact.file_id, audit_at) and o.cond == a.state}
        pick = self._pick(files, capture, prefer_capture=False)
        if pick:
            return pick, False
        return self._fallback(a, audit_at, capture)

    def verification(self, a: Assessment, audit_at: datetime, capture: str | None) -> tuple[str, bool]:
        """Proof of the compliant state for a COMPLETE case."""
        files = {o.fact.file_id for o in a.good if o.cond == a.state and self.citable(o.fact.file_id, audit_at)}
        if a.state == "ABSENT":
            files |= {s.file_id for s in a.scope_proofs if self.citable(s.file_id, audit_at)}
        pick = self._pick(files, capture, prefer_capture=True)
        if pick:
            return pick, False
        return self._fallback(a, audit_at, capture)

    def _fallback(self, a: Assessment, audit_at: datetime, capture: str | None) -> tuple[str, bool]:
        """OQ-5: no citable proof."""
        if capture:
            return capture, True
        mine = {f.file_id for f in self.store.for_resource(a.resource_id) if self.citable(f.file_id, audit_at)}
        pick = self._pick(mine, capture, prefer_capture=False)
        return (pick or "", True)
