"""RailFlow reference model (v1.6). NOT the product: an oracle the real tests compare against.
Reference implementation of the v1.6 semantics, used to verify the spec against the shipped data."""
import json, copy
from collections import defaultdict
from ortools.sat.python import cp_model
import pathlib, sys
D=str(pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else pathlib.Path(__file__).resolve().parents[1])
m=lambda s:int(s[:2])*60+int(s[3:]); hh=lambda x:f"{x//60:02d}:{x%60:02d}"
ST=json.load(open(f"{D}/station_shivneri.json",encoding="utf-8")); GAP=ST["min_gap"]; MAXH=ST["max_hold"]
def load(name): return {t["id"]:dict(t,arr=m(t["arr"]),dep=m(t["dep"])) for t in json.load(open(f"{D}/{name}"))["trains"]}
def delays(dis):
    ad=defaultdict(int); dd=defaultdict(int)
    for d in dis.get("delays",[]): (ad if d.get("kind","arrival")=="arrival" else dd)[d["train"]]+=d["min"]
    return ad,dd
# ---------------- validator (independent semantics, sweep line) ----------------
def validate(tt,dis,rev,applied=None,now=0):
    C=[]; ad,dd=delays(dis); plats={p["id"] for p in ST["platforms"]}
    ids=[a["id"] for a in rev]
    for t in tt:
        if ids.count(t)!=1: C.append(("MISSING_OR_DUP",[t],None,{}))
    frozen={a["id"]:a for a in (applied or []) if a["st"]=="A" and a["arr"]<=now}
    occ=defaultdict(list)
    for a in rev:
        t=tt.get(a["id"])
        if t is None: C.append(("UNKNOWN_TRAIN",[a["id"]],None,{})); continue
        if a["st"]=="U":
            if a["id"] in frozen: C.append(("FROZEN_CHANGED",[a["id"]],None,{}))
            continue
        if a["p"] not in plats: C.append(("UNKNOWN_PLATFORM",[a["id"]],a["p"],{})); continue
        if t["required_platform"] and a["p"]!=t["required_platform"]: C.append(("REQUIRED_PLATFORM",[a["id"]],a["p"],{}))
        if t["allowed_platforms"] and a["p"] not in t["allowed_platforms"]: C.append(("NOT_ALLOWED_PLATFORM",[a["id"]],a["p"],{}))
        exp_dwell=(t["dep"]-t["arr"])+dd[a["id"]]
        if a["dep"]-a["arr"]!=exp_dwell: C.append(("DWELL_CHANGED",[a["id"]],a["p"],{"expected":exp_dwell,"got":a["dep"]-a["arr"]}))
        earliest=t["arr"]+ad[a["id"]]
        if a["arr"]<earliest: C.append(("EARLIER_THAN_POSSIBLE",[a["id"]],a["p"],{"minutes":earliest-a["arr"]}))
        if a["arr"]-earliest>MAXH: C.append(("HOLD_EXCEEDED",[a["id"]],a["p"],{"minutes":a["arr"]-earliest}))
        f=frozen.get(a["id"])
        if f and (f["p"],f["arr"])!=(a["p"],a["arr"]): C.append(("FROZEN_CHANGED",[a["id"]],a["p"],{}))
        occ[a["p"]].append((a["arr"],a["dep"],a["id"]))
    for p,it in occ.items():
        it.sort()
        for i,(a1,d1,i1) in enumerate(it):
            for a2,d2,i2 in it[i+1:]:
                if a2>=d1+GAP: break
                stay=max(0,min(d1,d2)-a2)                       # both trains physically at the PF
                reserved=min(d1,d2)+GAP-a2                      # overlap of [arr, dep+gap) intervals
                code="OVERLAP" if a2<d1 else "GAP_VIOLATION"
                C.append((code,[i1,i2],p,{"stay_overlap_min":stay,"clearance_shortfall_min":(d1+GAP-a2) if a2>=d1 else None,"reserved_overlap_min":reserved}))
    for c in dis.get("closures",[]):
        for a,d,i in occ.get(c["p"],[]):
            if a<c["e"] and c["s"]<d+GAP: C.append(("CLOSURE_VIOLATION",[i],c["p"],{"minutes":min(d+GAP,c["e"])-max(a,c["s"])}))
    return C
