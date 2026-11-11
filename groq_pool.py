#!/usr/bin/env python3
"""
Groq Pool Bridge — one OpenAI-compatible endpoint in front of several Groq
free-tier accounts.

Why this exists
---------------
Groq's free tier is per account: 8,000 tokens/min and ~1,000 requests/day for
`qwen/qwen3.8-27b`. One account cannot carry a coding agent's ~35k-token turn,
and a client that retries a failed generation burns the daily budget in minutes.
This bridge pools N accounts behind 127.0.0.1 and makes the pool behave better
than the sum of its parts:

  * Picks the key with the most tokens left in the current minute (state is read
    from Groq's own `x-ratelimit-*` response headers on every call).
  * Rotates to the next account only on things another account can fix:
    429 (rate/quota), 401 (bad key), 403 (blocked model on that project), 5xx.
  * Treats 413 (request larger than the model's per-minute cap) as TERMINAL.
    Every free account has the same cap, so rotating would just waste requests.
  * Never sends a streamed header before the upstream status is known: the
    upstream 429/413 comes back as a real HTTP status, so clients never see
    "200 then socket closed" and never enter a retry storm.
  * Buffers Qwen tool turns (Groq's streamed tool-call grammar occasionally
    splits a call) and replays the finished completion as SSE.
  * Exposes real context windows in /v1/models and /health. No context padding;
    the window a model advertises is the window it has.

Config (environment, loaded from BruceAI/.env when present)
-----------------------------------------------------------
  GROQ_KEYS            "label=key,label=key" or newline/semicolon separated.
                       A file `groq_keys.txt` next to this script is also read.
                       GROQ_API_KEY is used as a last-resort single key.
  POOL_MAX_ATTEMPTS    max accounts tried per request (default 4)
  POOL_COOLDOWN_429    fallback cooldown seconds when Retry-After is absent (10)
  POOL_BUFFERED_MODELS comma list of models whose tool turns are buffered
                       (default qwen/qwen3.8-27b)
  POOL_CACHE=1         exact-match response cache (SQLite, default off; TTL 600 s)
  POOL_CACHE_TTL       seconds a cached answer stays valid
  POOL_DUP_LIMIT       identical requests per POOL_DUP_WINDOW (60 s) before the
                       bridge refuses with 429 instead of burning quota
  pool_bots.py         optional hook: answer(payload) -> completion dict | None,
                       for LLM calls that a local Python bot/DB should reply to.

Run:
  python groq_pool.py --port 8081
  curl http://127.0.0.1:8081/health
"""

import os
import re
import json
import time
import hashlib
import inspect
import sqlite3
import asyncio
from collections import deque
from typing import Any, Dict, List, Optional, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, ConfigDict
import uvicorn
import httpx

try:
    from env_loader import load_dotenv, sanitize_proxy_env
except ImportError:
    def load_dotenv(*_a, **_k):
        return {}

    def sanitize_proxy_env():
        return None

load_dotenv()
sanitize_proxy_env()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GROQ_API_BASE = "https://api.groq.com/openai/v1"

DEFAULT_MODEL = "openai/gpt-oss-120b"

# context_window is what the client may plan with; max_output is Groq's hard cap.
MODEL_META: Dict[str, Dict[str, int]] = {
    "openai/gpt-oss-120b": {"context_window": 131072, "max_output": 65536},
    "openai/gpt-oss-20b": {"context_window": 131072, "max_output": 32768},
    "qwen/qwen3.8-27b": {"context_window": 131072, "max_output": 16384},
    "allam-2-7b": {"context_window": 4096, "max_output": 4096},
}
GROQ_MODELS = list(MODEL_META)

BUFFERED_MODELS = {
    m.strip()
    for m in os.environ.get("POOL_BUFFERED_MODELS", "qwen/qwen3.8-27b").split(",")
    if m.strip()
}
MAX_ATTEMPTS = max(1, int(os.environ.get("POOL_MAX_ATTEMPTS", "4")))
COOLDOWN_429 = max(1.0, float(os.environ.get("POOL_COOLDOWN_429", "10")))
# Groq's free per-minute input cap. A turn above it 413s on every account, so
# send it straight to the same-model fallback instead of uploading it 4 times.
GROQ_TPM_CAP = max(1000, int(os.environ.get("POOL_GROQ_TPM", "7000")))
MS_HEADER_TIMEOUT = max(10.0, float(os.environ.get("POOL_MS_HEADER_TIMEOUT", "60")))
# Qwen 3.x reasons before it answers. Qoder shows that as dead air (a spinner
# with no tokens), so the ModelScope hop asks for thinking off by default;
# POOL_MS_THINKING=1 restores it for deep-coding turns.
MS_THINKING = os.environ.get("POOL_MS_THINKING", "0") == "1"

# Local answers: an optional Python bot (pool_bots.py) and/or an exact-match
# response cache can answer a call without spending Groq tokens. The duplicate
# guard stops a client/bot loop from re-sending the same request forever.
CACHE_ENABLED = os.environ.get("POOL_CACHE", "0") == "1"
CACHE_TTL = max(1.0, float(os.environ.get("POOL_CACHE_TTL", "600")))
CACHE_MAX_ROWS = max(10, int(os.environ.get("POOL_CACHE_MAX_ROWS", "500")))
DUP_LIMIT = max(2, int(os.environ.get("POOL_DUP_LIMIT", "12")))
DUP_WINDOW = max(5.0, float(os.environ.get("POOL_DUP_WINDOW", "60")))
CACHE_PATH = os.path.join(BASE_DIR, "pool_cache.db")

# Request dumps: POOL_DUMP=1 writes each incoming payload to logs/pool_dumps so the
# prompt can be decomposed (what a turn really costs). Off by default.
DUMP_ENABLED = os.environ.get("POOL_DUMP", "0") == "1"
DUMP_DIR = os.environ.get("POOL_DUMP_DIR", os.path.join(BASE_DIR, "logs", "pool_dumps"))
DUMP_MAX = max(1, int(os.environ.get("POOL_DUMP_MAX", "8")))
_dump_count = 0


