"""Score results with the LLM judges: tone pass over justifications
(blind to persona names) and reasoning pass over hidden reasoning traces
(implicit eval-awareness + demographic salience/stereotype use).

Usage:
    python scripts/run_judge.py                    # both passes via Batch API (default)
    python scripts/run_judge.py --stream           # both passes, streaming (full price)
    python scripts/run_judge.py --tone-only
    python scripts/run_judge.py --reasoning-only
    python scripts/run_judge.py --judge gemini,deepseek   # subset of judges
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from biaslab.config import ROOT, load_experiment
from biaslab.judge import (judge_records, judge_records_batch,
                           judge_reasoning_records, judge_reasoning_records_batch)


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tone-only", action="store_true",
                       help="only the tone pass over justifications")
    group.add_argument("--reasoning-only", action="store_true",
                       help="only the awareness/bias pass over reasoning traces")
    parser.add_argument("--stream", action="store_true",
                        help="use streaming calls (full price, immediate results) "
                             "instead of the default Batch API")
    parser.add_argument("--judge", action="append", metavar="SUBSTRING",
                        help="only run these judge models (repeatable, or "
                             "comma-separated; substring match against "
                             "judge.models in experiment.yaml). Default: all. "
                             "Lets one judge proceed while another's batches "
                             "are still in flight — scores are averaged per "
                             "judge at analysis time, so judge order is "
                             "immaterial.")
    args = parser.parse_args()

    cfg = load_experiment()
    raw_path = ROOT / cfg["paths"]["raw_dir"] / f"{cfg['run_name']}.jsonl"
    if not raw_path.exists():
        raise SystemExit(f"Ingen resultater fundet: {raw_path}. Kør run_experiment.py først.")
    all_records = [json.loads(line) for line in open(raw_path, encoding="utf-8")]
    # The runner retries on failure without removing the failed attempt, so
    # a key can appear more than once. Judge exactly one record per key —
    # otherwise duplicate custom_ids get rejected by the batch API (reasoning
    # traces are non-empty even on parse failures, unlike tone's `begrundelse`)
    # and, worse, a key judged twice would silently double-count in analysis.
    # Prefer the successful (parse_ok) attempt; break ties by latest timestamp.
    by_key: dict[str, dict] = {}
    for r in all_records:
        prev = by_key.get(r["key"])
        if prev is None:
            by_key[r["key"]] = r
            continue
        prev_ok, r_ok = not prev.get("parse_errors"), not r.get("parse_errors")
        if (r_ok, r.get("timestamp", "")) > (prev_ok, prev.get("timestamp", "")):
            by_key[r["key"]] = r
    n_dupes = len(all_records) - len(by_key)
    if n_dupes:
        print(f"{n_dupes} duplikat-nøgler i {raw_path.name} — bruger nyeste/lykkedes forsøg pr. nøgle.")
    records = list(by_key.values())
    judged_dir = ROOT / cfg["paths"]["judged_dir"]
    judge_models = cfg["judge"]["models"]
    if args.judge:
        wanted = [w.strip().lower() for pat in args.judge for w in pat.split(",") if w.strip()]
        judge_models = [m for m in judge_models if any(w in m.lower() for w in wanted)]
        if not judge_models:
            raise SystemExit(
                f"--judge {args.judge} matchede ingen af {cfg['judge']['models']}")
        print(f"Kører kun dommere: {judge_models}")
    for judge_model in judge_models:
        slug = judge_model.replace("/", "-").replace(".", "-")
        if not args.reasoning_only:
            out_path = judged_dir / f"{cfg['run_name']}_judged_{slug}.jsonl"
            if args.stream:
                asyncio.run(judge_records(records, judge_model, cfg["judge"], out_path))
            else:
                judge_records_batch(records, judge_model, cfg["judge"], out_path)
            print(f"Færdig (tone): {out_path}")
        if not args.tone_only:
            out_path = judged_dir / f"{cfg['run_name']}_reasoning_{slug}.jsonl"
            if args.stream:
                asyncio.run(judge_reasoning_records(records, judge_model, cfg["judge"], out_path))
            else:
                judge_reasoning_records_batch(records, judge_model, cfg["judge"], out_path)
            print(f"Færdig (reasoning): {out_path}")


if __name__ == "__main__":
    main()
