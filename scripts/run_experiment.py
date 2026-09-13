"""Run the experiment grid against OpenRouter.

Usage (from project root, with the llm-bias env active):
    python scripts/run_experiment.py --dry-run          # print 2 sample prompts, no calls
    python scripts/run_experiment.py --limit 8 --stream # smoke test: 8 calls, immediate results
    python scripts/run_experiment.py                    # full grid via Batch API (default,
                                                        #   ~50% pris på batch-modeller, resumable)
"""

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from biaslab.config import ROOT, build_grid, load_experiment
from biaslab.runner import run, run_batch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="only run N randomly chosen conditions")
    parser.add_argument("--dry-run", action="store_true", help="print sample prompts and exit")
    parser.add_argument("--stream", action="store_true",
                        help="use streaming calls (full price, immediate results) "
                             "instead of the default Batch API")
    args = parser.parse_args()

    cfg = load_experiment()
    conditions = build_grid(cfg)
    print(f"Grid: {len(conditions)} kald "
          f"({len(cfg['models'])} modeller x scenarier x personaer x framings x reps)")

    if args.dry_run:
        for cond in random.Random(0).sample(conditions, 2):
            print("\n" + "=" * 70)
            print(f"[{cond.key}]")
            print(f"--- SYSTEM ---\n{cond.system_prompt}")
            print(f"--- USER ---\n{cond.user_prompt}")
        return

    if args.limit:
        conditions = random.Random(0).sample(conditions, args.limit)

    out_path = ROOT / cfg["paths"]["raw_dir"] / f"{cfg['run_name']}.jsonl"

    # Provenance: freeze the exact configuration next to the results.
    snapshot_path = out_path.with_suffix(".config.json")
    if not snapshot_path.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "experiment": cfg,
            "configs": {
                p.name: p.read_text(encoding="utf-8")
                for p in sorted(Path(ROOT / "config").rglob("*.yaml"))
            },
        }
        snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Konfigurations-snapshot gemt: {snapshot_path}")
    if args.stream:
        asyncio.run(run(conditions, cfg["sampling"], out_path))
    else:
        run_batch(conditions, cfg["sampling"], out_path)
    print(f"Færdig. Resultater: {out_path}")


if __name__ == "__main__":
    main()
