"""OpenRouter Batch API (beta): submit, poll, collect.

Batch requests bill at ~50% of standard token pricing with a 24h completion
window; one model slug per batch. Outstanding batch ids and their in-flight
keys are persisted in <out_path>.batches.json so an interrupted poll resumes
instead of resubmitting (resubmission would double-bill). Requests that a
batch drops or fails simply stay not-done and are resubmitted on the next
--batch invocation, mirroring the streaming retry semantics.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable

import httpx
from dotenv import load_dotenv

BATCH_URL = "https://openrouter.ai/api/beta/batches"
POLL_INTERVAL_S = 60
# OpenRouter rejects a submission of more than 5,000 requests with 413, so a
# model's pending requests are split into chunks of at most this many and
# submitted as several batches. State is keyed by batch id, so several
# batches per model need no special handling downstream.
# Set to 1250 (2026-08-24): two 5,000-request batches sat at 0/5000 with
# usage=None for 7+ hours, while a 1,378-request batch for the same model
# submitted and collected in ~45 min. The beta API exposes no cancel
# operation, so oversized batches can only be waited out to the 24h window.
MAX_BATCH_REQUESTS = 1250
TERMINAL_STATUSES = {"completed", "failed", "expired", "cancelled"}


def _headers() -> dict:
    load_dotenv()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY mangler. Kopiér .env.example til .env og indsæt din nøgle."
        )
    return {"Authorization": f"Bearer {api_key}"}


def state_path(out_path: Path) -> Path:
    return out_path.with_suffix(out_path.suffix + ".batches.json")


def _load_state(out_path: Path) -> dict:
    p = state_path(out_path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"batches": {}}


def _save_state(out_path: Path, state: dict) -> None:
    state_path(out_path).write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class BatchUnsupportedError(Exception):
    """The model has no :batch endpoint on OpenRouter (per-model support)."""


class BatchSubmitError(Exception):
    """Submission rejected (e.g. 402 insufficient credits). The requests
    stay not-done; a later invocation resubmits them."""


def submit(model: str, requests: list[dict]) -> str:
    # endpoint and model must serialize before requests: the API
    # stream-parses the body to handle large request arrays.
    payload = {"endpoint": "/v1/chat/completions", "model": model, "requests": requests}
    r = httpx.post(BATCH_URL, headers=_headers(), json=payload, timeout=300)
    if r.status_code == 400 and "does not have a :batch endpoint" in r.text:
        raise BatchUnsupportedError(model)
    if r.status_code >= 400:
        raise BatchSubmitError(f"({r.status_code}) {r.text[:400]}")
    return r.json()["id"]


# A poll is a read against a batch we have already submitted AND persisted, so
# a transient failure must never kill the run: the batch keeps running and
# billing regardless, and the crash only costs us the collection. Observed
# twice on 2026-08-30 (and once on 2026-08-25) as a 404 seconds after
# creation — the batch id is not yet visible to the GET route (eventual
# consistency). Retried with backoff rather than failed outright.
POLL_MAX_ATTEMPTS = 6
POLL_RETRY_BACKOFF_S = 10
POLL_RETRY_STATUSES = {404, 408, 409, 425, 429, 500, 502, 503, 504}


def poll(batch_id: str) -> dict:
    """GET one batch's status. Transient errors are retried with linear
    backoff; a persistent failure still raises, so a genuinely bad batch id
    surfaces instead of looping forever."""
    for attempt in range(1, POLL_MAX_ATTEMPTS + 1):
        try:
            r = httpx.get(f"{BATCH_URL}/{batch_id}", headers=_headers(), timeout=120)
            if r.status_code in POLL_RETRY_STATUSES and attempt < POLL_MAX_ATTEMPTS:
                raise httpx.HTTPStatusError(
                    f"({r.status_code}) {r.text[:200]}", request=r.request, response=r
                )
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPStatusError, httpx.TransportError, json.JSONDecodeError) as e:
            if attempt == POLL_MAX_ATTEMPTS:
                raise
            wait = POLL_RETRY_BACKOFF_S * attempt
            print(f"  {batch_id}: poll-fejl ({type(e).__name__}), "
                  f"forsoeg {attempt}/{POLL_MAX_ATTEMPTS} — venter {wait}s.")
            time.sleep(wait)
    raise AssertionError("unreachable")


def _cid(key: str) -> str:
    """Wire custom_id for a condition key: some providers cap custom_id at
    64 chars, so send a short stable hash and keep key mapping in state."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _key_mapping(batch_entry: dict) -> dict[str, str]:
    keys = batch_entry["keys"]
    return keys if isinstance(keys, dict) else {k: k for k in keys}  # legacy list format


