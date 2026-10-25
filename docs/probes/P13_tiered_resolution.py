"""P13 - User's tiered resolution, simulated on the full dataset.
Tier 1 hard links   : run event linked to exactly one case of its reported_at slot by a validated identifier fact.
Tier 2 park         : everything else goes to an ambiguity table {event -> candidate cases}.
Tier 3 elimination  : constraint propagation to a fixpoint (sudoku style):
                      C1 each event belongs to exactly one case of its slot
                      C2 each case has exactly one account        (H-STP-02, 32/32)
                      C3 each case has at most one resource per type (32/32 samples)
                      -> naked singles (event with 1 candidate) and hidden singles
                         (case whose account can only be one event)
Tier 4 residual     : what would be handed to the LLM / tie-break.
Validated against sample answers. Run from repo root.
"""
import collections, os, re
__file__ = os.path.join('docs', 'probes', 'P04_run_linkage.py')
src = open(__file__).read()
src = src.rsplit("groups = collections.defaultdict(list)", 1)[0]
exec(src)

groups = collections.defaultdict(list)
for c in cases: groups[c['reported_at']].append(c)
rtype = lambda r: r.rsplit('_', 1)[0]
RU = {}
def ru(audit_at):
    if audit_at not in RU: RU[audit_at] = res_users(audit_at)
    return RU[audit_at]

tot = collections.Counter(); check = collections.Counter(); residual_examples = []
for rep, G in groups.items():
    ev = [a['resource_id'] for a in run_events(rep)]
    ev = list(dict.fromkeys(ev))
    cand = {}
    for rid in ev:
        linked = [c['case_id'] for c in G if c['uid'] in ru(c['audit_at']).get(rid, set())]
        cand[rid] = set(linked) if linked else {c['case_id'] for c in G}
        tot['tier1_hard' if len(linked) == 1 else ('single_case_slot' if len(G) == 1 else 'parked')] += 1
    assign = {r: next(iter(s)) for r, s in cand.items() if len(s) == 1}
    changed = True
    while changed:                                  # Tier 3: propagate to fixpoint
        changed = False
        for r, s in cand.items():                   # C3: remove cases whose type slot is taken
            if r in assign: continue
            taken = {assign[o] for o in assign if rtype(o) == rtype(r)}
            ns = s - taken
            if ns != s and ns: cand[r] = ns; changed = True
            if len(cand[r]) == 1: assign[r] = next(iter(cand[r])); changed = True; tot['tier3_elim'] += 1
        for c in G:                                 # C2: hidden single for accounts
            if any(rtype(r) == 'account' and assign.get(r) == c['case_id'] for r in assign): continue
            opts = [r for r in cand if rtype(r) == 'account' and r not in assign and c['case_id'] in cand[r]]
            if len(opts) == 1: assign[opts[0]] = c['case_id']; cand[opts[0]] = {c['case_id']}; changed = True; tot['tier3_elim'] += 1
    for r in cand:
        if r not in assign:
            tot[f'tier4_residual_{rtype(r)}'] += 1
            if len(residual_examples) < 6: residual_examples.append((rep, r, sorted(cand[r])))
    for c in G:
        if c['set'] == 'sample':
            truth = {s['resource_id'] for s in sout[c['case_id']] if s['system_id'] != 'security_service'}
            got = {r for r, cc in assign.items() if cc == c['case_id']}
            check['truth'] += len(truth); check['found'] += len(truth & got); check['wrong'] += len(got - truth)
    for c in G:
        if c['set'] == 'eval':
            got = {r for r, cc in assign.items() if cc == c['case_id']}
            tot['eval_cases_with_account'] += any(rtype(r) == 'account' for r in got)
for k in sorted(tot): print(f'{k:<32}{tot[k]}')
print('sample validation (non-audit resources):', dict(check))
print('residual examples:', residual_examples)
