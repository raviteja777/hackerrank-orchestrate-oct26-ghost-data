"""Deletion runs: slots, windows and phase chains (DESIGN §8.2; port of docs/probes/P04 and P14).

A slot is a `reported_at` value; the sample and eval cases that share it share one activity stream. A run
event (source deletion_worker) belongs to the slots whose kind-specific window around `reported_at` contains
it (G-LNK-01, P10). Chains (W-LNK-05, tier 3b): a follow-up event joins an anchor when
(t_event - t_anchor) mod 30 s falls in the kind's phase band; a single match makes it a chain member.
Rules: G-LNK-01, W-LNK-05 (probable generator artifact, switchable), H-STP-02.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from .loaders import Activity

ANCHOR, POLICY, FINAL, SCENARIO = "anchor", "policy", "final", "scenario"

# Minutes relative to reported_at (DESIGN §8.2, P10): anchor -80..-40, policy -35..0, final/check +30..+125,
# scenario style (other deletion_worker messages) -10..+15.
WINDOWS: dict[str, tuple[float, float]] = {
    ANCHOR: (-80.0, -40.0), POLICY: (-35.0, 0.0), FINAL: (30.0, 125.0), SCENARIO: (-10.0, 15.0),
}
SOURCE = "deletion_worker"


def classify(details: str) -> str:
    d = details.lower()
    if "submitted primary profile" in d:
        return ANCHOR
    if "policy action completed" in d:
        return POLICY
    if "target resource:" in d:
        return SCENARIO
    return FINAL  # final results and checks


@dataclass(frozen=True)
class RunEvent:
    activity_id: str
    t: datetime
    resource_id: str
    kind: str
    result: str  # a claim (H-STA-02)
    event_type: str


def run_events(activity: list[Activity]) -> list[RunEvent]:
    return [RunEvent(a.activity_id, a.event_time, a.resource_id, classify(a.details), a.reported_result, a.event_type)
            for a in activity if a.source_system == SOURCE]


def in_window(ev: RunEvent, reported_at: datetime) -> bool:
    lo, hi = WINDOWS[ev.kind]
    minutes = (ev.t - reported_at).total_seconds() / 60.0
    return lo <= minutes <= hi


class RunIndex:
    def __init__(self, events: list[RunEvent], slots: dict[datetime, list[str]],
                 policy_band: tuple[int, int] = (9, 11), final_band: tuple[int, int] = (20, 22)):
        self.events = sorted(events, key=lambda e: (e.t, e.activity_id))
        self.slots = {k: sorted(v) for k, v in slots.items()}  # reported_at -> case_ids (sample + eval together)
        self.bands = {POLICY: policy_band, FINAL: final_band}
        self.by_slot: dict[datetime, list[RunEvent]] = {s: [e for e in self.events if in_window(e, s)] for s in self.slots}
        self._slots_of: dict[str, list[datetime]] = defaultdict(list)
        for s, evs in self.by_slot.items():
            for e in evs:
                self._slots_of[e.activity_id].append(s)

    def slots_of(self, ev: RunEvent) -> list[datetime]:
        return sorted(self._slots_of.get(ev.activity_id, []))

    def candidate_cases(self, ev: RunEvent) -> set[str]:
        return {c for s in self.slots_of(ev) for c in self.slots[s]}

    def resources(self) -> set[str]:
        return {e.resource_id for e in self.events}

    # ---- chains (tier 3b) ---------------------------------------------------------------------------
    def chains(self, slot: datetime) -> tuple[dict[str, list[str]], list[RunEvent]]:
        """-> ({anchor resource: [member resources incl. the anchor]}, parked follow-ups) for one slot (P14)."""
        evs = self.by_slot.get(slot, [])
        anchors = [e for e in evs if e.kind == ANCHOR]
        chains: dict[str, list[str]] = {a.resource_id: [a.resource_id] for a in anchors}
        parked: list[RunEvent] = []
        for e in evs:
            if e.kind not in self.bands:
                continue
            lo, hi = self.bands[e.kind]
            match = [a for a in anchors if a.t <= e.t and lo <= int((e.t - a.t).total_seconds()) % 30 <= hi]
            if len(match) == 1:
                members = chains[match[0].resource_id]
                if e.resource_id not in members:
                    members.append(e.resource_id)
            else:
                parked.append(e)
        return chains, parked
