"""LLM judging stage: prompt construction, batching, parsing.

The prompt here is the one validated in the feasibility test
(artifacts/llm_feasibility.md): 100% accept-precision across 9 known-negative
controls on both Opus and Sonnet, with calibrated confidence. Change it only
with a re-run against controls -- it is load-bearing, not cosmetic.

No network calls live in this module. `build_requests` produces payloads and
`parse_table` consumes responses, so both are testable without an API key.
"""
from dataclasses import dataclass, asdict
import json
import re

MODEL_DEFAULT = "claude-sonnet-4-5"     # feasibility winner; verify exact id at call time
MODEL_ESCALATE = "claude-opus-4-1"      # for low-confidence rows

# Verify against current pricing before trusting any estimate.
# USD per million tokens, (input, output).
PRICES = {
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-opus-4-1": (15.0, 75.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

INSTRUCTIONS = """You are helping evaluate street name etymologies in Ada County, Idaho (Boise and
surrounding towns). For each street below, a candidate Wikidata entity has been
proposed by an automated matcher. Your job is to judge whether it is right.

## Essential background

Most American suburban street names have **no etymology at all**. A developer
filling out a plat picked a word because it sounded pleasant. "Meadowlark Lane"
usually does not honour the bird *Sturnella neglecta* — it is decoration.
So the goal is not to find a referent for everything. It is to identify the
minority that genuinely refer to something, and to say so when nothing does.

Subdivisions are typically themed: all trees, all birds, all Idaho mining towns.
The neighbouring street names are therefore strong evidence. A street named
"Griffon" surrounded by Doberman, Bluetick and Chesapeake is a dog breed, not a
mythological creature. But themes can be **mixed** (one real subdivision here
combines dog breeds, racehorses and racetracks), and many subdivisions have no
theme at all — just pleasant-sounding invented compounds.

## Verdict codes

- `y` — correct. The street really is named after the proposed entity.
- `w` — right **category**, wrong specific item.
- `n` — wrong. Not this, and not anything in this category.
- `q` — genuinely unsure.

`q` and `n` are valuable answers. A confident wrong answer is much worse than an
honest "unsure". Do not reach for a referent that is not there.

## Output format

Return a markdown table, one row per item, nothing else:

| n | street | verdict | confidence | theme | reasoning |

- `confidence`: high / medium / low
- `theme`: the theme you infer for the subdivision, or `none`, or `unclear`
- `reasoning`: one sentence, max ~20 words
"""


@dataclass
class Item:
    n: int
    street: str
    domain: str
    qid: str
    label: str
    description: str
    location: str
    subdivision: str
    neighbours: list[str]

    def render(self) -> str:
        loc = f" _(located in {self.location})_" if self.location else ""
        nb = ", ".join(self.neighbours) if self.neighbours else "(none)"
        return (f"### {self.n}. {self.street}\n"
                f"- **Proposed:** {self.label} — {self.description or '(no description)'}{loc}\n"
                f"- **Category:** {self.domain}\n"
                f"- **Subdivision:** {self.subdivision or '(none)'}\n"
                f"- **Other streets in that subdivision:** {nb}\n")


def build_prompt(items: list[Item]) -> str:
    body = "\n".join(i.render() for i in items)
    return f"{INSTRUCTIONS}\n---\n\n## Items ({len(items)})\n\n{body}"


def build_requests(items: list[Item], model: str = MODEL_DEFAULT,
                   chunk: int = 40, max_tokens: int = 8000) -> list[dict]:
    """Anthropic Batch API request payloads. Chunk size 40 matches the size the
    feasibility test validated; larger chunks are unvalidated."""
    out = []
    for start in range(0, len(items), chunk):
        group = items[start:start + chunk]
        out.append({
            "custom_id": f"batch-{start // chunk:04d}",
            "params": {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": build_prompt(group)}],
            },
            "_items": [i.n for i in group],       # local bookkeeping, stripped before send
        })
    return out


def estimate_cost(requests: list[dict], model: str = MODEL_DEFAULT,
                  out_tokens_per_item: int = 60, batch_discount: float = 0.5) -> dict:
    """Rough cost estimate. Token counts approximated at 4 chars/token."""
    inp = sum(len(r["params"]["messages"][0]["content"]) for r in requests) / 4
    n_items = sum(len(r["_items"]) for r in requests)
    outp = n_items * out_tokens_per_item
    pin, pout = PRICES.get(model, (0.0, 0.0))
    cost = (inp / 1e6 * pin + outp / 1e6 * pout) * batch_discount
    return {"requests": len(requests), "items": n_items,
            "input_tokens": int(inp), "output_tokens": int(outp),
            "usd_estimate": round(cost, 2), "model": model}


_ROW = re.compile(r"^\s*\|")


def parse_table(text: str) -> dict[int, dict]:
    """Parse the markdown table a model returns. Tolerates prose around it."""
    out = {}
    for line in text.splitlines():
        if not _ROW.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        v = cells[2].lower().strip("`")
        if v not in {"y", "n", "w", "q"}:
            continue
        out[int(cells[0])] = {
            "street": cells[1], "verdict": v,
            "confidence": cells[3].lower() if len(cells) > 3 else "",
            "theme": cells[4] if len(cells) > 4 else "",
            "reasoning": cells[5] if len(cells) > 5 else "",
        }
    return out