# ---------------- planner helpers ----------------
def applied_from(tt,key="platform"): return [dict(id=i,st="A",p=t[key],arr=t["arr"],dep=t["dep"],hold=0) for i,t in tt.items()]
def occupancy_after(tt,applied,dis):
    ad,dd=delays(dis); out={}
    for a in applied:
        if a["st"]!="A": continue
        out[a["id"]]=(a["p"],a["arr"]+ad[a["id"]],a["dep"]+ad[a["id"]]+dd[a["id"]])
    return out
def affected_set(tt,applied,dis):
    occ=occupancy_after(tt,applied,dis); A={d["train"] for d in dis.get("delays",[])}
    A|={t for t,(p,a,d) in occ.items() for c in dis.get("closures",[]) if c["p"]==p and a<c["e"] and c["s"]<d+GAP}
    grew=True
    while grew:
        grew=False
        for t,(p,a,d) in occ.items():
            if t in A: continue
            if any(occ[x][0]==p and a<occ[x][2]+GAP and occ[x][1]<d+GAP for x in A if x in occ): A.add(t); grew=True
    return A
def plan_cpsat(tt,applied,dis,now,objective="min_delay",movable=None,time=5.0):
    ad,dd=delays(dis); base={a["id"]:a for a in applied}
    mdl=cp_model.CpModel(); onp=defaultdict(list); dec={}
    for i,t in tt.items():
        a=base[i]; e=t["arr"]+ad[i]; size=(t["dep"]-t["arr"])+dd[i]+GAP
        fixed = (a["arr"]<=now) or (movable is not None and i not in movable)
        if fixed:
            s=a["arr"]+(0 if a["arr"]<=now else ad[i]); onp[a["p"]].append(mdl.NewFixedSizeIntervalVar(s,size,f"f{i}")); dec[i]=("F",a["p"],s,s+size-GAP); continue
        pi=5-t["priority"]; h=mdl.NewIntVar(0,MAXH,f"h{i}"); s=mdl.NewIntVar(e,e+MAXH,f"s{i}"); mdl.Add(s==e+h)
        xs={}
        for p in (t["allowed_platforms"] or [q["id"] for q in ST["platforms"]]):
            if t["required_platform"] and p!=t["required_platform"]: continue
            x=mdl.NewBoolVar(f"x{i}{p}"); onp[p].append(mdl.NewOptionalFixedSizeIntervalVar(s,size,x,f"iv{i}{p}")); xs[p]=x
        u=mdl.NewBoolVar(f"u{i}"); mdl.AddExactlyOne(list(xs.values())+[u])
        ch=(1-xs[a["p"]]) if a["p"] in xs else 1
        dec[i]=("M",xs,u,h,e,size-GAP,pi,ch)
    for c in dis.get("closures",[]): onp[c["p"]].append(mdl.NewFixedSizeIntervalVar(c["s"],c["e"]-c["s"],"cl"))
    for v in onp.values(): mdl.AddNoOverlap(v)
    M=[v for v in dec.values() if v[0]=="M"]
    unas=sum(v[6]*v[2] for v in M); dly=sum(v[6]*v[3] for v in M); chg=sum(v[7] for v in M)
    order=[unas]+([dly,chg] if objective=="min_delay" else [chg,dly])
    sol=cp_model.CpSolver(); sol.parameters.num_search_workers=8; sol.parameters.random_seed=42; sol.parameters.max_time_in_seconds=time/len(order)
    stats=[]
    for k,obj in enumerate(order):                      # sequential lexicographic optimisation
        mdl.Minimize(obj); st=sol.Solve(mdl)
        if st not in (cp_model.OPTIMAL,cp_model.FEASIBLE): return None,stats+[sol.StatusName(st)]
        val=int(sol.ObjectiveValue()); stats.append((sol.StatusName(st),val)); mdl.Add(obj<=val)
        if k<len(order)-1:
            mdl.ClearHints()
            for v in M:
                for p,x in v[1].items(): mdl.AddHint(x,sol.Value(x))
    out=[]
    for i,v in dec.items():
        if v[0]=="F": out.append(dict(id=i,st="A",p=v[1],arr=v[2],dep=v[3],hold=0)); continue
        _,xs,u,h,e,dw,pi,ch=v
        if sol.Value(u): out.append(dict(id=i,st="U",p=None,arr=None,dep=None,hold=None)); continue
        p=next(p for p,x in xs.items() if sol.Value(x)); hv=sol.Value(h); out.append(dict(id=i,st="A",p=p,arr=e+hv,dep=e+hv+dw,hold=hv))
    return out,stats
