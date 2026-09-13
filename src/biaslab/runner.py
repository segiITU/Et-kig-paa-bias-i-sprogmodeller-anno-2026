"""Async experiment runner against OpenRouter (primary) and any other
OpenAI-compatible provider configured per-model (see PROVIDERS below).

Writes one JSONL record per completed call and skips already-completed
conditions on restart, so an interrupted run can simply be re-run.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from tqdm import tqdm

from . import batch
from .config import Condition
from .parsing import extract_json, validate

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_ATTEMPTS = 5

# Model providers beyond OpenRouter. odincore (ordbogen.ai's odin-2-large,
# added 2026-08-23) serves a standard OpenAI-compatible Chat Completions
# endpoint — same request/response shape as OpenRouter, just a different
# host/key — so _call_one needs no branching, only the right client per
# condition's cond.model.provider.
# Reasoning text: odincore exposes no reasoning field anywhere (message has
# none; include_reasoning is a no-op; Responses' reasoning.summary stays
# empty) — BUT with `logprobs: true` their vLLM backend returns logprobs for
# the ENTIRE generation, hidden reasoning included, and usage.
# completion_tokens_details.reasoning_tokens is the exact split index
# (discovered 2026-08-23 evening; see _reasoning_from_logprobs). The odin
# model entry in experiment.yaml therefore carries extra_body.logprobs: true.
# NB odincore silently IGNORES max_tokens — only max_completion_tokens
# actually caps generation (also in that entry's extra_body).
#
# alexandra (platform.alexandra.dk, added 2026-08-23) serves the SAME Qwen
# model as OpenRouter (wire id "qwen3.5-397b") on 200 DKK free credits — used
# ONLY for qwen. Also OpenAI-compatible, but returns hidden reasoning under a
# THIRD field name: message.reasoning_content (OpenRouter uses .reasoning,
# odincore uses none), and the reasoning-token count at top-level
# usage.reasoning_tokens (not nested under completion_tokens_details). Both
# are handled by the fallback chains in _call_one. The OpenRouter-style
# reasoning budget param is silently ignored here (verified 2026-08-23), so
# the qwen entry drops it; Qwen reasons ~3-5k tokens by default regardless.
PROVIDERS = {
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "odincore": ("https://api.ordbogen.ai/v1", "ODINCORE_API_KEY"),
    "alexandra": ("https://inference.alexandra.dk/v1", "QWEN_API_KEY"),
}


def get_client(provider: str = "openrouter") -> AsyncOpenAI:
    load_dotenv()
    base_url, api_key_env = PROVIDERS[provider]
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise SystemExit(
            f"{api_key_env} mangler. Kopiér .env.example til .env og indsæt din nøgle."
        )
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


def _clients_for(conditions: list) -> dict[str, AsyncOpenAI]:
    """One client per distinct provider actually present in the grid, so a
    run that never touches odincore doesn't require ODINCORE_API_KEY. Also
    builds clients for any configured fallback_provider, since a primary
    failure routes there (so those keys must be present too)."""
    providers = {c.model.provider for c in conditions}
    providers |= {c.model.fallback_provider for c in conditions
                  if c.model.fallback_provider}
    return {p: get_client(p) for p in providers}


def load_done_keys(out_path: Path) -> set[str]:
    """Keys with usable output. Records that failed (empty parse, no judge
    scores) do not count as done, so they are retried on the next run."""
    if not out_path.exists():
        return set()
    done = set()
    with open(out_path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                if rec.get("parsed") or rec.get("judge_scores"):
                    done.add(rec["key"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def _reasoning_from_logprobs(resp) -> str | None:
    """Recover hidden reasoning from odincore's logprobs (2026-08-23).

    With `logprobs: true`, odincore's vLLM backend returns one logprob entry
    per token of the ENTIRE generation — hidden reasoning first, then the
    visible answer — while message.content still holds only the answer.
    usage.completion_tokens_details.reasoning_tokens is the exact split
    index (verified byte-exact against message.content).

    Their shape is non-standard: a LIST of {"content": [{token, ...}]}
    objects, one per token, instead of OpenAI's single {content: [...]}
    object. The list shape is deliberately used as the gate here: for a
    provider returning STANDARD logprobs (visible tokens only), slicing the
    first reasoning_tokens entries would mislabel answer text as reasoning.
    """
    lp = resp.choices[0].logprobs
    if not isinstance(lp, list):
        return None
    details = getattr(resp.usage, "completion_tokens_details", None)
    n = getattr(details, "reasoning_tokens", None) if details else None
    if not n:
        return None
    tokens: list[str] = []
    for entry in lp:
        # The SDK parses each list element into a ChoiceLogprobs pydantic
        # object; raw JSON (httpx) yields dicts. Handle both.
        content = (entry.get("content") if isinstance(entry, dict)
                   else getattr(entry, "content", None))
        for t in content or []:
            tok = t.get("token") if isinstance(t, dict) else getattr(t, "token", None)
            if tok is not None:
                tokens.append(tok)
    if len(tokens) < n:
        return None
    return "".join(tokens[:n]).strip() or None


# Substrings that mark a "this provider can't serve" error (out of credit /
# over quota / billing) — retrying the SAME provider is pointless, so fall
# back immediately instead of burning MAX_ATTEMPTS. The retry-exhaustion path
# in _call_one is a second, format-agnostic safety net, so this list only
# needs to catch the common cases to make the fallback fast.
CREDIT_ERROR_HINTS = ("insufficient", "credit", "balance", "quota",
                      "payment", "billing", "402")


def _is_credit_error(e: Exception) -> bool:
    status = getattr(e, "status_code", None)
    if status is None:
        status = getattr(getattr(e, "response", None), "status_code", None)
    if status == 402:
        return True
    msg = str(e).lower()
    return any(h in msg for h in CREDIT_ERROR_HINTS)


async def _try_provider(
    client: AsyncOpenAI, model_id: str, cond: Condition, sampling: dict
) -> tuple[dict | None, bool, Exception | None]:
    """Up to MAX_ATTEMPTS against ONE provider/client. Returns
    (record | None, credit_exhausted, last_error). The record's `model` field
    is the CONFIG id (cond.model.id), not `model_id` — so analysis groups a
    model as one even when a fallback served it under a different wire id;
    `served_by` (added by _call_one) records who actually answered."""
    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = await client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": cond.system_prompt},
                    {"role": "user", "content": cond.user_prompt},
                ],
                temperature=sampling["temperature"],
                max_tokens=cond.model.max_tokens or sampling["max_tokens"],
                timeout=sampling["request_timeout_s"],
                extra_body=cond.model.extra_body or None,
            )
            msg = resp.choices[0].message
            text = msg.content or ""
            # Empty content is never usable output in this pipeline (the
            # answer must be a JSON object), so treat it as a failed
            # attempt and retry instead of burning the cell until the
            # next manual rerun. Observed on odincore's odin-2-large
            # (2026-08-23): reasoning_effort=medium made it abort after
            # the hidden reasoning with finish_reason "stop" and content
            # "" — the config no longer sets that param, but the guard
            # protects against any provider's transient empty responses.
            if not text.strip():
                raise ValueError(
                    f"empty_content (reasoning_tokens spent: "
                    f"{getattr(getattr(resp.usage, 'completion_tokens_details', None), 'reasoning_tokens', None)})"
                )
            # Hidden reasoning arrives under a different non-standard field
            # per provider: OpenRouter uses message.reasoning, alexandra
            # uses message.reasoning_content. Both land in the SDK message's
            # model_extra. odincore exposes neither and needs the logprobs
            # reconstruction below.
            reasoning = getattr(msg, "reasoning", None)
            msg_extra = getattr(msg, "model_extra", None) or {}
            if reasoning is None:
                reasoning = msg_extra.get("reasoning") or msg_extra.get("reasoning_content")
            if reasoning is None:
                # odincore path: reasoning recovered from full-generation
                # logprobs (requested via the model's extra_body).
                reasoning = _reasoning_from_logprobs(resp)
            parsed = extract_json(text)
            clean, errors = validate(parsed, cond.scenario.output_schema)
            usage = resp.usage
            # OpenRouter reports hidden-reasoning token spend under
            # usage.completion_tokens_details.reasoning_tokens (OpenAI-style
            # usage shape). Captured for all models, but added specifically
            # to check whether reasoning "effort"/budget interacts with how
            # bias is expressed.
            details = getattr(usage, "completion_tokens_details", None)
            reasoning_tokens = getattr(details, "reasoning_tokens", None) if details else None
            # alexandra reports it at top-level usage.reasoning_tokens
            # instead of nested under completion_tokens_details.
            if reasoning_tokens is None:
                reasoning_tokens = getattr(usage, "reasoning_tokens", None)
                if reasoning_tokens is None and getattr(usage, "model_extra", None):
                    reasoning_tokens = usage.model_extra.get("reasoning_tokens")
            # OpenRouter is a ROUTER: for open-weight models it load-balances
            # across many third-party hosts at differing quantizations (Gemma
            # has 16 endpoints spanning fp4/fp8/bf16/fp16), and it switches
            # between them mid-run — 6 identical calls on 2026-08-30 split 3
            # DeepInfra / 3 CoreWeave. The reply names the host in a top-level
            # `provider` field; store it, because `served_by` only records the
            # provider LAYER ("openrouter") and `call_id` is a local uuid4, so
            # without this the upstream host is unrecoverable after the fact.
            # None for non-OpenRouter providers, which don't send the field.
            upstream = (getattr(resp, "model_extra", None) or {}).get("provider")
            return {
                "key": cond.key,
                "call_id": str(uuid.uuid4()),
                "upstream_provider": upstream,
                "model": cond.model.id,
                "scenario": cond.scenario.id,
                "domaene": cond.scenario.domaene,
                "persona": cond.persona.id,
                "koen": cond.persona.koen,
                "baggrund": cond.persona.baggrund,
                "framing": cond.framing,
                "paraphrase": cond.paraphrase,
                "rep": cond.rep,
                "raw_text": text,
                "reasoning": reasoning,
                "parsed": clean,
                "parse_errors": errors,
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "reasoning_tokens": reasoning_tokens,
                "temperature": sampling["temperature"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, False, None
        except Exception as e:  # noqa: BLE001 — retry on any transport/API error
            last_error = e
            if _is_credit_error(e):
                return None, True, e  # pointless to retry this provider
            await asyncio.sleep(min(60, 2**attempt + random.random() * 2))
    return None, False, last_error


def _failure_record(cond: Condition, sampling: dict, served_by: str,
                    error: Exception | None) -> dict:
    return {
        "key": cond.key,
        "call_id": str(uuid.uuid4()),
        "model": cond.model.id,
        "scenario": cond.scenario.id,
        "domaene": cond.scenario.domaene,
        "persona": cond.persona.id,
        "koen": cond.persona.koen,
        "baggrund": cond.persona.baggrund,
        "framing": cond.framing,
        "paraphrase": cond.paraphrase,
        "rep": cond.rep,
        "raw_text": None,
        "reasoning": None,
        "parsed": {},
        "parse_errors": [f"request_failed:{type(error).__name__}:{error}"],
        "prompt_tokens": None,
        "completion_tokens": None,
        "reasoning_tokens": None,
        "temperature": sampling["temperature"],
        "served_by": served_by,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _call_one(
    clients: dict[str, AsyncOpenAI], cond: Condition, sampling: dict,
    sem: asyncio.Semaphore
) -> dict:
    """Run one condition against its provider, falling back to
    cond.model.fallback_provider if the primary can't serve it. Stamps
    `served_by` on the record so a fallback is tagged, never silent."""
    async with sem:
        primary = cond.model.provider
        record, credit_out, err = await _try_provider(
            clients[primary], cond.model.id, cond, sampling)
        served = primary
        fb = cond.model.fallback_provider
        if record is None and fb and fb in clients:
            fb_id = cond.model.fallback_id or cond.model.id
            reason = "kredit opbrugt/kvote" if credit_out else "opgav efter gentagne forsøg"
            print(f"[fallback] {cond.key}: {primary} fejlede ({reason}) "
                  f"→ {fb} ({fb_id})")
            record, _, err = await _try_provider(
                clients[fb], fb_id, cond, sampling)
            served = fb
        if record is not None:
            record["served_by"] = served
            return record
        return _failure_record(cond, sampling, served, err)


def run_batch(conditions: list[Condition], sampling: dict, out_path: Path) -> None:
    """Same grid, same output records — via the OpenRouter Batch API
    (~50% token price, up to 24h). Resumable exactly like streaming mode.

    Batch submission is OpenRouter-specific: non-"openrouter" providers
    (e.g. odincore) are never submitted there — no evidence odincore offers
    a batch/async discount endpoint, and submitting its model id to
    OpenRouter's batch job would just fail against the wrong API. Those
    conditions always run via streaming instead.
    """
    done = load_done_keys(out_path)
    todo = [c for c in conditions if c.key not in done]
    print(f"{len(done)} allerede kørt, {len(todo)} tilbage.")
    if not todo:
        return

    non_batch_todo = [c for c in todo if c.model.provider != "openrouter"]
    if non_batch_todo:
        print(f"Kører {len(non_batch_todo)} kald via streaming "
              f"(provider uden batch-understøttelse: "
              f"{sorted({c.model.provider for c in non_batch_todo})}).")
        asyncio.run(run(non_batch_todo, sampling, out_path))

    todo = [c for c in todo if c.model.provider == "openrouter"]
    if not todo:
        return

    by_model: dict[str, list[dict]] = {}
    for c in todo:
        body = {
            "messages": [
                {"role": "system", "content": c.system_prompt},
                {"role": "user", "content": c.user_prompt},
            ],
            "temperature": sampling["temperature"],
            "max_tokens": c.model.max_tokens or sampling["max_tokens"],
            **(c.model.extra_body or {}),
        }
        by_model.setdefault(c.model.id, []).append({"custom_id": c.key, "body": body})

    cond_by_key = {c.key: c for c in todo}
    written: set[str] = set()

    def write_record(key: str, body: dict | None, error: str | None) -> dict | None:
        cond = cond_by_key.get(key)
        if cond is None or key in done or key in written:
            return None
        written.add(key)
        record = {
            "key": key,
            "call_id": str(uuid.uuid4()),
            "model": cond.model.id,
            "scenario": cond.scenario.id,
            "domaene": cond.scenario.domaene,
            "persona": cond.persona.id,
            "koen": cond.persona.koen,
            "baggrund": cond.persona.baggrund,
            "framing": cond.framing,
            "paraphrase": cond.paraphrase,
            "rep": cond.rep,
            "raw_text": None,
            "reasoning": None,
            "parsed": {},
            "parse_errors": [f"batch_failed:{error}"],
            "prompt_tokens": None,
            "completion_tokens": None,
            "reasoning_tokens": None,
            "temperature": sampling["temperature"],
            "served_by": "openrouter",  # the batch path is OpenRouter-only
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if body:
            msg = body["choices"][0]["message"]
            text = msg.get("content") or ""
            parsed = extract_json(text)
            clean, errors = validate(parsed, cond.scenario.output_schema)
            usage = body.get("usage") or {}
            details = usage.get("completion_tokens_details") or {}
            record.update(
                raw_text=text,
                reasoning=msg.get("reasoning"),
                parsed=clean,
                parse_errors=errors,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                reasoning_tokens=details.get("reasoning_tokens"),
            )
        return record

    unsupported = batch.submit_pending(out_path, by_model)
    if unsupported:
        streaming_conds = [c for c in todo if c.model.id in unsupported]
        print(f"Kører {len(streaming_conds)} kald via streaming (modeller uden batch-endpoint).")
        asyncio.run(run(streaming_conds, sampling, out_path))
    batch.poll_and_collect(out_path, write_record)


async def run(conditions: list[Condition], sampling: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = load_done_keys(out_path)
    in_flight = batch.in_flight_keys(out_path)
    todo = [c for c in conditions if c.key not in done and c.key not in in_flight]
    if in_flight:
        print(f"{len(in_flight)} kald afventer i batches og springes over.")
    print(f"{len(done)} allerede kørt, {len(todo)} tilbage.")
    if not todo:
        return

    clients = _clients_for(todo)
    sem = asyncio.Semaphore(sampling["concurrency"])
    write_lock = asyncio.Lock()
    progress = tqdm(total=len(todo), unit="call")

    async def worker(cond: Condition) -> None:
        record = await _call_one(clients, cond, sampling, sem)
        async with write_lock:
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        progress.update(1)

    try:
        await asyncio.gather(*(worker(c) for c in todo))
    finally:
        progress.close()
        await asyncio.gather(*(c.close() for c in clients.values()))
