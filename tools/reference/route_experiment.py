"""Tier-3 experiment: throat route conflicts at SVNJ (SPEC §48). Not part of the MVP."""
import json, sys, pathlib, itertools
from collections import defaultdict
from ortools.sat.python import cp_model
D=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else pathlib.Path(__file__).resolve().parents[1]
m=lambda s:int(s[:2])*60+int(s[3:]); hh=lambda x:f"{x//60:02d}:{x%60:02d}"
st=json.load(open(D/"station_shivneri.json",encoding="utf-8")); GAP=st["min_gap"]; MAXH=st["max_hold"]
TT=json.load(open(D/"timetable_normal.json"))["trains"]
APP,CLR=3,2          # arrival route set APP min before arrival; departure route held CLR min after departure
row=lambda p:int(p[1])
def movements(t,p):
    """(throat, kind, pf_row, offset_start, offset_end) relative to arrival a and departure d."""
    k=row(p)
    if p=="P5":                                   # west-end bay: MEMU arrive and leave via the west throat
        return [("W","DN_ARR",k,"a",-APP,0),("W","UP_DEP",k,"d",0,CLR)]
    if t["direction"]=="DN": return [("W","DN_ARR",k,"a",-APP,0),("E","DN_DEP",k,"d",0,CLR)]
    return [("E","UP_ARR",k,"a",-APP,0),("W","UP_DEP",k,"d",0,CLR)]
def crosses(x,y):
    """Route conflict table. Lines: DN main on the PF 1 side, UP main on the PF 4/5 side."""
    if x[0]!=y[0]: return False
    if x[1]==y[1]: return True                    # same line through the same throat
    k=dict([(x[1],x[2]),(y[1],y[2])])
    if x[0]=="W" and {"DN_ARR","UP_DEP"}=={x[1],y[1]}: return k["UP_DEP"]<=k["DN_ARR"]
    if x[0]=="E" and {"UP_ARR","DN_DEP"}=={x[1],y[1]}: return k["UP_ARR"]<=k["DN_DEP"]
    return False
def check(assign):                                # independent sweep: list route conflicts of a fixed plan
    mv=[]
    for t in TT:
        p,a,d=assign[t["id"]]
        for th,kind,k,ref,o1,o2 in movements(t,p):
            b=a if ref=="a" else d; mv.append((th,kind,k,b+o1,b+o2,t["id"]))
    return [(x,y) for x,y in itertools.combinations(mv,2) if x[5]!=y[5] and crosses(x,y) and x[3]<y[4] and y[3]<x[4]]
sched={t["id"]:(t["platform"],m(t["arr"]),m(t["dep"])) for t in TT}
before=check(sched)
mdl=cp_model.CpModel(); onp=defaultdict(list); routes=[]; dec={}
for t in TT:
    i=t["id"]; e=m(t["arr"]); dw=m(t["dep"])-e; pi=5-t["priority"]
    h=mdl.NewIntVar(0,MAXH,f"h{i}"); s=mdl.NewIntVar(e,e+MAXH,f"s{i}"); mdl.Add(s==e+h); xs={}
    for p in t["allowed_platforms"]:
        x=mdl.NewBoolVar(f"x{i}{p}"); xs[p]=x
        onp[p].append(mdl.NewOptionalFixedSizeIntervalVar(s,dw+GAP,x,f"pf{i}{p}"))
        for th,kind,k,ref,o1,o2 in movements(t,p):
            st_=mdl.NewIntVar(e-APP-5,e+dw+MAXH+5,""); mdl.Add(st_==s+(o1 if ref=="a" else dw+o1))
            routes.append((i,(th,kind,k),mdl.NewOptionalFixedSizeIntervalVar(st_,o2-o1,x,f"r{i}{p}{kind}")))
    mdl.AddExactlyOne(list(xs.values())); dec[i]=(xs,h,pi,t["platform"])
for v in onp.values(): mdl.AddNoOverlap(v)
for (i1,r1,iv1),(i2,r2,iv2) in itertools.combinations(routes,2):
    if i1!=i2 and crosses(r1,r2): mdl.AddNoOverlap([iv1,iv2])
dly=sum(pi*h for xs,h,pi,_ in dec.values()); chg=sum(1-xs[b] for xs,h,pi,b in dec.values() if b in xs)
sol=cp_model.CpSolver(); sol.parameters.num_search_workers=8; sol.parameters.random_seed=42; sol.parameters.max_time_in_seconds=10
stages=[]
for obj in (dly,chg):
    mdl.Minimize(obj); r=sol.Solve(mdl); stages.append((sol.StatusName(r),int(sol.ObjectiveValue()))); mdl.Add(obj<=int(sol.ObjectiveValue()))
after={}; changes=[]
for t in TT:
    xs,h,pi,b=dec[t["id"]]; p=next(p for p,x in xs.items() if sol.Value(x)); hv=sol.Value(h); a=m(t["arr"])+hv
    after[t["id"]]=(p,a,a+m(t["dep"])-m(t["arr"]))
    if hv or p!=b: changes.append(f"- {t['id']} ({t['type']} {t['direction']}): {b} → {p}, held {hv} min")
print("# Route-conflict experiment (generated)\n")
print(f"Model: arrival route {APP} min before arrival, departure route {CLR} min after departure; PF 5 is a west-end bay.\n")
print(f"Route conflicts in `timetable_normal.json` as scheduled: **{len(before)}**\n")
for x,y in before: print(f"- {x[0]} throat · {x[5]} {x[1]} PF {x[2]} ({hh(x[3])}–{hh(x[4])}) × {y[5]} {y[1]} PF {y[2]} ({hh(y[3])}–{hh(y[4])})")
print(f"\nCP-SAT with route constraints (stages: weighted delay → changes): {stages}\n")
print(f"Route conflicts after solving: **{len(check(after))}** · platform conflicts: re-check with the main validator\n")
print("Changes:\n"); print("\n".join(changes) or "- none")
