"""Surface naming-plat choices for a human to eyeball. No scoring.

A street whose name resembles one of the plats covering it is a case where a
reader can judge the choice at a glance. That resemblance is a REVIEW AID ONLY:
it is not written anywhere the pipeline can see it, and it is not treated as
ground truth. It exists for two reasons -- the direction of naming is often the
reverse of what it looks like (a 2023 plat can be named after a 1975 street),
and only a person can tell which way it ran.

Prints the choice, the resembling plat, and the run lengths that decided it.
"""
import argparse, json, re

from streetymology.config import data_path

CTX = "place_context.json"
_WS = re.compile(r"[^a-z0-9 ]")


def norm(s):
    return _WS.sub("", (s or "").lower()).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--weak", action="store_true",
                    help="places whose naming plat holds little of the street")
    ap.add_argument("--max-length", type=float, default=6000.0,
                    help="ignore streets longer than this; they are section-line "
                         "roads no plat laid out")
    ap.add_argument("--max-share", type=float, default=0.25,
                    help="with --weak, the share below which a choice is weak")
    ap.add_argument("--contested", action="store_true",
                    help="places where two plats score almost the same")
    ap.add_argument("--max-margin", type=float, default=0.05,
                    help="with --contested, the score gap that counts as close")
    ap.add_argument("--numbered", action="store_true",
                    help="numbered streets: they belong to original townsites, "
                         "so any other naming plat is a red flag")
    ap.add_argument("--agreements", action="store_true",
                    help="show cases where the choice DOES match the name")
    a = ap.parse_args()

    ctx = json.loads((data_path(CTX)).read_text())

    if a.weak:
        rows = [v for v in ctx.values()
                if v["analysed"] and v["plats"] and v["naming_plat"]
                and v["plats"][0]["street_m"] <= a.max_length
                and (v["naming_share"] or 0) < a.max_share]
        rows.sort(key=lambda v: v["naming_share"] or 0)
        print(f"{len(rows)} place(s) under {a.max_share:.0%} of the street inside "
              f"the naming plat, streets up to {a.max_length:.0f} m\n")
        for v in rows[:a.limit]:
            print(f"  {v['name'][:32]:32s} street {v['plats'][0]['street_m']:5.0f} m"
                  f"  in {len(v['plats'])} plats")
            for pl in v["plats"][:4]:
                mark = "->" if pl["name"] == v["naming_plat"] else "  "
                print(f"    {mark} {pl['name'][:28]:28s} {str(pl['recorded'])[:4]}"
                      f"  run {pl['run_m']:5.0f}  inside {pl['inside_m']:5.0f}"
                      f"  pieces {pl['pieces']}")
        return

    if a.contested:
        rows = [v for v in ctx.values()
                if v["analysed"] and v["naming_plat"]
                and v.get("margin") is not None and v["margin"] <= a.max_margin]
        rows.sort(key=lambda v: (v["margin"], -(v["naming_score"] or 0)))
        print(f"{len(rows)} place(s) where the top two plats are within "
              f"{a.max_margin} of each other\n")
        for v in rows[:a.limit]:
            print(f"  {v['name'][:30]:30s} street {v['plats'][0]['street_m']:5.0f} m"
                  f"  in {len(v['plats'])} plats  margin {v['margin']:.3f}")
            for pl in v["plats"][:4]:
                mark = "->" if pl["name"] == v["naming_plat"] else "  "
                print(f"    {mark} {pl['name'][:26]:26s} {str(pl['recorded'])[:4]}"
                      f"  score {pl['score']:.2f} conf {pl['confidence']:.2f}"
                      f"  inside {pl['inside_m']:5.0f}  run {pl['run_m']:5.0f}")
        return

    if a.numbered:
        # A numbered street is laid out by the town grid, not by a developer.
        # Anything but an original townsite or addition is a sign the rule is
        # attaching streets to plats that merely sit along them.
        num = re.compile(r"^\d+(st|nd|rd|th)$")
        rows = [v for v in ctx.values()
                if v["analysed"] and num.match(norm(v["core"]))]
        rows.sort(key=lambda v: (v["naming_plat"] or "", v["name"]))
        named = [v for v in rows if v["naming_plat"]]
        print(f"{len(rows)} numbered street place(s); {len(named)} get a naming "
              f"plat, {len(rows) - len(named)} abstain\n")
        for v in rows[:a.limit]:
            pl = v["naming_plat"] or "(abstains)"
            rec = str(v["naming_recorded"])[:4] if v["naming_recorded"] else "----"
            print(f"  {v['name'][:24]:24s} {v['plats'][0]['street_m'] if v['plats'] else 0:5.0f} m"
                  f"  in {len(v['plats']):2d} plats -> {pl[:34]:34s} {rec}"
                  f"  share {v['naming_share'] or 0:.2f}")
        return

    rows = []
    for v in ctx.values():
        if not v["analysed"] or len(v["plats"]) < 2 or not v["naming_plat"]:
            continue
        core = norm(v["core"])
        like = [p for p in v["plats"] if core and core in norm(p["name"])]
        if not like:
            continue
        chosen_matches = norm(v["naming_plat"]).find(core) >= 0
        if chosen_matches != a.agreements:
            continue
        rows.append((v, like[0]))

    rows.sort(key=lambda t: -t[1]["run_m"])
    kind = "matches" if a.agreements else "does NOT match"
    print(f"{len(rows)} place(s) where the chosen plat {kind} the street name\n")
    for v, like in rows[:a.limit]:
        ch = next(p for p in v["plats"] if p["name"] == v["naming_plat"])
        print(f"  {v['name'][:30]:30s} street {ch['street_m']:5.0f} m")
        print(f"      chose      {ch['name'][:28]:28s} {str(ch['recorded'])[:4]}"
              f"  run {ch['run_m']:5.0f} m  inside {ch['inside_m']:5.0f} m")
        if not a.agreements:
            print(f"      name-alike {like['name'][:28]:28s} "
                  f"{str(like['recorded'])[:4]}  run {like['run_m']:5.0f} m"
                  f"  inside {like['inside_m']:5.0f} m")


if __name__ == "__main__":
    main()