def in_flight_keys(out_path: Path) -> set[str]:
    """Keys awaiting results in pending batches. Streaming runners must
    skip these, or an interrupted batch run followed by a streaming run
    would execute (and bill) the same calls twice."""
    state = _load_state(out_path)
    return {k for b in state["batches"].values() for k in _key_mapping(b).values()}


def submit_pending(
    out_path: Path, pending_by_model: dict[str, list[dict]]
) -> list[str]:
    """Submit a batch per model for requests not already in flight.
    Returns the models that have no batch endpoint (caller should fall
    back to streaming for those)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    state = _load_state(out_path)
    in_flight = in_flight_keys(out_path)

    unsupported = []
    for model, requests in pending_by_model.items():
        requests = [r for r in requests if r["custom_id"] not in in_flight]
        if not requests:
            continue
        chunks = [requests[i:i + MAX_BATCH_REQUESTS]
                  for i in range(0, len(requests), MAX_BATCH_REQUESTS)]
        if len(chunks) > 1:
            print(f"{model}: {len(requests)} kald opdeles i {len(chunks)} batches "
                  f"(maks. {MAX_BATCH_REQUESTS} pr. batch).")
        for n, chunk in enumerate(chunks, 1):
            mapping = {_cid(r["custom_id"]): r["custom_id"] for r in chunk}
            wire = [{**r, "custom_id": _cid(r["custom_id"])} for r in chunk]
            try:
                batch_id = submit(model, wire)
            except BatchUnsupportedError:
                print(f"{model}: intet batch-endpoint på OpenRouter — falder tilbage til streaming.")
                unsupported.append(model)
                break
            except BatchSubmitError as e:
                # Stop at the first rejected chunk: a 402/413 will hit the
                # remaining chunks too. Already-submitted chunks stay in
                # state and are polled; this chunk's requests stay not-done
                # and are resubmitted on the next invocation.
                remaining = sum(len(c) for c in chunks[n - 1:])
                print(f"{model}: batch-indsendelse afvist {e} — "
                      f"{remaining} kald udestår; kør kommandoen igen for at genindsende.")
                break
            # Save after every submission: an interruption here must not
            # lose a batch id, or the next run would resubmit and double-bill.
            state["batches"][batch_id] = {"model": model, "keys": mapping}
            _save_state(out_path, state)
            print(f"Batch indsendt: {batch_id} ({len(chunk)} kald, {model}"
                  f"{f', del {n}/{len(chunks)}' if len(chunks) > 1 else ''})")
    return unsupported


def poll_and_collect(
    out_path: Path,
    write_record: Callable[[str, dict | None, str | None], dict | None],
) -> None:
    """Poll all outstanding batches to completion, appending one JSONL
    record per finished request via write_record(custom_id, response_body,
    error). write_record may return None to skip (e.g. key already done)."""
    state = _load_state(out_path)
    if not state["batches"]:
        return
    print(f"Venter på {len(state['batches'])} batch(es) — op til 24 timer. "
          "Afbryd frit; en ny kørsel genoptager polling uden at genindsende.")
    while state["batches"]:
        for batch_id in list(state["batches"]):
            info = poll(batch_id)
            status = info["status"]
            counts = info.get("request_counts") or {}
            model = state["batches"][batch_id]["model"]
            print(f"  {batch_id} ({model}): {status} "
                  f"{counts.get('completed', 0)}/{counts.get('total', '?')}")
            if status not in TERMINAL_STATUSES:
                continue
            mapping = _key_mapping(state["batches"][batch_id])
            written = 0
            with open(out_path, "a", encoding="utf-8") as f:
                for result in info.get("results") or []:
                    body = (result.get("response") or {}).get("body")
                    error = None if body else json.dumps(
                        result.get("error") or {"batch_status": status})
                    key = mapping.get(result["custom_id"], result["custom_id"])
                    record = write_record(key, body, error)
                    if record is not None:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        written += 1
            print(f"  {batch_id}: {status}, {written} resultater skrevet til {out_path.name}")
            del state["batches"][batch_id]
            _save_state(out_path, state)
        if state["batches"]:
            time.sleep(POLL_INTERVAL_S)
