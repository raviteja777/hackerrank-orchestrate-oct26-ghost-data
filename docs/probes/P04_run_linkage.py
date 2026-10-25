"""P04 - How ambiguous are deletion runs when cases share reported_at?

1. Fact index from all TEXT evidence (json/sql/log/txt + pdftotext of PDFs):
   each fact = (resource_ids, identifiers, file_id, fact_time) at record granularity:
   JSON object holding a resource_id, SQL row, log trace_id group, TXT line, PDF file.
2. identifier -> user_id via user_identities + user_audit_log (emails, hashes, phones, user_id).
3. resource -> set(users) from facts whose fact_time <= the case's audit_at (decision D3).
4. Runs: deletion_worker events grouped by the reported_at they sit around
   (anchor 'submitted primary profile' in [-80,-40] min; policy actions in [-35,0];
    failures/checks in [+30,+125]).  Groups = cases sharing reported_at.
5. For each group: resources linked to exactly one case of the group (direct), then
   elimination (one unassigned account and one unassigned case left -> assign).
Validated on samples against sample_output.  Run from repo root.
"""
import csv, json, os, re, subprocess, collections
from datetime import datetime, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DS = os.path.join(ROOT, 'dataset')
rd = lambda f: list(csv.DictReader(open(os.path.join(DS, f), encoding='utf-8')))
T = lambda s: datetime.fromisoformat(s.replace('Z', '+00:00'))
ui, audit, act, ef = rd('user_identities.csv'), rd('user_audit_log.csv'), rd('system_activity.csv'), rd('evidence_files.csv')
cases = [dict(r, set='sample') for r in rd('sample_deletion_requests.csv')] + [dict(r, set='eval') for r in rd('deletion_requests.csv')]
sout = {r['case_id']: json.loads(r['steps_json']) for r in rd('sample_output.csv')}

digits = lambda p: re.sub(r'\D', '', p)
ID2U = {}
for u in ui:
    ID2U[u['email'].lower()] = u['user_id']; ID2U[u['email_hash']] = u['user_id']; ID2U[digits(u['phone'])] = u['user_id']; ID2U[u['user_id']] = u['user_id']
for a in audit:
    v = a['old_value']; ID2U[(digits(v) if a['field_name'] == 'phone' else v.lower())] = a['user_id']
EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+'); HASH = re.compile(r'\b[0-9a-f]{64}\b'); UID = re.compile(r'\buser_\d+\b')
PHONE = re.compile(r'\+\d[\d ()\-]{7,}\d'); RES = re.compile(r'\b(?:account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|cache|email_delivery|legal_hold|marketing|object)_\d+\b')
def users_in(text):
    t = text.lower(); out = set()
    for e in EMAIL.findall(t):
        if e in ID2U: out.add(ID2U[e])
    for x in HASH.findall(t) + UID.findall(t):
        if x in ID2U: out.add(ID2U[x])
    for p in PHONE.findall(text):
        if digits(p) in ID2U: out.add(ID2U[digits(p)])
    return out
TS = re.compile(r'20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ')

facts = []   # (resources, users, file_id, fact_time)
def add(text, fid, t):
    r = set(RES.findall(text)); u = users_in(text)
    if r and u: facts.append((r, u, fid, t))
for f in ef:
    path = os.path.join(DS, f['file_path']); ext = path.rsplit('.', 1)[-1]; cap = f['captured_at']
    if ext == 'json':
        d = json.load(open(path, encoding='utf-8'))
        def walk(o, t):
            if isinstance(o, dict):
                t = o.get('captured_at') or o.get('observed_at') or t
                if 'resource_id' in o: add(json.dumps(o), f['file_id'], t)
                for v in o.values(): walk(v, t)
            elif isinstance(o, list):
                for v in o: walk(v, t)
        walk(d, cap)
    elif ext == 'sql':
        for line in open(path, encoding='utf-8'):
            if line.startswith('INSERT'):
                ts = TS.findall(line); add(line, f['file_id'], max(ts) if ts else cap)
    elif ext == 'log':
        groups = collections.defaultdict(list)
        for line in open(path, encoding='utf-8'):
            m = re.search(r'trace_id"?[=:]"?([\w-]+)', line); groups[m.group(1) if m else id(line)].append(line)
        for g in groups.values():
            ts = [TS.match(l).group(0) for l in g if TS.match(l)]; add(' '.join(g), f['file_id'], max(ts) if ts else cap)
    elif ext == 'txt':
        for line in open(path, encoding='utf-8'):
            ts = TS.findall(line); add(line, f['file_id'], ts[0] if ts else cap)
    elif ext == 'pdf':
        txt = subprocess.run(['pdftotext', '-layout', path, '-'], capture_output=True, text=True).stdout
        add(txt, f['file_id'], cap)
