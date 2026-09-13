"""Probe: is Claude Sonnet 5's thinking adaptive when no reasoning param is sent?

STANDALONE DIAGNOSTIC — NOT part of the study. Writes to results/probe/ only.

Question (2026-09-04): Claude's entry in experiment.yaml carries no
`extra_body` and no `reasoning` parameter, yet 1,457 of its 2,304 collected
calls were billed for reasoning tokens. The rate tracks the task
(credit 99.1%, CV screening 20.8%) and the wording (welfare 47.6% under
bullets, 95.5% under prose). Two readings fit:

  (a) the model decides per request — thinking is adaptive by default, or
  (b) something outside the prompt decided it, e.g. OpenRouter routing to
      different upstream endpoints, or a provider default that changed
      during collection.

The collected records cannot separate these: `upstream_provider` was added
after Claude was collected and is null on every one of its rows.

The arms below re-send the study's OWN prompts, unchanged, with the study's
own settings, and vary only one thing at a time:

  A/B     same wording, different task            -> is it the task?
  C/D     same task, different wording            -> is it the wording?
  E       the never-reasoning task, thinking ON   -> can it be forced on?
  F       the always-reasoning task, thinking OFF -> is the parameter delivered?

If A reasons and B does not, under identical settings in the same minutes,
then the choice is being made per request from the prompt — reading (a), and
neither routing nor a time-varying default can explain it.

Result, 2026-09-04 (n=5 for A-D, n=3 for E/F):

  A kredit, no param         5/5 reasoned, median 219 tokens
  B ansaettelse, no param    1/5
  C velfaerd p0, no param    1/5
  D velfaerd p1, no param    5/5
  E ansaettelse + enabled/effort/budget   0/3 each -- cannot be forced ON
  F kredit + enabled:false                0/3      -- CAN be forced OFF
  F2 kredit + exclude:true                3/3 reasoned, 0/3 visible

So: the parameter IS delivered (F turns thinking off), the default is
"permitted, model's discretion", and permission cannot be converted into a
floor -- asking for thinking on the CV-screening prompt does not produce any.
Sending nothing, as the study did, leaves the model to decide per request.
Note this differs from Gemma, whose default is OFF and where
`reasoning: {enabled: true}` does turn it on.

Usage:  python scripts/probe_claude_reasoning.py [--n 5]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402

from biaslab.config import build_grid, load_experiment  # noqa: E402

MODEL = "anthropic/claude-sonnet-5"
BASE_URL = "https://openrouter.ai/api/v1"
OUT = Path("results/probe/claude_reasoning_probe.jsonl")
MAX_TOKENS = 1200          # the study's own cap for this model
TEMPERATURE = 0.0          # the study's own temperature
CONCURRENCY = 4
MAX_ATTEMPTS = 3

# Study cells to reuse verbatim, as (scenario, paraphrase). dansk_mand, rep 0.
CELLS = {
    # A-D: no reasoning parameter at all, exactly as the study sent them.
    "A_kredit_p0":       ("finans_forbrugslaan", 0),
    "B_ansaettelse_p0":  ("ansaettelse_screening", 0),
    "C_velfaerd_p0":     ("velfaerd_enkeltydelse", 0),
    "D_velfaerd_p1":     ("velfaerd_enkeltydelse", 1),
    # E: can thinking be FORCED ON where the model declines to think?
    "E_ansaettelse_on":  ("ansaettelse_screening", 0),
    "E2_ansaettelse_budget": ("ansaettelse_screening", 0),
    "E3_ansaettelse_effort": ("ansaettelse_screening", 0),
    # F: can it be forced OFF where the model always thinks? This is the arm
    # that proves the parameter is delivered at all rather than ignored.
    "F_kredit_off":      ("finans_forbrugslaan", 0),
    "F2_kredit_exclude": ("finans_forbrugslaan", 0),
}
EXTRA_BODY = {
    "E_ansaettelse_on":       {"reasoning": {"enabled": True}},
    "E2_ansaettelse_budget":  {"reasoning": {"max_tokens": 2000}},
    "E3_ansaettelse_effort":  {"reasoning": {"effort": "high"}},
    "F_kredit_off":           {"reasoning": {"enabled": False}},
    "F2_kredit_exclude":      {"reasoning": {"exclude": True}},
}

OBSERVED = {  # collected rate of reasoning_tokens > 0, for comparison
    "A_kredit_p0": 0.997,
    "B_ansaettelse_p0": 0.049,
    "C_velfaerd_p0": 0.538,
    "D_velfaerd_p1": 0.986,
    "E_ansaettelse_on": None,
    "E2_ansaettelse_budget": None,
    "E3_ansaettelse_effort": None,
    "F_kredit_off": None,
    "F2_kredit_exclude": None,
}


def study_prompts() -> dict[str, tuple[str, str]]:
    """The exact system/user prompts the study sent, keyed by arm."""
    cfg = load_experiment()
    # several arms can share one cell (B and E differ only by the parameter),
    # so map cell -> every arm that wants it, not cell -> one arm
    wanted: dict[tuple[str, int], list[str]] = defaultdict(list)
    for arm, cell in CELLS.items():
        wanted[cell].append(arm)
    out: dict[str, tuple[str, str]] = {}
    for c in build_grid(cfg):
        if c.model.id != MODEL or c.persona.id != "dansk_mand" or c.rep != 0:
            continue
        for arm in wanted.get((c.scenario.id, c.paraphrase), []):
            out.setdefault(arm, (c.system_prompt, c.user_prompt))
    return out


async def one_call(client, sem, arm, system_prompt, user_prompt, i):
    async with sem:
        kwargs = dict(
            model=MODEL,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_prompt}],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        if arm in EXTRA_BODY:
            kwargs["extra_body"] = EXTRA_BODY[arm]
        last = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                r = await client.chat.completions.create(**kwargs)
                msg = r.choices[0].message
                usage = r.usage.model_dump() if r.usage else {}
                details = usage.get("completion_tokens_details") or {}
                return {
                    "arm": arm, "i": i,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reasoning_tokens": details.get("reasoning_tokens")
                                        or usage.get("reasoning_tokens") or 0,
                    "completion_tokens": usage.get("completion_tokens"),
                    "reasoning": getattr(msg, "reasoning", None)
                                 or getattr(msg, "reasoning_content", None) or "",
                    "content": (msg.content or "")[:400],
                    "sent_reasoning_param": arm in EXTRA_BODY,
                    "error": None,
                }
            except Exception as exc:  # noqa: BLE001 - diagnostic script
                last = f"{type(exc).__name__}: {exc}"
                await asyncio.sleep(2 * (attempt + 1))
        return {"arm": arm, "i": i, "error": last, "reasoning_tokens": None}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5, help="calls per arm")
    args = ap.parse_args()

    load_dotenv()
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY mangler i .env")

    prompts = study_prompts()
    missing = [a for a in CELLS if a not in prompts]
    if missing:
        raise SystemExit(f"Kunne ikke finde prompts for: {missing}")

    client = AsyncOpenAI(api_key=key, base_url=BASE_URL)
    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [one_call(client, sem, arm, *prompts[arm], i)
             for arm in CELLS for i in range(args.n)]
    print(f"{len(tasks)} kald ({args.n} pr. arm), model={MODEL}, "
          f"temperature={TEMPERATURE}, max_tokens={MAX_TOKENS}")
    results = await asyncio.gather(*tasks)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    by_arm = defaultdict(list)
    for r in results:
        by_arm[r["arm"]].append(r)
    print(f"\n{'arm':32s}{'param':>7s}{'taenkte':>9s}{'median tok':>12s}{'i studiet':>11s}")
    for arm in CELLS:
        rows = [r for r in by_arm[arm] if r.get("error") is None]
        if not rows:
            print(f"{arm:32s}  ALLE KALD FEJLEDE: {by_arm[arm][0].get('error')}")
            continue
        pos = [r["reasoning_tokens"] for r in rows if (r["reasoning_tokens"] or 0) > 0]
        med = sorted(pos)[len(pos) // 2] if pos else 0
        obs = OBSERVED[arm]
        print(f"{arm:32s}{('ja' if arm in EXTRA_BODY else 'nej'):>7s}"
              f"{len(pos):5d}/{len(rows):<3d}{med:12d}"
              f"{(f'{obs:.1%}' if obs is not None else '-'):>11s}")
    errs = [r for r in results if r.get("error")]
    if errs:
        print(f"\n{len(errs)} fejlede kald, fx: {errs[0]['error'][:160]}")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
