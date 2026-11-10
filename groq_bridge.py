#!/usr/bin/env python3
"""
Groq Free Tier Bridge — OpenAI-Compatible Local Server (UPDATED 2026-09-23)
============================================================================
Runs a local OpenAI-compatible API server that proxies to Groq free tier.
Hermes connects to this as a custom provider (like OmniRoute).

Current Free Models on Groq (as of 2026-09-23):
- openai/gpt-oss-120b         (primary - 120B, reasoning)
- openai/gpt-oss-20b          (smaller, faster)
- qwen/qwen3.8-27b            (Qwen 27B)
- allam-2-7b                  (Arabic-optimized)
- canopylabs/orpheus-v1-english (TTS/voice)
- whisper-large-v3            (audio transcription)
- whisper-large-v3-turbo      (fast audio transcription)

Usage:
  python groq_bridge.py --port 8080 --api-key YOUR_GROQ_KEY
  
Then in Hermes config:
  custom_providers:
    - name: GroqBridge
      base_url: http://127.0.0.1:8080/v1
      api_key: "dummy"
      api_mode: openai
"""

import os
import json
import time
import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
import uvicorn
import httpx

try:
    from env_loader import load_dotenv, sanitize_proxy_env
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return {}

    def sanitize_proxy_env():
        return None

load_dotenv()
sanitize_proxy_env()


# ─── CONFIG ──────────────────────────────────────────────────────────────
GROQ_API_BASE = "https://api.groq.com/openai/v1"
GROQ_MODELS = [
    "openai/gpt-oss-120b",           # PRIMARY - 120B, reasoning
    "openai/gpt-oss-20b",            # fallback 1 - smaller, faster
    "qwen/qwen3.8-27b",              # fallback 2 - Qwen 27B
    "allam-2-7b",                    # fallback 3 - Arabic
    "canopylabs/orpheus-v1-english", # TTS
    "whisper-large-v3",              # audio
    "whisper-large-v3-turbo",        # fast audio
]

DEFAULT_MODEL = "openai/gpt-oss-120b"

# Per-model hard caps enforced by Groq. Clients (Qoder) may ask for more output
# tokens than a given model allows; exceeding the cap is a 400, so clamp instead.
MODEL_MAX_OUTPUT = {
    "qwen/qwen3.8-27b": 16384,
}

# Models whose streamed tool calls are unreliable on Groq; their tool turns are
# executed non-streamed and replayed to the client as SSE.
BUFFERED_STREAM_MODELS = {"qwen/qwen3.8-27b"}

# Same-model alternate hosts, in order. Groq's free tier caps qwen at 7,000
# input tokens/minute, and Qoder's agent prompt alone is ~35k tokens, so a 413
# there is expected; the same qwen3.8-27b model is served by Cloudflare Workers
# AI (free daily quota) and OpenRouter (paid credits). Keys come from .env.
FALLBACK_TRIGGER_STATUS = {413, 429, 503}
CLOUDFLARE_API_KEY = os.environ.get("CLOUDFLARE_API_KEY")
CLOUDFLARE_AI_BASE = os.environ.get("CLOUDFLARE_AI_BASE")
CLOUDFLARE_QWEN_MODEL = os.environ.get("CLOUDFLARE_QWEN_MODEL", "@cf/qwen/qwen3.8-27b")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")


def clamp_output_tokens(model: str, payload: Dict[str, Any]) -> None:
    cap = MODEL_MAX_OUTPUT.get(model)
    if not cap:
        return
    for key in ("max_tokens", "max_completion_tokens"):
        value = payload.get(key)
        if isinstance(value, int) and value > cap:
            payload[key] = cap
            print(f"[groq_bridge] clamped {key} {value} -> {cap} for {model}", flush=True)


def is_tool_failure(text: str) -> bool:
    """Groq reports Qwen's malformed tool calls in a few different shapes."""
    low = text.lower()
    return (
        "tool_use_failed" in low
        or "tool call validation failed" in low
        or ("did not match schema" in low and "tool" in low)
    )


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

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = 1677610602
    owned_by: str = "groq"

class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


# ─── GROQ CLIENT ─────────────────────────────────────────────────────────
def resolve_model(model: str) -> str:
    """Unknown names (including "auto") fall back to the default model."""
    return model if model in GROQ_MODELS else DEFAULT_MODEL


def sse_error(status: int, detail: str) -> str:
    """One SSE error event plus terminator, for failures after headers went out."""
    err = json.dumps(
        {"error": {"message": str(detail)[:800], "type": "upstream_error", "code": status}}
    )
    return f"data: {err}\n\n" + "data: [DONE]\n\n"