def two_stage(tt,applied,dis,now,objective):
    A=affected_set(tt,applied,dis); rev,st=plan_cpsat(tt,applied,dis,now,objective,movable=A)
    widened=False
    if rev is None or any(a["st"]=="U" for a in rev):
        rev,st=plan_cpsat(tt,applied,dis,now,objective,movable=None); widened=True
    return rev,st,A,widened
def diff(applied,rev):
    b={a["id"]:a for a in applied}; out=[]
    for a in rev:
        o=b[a["id"]]
        if (o["p"],o["arr"],o["dep"])!=(a["p"],a["arr"],a["dep"]): out.append((a["id"],o["p"],hh(o["arr"]),a["p"],hh(a["arr"]) if a["arr"] is not None else "-",a["hold"]))
    return out

def recovery(rev, solver_ok=True):
    if rev is None or not solver_ok: return "SOLVER_FAILED"          # a timeout is not a proof of infeasibility
    return "PARTIAL" if any(a["st"]=="U" for a in rev) else "FULLY_ASSIGNED"
def plan_greedy(tt,applied,dis,now,movable=None):
    ad,dd=delays(dis); base={a["id"]:a for a in applied}; busy=defaultdict(list); out=[]; mov=[]
    for i,t in tt.items():
        a=base[i]
        if a["arr"]<=now or (movable is not None and i not in movable):
            s=a["arr"]+(0 if a["arr"]<=now else ad[i]); d=s+(t["dep"]-t["arr"])+dd[i]; busy[a["p"]].append((s,d+GAP)); out.append(dict(id=i,st="A",p=a["p"],arr=s,dep=d,hold=0))
        else: mov.append(i)
    for c in dis.get("closures",[]): busy[c["p"]].append((c["s"],c["e"]))
    for i in sorted(mov,key=lambda i:(tt[i]["required_platform"] is None,tt[i]["arr"]+ad[i],tt[i]["priority"])):
        t=tt[i]; e=t["arr"]+ad[i]; dw=(t["dep"]-t["arr"])+dd[i]; best=None
        for p in t["allowed_platforms"]:
            if t["required_platform"] and p!=t["required_platform"]: continue
            s=e
            for a,b in sorted(busy[p]):
                if s+dw+GAP<=a: break
                s=max(s,b)
            if s-e<=MAXH:
                k=(s-e,p!=base[i]["p"],p); best=min(best,(k,p,s)) if best else (k,p,s)
        if best is None: out.append(dict(id=i,st="U",p=None,arr=None,dep=None,hold=None)); continue
        _,p,s=best; busy[p].append((s,s+dw+GAP)); out.append(dict(id=i,st="A",p=p,arr=s,dep=s+dw,hold=s-e))
    return out
def metrics(tt,applied,rev):
    b={a["id"]:a for a in applied}; mv=[a for a in rev if a["st"]=="A" and a["p"]!=b[a["id"]]["p"]]
    hold=sum(a["hold"] or 0 for a in rev if a["st"]=="A"); w=sum((5-tt[a["id"]]["priority"])*(a["hold"] or 0) for a in rev if a["st"]=="A")
    return {"platform_changes":len(mv),"total_hold_min":hold,"weighted_delay":w,"unassigned":sum(a["st"]=="U" for a in rev)}
