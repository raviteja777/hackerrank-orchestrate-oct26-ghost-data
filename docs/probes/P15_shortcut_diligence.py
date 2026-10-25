"""P15: due diligence on the "no case-family shortcuts" rule for tier 3b and tier 5 (2026-10-25, planning chat).
Run from code/:  python ../docs/probes/P15_shortcut_diligence.py
Part 1: 3b phase law out of sample (eval-only single-anchor slots, no labels needed).
Part 2: does case-number order carry information about anchor order? (tier 5 must be a pure tie-break)
Part 3: does tier 5 change any status? (run separately: /tmp/abl5.py logic, result 0/518)
Results: policy 23/23 in band; final 72/133 own + 61/61 in band for a neighbouring slot anchor (0 unexplained);
multi-anchor slots unique match policy 143/193, final 383/640; 120/460 anchor pairs phase-collide (parked);
case-number order == anchor order on 88/186 high-confidence pairs (47%, no signal); sample truth 9/13;
tier 5 off changes 0/518 statuses."""
import sys, collections
sys.path.insert(0,'.')
from ghost import loaders
from ghost.runs import run_events, RunIndex, ANCHOR, POLICY, FINAL
reqs=loaders.load_requests(); samp=loaders.load_requests(None,"sample_deletion_requests.csv")
eval_ids={r.case_id for r in reqs}
slots=collections.defaultdict(list)
for r in reqs+samp: slots[loaders.parse_ts(r.reported_at) if isinstance(r.reported_at,str) else r.reported_at].append(r.case_id)
ri=RunIndex(run_events(loaders.load_activity()), dict(slots))
def ph(e,a): return int((e.t-a.t).total_seconds())%30
single=collections.Counter(); singleN=collections.Counter(); hist=collections.defaultdict(collections.Counter)
multi_unique=collections.Counter(); multi_tot=collections.Counter(); wrong_hit=collections.Counter(); wrong_tot=collections.Counter()
for s,cases in ri.slots.items():
    evs=ri.by_slot[s]; anchors=[e for e in evs if e.kind==ANCHOR]
    eval_only=all(c in eval_ids for c in cases)
    if not eval_only: continue
    for e in evs:
        if e.kind not in (POLICY,FINAL): continue
        lo,hi={POLICY:(9,11),FINAL:(20,22)}[e.kind]
        prior=[a for a in anchors if a.t<=e.t]
        if len(cases)==1 and len(anchors)==1:
            p=ph(e,anchors[0]); hist[e.kind][p]+=1; singleN[e.kind]+=1; single[e.kind]+= lo<=p<=hi
        elif len(anchors)>1:
            m=[a for a in prior if lo<=ph(e,a)<=hi]; multi_tot[e.kind]+=1; multi_unique[e.kind]+= len(m)==1
print("eval-only single-anchor slots: in-band fraction", {k:f"{single[k]}/{singleN[k]}" for k in singleN})
for k in hist: print(k, "off-band phases:", {p:c for p,c in sorted(hist[k].items()) if not ({POLICY:(9,11),FINAL:(20,22)}[k][0]<=p<={POLICY:(9,11),FINAL:(20,22)}[k][1])})
print("eval-only multi-anchor slots: events with exactly one in-band anchor", {k:f"{multi_unique[k]}/{multi_tot[k]}" for k in multi_tot})
# anchor phase collisions: pairs of anchors in same slot whose offset mod 30 lets bands overlap
coll=tot=0
for s,cases in ri.slots.items():
    a=[e for e in ri.by_slot[s] if e.kind==ANCHOR]
    for i in range(len(a)):
        for j in range(i+1,len(a)):
            tot+=1; d=int(abs((a[i].t-a[j].t).total_seconds()))%30; coll+= d<=2 or d>=28
print("anchor pairs sharing a slot:",tot,"phase-colliding (|d| mod 30 <=2):",coll)
print("---- off-band finals in single-anchor eval slots")
own=other=none=0; kinds=collections.Counter()
for s,cases in ri.slots.items():
    evs=ri.by_slot[s]; anchors=[e for e in evs if e.kind==ANCHOR]
    if not(len(cases)==1 and len(anchors)==1 and cases[0] in eval_ids): continue
    for e in evs:
        if e.kind!=FINAL: continue
        if 20<=ph(e,anchors[0])<=22: continue
        alt=[a for s2 in ri.slots_of(e) if s2!=s for a in ri.by_slot[s2] if a.kind==ANCHOR and a.t<=e.t and 20<=ph(e,a)<=22]
        if alt: other+=1
        else: none+=1; kinds[(e.event_type, e.resource_id.split('_')[0])]+=1
print("fits another slot's anchor:",other," fits no anchor:",none)
print(kinds.most_common(10))

# ---- Part 2
from ghost import config, pipeline, loaders
import json, csv
from ghost.resolve import LOW_CONFIDENCE_TIERS
ctx=pipeline.build_context()
res=ctx.resolution; runs=ctx.runs
acct={}
for cid,m in res.assignments.items():
    for r,a in m.items():
        if r.startswith("account_"): acct[cid]=(r,a.tier)
num=lambda c:int(c.split('_')[1])
# evidence-only (non low-confidence) slots with >=2 resolved cases: does case-number order equal anchor-time order?
agree=pairs=0
# also sample-truth backtest
exp={}
for row in csv.DictReader(open(config.DATASET_DIR/'sample_output.csv',encoding='utf-8')):
    for s in json.loads(row['steps_json']):
        if str(s.get('resource_id','')).startswith('account_'): exp[row['case_id']]=s['resource_id']
sagree=spairs=0
for slot,cases in runs.slots.items():
    at={e.resource_id:e.t for e in runs.by_slot[slot] if e.kind==ANCHOR}
    strong=[c for c in cases if c in acct and acct[c][1] not in LOW_CONFIDENCE_TIERS and acct[c][0] in at]
    for i in range(len(strong)):
        for j in range(i+1,len(strong)):
            a,b=strong[i],strong[j]; pairs+=1
            agree+= (num(a)<num(b))==(at[acct[a][0]]<at[acct[b][0]])
    st=[c for c in cases if c in exp and exp[c] in at]
    for i in range(len(st)):
        for j in range(i+1,len(st)):
            a,b=st[i],st[j]; spairs+=1; sagree+=(num(a)<num(b))==(at[exp[a]]<at[exp[b]])
print("high-confidence pairs in shared slots: case-number order == anchor-time order:",agree,"/",pairs)
print("sample truth pairs:",sagree,"/",spairs)
