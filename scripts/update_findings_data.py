"""Rebuild the inlined `const DATA = {...}` blob in the findings pages.

`results/report/findings.html` and `findings-da.html` are hand-authored, but the
score tables at the bottom are driven by one inlined JSON object. This script
regenerates that object from `results/analysis/<run_name>/diffs_vs_reference.csv`
and rewrites the line in place, leaving all prose untouched.

The scenario/outcome/persona metadata (labels, units, decimals, favourability)
is preserved from whatever is already in the file, so the two language versions
keep their own labels.

Usage:
    python scripts/update_findings_data.py --check     # reproduce current blob, report drift
    python scripts/update_findings_data.py             # rewrite both findings pages
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from biaslab.analysis import load_results  # noqa: E402
from biaslab.config import ROOT, load_experiment  # noqa: E402

PAGES = ["results/report/findings.html", "results/report/findings-da.html"]
PREFIX = "const DATA = "

# 0/1 outcomes are reported as percentages in the tables; rente_pct already is a
# percentage and must not be scaled again.
DUMMY_OUTCOMES = {"indkald_til_samtale", "smertestillende_nu", "bevilget"}


def is_dummy(outcome_id: str) -> bool:
    return outcome_id.startswith("afgoerelse=") or outcome_id in DUMMY_OUTCOMES


def load_means(run: str):
    """Full-precision cell means, straight from the source records.

    The analysis CSVs store means rounded to 3 decimals, which is not enough to
    reproduce the tables' own rounding on exact halves (9.125 -> 9.12, not 9.13),
    so the means are recomputed here the way `analysis.cell_means` does.
    """
    raw = ROOT / "results" / "raw" / f"{run}.jsonl"
    judged_dir = ROOT / "results" / "judged"
    df = load_results(
        raw,
        sorted(judged_dir.glob(f"{run}_judged_*.jsonl")),
        sorted(judged_dir.glob(f"{run}_reasoning_*.jsonl")),
    )
    df = df[df.parse_ok]
    grouped = df.groupby(["model", "scenario", "persona"])
    means: dict[tuple[str, str, str, str], tuple[float, int]] = {}
    for (model, scenario, persona), block in grouped:
        for col in block.columns:
            series = block[col]
            if series.dtype.kind not in "fi":
                continue
            valid = series.dropna()
            if valid.empty:
                continue
            means[(scenario, col, model, persona)] = (float(valid.mean()), int(valid.size))
    return means


def load_sig(run: str) -> set:
    """(scenario, outcome, model, persona) for every comparison that survives FDR."""
    path = ROOT / "results" / "analysis" / run / "diffs_vs_reference.csv"
    sig = set()
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["significant"].strip().lower() in ("true", "1"):
                sig.add((r["scenario"], r["outcome"], r["model"], r["persona"]))
    return sig


def rebuild(data: dict, means: dict, sig: set) -> tuple[dict, list[str]]:
    """Refill every cell from `means`, adding model/persona keys that gained data.

    The blob is rebuilt from the full model x persona grid rather than from the
    keys already present: a model can acquire cells it did not have before (Gemma
    had two reasoning traces under thinking-off and 2.304 under thinking-on), and
    those must appear rather than be silently skipped. Cells with no data at all
    are left out, which is how the tables mark a model as absent.
    """
    models = [m["id"] for m in data["models"]]
    personas = [p["id"] for p in data["personas"]]
    added: list[str] = []
    for scenario in data["scenarios"]:
        sid = scenario["id"]
        for outcome in scenario["outcomes"]:
            oid = outcome["id"]
            dec, scale = outcome["dec"], (100.0 if is_dummy(oid) else 1.0)
            cells: dict[str, dict] = {}
            for model in models:
                per_persona = {}
                for persona in personas:
                    cell = means.get((sid, oid, model, persona))
                    if cell is None:
                        continue
                    mean, n = cell
                    per_persona[persona] = {
                        "v": round(mean * scale, dec),
                        "n": n,
                        "sig": (sid, oid, model, persona) in sig,
                    }
                if not per_persona:
                    continue
                was = outcome["cells"].get(model, {})
                for persona in per_persona:
                    if persona not in was:
                        added.append(f"added: {sid}/{oid}/{model}/{persona}")
                cells[model] = per_persona
            outcome["cells"] = cells
    return data, added


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="rebuild against the CURRENT file's own run and diff, without writing")
    ap.add_argument("--run", default=None, help="override run_name")
    args = ap.parse_args()

    run = args.run or load_experiment()["run_name"]
    means, sig = load_means(run), load_sig(run)

    for rel in PAGES:
        path = ROOT / rel
        lines = path.read_text(encoding="utf-8").split("\n")
        idx = next(i for i, ln in enumerate(lines) if ln.startswith(PREFIX))
        old = json.loads(lines[idx][len(PREFIX):].rstrip().rstrip(";"))
        new, problems = rebuild(json.loads(json.dumps(old)), means, sig)
        if problems:
            print(f"  + {len(problems)} new cells (models that gained data)")
        if args.check:
            def flat(blob):
                return {
                    (s["id"], o["id"], m, p): cell
                    for s in blob["scenarios"] for o in s["outcomes"]
                    for m, per in o["cells"].items() for p, cell in per.items()
                }
            a, b = flat(old), flat(new)
            changed = sum(1 for k in a.keys() | b.keys() if a.get(k) != b.get(k))
            print(f"{rel}: {changed} cells would change (run={run})")
            continue
        lines[idx] = PREFIX + json.dumps(new, ensure_ascii=False, separators=(",", ":")) + ";"
        path.write_text("\n".join(lines), encoding="utf-8")
        print(f"{rel}: DATA rebuilt from run={run}")


if __name__ == "__main__":
    main()
