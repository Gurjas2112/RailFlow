"""Runs every demo scenario through the reference model and prints a markdown report."""
import sys, time, copy, pathlib
sys.path.insert(0,str(pathlib.Path(__file__).parent)); from rf_reference import *
def row(name,rev,st,ap,dis,now,A=None,w=None):
    v=validate(TT,dis,rev,ap,now) if rev else ["no solution"]; mt=metrics(TT,ap,rev) if rev else {}
    return f"| {name} | {'VALID' if not v else 'NOT VALID ('+str(len(v))+')'} | {recovery(rev)} | {mt.get('platform_changes','-')} | {mt.get('total_hold_min','-')} | {mt.get('weighted_delay','-')} | {st[-1][0] if st and isinstance(st[-1],tuple) else st} |"
out=["# Reference run (generated)","","Produced by `reference/run_reference.py` on the shipped data. Every number below is computed, not typed. Deterministic: seed 42, no timings (measure speed with bench.py on the laptop).",""]
TT=load("timetable_normal.json"); CF=load("timetable_conflicts.json")
out+=["## S3 — timetable as scheduled","","| Rule | PF | Trains | Stay overlap | Clearance shortfall | Reserved overlap |","|---|---|---|---|---|---|"]
for c in validate(CF,{},applied_from(CF)): out.append(f"| {c[0]} | {c[2]} | {' ↔ '.join(c[1])} | {c[3]['stay_overlap_min']} | {c[3]['clearance_shortfall_min'] if c[3]['clearance_shortfall_min'] is not None else '—'} | {c[3]['reserved_overlap_min']} |")
out+=["",f"Conflict-free sheet: {len(validate(TT,{},applied_from(TT)))} conflicts.",""]
def scen(title,dis,now,note=""):
    global out
    ap=applied_from(TT); n=m(now); A=affected_set(TT,ap,dis)
    out+=[f"## {title} (now {now})","",note,"",f"Affected set (cascade-closed): {', '.join(sorted(A))} — {len(A)} of {len(TT)}.","","| Revision | Validator | Recovery | Platform changes | Total hold (min) | Weighted delay | Solver |","|---|---|---|---|---|---|---|"]
    revs={}
    for obj in ("min_delay","min_changes"):
        t0=time.time(); rev,st,_,w=two_stage(TT,ap,dis,n,obj); revs[obj]=rev
        out.append(row(f"CP-SAT {obj}{' (widened)' if w else ''}",rev,st,ap,dis,n))
    g=plan_greedy(TT,ap,dis,n,movable=A); out.append(row("Greedy (stage 1)",g,[("HEURISTIC",)],ap,dis,n)); revs["greedy"]=g
    for k,rev in revs.items():
        out+=["",f"**{k}** changes:",""]+[f"- {i}: {p0} {a0} → {p1} {a1} (hold {h})" for i,p0,a0,p1,a1,h in diff(ap,rev)]
    out.append(""); return revs
scen("S1 — assign platforms",{},"00:00","All trains movable; scheduled platforms as the base.")
scen("S2 — 11209 +30 min, PF 3 closed 14:00–15:30",{"delays":[{"train":"11209","min":30,"kind":"arrival"}],"closures":[{"p":"P3","s":m("14:00"),"e":m("15:30")}]},"13:50","At 14:05 the same message must be rejected: 11209 has arrived at 14:02.")
r8=scen("S8 — 51218 departure +25, PF 3 closed 14:30–15:10",{"delays":[{"train":"51218","min":25,"kind":"departure"}],"closures":[{"p":"P3","s":m("14:30"),"e":m("15:10")}]},"14:10")
bad=copy.deepcopy(r8["min_delay"]); x=next(a for a in bad if a["id"]=="12222"); y=next(a for a in bad if a["id"]=="51215"); y["p"]=x["p"]; y["arr"]=x["arr"]+5; y["dep"]=y["arr"]+10
d8={"delays":[{"train":"51218","min":25,"kind":"departure"}],"closures":[{"p":"P3","s":m("14:30"),"e":m("15:10")}]}
out+=["## S5 — fault injection on S8 min_delay","",*[f"- {c[0]} · {c[2]} · {' ↔ '.join(c[1])} · {c[3]}" for c in validate(TT,d8,bad,applied_from(TT),m("14:10"))],""]
d2={"closures":[{"p":"P4","s":m("12:30"),"e":m("13:00")}]}; rev,st=plan_cpsat(TT,applied_from(TT),d2,0)
out+=["## Lexicographic check — PF 4 (only goods PF) closed 12:30–13:00","",f"Unassigned: {[a['id'] for a in rev if a['st']=='U']} · held: {[(a['id'],a['hold']) for a in rev if a.get('hold')]} · stages: {st}",""]
print("\n".join(out))