for a in act:   # data-catalog LINK events are explicit links
    if a['event_type'] == 'LINK_RESOURCE_IDENTITY': add(a['details'] + ' ' + a['resource_id'], a['activity_id'], a['event_time'])

def res_users(audit_at):
    m = collections.defaultdict(set)
    for r, u, fid, t in facts:
        if t <= audit_at:
            for x in r: m[x] |= u
    return m

owner = {}
for a in audit:
    if a['field_name'] == 'email': owner[a['old_value'].lower()] = a['user_id']
for u in ui: owner[u['email'].lower()] = u['user_id']
for c in cases: c['uid'] = owner[c['email'].strip().lower()]

DW = [a for a in act if a['source_system'] == 'deletion_worker']
def run_events(rep):
    R = T(rep); out = []
    for a in DW:
        d = (T(a['event_time']) - R).total_seconds() / 60
        anchor = 'submitted primary profile' in a['details']
        if (anchor and -80 <= d <= -40) or (not anchor and (-35 <= d <= 0 or 30 <= d <= 125)): out.append(a)
    return out

groups = collections.defaultdict(list)
for c in cases: groups[('all', c['reported_at'])].append(c)   # sample+eval share one activity stream
REPS = sorted({c['reported_at'] for c in cases})
def in_win(a, rep):
    d = (T(a['event_time']) - T(rep)).total_seconds() / 60; anchor = 'submitted primary profile' in a['details']
    return (anchor and -80 <= d <= -40) or (not anchor and (-35 <= d <= 0 or 30 <= d <= 125))
NWIN = {a['activity_id']: sum(in_win(a, r) for r in REPS) for a in DW}
stats = collections.Counter(); sample_check = collections.Counter()
for (_, rep), G in groups.items():
    ev = run_events(rep); k = len(G); st = 'eval' if all(c['set'] == 'eval' for c in G) else 'sample+'
    for c in G: c['assigned'] = set()
    acc_unassigned = []
    for a in ev:
        rid = a['resource_id']; cands = []
        for c in G:
            if c['uid'] in res_users(c['audit_at']).get(rid, set()): cands.append(c)
        is_acc = rid.startswith('account_')
        if len(cands) == 1: cands[0]['assigned'].add(rid); stats[(st, k, 'direct', is_acc)] += 1
        elif len(cands) > 1: stats[(st, k, 'multi-link', is_acc)] += 1; acc_unassigned.append((rid, is_acc))
        elif k == 1 and NWIN[a['activity_id']] == 1: G[0]['assigned'].add(rid); stats[(st, k, 'single-case', is_acc)] += 1
        elif k == 1: stats[(st, k, 'overlap-win', is_acc)] += 1
        else: stats[(st, k, 'ambiguous', is_acc)] += 1; acc_unassigned.append((rid, is_acc))
    # elimination on accounts: each case has exactly one account
    free = [c for c in G if not any(r.startswith('account_') for r in c['assigned'])]
    ua = [r for r, isacc in acc_unassigned if isacc]
    if len(free) == 1 and len(ua) == 1:
        free[0]['assigned'].add(ua[0]); stats[(st, k, 'elim', True)] += 1; stats[(st, k, 'ambiguous', True)] -= 1
    for c in G:
        if c['set'] == 'sample':
                truth = {s['resource_id'] for s in sout[c['case_id']] if s['system_id'] != 'security_service'}
                sample_check['truth'] += len(truth); sample_check['found'] += len(truth & c['assigned']); sample_check['wrong'] += len(c['assigned'] - truth)

print('group sizes:', collections.Counter(len(G) for G in groups.values()))
print(f"{'set':<7}{'k':>2} {'how':<12}{'account?':<9}{'n':>5}")
for key in sorted(stats): print(f"{key[0]:<7}{key[1]:>2} {key[2]:<12}{str(key[3]):<9}{stats[key]:>5}")
print('sample validation (non-audit resources):', dict(sample_check))
for st in ('sample', 'eval'):
    C = [c for c in cases if c['set'] == st]
    print(st, 'cases with an account assigned:', sum(any(r.startswith('account_') for r in c['assigned']) for c in C), '/', len(C),
          '| mean resources assigned per case:', round(sum(len(c['assigned']) for c in C) / len(C), 2))
