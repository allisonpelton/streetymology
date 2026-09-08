"""Draw a held-out sample of naming-plat decisions for AP to judge.

Every parameter in the scoring was chosen by looking at the same handful of
streets -- Retort, Chester, Avimor, Copenhagen, 29th -- which is fitting to a
sample. This draws places that were NOT looked at, so the rule can be measured
on streets nobody tuned against.

Seeded, so the same draw can be reproduced. Excludes the tuning streets by core
name. Writes a CSV for LibreOffice with the evidence laid out and two blank
columns; nothing else in the tree reads the result, so a verdict costs only the
judging.

Two columns because the rule answers two questions. `verdict` judges the choice
of plat; `theme_ok` judges whether that plat could help identify an etymology at
all, which is the only test of the era weight.
"""
import argparse, csv, json, random

from streetymology.config import DELIVERABLES_DIR, data_path

CTX = "place_context.json"
# Cores used while building the rule. Judging these would measure memory.
TUNED = {"retort", "chester", "avimor", "copenhagen", "29th", "10th", "11th",
         "quail ridge", "camden", "wichita", "sycamore", "wardle", "elder",
         "eyrie", "lupine", "vega", "meadow view", "goose creek", "eminence",
         "shaelyn", "milestone", "bright light", "inspirado"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20260908)
    ap.add_argument("--out", default=str(DELIVERABLES_DIR / "naming_plat_review" /
                                         "naming_plat_sample.csv"))
    a = ap.parse_args()

    ctx = json.loads((data_path(CTX)).read_text())
    pool = [v for v in ctx.values()
            if v["analysed"] and v["plats"] and v["core"] not in TUNED]
    rng = random.Random(a.seed)
    picked = rng.sample(pool, min(a.n, len(pool)))
    picked.sort(key=lambda v: v["name"])

    out = __import__("pathlib").Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["n", "street", "street_m", "platted_share",
                    "pipeline_choice", "choice_year", "confidence",
                    "theme_confidence", "contenders", "plats_covering",
                    "verdict", "theme_ok", "notes"])
        for i, v in enumerate(picked, 1):
            plats = "; ".join(
                f"{p['name']} ({str(p['recorded'])[:4]}, {p['inside_m']}m"
                f"{'/' + str(p['run_m']) + 'm run' if p['run_m'] != p['inside_m'] else ''})"
                for p in v["plats"][:6])
            w.writerow([i, v["name"], v["plats"][0]["street_m"],
                        v["platted_share"],
                        v["naming_plat"] or "(abstains)",
                        str(v["naming_recorded"])[:4] if v["naming_recorded"] else "",
                        v["confidence"] if v["confidence"] is not None else "",
                        v["theme_confidence"]
                        if v["theme_confidence"] is not None else "",
                        v["contenders"], plats, "", "", ""])
    out.chmod(0o664)
    print(f"wrote {out}  ({len(picked)} places, seed {a.seed})")
    print("verdict:  right / wrong / none / missed / tie / unsure")
    print("theme_ok: yes / no / unsure")
    ab = sum(1 for v in picked if not v["naming_plat"])
    print(f"of the sample, {ab} abstain and {len(picked) - ab} name a plat")


if __name__ == "__main__":
    main()
