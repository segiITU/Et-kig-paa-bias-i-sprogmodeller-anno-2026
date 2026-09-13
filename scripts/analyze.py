"""Produce the analysis tables from raw + judged results.

Usage:
    python scripts/analyze.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from biaslab.analysis import run_analysis
from biaslab.config import ROOT, load_experiment


def main() -> None:
    cfg = load_experiment()
    raw_path = ROOT / cfg["paths"]["raw_dir"] / f"{cfg['run_name']}.jsonl"
    judged_dir = ROOT / cfg["paths"]["judged_dir"]
    judged_paths = sorted(judged_dir.glob(f"{cfg['run_name']}_judged_*.jsonl"))
    reasoning_paths = sorted(judged_dir.glob(f"{cfg['run_name']}_reasoning_*.jsonl"))
    if not raw_path.exists():
        raise SystemExit(f"Ingen resultater fundet: {raw_path}. Kør run_experiment.py først.")
    run_analysis(raw_path, judged_paths,
                 ROOT / cfg["paths"]["analysis_dir"] / cfg["run_name"], reasoning_paths)


if __name__ == "__main__":
    main()