def dump_payload(payload: Dict[str, Any]) -> None:
    global _dump_count
    if not DUMP_ENABLED or _dump_count >= DUMP_MAX:
        return
    try:
        os.makedirs(DUMP_DIR, exist_ok=True)
        _dump_count += 1
        path = os.path.join(DUMP_DIR, f"req_{int(time.time() * 1000)}_{_dump_count}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        print(f"[pool] dumped request #{_dump_count} -> {path}", flush=True)
    except OSError as exc:
        print(f"[pool] dump failed: {exc!r}", flush=True)

# Same-model escape hatch when every Groq account refuses: Cloudflare Workers AI
# serves the same open models with a different (free daily) budget. Used only
# after Groq gives 413/429/5xx on all usable keys. Cloudflare's own daily neuron
# allowance is account-wide and resets at 00:00 UTC (05:30 IST).
CF_MODEL = "qwen/qwen3.8-27b"
CLOUDFLARE_API_KEY = os.environ.get("CLOUDFLARE_API_KEY")
CLOUDFLARE_AI_BASE = os.environ.get("CLOUDFLARE_AI_BASE")
CLOUDFLARE_QWEN_MODEL = os.environ.get("CLOUDFLARE_QWEN_MODEL", "@cf/qwen/qwen3.8-27b")
CLOUDFLARE_GPT_OSS_MODEL = os.environ.get("CLOUDFLARE_GPT_OSS_MODEL", "@cf/openai/gpt-oss-120b")
# groq model id -> cloudflare model id
CLOUDFLARE_MODELS = {
    "qwen/qwen3.8-27b": CLOUDFLARE_QWEN_MODEL,
    "openai/gpt-oss-120b": CLOUDFLARE_GPT_OSS_MODEL,
}
CF_ENABLED = bool(CLOUDFLARE_API_KEY and CLOUDFLARE_AI_BASE) and os.environ.get("POOL_CF_FALLBACK", "1") == "1"

# Preferred escape hatch for large turns: ModelScope API-Inference serves the same
# Qwen with 2,000 free calls/day and no card, at ~37K-token prompts. Note the host:
# a token minted on www.modelscope.ai authenticates on api-inference.modelscope.ai
# and is rejected with 401 by the .cn host. ModelScope has no gpt-oss, so that
# model keeps Cloudflare as its only fallback.
MODEL_SCOPE_API_KEY = os.environ.get("MODEL_SCOPE_API_KEY")
MODEL_SCOPE_BASE = os.environ.get("MODEL_SCOPE_BASE", "https://api-inference.modelscope.ai/v1")
MODEL_SCOPE_QWEN_MODEL = os.environ.get("MODEL_SCOPE_QWEN_MODEL", "Qwen/Qwen3.8-27B")
# groq model id -> modelscope model id
MODEL_SCOPE_MODELS = {
    "qwen/qwen3.8-27b": MODEL_SCOPE_QWEN_MODEL,
}
MS_ENABLED = bool(MODEL_SCOPE_API_KEY) and os.environ.get("POOL_MS_FALLBACK", "1") == "1"


# ─── MODELS ──────────────────────────────────────────────────────────────
class Message(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str
    content: Optional[Any] = None
    name: Optional[str] = None
    tool_calls: Optional[List[Any]] = None
    tool_call_id: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    top_p: Optional[float] = 1.0
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0
    stop: Optional[List[str]] = None
    tools: Optional[List[Any]] = None
    tool_choice: Optional[Any] = None


def resolve_model(model: str) -> str:
    """Unknown names (including "auto") fall back to the default model."""
    return model if model in MODEL_META else DEFAULT_MODEL


def clamp_output_tokens(model: str, payload: Dict[str, Any]) -> None:
    cap = MODEL_META.get(model, {}).get("max_output")
    if not cap:
        return
    for key in ("max_tokens", "max_completion_tokens"):
        value = payload.get(key)
        if isinstance(value, int) and value > cap:
            payload[key] = cap
            print(f"[pool] clamped {key} {value} -> {cap} for {model}", flush=True)


def is_tool_failure(text: str) -> bool:
    low = text.lower()
    return (
        "tool_use_failed" in low
        or "tool call validation failed" in low
        or ("did not match schema" in low and "tool" in low)
    )


def request_hash(payload: Dict[str, Any]) -> str:
    """Stable hash of everything that changes the answer (stream flags excluded)."""
    canon = {k: v for k, v in payload.items() if k not in ("stream", "stream_options")}
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def strip_reasoning(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Remove reasoning traces from an outbound payload.

    Groq's schema rejects an assistant message carrying `reasoning_content`
    ("property 'reasoning_content' is unsupported") with a 400, and Qoder
    echoes the reasoning a fallback model emitted back into the next turn.
    Dropping those keys keeps history valid on every upstream.
    """
    msgs = payload.get("messages")
    if not isinstance(msgs, list):
        return payload
    cleaned = []
    dirty = False
    for m in msgs:
        if isinstance(m, dict) and ("reasoning_content" in m or "reasoning" in m):
            m = {k: v for k, v in m.items() if k not in ("reasoning_content", "reasoning")}
            dirty = True
        cleaned.append(m)
    if not dirty:
        return payload
    return {**payload, "messages": cleaned}


def estimate_input_tokens(payload: Dict[str, Any]) -> int:
    """Rough prompt size (~4 chars/token) plus tools and a safety margin."""
    chars = 0
    for m in payload.get("messages") or []:
        if not isinstance(m, dict):
            continue
        content = m.get("content")
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "image_url":
                        chars += 12000  # an image is not free even at 4 chars/token
                    else:
                        chars += len(str(part.get("text") or ""))
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function") if isinstance(tc, dict) else None
            if isinstance(fn, dict):
                chars += len(str(fn.get("arguments") or ""))
    tools = payload.get("tools")
    if tools:
        chars += len(json.dumps(tools, default=str))
    return chars // 4 + 64


def load_bots():
    """Optional pool_bots.py next to this file: answer(payload) -> dict | awaitable."""
    try:
        import pool_bots  # type: ignore
    except Exception as exc:  # missing or broken hook must not take the bridge down
        if exc.__class__.__name__ != "ModuleNotFoundError":
            print(f"[pool] pool_bots disabled: {exc!r}", flush=True)
        return None
    return pool_bots if hasattr(pool_bots, "answer") else None


# ─── SSE helpers ─────────────────────────────────────────────────────────
def sse_error(status: int, detail: str) -> str:
    err = json.dumps(
        {"error": {"message": str(detail)[:800], "type": "upstream_error", "code": status}}
    )
    return f"data: {err}\n\n" + "data: [DONE]\n\n"


def completion_to_sse(result: Dict[str, Any]):
    """Replay a non-streamed completion as an OpenAI-compatible SSE stream."""
    cid = result.get("id") or "chatcmpl-pool"
    created = result.get("created") or int(time.time())
    model = result.get("model") or ""
    choice = (result.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    finish = choice.get("finish_reason") or ("tool_calls" if msg.get("tool_calls") else "stop")

    def chunk(delta: Dict[str, Any], finish_reason: Optional[str] = None) -> str:
        body = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
        return "data: " + json.dumps(body) + "\n\n"

    yield chunk({"role": "assistant", "content": ""})
    content = msg.get("content") or ""
    for i in range(0, len(content), 500):
        yield chunk({"content": content[i : i + 500]})
    for idx, tc in enumerate(msg.get("tool_calls") or []):
        fn = tc.get("function") or {}
        yield chunk(
            {
                "tool_calls": [
                    {
                        "index": idx,
                        "id": tc.get("id") or f"call_{idx}",
                        "type": "function",
                        "function": {
                            "name": fn.get("name", ""),
                            "arguments": fn.get("arguments", ""),
                        },
                    }
                ]
            }
        )
    yield chunk({}, finish)
    yield "data: [DONE]\n\n"


# ─── KEYS ────────────────────────────────────────────────────────────────
def parse_duration(value: Optional[str]) -> Optional[float]:
    """Groq sends reset windows as "105ms", "46m4.8s", "1h2m". Return seconds."""
    if not value:
        return None
    m = re.fullmatch(r"\s*(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?(?:(\d+(?:\.\d+)?)ms)?\s*", value)
    if not m or not any(m.groups()):
        return None
    h, mi, s, ms = (float(g) if g else 0.0 for g in m.groups())
    return h * 3600 + mi * 60 + s + ms / 1000.0


def looks_like_key(value: str) -> bool:
    v = value.strip()
    return len(v) >= 20 and not v.startswith("<") and " " not in v


def _split_keys(raw: str) -> List[Tuple[str, str]]:
    out = []
    for part in re.split(r"[,;\n\r]+", raw):
        part = part.strip()
        if not part or part.startswith("#"):
            continue
        if "=" in part:
            label, _, key = part.partition("=")
            label = label.strip() or "key"
        else:
            label, key = "key", part
        if looks_like_key(key):
            out.append((label, key.strip()))
    return out


def load_keys() -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    found += _split_keys(os.environ.get("GROQ_KEYS", ""))

    path = os.path.join(BASE_DIR, "groq_keys.txt")
    try:
        with open(path, encoding="utf-8") as fh:
            found += _split_keys(fh.read())
    except OSError:
        pass

    single = os.environ.get("GROQ_API_KEY")
    if single and looks_like_key(single):
        found.append(("primary", single.strip()))

    seen, unique = set(), []
    for label, key in found:
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, key))
    return unique


class KeyState:
    def __init__(self, label: str, key: str):
        self.label = label
        self.key = key
        self.last4 = key[-4:]
        self.tpm_limit: Optional[int] = None
        self.tpm_remaining: Optional[int] = None
        self.req_limit: Optional[int] = None
        self.req_remaining: Optional[int] = None
        self.reset_tokens: Optional[float] = None
        self.cooldown_until = 0.0
        self.blocked_models: set = set()
        self.disabled_reason: Optional[str] = None
        self.ok = 0
        self.fail = 0
        self.tokens_served = 0
        self.last_status: Optional[int] = None
        self.last_used = 0.0

    def auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}

    def usable(self, model: str) -> bool:
        if self.disabled_reason:
            return False
        if model in self.blocked_models:
            return False
        return time.monotonic() >= self.cooldown_until

    def pool_rank(self) -> Tuple[int, float, float]:
        remaining = self.tpm_remaining if self.tpm_remaining is not None else 10**9
        return (-remaining, self.last_used, -self.ok)

    def snapshot(self) -> Dict[str, Any]:
        now = time.monotonic()
        return {
            "label": self.label,
            "key": f"...{self.last4}",
            "tpm": f"{self.tpm_remaining}/{self.tpm_limit}"
            if self.tpm_limit is not None
            else "unknown",
            "requests": f"{self.req_remaining}/{self.req_limit}"
            if self.req_limit is not None
            else "unknown",
            "cooldown_s": round(max(0.0, self.cooldown_until - now), 1),
            "disabled": self.disabled_reason,
            "blocked_models": sorted(self.blocked_models),
            "ok": self.ok,
            "fail": self.fail,
            "tokens_served": self.tokens_served,
            "last_status": self.last_status,
        }


class KeyPool:
    def __init__(self, keys: List[Tuple[str, str]]):
        self.keys = [KeyState(label, key) for label, key in keys]
        self.client = httpx.AsyncClient(
            base_url=GROQ_API_BASE,
            timeout=httpx.Timeout(240.0, connect=10.0),
        )
        self.bots = load_bots()
        self.cache_hits = 0
        self.bot_hits = 0
        self.dup_blocks = 0
        self.recent: Dict[str, deque] = {}
        self.db: Optional[sqlite3.Connection] = None
        if CACHE_ENABLED:
            self.db = sqlite3.connect(CACHE_PATH, check_same_thread=False)
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS responses("
                "hash TEXT PRIMARY KEY, body TEXT NOT NULL, created REAL NOT NULL, model TEXT)"
            )
            self.db.commit()

        self.cf: Optional[httpx.AsyncClient] = None
        self.cf_ok = 0
        self.cf_fail = 0
        if CF_ENABLED:
            self.cf = httpx.AsyncClient(
                base_url=CLOUDFLARE_AI_BASE.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {CLOUDFLARE_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(240.0, connect=10.0),
            )

        self.ms: Optional[httpx.AsyncClient] = None
        self.ms_ok = 0
        self.ms_fail = 0
        if MS_ENABLED:
            self.ms = httpx.AsyncClient(
                base_url=MODEL_SCOPE_BASE.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {MODEL_SCOPE_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(300.0, connect=10.0),
            )

    # ── local answers ────────────────────────────────────────────────────
    def _cache_get(self, key_hash: str) -> Optional[Dict[str, Any]]:
        if not self.db:
            return None
        row = self.db.execute(
            "SELECT body, created FROM responses WHERE hash = ?", (key_hash,)
        ).fetchone()
        if not row:
            return None
        body, created = row
        if time.time() - created > CACHE_TTL:
            self.db.execute("DELETE FROM responses WHERE hash = ?", (key_hash,))
            self.db.commit()
            return None
        return json.loads(body)

    def _cache_put(self, key_hash: str, body: Dict[str, Any]) -> None:
        if not self.db:
            return
        try:
            self.db.execute(
                "INSERT OR REPLACE INTO responses(hash, body, created, model) VALUES (?,?,?,?)",
                (key_hash, json.dumps(body), time.time(), body.get("model")),
            )
            self.db.execute(
                "DELETE FROM responses WHERE hash IN ("
                "SELECT hash FROM responses ORDER BY created DESC LIMIT -1 OFFSET ?)",
                (CACHE_MAX_ROWS,),
            )
            self.db.commit()
        except sqlite3.Error as exc:
            print(f"[pool] cache write failed: {exc}", flush=True)

    def _guard_duplicate(self, key_hash: str) -> None:
        now = time.monotonic()
        window = self.recent.setdefault(key_hash, deque())
        while window and now - window[0] > DUP_WINDOW:
            window.popleft()
        if len(window) >= DUP_LIMIT:
            self.dup_blocks += 1
            raise HTTPException(
                429,
                f"identical request sent {len(window)} times in {DUP_WINDOW:.0f}s; "
                "refusing to spend more quota (possible client or bot loop)",
            )
        window.append(now)
        if len(self.recent) > 5000:
            self.recent.clear()

    async def local_answer(self, payload: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], str]]:
        """Bot or cached answer, without touching Groq."""
        key_hash = request_hash(payload)

        if self.bots:
            try:
                result = self.bots.answer(payload)
                if inspect.isawaitable(result):
                    result = await result
                if isinstance(result, dict):
                    self.bot_hits += 1
                    print("[pool] answered by pool_bots", flush=True)
                    return result, "bot"
            except Exception as exc:
                print(f"[pool] pool_bots failed: {exc!r}", flush=True)

        cached = self._cache_get(key_hash)
        if cached is not None:
            self.cache_hits += 1
            return cached, "cache"

        self._guard_duplicate(key_hash)
        return None

    # ── state ────────────────────────────────────────────────────────────
    def note_response(self, key: KeyState, resp: httpx.Response) -> None:
        key.last_status = resp.status_code
        key.last_used = time.monotonic()
        h = resp.headers
        try:
            if h.get("x-ratelimit-limit-tokens"):
                key.tpm_limit = int(h["x-ratelimit-limit-tokens"])
            if h.get("x-ratelimit-remaining-tokens"):
                key.tpm_remaining = int(h["x-ratelimit-remaining-tokens"])
            if h.get("x-ratelimit-limit-requests"):
                key.req_limit = int(h["x-ratelimit-limit-requests"])
            if h.get("x-ratelimit-remaining-requests"):
                key.req_remaining = int(h["x-ratelimit-remaining-requests"])
            key.reset_tokens = parse_duration(h.get("x-ratelimit-reset-tokens"))
        except ValueError:
            pass

    def note_usage(self, key: KeyState, body: Dict[str, Any]) -> None:
        usage = body.get("usage") or {}
        total = usage.get("total_tokens")
        if isinstance(total, int):
            key.tokens_served += total

    def cool_down(self, key: KeyState, resp: httpx.Response) -> float:
        delay = parse_duration(resp.headers.get("retry-after"))
        if delay is None or delay <= 0:
            delay = COOLDOWN_429
        # A 429 can be "this minute" (ms) or "tomorrow" (hours); cap cooldowns so
        # an exhausted daily key is retried occasionally instead of parked forever.
        delay = min(max(delay, 1.0), 120.0)
        key.cooldown_until = time.monotonic() + delay
        return delay

    def disable(self, key: KeyState, reason: str) -> None:
        key.disabled_reason = reason
        print(f"[pool] key {key.label} (...{key.last4}) disabled: {reason}", flush=True)

    def block_model(self, key: KeyState, model: str) -> None:
        key.blocked_models.add(model)
        print(f"[pool] key {key.label} (...{key.last4}) blocked for {model}", flush=True)

    def candidates(self, model: str) -> List[KeyState]:
        usable = [k for k in self.keys if k.usable(model)]
        usable.sort(key=KeyState.pool_rank)
        return usable

    def exhausted_error(self, model: str, failures: List[str]) -> HTTPException:
        if not self.keys:
            return HTTPException(503, "no Groq keys configured (GROQ_KEYS / groq_keys.txt)")
        soonest = min(
            (k.cooldown_until - time.monotonic() for k in self.keys if not k.disabled_reason),
            default=0.0,
        )
        note = f"all {len(self.keys)} keys are rate-limited or unusable"
        if soonest > 0:
            note += f"; earliest retry in {soonest:.0f}s"
        if failures:
            note += "; " + " | ".join(failures[-min(3, len(failures)):])
        status = 429 if soonest > 0 else 503
        return HTTPException(status, note)

    # ── Cloudflare same-model escape hatch ───────────────────────────────
    @staticmethod
    def _cf_request(payload: Dict[str, Any], cf_model: str) -> Dict[str, Any]:
        """Shape a Qoder/OpenAI payload for Workers AI's compat endpoint.

        Qoder sends message content as a list of {type: text, text: ...} parts;
        Cloudflare validates `content` as a plain string and rejects the array
        with 400 before quota is even checked. Text parts are joined, non-text
        parts (images) are dropped because these two models are text-only.
        """
        req = {
            k: v
            for k, v in strip_reasoning(payload).items()
            if k not in ("stream", "stream_options")
        }
        req["model"] = cf_model
        msgs = []
        for m in req.get("messages", []):
            content = m.get("content")
            if isinstance(content, list):
                texts = [
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                ]
                content = "\n\n".join(t for t in texts if t)
            msgs.append({**{k: v for k, v in m.items() if k != "content"}, "content": content})
        req["messages"] = msgs
        return req

    @staticmethod
    def _ms_request(payload: Dict[str, Any], ms_model: str) -> Dict[str, Any]:
        """ModelScope payload: Cloudflare-compatible shape plus the thinking flag."""
        req = KeyPool._cf_request(payload, ms_model)
        if not MS_THINKING:
            req["enable_thinking"] = False
            # Clients that expose a reasoning dial (Hermes, some SDKs) send
            # reasoning_effort. ModelScope rejects it alongside
            # enable_thinking=false (400 "reasoning_effort must be 'none'"),
            # so pin it to the only value that combination accepts.
            if "reasoning_effort" in req:
                req["reasoning_effort"] = "none"
        return req

    @staticmethod
    def _normalize_ms_body(body: Dict[str, Any], model: str) -> Dict[str, Any]:
        """ModelScope answers non-streamed calls with `delta`-shaped choices.

        An OpenAI client reads choices[].message, so a body without it looks
        like an empty reply. Promote the delta to a message and drop the
        reasoning trace Qoder would otherwise echo back into history.
        """
        body["model"] = model
        for ch in body.get("choices") or []:
            if not isinstance(ch, dict):
                continue
            if "message" not in ch and isinstance(ch.get("delta"), dict):
                msg = dict(ch.pop("delta"))
                msg.pop("reasoning_content", None)
                msg.pop("reasoning", None)
                ch["message"] = msg
            elif isinstance(ch.get("message"), dict):
                ch["message"].pop("reasoning_content", None)
                ch["message"].pop("reasoning", None)
            # ModelScope also ships an empty placeholder delta beside the
            # message; it means nothing to an OpenAI client.
            if isinstance(ch.get("delta"), dict) and not any(
                v for k, v in ch["delta"].items() if k != "reasoning_content"
            ):
                ch.pop("delta")
        return body

    async def _cloudflare_complete(
        self, payload: Dict[str, Any], model: str
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Returns (body, note). body is None when CF is off or refused."""
        cf_model = CLOUDFLARE_MODELS.get(model)
        if not self.cf or not cf_model:
            return None, ""
        req = self._cf_request(payload, cf_model)
        try:
            resp = await self.cf.post("/chat/completions", json=req)
        except Exception as exc:
            self.cf_fail += 1
            print(f"[pool] cloudflare unreachable: {exc!r}", flush=True)
            return None, f"cloudflare unreachable ({type(exc).__name__})"
        if resp.status_code < 400:
            self.cf_ok += 1
            body = resp.json()
            self._normalize_ms_body(body, model)
            self._cache_put(request_hash(payload), body)
            print(f"[pool] {model} served by cloudflare ({cf_model})", flush=True)
            return body, ""
        self.cf_fail += 1
        print(f"[pool] cloudflare {resp.status_code}: {resp.text[:200]}", flush=True)
        return None, f"cloudflare {resp.status_code}: {resp.text[:200]}"

    async def _cloudflare_stream(
        self, payload: Dict[str, Any], model: str
    ) -> Tuple[Optional[httpx.Response], str]:
        cf_model = CLOUDFLARE_MODELS.get(model)
        if not self.cf or not cf_model:
            return None, ""
        req = self._cf_request(payload, cf_model)
        req["stream"] = True
        try:
            request = self.cf.build_request("POST", "/chat/completions", json=req)
            resp = await self.cf.send(request, stream=True)
        except Exception as exc:
            self.cf_fail += 1
            print(f"[pool] cloudflare unreachable: {exc!r}", flush=True)
            return None, f"cloudflare unreachable ({type(exc).__name__})"
        if resp.status_code < 400:
            self.cf_ok += 1
            print(f"[pool] {model} stream served by cloudflare ({cf_model})", flush=True)
            return resp, ""
        body = await resp.aread()
        await resp.aclose()
        self.cf_fail += 1
        detail = body.decode(errors="replace")
        print(f"[pool] cloudflare stream {resp.status_code}: {detail[:200]}", flush=True)
        return None, f"cloudflare {resp.status_code}: {detail[:200]}"

    # ── ModelScope escape hatch (qwen only) ──────────────────────────────
    async def _modelscope_complete(
        self, payload: Dict[str, Any], model: str
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Same-model hop with a bigger free budget than Groq's 8K TPM.

        Returns (body, note); body is None when ModelScope is off or refused.
        """
        ms_model = MODEL_SCOPE_MODELS.get(model)
        if not self.ms or not ms_model:
            return None, ""
        req = self._ms_request(payload, ms_model)
        req["stream"] = False
        try:
            resp = await self.ms.post("/chat/completions", json=req)
        except Exception as exc:
            self.ms_fail += 1
            print(f"[pool] modelscope unreachable: {exc!r}", flush=True)
            return None, f"modelscope unreachable ({type(exc).__name__})"
        if resp.status_code < 400:
            self.ms_ok += 1
            body = resp.json()
            self._normalize_ms_body(body, model)
            self._cache_put(request_hash(payload), body)
            print(f"[pool] {model} served by modelscope ({ms_model})", flush=True)
            return body, ""
        self.ms_fail += 1
        detail = resp.text[:300]
        print(f"[pool] modelscope {resp.status_code}: {detail}", flush=True)
        return None, f"modelscope {resp.status_code}: {detail}"

    async def _modelscope_stream(
        self, payload: Dict[str, Any], model: str
    ) -> Tuple[Optional[httpx.Response], str]:
        ms_model = MODEL_SCOPE_MODELS.get(model)
        if not self.ms or not ms_model:
            return None, ""
        req = self._ms_request(payload, ms_model)
        req["stream"] = True
        t0 = time.monotonic()
        try:
            request = self.ms.build_request("POST", "/chat/completions", json=req)
            resp = await asyncio.wait_for(
                self.ms.send(request, stream=True), MS_HEADER_TIMEOUT
            )
        except asyncio.TimeoutError:
            self.ms_fail += 1
            print(
                f"[pool] modelscope: no stream headers in {MS_HEADER_TIMEOUT:.0f}s, "
                "falling through",
                flush=True,
            )
            return None, f"modelscope no headers in {MS_HEADER_TIMEOUT:.0f}s"
        except Exception as exc:
            self.ms_fail += 1
            print(f"[pool] modelscope unreachable: {exc!r}", flush=True)
            return None, f"modelscope unreachable ({type(exc).__name__})"
        if resp.status_code < 400:
            self.ms_ok += 1
            print(
                f"[pool] {model} stream served by modelscope "
                f"({ms_model}) headers in {time.monotonic() - t0:.1f}s",
                flush=True,
            )
            return resp, ""
        body = await resp.aread()
        await resp.aclose()
        self.ms_fail += 1
        detail = body.decode(errors="replace")[:300]
        print(f"[pool] modelscope stream {resp.status_code}: {detail}", flush=True)
        return None, f"modelscope {resp.status_code}: {detail}"

    async def fallback_complete(
        self, payload: Dict[str, Any], model: str
    ) -> Tuple[Optional[Dict[str, Any]], str, str]:
        """Escalation chain for a turn no Groq key can carry: ModelScope, then
        Cloudflare. Returns (body, label, note)."""
        ms_body, ms_note = await self._modelscope_complete(payload, model)
        if ms_body is not None:
            return ms_body, "modelscope", ""
        cf_body, cf_note = await self._cloudflare_complete(payload, model)
        if cf_body is not None:
            return cf_body, "cloudflare", ""
        notes = " | ".join(n for n in (ms_note, cf_note) if n)
        return None, "", notes

    async def fallback_stream(
        self, payload: Dict[str, Any], model: str
    ) -> Tuple[Optional[httpx.Response], str, str]:
        ms_resp, ms_note = await self._modelscope_stream(payload, model)
        if ms_resp is not None:
            return ms_resp, "modelscope", ""
        cf_resp, cf_note = await self._cloudflare_stream(payload, model)
        if cf_resp is not None:
            return cf_resp, "cloudflare", ""
        notes = " | ".join(n for n in (ms_note, cf_note) if n)
        return None, "", notes

    # ── routing helpers ──────────────────────────────────────────────────
    def alt_available(self, model: str) -> bool:
        """True when a same-model fallback (ModelScope or Cloudflare) is wired."""
        return bool(
            (self.ms and MODEL_SCOPE_MODELS.get(model))
            or (self.cf and CLOUDFLARE_MODELS.get(model))
        )

    def should_skip_groq(self, payload: Dict[str, Any], model: str) -> int:
        """Estimated prompt size when a Groq call cannot fit the free cap.

        Groq answers an oversized turn with 413 on every account, so uploading
        it once just adds seconds of blank screen. Returns 0 when Groq is still
        worth trying (small turn, or no fallback configured).
        """
        if not self.alt_available(model):
            return 0
        est = estimate_input_tokens(payload)
        return est if est > GROQ_TPM_CAP else 0

    # ── non-streamed ─────────────────────────────────────────────────────
    async def complete(
        self, payload: Dict[str, Any], model: str, allow_fallback: bool = True
    ) -> Tuple[Dict[str, Any], str]:
        failures: List[str] = []
        tried: set = set()
        payload = strip_reasoning(payload)

        skip = self.should_skip_groq(payload, model) if allow_fallback else 0
        if skip:
            print(
                f"[pool] {model}: ~{skip} input tokens over the {GROQ_TPM_CAP} TPM "
                "free cap, going straight to the fallback",
                flush=True,
            )
            fb_body, fb_label, fb_note = await self.fallback_complete(payload, model)
            if fb_body is not None:
                return fb_body, fb_label
            if fb_note:
                failures.append(fb_note)

        while len(tried) < MAX_ATTEMPTS:
            cands = [k for k in self.candidates(model) if id(k) not in tried]
            if not cands:
                break
            key = cands[0]
            tried.add(id(key))

            for inner in range(3):
                resp = await self.client.post("/chat/completions", json=payload, headers=key.auth_headers())
                self.note_response(key, resp)

                if resp.status_code < 400:
                    body = resp.json()
                    key.ok += 1
                    self.note_usage(key, body)
                    self._cache_put(request_hash(payload), body)
                    return body, key.label

                detail = resp.text
                if resp.status_code == 400 and is_tool_failure(detail) and inner < 2:
                    print(f"[pool] {key.label}: tool failure, retry {inner + 1}/2", flush=True)
                    continue

                if resp.status_code == 413:
                    # Structural, not per-account: every free key has the same
                    # per-minute cap. Rotating here only burns request quota.
                    key.fail += 1
                    print(f"[pool] {key.label}: 413 for {model}: {detail[:400]}", flush=True)
                    if not allow_fallback:
                        raise HTTPException(413, detail)
                    fb_body, fb_label, fb_note = await self.fallback_complete(payload, model)
                    if fb_body is not None:
                        return fb_body, fb_label
                    raise HTTPException(
                        413,
                        detail + " | note: this request exceeds the model's free-tier "
                        "tokens-per-minute cap on every pooled account; no rotation attempted"
                        + (f" | {fb_note}" if fb_note else ""),
                    )

                if resp.status_code == 429:
                    key.fail += 1
                    wait = self.cool_down(key, resp)
                    failures.append(f"{key.label} 429 ({wait:.0f}s)")
                    print(f"[pool] {key.label}: 429, cooling {wait:.0f}s", flush=True)
                    break

                if resp.status_code == 401:
                    key.fail += 1
                    self.disable(key, "401 invalid key")
                    failures.append(f"{key.label} 401")
                    break

                if resp.status_code == 403:
                    key.fail += 1
                    if model.lower() in detail.lower():
                        self.block_model(key, model)
                        failures.append(f"{key.label} 403 for {model}")
                    else:
                        self.disable(key, "403 forbidden")
                        failures.append(f"{key.label} 403")
                    break

                if resp.status_code >= 500:
                    key.fail += 1
                    failures.append(f"{key.label} {resp.status_code}")
                    print(f"[pool] {key.label}: upstream {resp.status_code}, trying next key", flush=True)
                    break

                # Any other 4xx is about the request, not the account.
                key.fail += 1
                raise HTTPException(resp.status_code, detail)

        fb_body, fb_label, fb_note = await self.fallback_complete(payload, model)
        if fb_body is not None:
            return fb_body, fb_label
        if fb_note:
            failures.append(fb_note)
        raise self.exhausted_error(model, failures)

    # ── streamed ─────────────────────────────────────────────────────────
    async def open_stream(self, payload: Dict[str, Any], model: str) -> Tuple[str, httpx.Response]:
        """Open the upstream stream and return only after a 200 exists, so an
        error is still a real HTTP status and never a 200 that dies mid-body."""
        failures: List[str] = []
        tried: set = set()
        payload = strip_reasoning(payload)

        skip = self.should_skip_groq(payload, model)
        if skip:
            print(
                f"[pool] {model}: ~{skip} input tokens over the {GROQ_TPM_CAP} TPM "
                "free cap, going straight to the fallback",
                flush=True,
            )
            fb_resp, fb_label, fb_note = await self.fallback_stream(payload, model)
            if fb_resp is not None:
                return fb_label, fb_resp
            if fb_note:
                failures.append(fb_note)

        while len(tried) < MAX_ATTEMPTS:
            cands = [k for k in self.candidates(model) if id(k) not in tried]
            if not cands:
                break
            key = cands[0]
            tried.add(id(key))

            for inner in range(3):
                request = self.client.build_request(
                    "POST", "/chat/completions", json=payload, headers=key.auth_headers()
                )
                resp = await self.client.send(request, stream=True)
                self.note_response(key, resp)

                if resp.status_code < 400:
                    key.ok += 1
                    return key.label, resp

                body = await resp.aread()
                await resp.aclose()
                detail = body.decode(errors="replace")

                if resp.status_code == 400 and is_tool_failure(detail) and inner < 2:
                    print(f"[pool] {key.label}: stream tool failure, retry {inner + 1}/2", flush=True)
                    continue

                if resp.status_code == 413:
                    key.fail += 1
                    print(f"[pool] {key.label}: stream 413 for {model}: {detail[:400]}", flush=True)
                    fb_resp, fb_label, fb_note = await self.fallback_stream(payload, model)
                    if fb_resp is not None:
                        return fb_label, fb_resp
                    raise HTTPException(
                        413,
                        detail + " | note: this request exceeds the model's free-tier "
                        "tokens-per-minute cap on every pooled account; no rotation attempted"
                        + (f" | {fb_note}" if fb_note else ""),
                    )

                if resp.status_code == 429:
                    key.fail += 1
                    wait = self.cool_down(key, resp)
                    failures.append(f"{key.label} 429 ({wait:.0f}s)")
                    print(f"[pool] {key.label}: stream 429, cooling {wait:.0f}s", flush=True)
                    break

                if resp.status_code == 401:
                    key.fail += 1
                    self.disable(key, "401 invalid key")
                    failures.append(f"{key.label} 401")
                    break

                if resp.status_code == 403:
                    key.fail += 1
                    if model.lower() in detail.lower():
                        self.block_model(key, model)
                        failures.append(f"{key.label} 403 for {model}")
                    else:
                        self.disable(key, "403 forbidden")
                        failures.append(f"{key.label} 403")
                    break

                if resp.status_code >= 500:
                    key.fail += 1
                    failures.append(f"{key.label} {resp.status_code}")
                    break

                key.fail += 1
                raise HTTPException(resp.status_code, detail)

        fb_resp, fb_label, fb_note = await self.fallback_stream(payload, model)
        if fb_resp is not None:
            return fb_label, fb_resp
        if fb_note:
            failures.append(fb_note)
        raise self.exhausted_error(model, failures)

    async def close(self) -> None:
        await self.client.aclose()
        if self.cf:
            await self.cf.aclose()


# ─── SERVER ──────────────────────────────────────────────────────────────
pool: Optional[KeyPool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    keys = load_keys()
    if not keys:
        print("WARNING: no Groq keys found. Set GROQ_KEYS or create groq_keys.txt.", flush=True)
    else:
        pool = KeyPool(keys)
        labels = ", ".join(k[0] for k in keys)
        print(f"[pool] started with {len(keys)} key(s): {labels}", flush=True)
        print(f"[pool] models: {', '.join(GROQ_MODELS)}", flush=True)
    yield
    if pool:
        await pool.close()


app = FastAPI(title="Groq Pool Bridge", lifespan=lifespan)


def require_pool() -> KeyPool:
    if not pool:
        raise HTTPException(503, "no Groq keys configured (GROQ_KEYS / groq_keys.txt)")
    return pool


@app.get("/v1/models")
async def list_models():
    data = [
        {
            "id": name,
            "object": "model",
            "created": 1677610602,
            "owned_by": "groq",
            "context_window": meta["context_window"],
            "max_output_tokens": meta["max_output"],
        }
        for name, meta in MODEL_META.items()
    ]
    return {"object": "list", "data": data}


def _send_stream(resp: httpx.Response, normalize_fallback: bool = False):
    """Relay an upstream SSE body.

    normalize_fallback cleans up what the same-model hops send: reasoning
    traces (Qoder would render them as the answer and echo them back) and
    empty `id`/`name` fields on follow-up tool-call fragments, which can
    overwrite the real call id in a client that merges by that key.
    """
    async def body():
        saw_done = False
        try:
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                if line.startswith(("data:", "event:")):
                    if line.strip() == "data: [DONE]":
                        saw_done = True
                    elif normalize_fallback and line.startswith("data:"):
                        raw = line[5:].strip()
                        try:
                            chunk = json.loads(raw)
                        except Exception:
                            chunk = None
                        if isinstance(chunk, dict):
                            choices = chunk.get("choices") or []
                            changed = False
                            for choice in choices:
                                delta = choice.get("delta")
                                if not isinstance(delta, dict):
                                    continue
                                if "reasoning_content" in delta or "reasoning" in delta:
                                    delta.pop("reasoning_content", None)
                                    delta.pop("reasoning", None)
                                    changed = True
                                for tc in delta.get("tool_calls") or []:
                                    if not isinstance(tc, dict):
                                        continue
                                    if tc.get("id") == "":
                                        tc.pop("id")
                                        changed = True
                                    fn = tc.get("function")
                                    if isinstance(fn, dict) and fn.get("name") == "":
                                        fn.pop("name")
                                        changed = True
                            if changed:
                                if not any(c.get("delta") for c in choices):
                                    continue  # nothing left to say in this chunk
                                line = "data: " + json.dumps(
                                    chunk, separators=(",", ":"), ensure_ascii=False
                                )
                    yield f"{line}\n\n"
                else:
                    yield f"data: {line}\n\n"
            if not saw_done:
                yield "data: [DONE]\n\n"
        except Exception as exc:  # connection dropped mid-body
            print(f"[pool] stream body crashed: {exc!r}", flush=True)
            yield sse_error(502, f"upstream stream interrupted: {exc!r}")
        finally:
            await resp.aclose()

    return body()


@app.post("/v1/chat/completions")
async def chat_completion(request: ChatCompletionRequest):
    p = require_pool()
    model = resolve_model(request.model)

    payload = request.model_dump(exclude_none=True)
    payload["model"] = model
    clamp_output_tokens(model, payload)
    dump_payload(payload)

    local = await p.local_answer(payload)
    if local:
        body, source = local
        headers = {"X-Pool-Source": source}
        if request.stream:
            return StreamingResponse(
                completion_to_sse(body), media_type="text/event-stream", headers=headers
            )
        return JSONResponse(body, headers=headers)

    if request.stream:
        if model in BUFFERED_MODELS and request.tools:
            # Probe Groq buffered: if a key can carry the turn, replay it as SSE
            # (same as before). If it 413s, do NOT buffer the fallback — stream
            # ModelScope live, otherwise the UI shows a 60-90 s blank screen.
            buffered = dict(payload)
            buffered["stream"] = False
            buffered.pop("stream_options", None)
            if p.should_skip_groq(buffered, model):
                # No point firing a request we know will 413: stream the
                # fallback straight away so the UI gets tokens, not a spinner.
                fb_resp, fb_label, fb_note = await p.fallback_stream(payload, model)
                if fb_resp is not None:
                    return StreamingResponse(
                        _send_stream(fb_resp, normalize_fallback=True),
                        media_type="text/event-stream",
                        headers={"X-Groq-Key": fb_label, "X-Accel-Buffering": "no"},
                    )
                print(f"[pool] {model}: oversized turn, fallback failed: {fb_note}", flush=True)
            try:
                result, label = await p.complete(buffered, model, allow_fallback=False)
            except HTTPException as exc:
                if exc.status_code != 413:
                    raise
                fb_resp, fb_label, fb_note = await p.fallback_stream(payload, model)
                if fb_resp is None:
                    raise HTTPException(
                        413,
                        str(exc.detail)
                        + " | note: no stream fallback answered"
                        + (f" | {fb_note}" if fb_note else ""),
                    )
                return StreamingResponse(
                    _send_stream(fb_resp, normalize_fallback=True),
                    media_type="text/event-stream",
                    headers={"X-Groq-Key": fb_label, "X-Accel-Buffering": "no"},
                )
            return StreamingResponse(
                completion_to_sse(result),
                media_type="text/event-stream",
                headers={"X-Groq-Key": label, "X-Accel-Buffering": "no"},
            )

        label, resp = await p.open_stream(payload, model)
        return StreamingResponse(
            _send_stream(resp, normalize_fallback=label in ("modelscope", "cloudflare")),
            media_type="text/event-stream",
            headers={"X-Groq-Key": label, "X-Accel-Buffering": "no"},
        )

    body, label = await p.complete(payload, model)
    return JSONResponse(body, headers={"X-Groq-Key": label})


@app.get("/health")
async def health():
    if not pool:
        return {"status": "no_keys", "keys": [], "models": MODEL_META}
    return {
        "status": "ok",
        "keys": [k.snapshot() for k in pool.keys],
        "models": MODEL_META,
        "buffered_models": sorted(BUFFERED_MODELS),
        "max_attempts": MAX_ATTEMPTS,
        "local_answers": {
            "bots": bool(pool.bots),
            "cache": CACHE_ENABLED,
            "cache_hits": pool.cache_hits,
            "bot_hits": pool.bot_hits,
            "dup_limit": DUP_LIMIT,
            "dup_window_s": DUP_WINDOW,
            "dup_blocks": pool.dup_blocks,
        },
        "cloudflare": {
            "enabled": CF_ENABLED,
            "models": CLOUDFLARE_MODELS if CF_ENABLED else None,
            "served": pool.cf_ok,
            "refused": pool.cf_fail,
        },
        "modelscope": {
            "enabled": MS_ENABLED,
            "base": MODEL_SCOPE_BASE if MS_ENABLED else None,
            "models": MODEL_SCOPE_MODELS if MS_ENABLED else None,
            "served": pool.ms_ok,
            "refused": pool.ms_fail,
        },
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Groq Pool Bridge — OpenAI-compatible")
    parser.add_argument("--port", type=int, default=8081, help="Port (default 8081)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default 127.0.0.1)")
    parser.add_argument("--keys", help='"label=key,label=key" (or use GROQ_KEYS / groq_keys.txt)')
    args = parser.parse_args()

    if args.keys:
        os.environ["GROQ_KEYS"] = args.keys

    print(f"Starting Groq Pool Bridge on http://{args.host}:{args.port}")
    print("OpenAI-compatible base URL:", f"http://{args.host}:{args.port}/v1")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
