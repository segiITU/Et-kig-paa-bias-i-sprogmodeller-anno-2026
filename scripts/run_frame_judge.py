"""Targeted judge pass over the regex-flagged reasoning traces.

Separates the two constructs that the reasoning pass's `testmistanke`
conflated: knowing the CASE is not real (rammebevidsthed) vs. suspecting
the MODEL ITSELF is under audit (revisionsmistanke), plus whether that
awareness visibly changes the decision (adfaerdsaendring).

Scope: only traces flagged by analysis.scan_eval_awareness. The denominator
is therefore the flagged set, never the corpus — these scores are a review
aid, not a population estimate.

Usage:
    python scripts/run_frame_judge.py --stream        # immediate, full price
    python scripts/run_frame_judge.py                 # Batch API (<=24h)
    python scripts/run_frame_judge.py --judge deepseek
    python scripts/run_frame_judge.py --dry-run       # count + cost sizing only
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from biaslab.analysis import scan_eval_awareness
from biaslab.config import ROOT, load_experiment
from biaslab.judge import judge_frame_records, judge_frame_records_batch


def flagged_records(raw_path: Path) -> list[dict]:
    """One record per key (prefer the parse_ok / latest attempt, as in
    run_judge.py), keeping only those whose trace trips the awareness regex."""
    by_key: dict[str, dict] = {}
    for line in open(raw_path, encoding="utf-8"):
        r = json.loads(line)
        prev = by_key.get(r["key"])
        if prev is None or (not r.get("parse_errors"), r.get("timestamp", "")) > (
                not prev.get("parse_errors"), prev.get("timestamp", "")):
            by_key[r["key"]] = r
    out = []
    for r in by_key.values():
        hits = scan_eval_awareness(r.get("reasoning") or "")
        if hits:
            r["_awareness_hits"] = hits
            out.append(r)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stream", action="store_true",
                        help="streaming calls (full price, immediate) instead of Batch API")
    parser.add_argument("--judge", action="append", metavar="SUBSTRING",
                        help="only these judge models (repeatable/comma-separated)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report how many traces would be judged, then exit")
    args = parser.parse_args()

    cfg = load_experiment()
    raw_path = ROOT / cfg["paths"]["raw_dir"] / f"{cfg['run_name']}.jsonl"
    if not raw_path.exists():
        raise SystemExit(f"Ingen resultater fundet: {raw_path}.")
    records = flagged_records(raw_path)
    chars = sum(len(r.get("reasoning") or "") for r in records)
    print(f"{len(records)} flagede spor ({chars:,} tegn, ~{chars/3.6:,.0f} input-tokens pr. dommer).")
    by_model: dict[str, int] = {}
    for r in records:
        by_model[r["model"]] = by_model.get(r["model"], 0) + 1
    for m, n in sorted(by_model.items(), key=lambda kv: -kv[1]):
        print(f"  {m:26s} {n:4d}")
    if args.dry_run:
        return

    judged_dir = ROOT / cfg["paths"]["judged_dir"]
    judge_models = cfg["judge"]["models"]
    if args.judge:
        wanted = [w.strip().lower() for pat in args.judge for w in pat.split(",") if w.strip()]
        judge_models = [m for m in judge_models if any(w in m.lower() for w in wanted)]
        if not judge_models:
            raise SystemExit(f"--judge {args.judge} matchede ingen af {cfg['judge']['models']}")
    # The rubric quotes verbatim excerpts from three dimensions; 500 tokens
    # (the tone/reasoning cap) truncates roughly one reply in ten.
    judge_cfg = {**cfg["judge"], "max_tokens": max(cfg["judge"]["max_tokens"], 800)}
    for judge_model in judge_models:
        slug = judge_model.replace("/", "-").replace(".", "-")
        out_path = judged_dir / f"{cfg['run_name']}_frame_{slug}.jsonl"
        if args.stream:
            asyncio.run(judge_frame_records(records, judge_model, judge_cfg, out_path))
        else:
            judge_frame_records_batch(records, judge_model, judge_cfg, out_path)
        print(f"Færdig (frame): {out_path}")


if __name__ == "__main__":
    main()