def completion_to_sse(result: Dict[str, Any]):
    """Replay a non-streamed completion as an OpenAI-compatible SSE stream."""
    cid = result.get("id") or "chatcmpl-bridge"
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


class GroqClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            base_url=GROQ_API_BASE,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )
        self.cf = None
        if CLOUDFLARE_API_KEY and CLOUDFLARE_AI_BASE:
            self.cf = httpx.AsyncClient(
                base_url=CLOUDFLARE_AI_BASE,
                headers={
                    "Authorization": f"Bearer {CLOUDFLARE_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=240.0,
            )
        self.openrouter = None
        if OPENROUTER_API_KEY:
            self.openrouter = httpx.AsyncClient(
                base_url="https://openrouter.ai/api/v1",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "X-Title": "BruceAI bridge",
                },
                timeout=240.0,
            )

    async def _post_fallbacks(self, payload: Dict[str, Any], resp) -> Optional[Dict[str, Any]]:
        """Qwen only: Groq's free ITPM cap (7k) cannot hold Qoder's ~35k prompt.
        Re-issue the same model on hosts with room, in order."""
        if payload.get("model") != "qwen/qwen3.8-27b":
            return None
        if resp is None or resp.status_code not in FALLBACK_TRIGGER_STATUS:
            return None

        failures = []
        if self.cf:
            cf_payload = dict(payload)
            cf_payload["model"] = CLOUDFLARE_QWEN_MODEL
            r = await self.cf.post("/chat/completions", json=cf_payload)
            if r.status_code < 400:
                print("[groq_bridge] qwen served by cloudflare", flush=True)
                return r.json()
            failures.append(f"cloudflare {r.status_code}: {r.text[:300]}")
            print(f"[groq_bridge] cloudflare fallback {r.status_code}: {r.text[:200]}", flush=True)

        if self.openrouter:
            r = await self.openrouter.post("/chat/completions", json=payload)
            if r.status_code < 400:
                print("[groq_bridge] qwen served by openrouter", flush=True)
                return r.json()
            failures.append(f"openrouter {r.status_code}: {r.text[:300]}")
            print(f"[groq_bridge] openrouter fallback {r.status_code}: {r.text[:200]}", flush=True)

        if failures:
            raise HTTPException(
                status_code=resp.status_code,
                detail=resp.text + " | fallbacks: " + " ; ".join(failures),
            )
        return None

    async def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /chat/completions, retrying rate limits and Qwen tool-call glitches."""
        resp = None
        for attempt in range(4):
            resp = await self.client.post("/chat/completions", json=payload)

            if resp.status_code == 429 and attempt < 3:
                retry_after = resp.headers.get("retry-after")
                delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else (attempt + 1) * 1.5
                print(f"[groq_bridge] upstream 429, retrying in {delay:.1f}s ({attempt + 1}/3)", flush=True)
                await asyncio.sleep(delay)
                continue

            if resp.status_code == 400 and is_tool_failure(resp.text) and attempt < 3:
                print(f"[groq_bridge] tool failure, retry {attempt + 1}/3", flush=True)
                continue

            break

        if resp is not None and resp.status_code >= 400:
            # Groq's free ITPM (7k) is below Qoder's ~35k agent prompt, so a
            # 413 here is structural, not transient: try hosts with room.
            fallback = await self._post_fallbacks(payload, resp)
            if fallback is not None:
                return fallback
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        return resp.json()

    async def chat_completion(self, request: ChatCompletionRequest) -> Dict[str, Any]:
        model = resolve_model(request.model)

        payload = request.model_dump(exclude_none=True)
        payload["model"] = model
        clamp_output_tokens(model, payload)

        return await self._post(payload)

    async def buffered_completion(self, request: ChatCompletionRequest) -> Dict[str, Any]:
        """Run a Qwen tool turn non-streamed so Groq's flaky streamed tool
        grammar cannot split the call; the route replays it as SSE afterwards."""
        payload = request.model_dump(exclude_none=True)
        payload["model"] = resolve_model(request.model)
        payload["stream"] = False
        payload.pop("stream_options", None)
        clamp_output_tokens(payload["model"], payload)
        return await self._post(payload)

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        model = resolve_model(request.model)

        payload = request.model_dump(exclude_none=True)
        payload["model"] = model
        clamp_output_tokens(model, payload)
        payload["stream"] = True

        for attempt in range(3):
            restarted = False
            sent = False
            async with self.client.stream("POST", "/chat/completions", json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    detail = body.decode(errors="replace")
                    if resp.status_code == 429 and attempt < 2:
                        print(f"[groq_bridge] stream 429, retry {attempt + 1}/2", flush=True)
                        await asyncio.sleep((attempt + 1) * 1.5)
                        continue
                    if resp.status_code == 400 and is_tool_failure(detail) and attempt < 2:
                        print(f"[groq_bridge] stream tool failure, retry {attempt + 1}/2", flush=True)
                        continue
                    print(f"[groq_bridge] upstream {resp.status_code} on stream: {detail[:500]}", flush=True)
                    yield sse_error(resp.status_code, detail[:500])
                    return

                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = f"{line}\n\n" if line.startswith(("data:", "event:")) else f"data: {line}\n\n"
                    # A tool failure arrives as an SSE error event; retry only if
                    # no content has reached the client yet.
                    if '"error"' in line and is_tool_failure(line) and attempt < 2 and not sent:
                        print(f"[groq_bridge] stream tool failure event, retry {attempt + 1}/2", flush=True)
                        restarted = True
                        break
                    sent = True
                    yield chunk
            if restarted:
                continue
            yield "data: [DONE]\n\n"
            return

    async def list_models(self) -> List[ModelInfo]:
        return [ModelInfo(id=m) for m in GROQ_MODELS]

    async def close(self):
        await self.client.aclose()


# ─── SERVER ──────────────────────────────────────────────────────────────
groq_client: Optional[GroqClient] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global groq_client
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("WARNING: GROQ_API_KEY not set. Set it in environment.")
    else:
        groq_client = GroqClient(api_key)
        print(f"Groq Bridge started. Models: {', '.join(GROQ_MODELS)}")
    yield
    if groq_client:
        await groq_client.close()

app = FastAPI(title="Groq Bridge", lifespan=lifespan)

@app.get("/v1/models")
async def list_models():
    if not groq_client:
        raise HTTPException(503, "Groq client not initialized (missing API key)")
    models = await groq_client.list_models()
    return ModelsResponse(data=models).model_dump()

@app.post("/v1/chat/completions")
async def chat_completion(request: ChatCompletionRequest, raw_request: Request):
    if not groq_client:
        raise HTTPException(503, "Groq client not initialized (missing API key)")
    
    if request.stream:
        model = resolve_model(request.model)
        # Qwen tool turns are buffered: fetch BEFORE the response starts so an
        # upstream error (413/429/400) returns a real HTTP status instead of a
        # 200 whose socket dies mid-stream (clients then retry in a storm).
        if model in BUFFERED_STREAM_MODELS and request.tools:
            result = await groq_client.buffered_completion(request)
            return StreamingResponse(
                completion_to_sse(result),
                media_type="text/event-stream",
            )

        async def guarded():
            try:
                async for chunk in groq_client.chat_completion_stream(request):
                    yield chunk
            except HTTPException as exc:
                print(f"[groq_bridge] stream error {exc.status_code}: {str(exc.detail)[:300]}", flush=True)
                yield sse_error(exc.status_code, exc.detail)
            except Exception as exc:
                print(f"[groq_bridge] stream crash: {exc!r}", flush=True)
                yield sse_error(500, repr(exc))

        return StreamingResponse(guarded(), media_type="text/event-stream")
    else:
        result = await groq_client.chat_completion(request)
        return result

@app.get("/health")
async def health():
    return {"status": "ok", "models": len(GROQ_MODELS)}


# ─── CLI ─────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Groq Free Tier Bridge - OpenAI Compatible")
    parser.add_argument("--port", type=int, default=8080, help="Port to run on (default: 8080)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--api-key", help="Groq API key (or set GROQ_API_KEY env)")
    args = parser.parse_args()
    
    if args.api_key:
        os.environ["GROQ_API_KEY"] = args.api_key
    elif not os.environ.get("GROQ_API_KEY"):
        print("ERROR: Set GROQ_API_KEY environment variable or use --api-key")
        print("Get free key at: https://console.groq.com/keys")
        return
    
    print(f"Starting Groq Bridge on http://{args.host}:{args.port}")
    print(f"Hermes config:")
    print(f"  custom_providers:")
    print(f"    - name: GroqBridge")
    print(f"      base_url: http://{args.host}:{args.port}/v1")
    print(f"      api_key: \"dummy\"")
    print(f"      api_mode: openai")
    print(f"      models:")
    for m in GROQ_MODELS:
        print(f"        {m}: {{}}")
    
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()