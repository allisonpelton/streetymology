"""Turn raw batch responses into a verdicts CSV, mapped back to streets."""
import argparse, csv, json, collections
from pathlib import Path
from streetymology.config import data_path, ARTIFACTS_DIR
from streetymology import llm

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("results", help="llm_batch_results_<id>.json")
    ap.add_argument("--model", default=llm.MODEL_DEFAULT)
    a = ap.parse_args()

    raw = json.loads(Path(a.results).read_text())
    index = json.loads((data_path("llm_batch_index.json")).read_text())
    items = {i.n: i for i in __import__("build_llm_batch").build_items()} if False else {}

    verdicts, missing = {}, []
    for custom_id, text in raw.items():
        parsed = llm.parse_table(text)
        expected = index.get(custom_id, [])
        for n in expected:
            if n in parsed:
                verdicts[n] = parsed[n]
            else:
                missing.append((custom_id, n))

    out = ARTIFACTS_DIR / "llm_verdicts.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n", "street", "verdict", "confidence", "theme", "reasoning"])
        for n in sorted(verdicts):
            v = verdicts[n]
            w.writerow([n, v["street"], v["verdict"], v["confidence"], v["theme"], v["reasoning"]])
    print(f"parsed {len(verdicts)} verdicts, {len(missing)} missing")
    print("verdict mix:", collections.Counter(v["verdict"] for v in verdicts.values()).most_common())
    print("confidence :", collections.Counter(v["confidence"] for v in verdicts.values()).most_common())
    print(f"-> {out}")
    if missing:
        print("WARNING: some requested items were absent from the model output.")
        print("  first few:", missing[:5])
