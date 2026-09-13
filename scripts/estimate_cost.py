"""Estimate the API cost of the configured grid before running it.

Fetches live pricing from OpenRouter's public model catalog.

Usage:
    python scripts/estimate_cost.py
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from biaslab.config import build_grid, load_experiment

ASSUMED_COMPLETION_TOKENS = 300  # justification + JSON
# Measured from results/raw/pilot.jsonl actual prompt/completion_tokens
# (2026-08-09; the pilot's own estimate undershot the real qwen bill by ~1.5x
# because this constant — then 1900 — was itself an earlier, lower guess.
# Hidden reasoning tokens bill as completion tokens; recheck against a fresh
# pilot before a full run, this drifts as models/prompts change).
# STALE as of 2026-08-11: qwen's reasoning.max_tokens was raised from
# effort:low to an explicit 8000-token budget (config/experiment.yaml) after
# these constants were measured, so both entries below now undershoot — rerun
# a fresh smoke test and update before trusting this estimate for qwen.
COMPLETION_OVERRIDES = {
    # qwen3.5-397b via alexandra: measured mean completion_tokens (reasoning
    # included) 2611 across 8 real calls (range 1712-4942); 2800 adds light
    # headroom.
    "qwen3.5-397b": 2800,
    # odin-2-large (2026-08-23, evening — remeasured after reasoning_effort
    # was removed from experiment.yaml; the old 1700 figure was measured
    # under reasoning_effort=medium, which turned out to break the model and
    # is no longer configured): 7 successful probe/smoke calls across all 4
    # scenarios at the current default-reasoning config gave completion_tokens
    # (reasoning included) of ~350-1370, mean ~690. 900 keeps ~30% headroom
    # over the mean; per-call variance is real, so re-check against the full
    # run's first hours on ordbogen.ai's usage page.
    "odin-2-large": 900,
}
JUDGE_PROMPT_TOKENS = 650        # 6-dim tone rubric + masked justification
JUDGE_COMPLETION_TOKENS = 100
# Reasoning pass: judge prompt is dominated by the trace length. Models not
# listed here are assumed to emit no reasoning (their records are skipped).
# Also measured from pilot.jsonl's actual `reasoning` field length (chars/3.5)
# — gpt-5.6-sol's traces run much shorter than qwen's in practice.
REASONING_TRACE_TOKENS = {
    "qwen3.5-397b": 2600,   # alexandra; reasoning ~1700-4800 tokens observed, mean ~2500
    "openai/gpt-5.6-sol": 150,
    # claude emits a trace on ~half its records (45-253 tokens observed in
    # the 2026-08-23 smoke data); a flat small figure is close enough here.
    "anthropic/claude-sonnet-5": 150,
    # odin-2-large traces are recovered via logprobs since 2026-08-23
    # (runner._reasoning_from_logprobs); 210-1301 reasoning tokens observed.
    "odin-2-large": 700,
}
REASONING_RUBRIC_TOKENS = 400
REASONING_COMPLETION_TOKENS = 120
# Batch API support is per-model on OpenRouter (observed: Anthropic/OpenAI
# models yes, Gemma/Qwen no). Batchable models bill ~50% with --batch.
BATCH_PREFIXES = ("anthropic/", "openai/")

# odincore/ordbogen.ai (added 2026-08-23) isn't on OpenRouter's catalog, so
# it can't be priced from the live `pricing` dict below — manual override,
# converted DKK -> USD at an approximate, NOT live, rate. Verify against a
# current rate before trusting this number closely; it only needs to be in
# the right ballpark for a pre-launch budget check.
DKK_PER_USD = 6.9  # approximate as of 2026-08; not fetched live
MANUAL_PRICING_DKK_PER_M = {"odin-2-large": {"prompt": 6.25, "completion": 25.00}}
MANUAL_PRICING = {
    mid: {k: v / DKK_PER_USD / 1_000_000 for k, v in p.items()}
    for mid, p in MANUAL_PRICING_DKK_PER_M.items()
}
# odincore has no evidence of a batch/async discount endpoint (see
# runner.PROVIDERS) — never eligible for the batch-price column.

# Non-OpenRouter providers are billed to their own free-credit pools, NOT the
# OpenRouter balance — reported separately below. qwen3.5-397b is served by
# alexandra (2026-08-23) on a 200 DKK free credit; its price is proxied from
# OpenRouter's identical qwen entry since alexandra isn't in that catalog.
PROXY_PRICE = {"qwen3.5-397b": "qwen/qwen3.5-397b-a17b"}
FREE_CREDIT_NOTE = {"odin-2-large": "odincore ~100 DKK",
                    "qwen3.5-397b": "alexandra ~200 DKK"}


def main() -> None:
    cfg = load_experiment()
    conditions = build_grid(cfg)
    providers = {m["id"]: m.get("provider", "openrouter") for m in cfg["models"]}
    catalog = httpx.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]
    pricing = {m["id"]: m["pricing"] for m in catalog}
    pricing.update(MANUAL_PRICING)  # non-OpenRouter models (e.g. odincore)
    for mid, src in PROXY_PRICE.items():  # alexandra-qwen priced off OpenRouter's qwen
        if mid not in pricing and src in pricing:
            pricing[mid] = pricing[src]

    or_total = 0.0        # OpenRouter balance (the user's $5)
    or_batch = 0.0
    free_total = 0.0      # non-OpenRouter free-credit pools (odincore, alexandra)
    print(f"{'model':45s} {'kald':>6s} {'est. pris':>10s}")
    for model_cfg in cfg["models"]:
        mid = model_cfg["id"]
        conds = [c for c in conditions if c.model.id == mid]
        if mid not in pricing:
            print(f"{mid:45s} {'?':>6s}  IKKE FUNDET i OpenRouter-kataloget!")
            continue
        p_in = float(pricing[mid]["prompt"])
        p_out = float(pricing[mid]["completion"])
        # ~3.5 chars/token is a reasonable estimate for Danish text
        out_tokens = COMPLETION_OVERRIDES.get(mid, ASSUMED_COMPLETION_TOKENS)
        cost = sum(
            (len(c.system_prompt + c.user_prompt) / 3.5) * p_in
            + out_tokens * p_out
            for c in conds
        )
        on_openrouter = providers.get(mid, "openrouter") == "openrouter"
        if on_openrouter:
            or_total += cost
            batchable = mid.startswith(BATCH_PREFIXES)
            or_batch += cost * (0.5 if batchable else 1.0)
            suffix = ""
        else:
            free_total += cost
            suffix = f" [{FREE_CREDIT_NOTE.get(mid, providers[mid])}, ikke OpenRouter]"
        print(f"{mid:45s} {len(conds):>6d} {cost:>9.2f}${suffix}")

    reasoning_conds = [c for c in conditions if c.model.id in REASONING_TRACE_TOKENS]
    for judge_id in cfg["judge"]["models"]:
        if judge_id not in pricing:
            print(f"{judge_id:45s} {'?':>6s}  IKKE FUNDET i OpenRouter-kataloget!")
            continue
        jp = pricing[judge_id]
        p_in, p_out = float(jp["prompt"]), float(jp["completion"])
        judge_batchable = 0.5 if judge_id.startswith(BATCH_PREFIXES) else 1.0
        judge_cost = len(conditions) * (
            JUDGE_PROMPT_TOKENS * p_in + JUDGE_COMPLETION_TOKENS * p_out
        )
        or_total += judge_cost                    # all judges run on OpenRouter
        or_batch += judge_cost * judge_batchable
        print(f"{judge_id + ' (judge, tone)':45s} {len(conditions):>6d} {judge_cost:>9.2f}$")
        r_cost = sum(
            (REASONING_RUBRIC_TOKENS + REASONING_TRACE_TOKENS[c.model.id]) * p_in
            + REASONING_COMPLETION_TOKENS * p_out
            for c in reasoning_conds
        )
        or_total += r_cost
        or_batch += r_cost * judge_batchable
        print(f"{judge_id + ' (judge, reasoning)':45s} {len(reasoning_conds):>6d} {r_cost:>9.2f}$")

    print("-" * 72)
    print(f"{'OpenRouter-saldo — streaming':52s} {or_total:>9.2f}$")
    print(f"{'OpenRouter-saldo — batch':52s} {or_batch:>9.2f}$")
    print(f"{'Fri kredit (odincore + alexandra, IKKE OpenRouter)':52s} {free_total:>9.2f}$"
          f"  ~ {free_total * DKK_PER_USD:.0f} DKK")
    print(f"{'Alt i alt (streaming)':52s} {or_total + free_total:>9.2f}$")
    print("\nNB: Testmodeller på fri kredit (odin-2-large→odincore, qwen3.5-397b→alexandra) "
          "belaster IKKE OpenRouter-saldoen. Reasoning-modeller kan bruge flere "
          "completion-tokens end antaget — sammenlign faktisk forbrug på udbydernes "
          "aktivitets-sider efter de første kald.")


if __name__ == "__main__":
    main()
