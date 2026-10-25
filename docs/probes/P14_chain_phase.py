"""P14 - Tier 3b candidate: deletion-run 'chains' by timing phase.
Observation (samples): for an event of a case's run, (t_event - t_anchor) mod 30 s is
9..11 for policy actions and 20..22 for final results / checks (39/39 true pairs),
while wrong anchor pairs spread uniformly over 0..29. Likely a generator cadence artifact.
Method: chain(anchor) = events in the same reported_at slot whose kind-specific phase matches.
Case <-> chain via validated identifier links on ANY chain member (or the anchor), then
constraint elimination (1 account per case, <=1 per type). Validated on samples.
Run from repo root.
"""
import collections, os
__file__ = os.path.join('docs', 'probes', 'P04_run_linkage.py')
src = open(__file__).read().rsplit("groups = collections.defaultdict(list)", 1)[0]
exec(src)
from datetime import timedelta
groups = collections.defaultdict(list)
for c in cases: groups[c['reported_at']].append(c)
RU = {}
def ru(a):
    if a not in RU: RU[a] = res_users(a)
    return RU[a]
def kind(a):
    if 'submitted primary profile' in a['details']: return 'anchor'
    if 'Policy action completed' in a['details']: return 'policy'
    return 'final'
PH = {'policy': range(8, 13), 'final': range(19, 24)}
stat = collections.Counter(); chk = collections.Counter()
for rep, G in groups.items():
    ev = run_events(rep); anchors = [a for a in ev if kind(a) == 'anchor']; others = [a for a in ev if kind(a) != 'anchor']
    chains = {a['resource_id']: [a['resource_id']] for a in anchors}
    for e in others:
        m = [a for a in anchors if T(a['event_time']) <= T(e['event_time']) and
             int((T(e['event_time']) - T(a['event_time'])).total_seconds()) % 30 in PH.get(kind(e), ())]
        stat['event_phase_matches_%d' % min(len(m), 2)] += 1
        if len(m) == 1: chains[m[0]['resource_id']].append(e['resource_id'])
    # chain -> case by identifier links on any member
    owner = {}
    for anc, members in chains.items():
        hits = {c['case_id'] for c in G for r in members if c['uid'] in ru(c['audit_at']).get(r, set())}
        if len(hits) == 1: owner[anc] = hits.pop()
    # elimination: one chain (account) per case
    changed = True
    while changed:
        changed = False
        free_c = [c['case_id'] for c in G if c['case_id'] not in owner.values()]
        free_a = [a for a in chains if a not in owner]
        if len(free_c) == 1 and len(free_a) == 1: owner[free_a[0]] = free_c[0]; changed = True
    for c in G:
        mine = [a for a, cc in owner.items() if cc == c['case_id']]
        stat[(c['set'], 'case_has_chain' if mine else 'case_no_chain')] += 1
        if c['set'] == 'sample' and mine:
            truth = {s['resource_id'] for s in sout[c['case_id']] if s['system_id'] != 'security_service'}
            got = set(chains[mine[0]])
            chk['truth'] += len(truth); chk['found'] += len(truth & got); chk['wrong'] += len(got - truth)
for k in sorted(stat, key=str): print(k, stat[k])
print('sample validation for cases with a chain:', dict(chk))
