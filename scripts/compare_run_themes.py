"""Theme and confidence movement between the old runs and the plat-context run.

Answers three questions AP asked of the results, none of which the accuracy
score covers:

  which cores now carry a concrete theme that was vague before
  which cores LOST a theme that an earlier run had found
  how the confidence distribution moved

A theme is "vague" if it is none, unclear, mixed, generic or blank. Everything
else is read as concrete, including a hedged theme like "presidents (partial)",
which is reported separately where the hedge later disappears.

Judging whether a gained theme is real or invented is not automated. The model
annotates its own hedges -- "(mismatch)", "(loose)", "weak" -- and those
annotations are worth reading before trusting a gain.

Usage:
  python scripts/compare_run_themes.py
"""
import collections
import csv
import json
import pathlib
import re
from streetymology.config import DELIVERABLES_DIR
EG = DELIVERABLES_DIR/"equal_ground"; CP = DELIVERABLES_DIR/"context_prompt"
def rt(p):
    out={}
    for line in pathlib.Path(p).read_text(encoding="utf-8-sig").splitlines():
        if not line.strip().startswith("|"): continue
        c=[x.strip() for x in line.strip().strip("|").split("|")]
        if len(c)<3 or not c[0].isdigit(): continue
        out[int(c[0])]=c
    return out
new=rt(CP/"context_prompt_RESULT.md")
old={1:rt(EG/"round1"/"equal_ground_results.md"),2:rt(EG/"round2"/"equal_ground_2_results.md")}
truth={}
for r in csv.DictReader((EG/"all_labels_recode.csv").open()):
    a=r["answer"].strip().upper(); c=r["new_class"].strip().upper()
    truth[(int(r["round"]),int(r["n"]))]= c if a in {"NONE","NOETYM"} and c and c!="(NO ACTION)" else a
rows=[]
for r in csv.DictReader((CP/"context_prompt_index.csv").open()):
    n=int(r["n"]); k=(int(r["round"]),int(r["round_n"]))
    if r["score"]!="yes": continue
    o=old[k[0]].get(k[1]); nn=new.get(n)
    if not o or not nn: continue
    rows.append({"street":r["street"],"round":k[0],"truth":truth.get(k),
                 "old_choice":o[2],"new_choice":nn[2],
                 "old_conf":o[3].lower(),"new_conf":nn[3].lower(),
                 "old_theme":o[4].strip(),"new_theme":nn[4].strip(),
                 "new_reason":nn[5]})

VAGUE = re.compile(r"^(none|unclear|n/?a|mixed|generic|no theme|unknown|"
                   r"none/unclear|unclear/generic|none \(mixed\)|mixed/unclear)$", re.I)
def vague(t): return not t or bool(VAGUE.match(t)) or t.lower() in {"-",""}
print("CONFIDENCE DISTRIBUTION")
for lab,key in (("old","old_conf"),("new","new_conf")):
    c=collections.Counter(r[key] for r in rows)
    tot=sum(c.values())
    print(f"  {lab}: " + "  ".join(f"{k} {v} ({v/tot:.0%})" for k,v in
          sorted(c.items(), key=lambda x:{"high":0,"medium":1,"low":2}.get(x[0],3))))
mv=collections.Counter((r["old_conf"],r["new_conf"]) for r in rows)
print("\n  movement (old -> new), top:")
for (a,b),n in mv.most_common(9):
    print(f"    {a:7} -> {b:7} {n}" + ("   (unchanged)" if a==b else ""))
print("\nTHEME PRESENCE")
print(f"  vague in old, concrete in new : {sum(1 for r in rows if vague(r['old_theme']) and not vague(r['new_theme']))}")
print(f"  concrete in old, vague in new : {sum(1 for r in rows if not vague(r['old_theme']) and vague(r['new_theme']))}")
print(f"  concrete both                 : {sum(1 for r in rows if not vague(r['old_theme']) and not vague(r['new_theme']))}")
print(f"  vague both                    : {sum(1 for r in rows if vague(r['old_theme']) and vague(r['new_theme']))}")
