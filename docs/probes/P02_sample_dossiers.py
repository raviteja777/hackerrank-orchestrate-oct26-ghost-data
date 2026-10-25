"""P02 - Build a per-case evidence dossier for every sample case.

For each sample case:
  * resolve the identifier set (current + historical email, email_hash, phone, user_id)
  * list answer steps
  * for every text evidence file: lines that mention any identifier OR any answer resource_id
    (flagged [<=audit] or [>audit] by captured_at), plus whether the file was cited
  * system_activity rows touching answer resource ids or mentioning identifiers
Output: docs/probes/out/P02_<case_id>.txt  (+ P02_index.txt)
Run from repo root:  python docs/probes/P02_sample_dossiers.py
"""
import csv, json, os, re, collections
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DS = os.path.join(ROOT, 'dataset'); OUT = os.path.join(ROOT, 'docs', 'probes', 'out')
os.makedirs(OUT, exist_ok=True)
rd = lambda f: list(csv.DictReader(open(os.path.join(DS, f), encoding='utf-8')))
req = rd('sample_deletion_requests.csv'); sout = {r['case_id']: r for r in rd('sample_output.csv')}
ui = {r['user_id']: r for r in rd('user_identities.csv')}; audit = rd('user_audit_log.csv')
act = rd('system_activity.csv'); ef = rd('evidence_files.csv')

owner = {}
for a in audit:
    if a['field_name'] == 'email': owner[a['old_value'].lower()] = a['user_id']
for u in ui.values(): owner[u['email'].lower()] = u['user_id']
def idset(uid):
    u = ui[uid]; s = {u['email'].lower(), u['email_hash'], u['phone'], uid}
    for a in audit:
        if a['user_id'] == uid: s |= {a['old_value'].lower(), a['new_value'].lower()}
    return s

TEXT = {}
for f in ef:
    if f['file_path'].rsplit('.', 1)[-1] in ('sql', 'log', 'json', 'txt'):
        TEXT[f['file_id']] = open(os.path.join(DS, f['file_path']), encoding='utf-8').read().splitlines()
CAP = {f['file_id']: f['captured_at'] for f in ef}; PATH = {f['file_id']: f['file_path'] for f in ef}

def hit(line, keys):
    l = line.lower()
    return [k for k in keys if (re.search(r'\b' + re.escape(k) + r'\b', l) if re.match(r'^(user|[a-z_]+)_\d+$', k) else k in l)]

idx = []
for r in req:
    cid = r['case_id']; uid = owner[r['email'].strip().lower()]; ids = idset(uid)
    steps = json.loads(sout[cid]['steps_json']); res = {s['resource_id'] for s in steps}
    cited = {s['evidence_id'] for s in steps if s['evidence_id']}
    keys = {k.lower() for k in ids | res}
    L = [f"=== {cid}  user={uid}  status={sout[cid]['deletion_status']}  reported={r['reported_status']}",
         f"requested={r['requested_at']} reported={r['reported_at']} audit={r['audit_at']}",
         f"text: {r['request_text']}", f"identifiers: {sorted(ids)}", "", "--- ANSWER STEPS"]
    for s in steps:
        L.append(f"  {s['step_no']:>2} {s['phase']:<12} {s['operation']:<26} {s['system_id']:<20} {s['resource_id']:<18} {s['evidence_id']}")
    L += ["", "--- EVIDENCE HITS (file_id captured_at [cut] cited? path)"]
    nfiles = 0
    for fid, lines in sorted(TEXT.items(), key=lambda x: CAP[x[0]]):
        hits = [(i, ln, hit(ln, keys)) for i, ln in enumerate(lines)]
        hits = [h for h in hits if h[2]]
        if not hits: continue
        nfiles += 1
        tag = '<=audit' if CAP[fid] <= r['audit_at'] else '>AUDIT'
        L.append(f"[{fid}] {CAP[fid]} [{tag}] {'CITED' if fid in cited else ''} {PATH[fid]}")
        for i, ln, k in hits[:25]:
            L.append(f"    L{i+1}: {ln.strip()[:260]}   <- {k}")
        if len(hits) > 25: L.append(f"    ... {len(hits)-25} more")
    for fid in cited:
        if fid not in TEXT: L.append(f"[{fid}] {CAP[fid]} CITED (binary) {PATH[fid]}")
    L += ["", "--- ACTIVITY (resource in answer, or identifier in details)"]
    for a in sorted(act, key=lambda a: a['event_time']):
        k = hit(a['details'], keys) if a['resource_id'] not in res else [a['resource_id']]
        if a['resource_id'] in res or k:
            tag = '<=audit' if a['event_time'] <= r['audit_at'] else '>AUDIT'
            L.append(f"  {a['activity_id']:<14} {a['event_time']} [{tag}] {a['event_type']:<22} {a['source_system']}->{a['target_system']} {a['resource_id']} {a['reported_result']} | {a['details']}")
    open(os.path.join(OUT, f'P02_{cid}.txt'), 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')
    idx.append(f"{cid} {uid} {sout[cid]['deletion_status']:<10} steps={len(steps):>2} files_hit={nfiles} cited={sorted(cited)}")
open(os.path.join(OUT, 'P02_index.txt'), 'w', encoding='utf-8', newline='\n').write('\n'.join(idx) + '\n')
print('\n'.join(idx))
