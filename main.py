#!/usr/bin/env python3
"""
Provider Console - FastAPI server on port 9001
Routes to: Groq Bridge (8080), OpenCode subprocess, OpenRouter direct
Standalone version - no external dependencies
"""
import os
import json
import time
import logging
import shutil
import subprocess
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
import httpx
import uvicorn

try:
    from env_loader import load_dotenv, sanitize_proxy_env
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return {}

    def sanitize_proxy_env():
        return None

load_dotenv()
sanitize_proxy_env()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("provider_console")

app = FastAPI(title="BruceAI Provider Console", version="1.0")

# Configuration from environment
GROQ_BRIDGE_URL = os.getenv("GROQ_BRIDGE_URL", "http://127.0.0.1:8080/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENCODE_KEY = os.getenv("OPENCODE_KEY")
SUPER_SOLDIER_URL = os.getenv("SUPER_SOLDIER_URL", "http://127.0.0.1:8082/process")
SUPER_SOLDIER_GROQ_MODEL = os.getenv("SUPER_SOLDIER_GROQ_MODEL", "openai/gpt-oss-120b")
SUPER_SOLDIER_TASK_LIMIT = int(os.getenv("SUPER_SOLDIER_TASK_LIMIT", "10000"))
# Local ColiBRI engine (coli serve). OpenAI-compatible, full tool-calling
# pass-through - see ~/.bruceai/config.yaml for the provider entry.
COLIBRI_URL = os.getenv("COLIBRI_URL", "http://127.0.0.1:9002/v1")
# coli serve 404s any id that isn't the one it reports in /models, so the id
# is resolved from the engine (colibri_model_id) rather than hardcoded.
COLIBRI_MODEL_ID = os.getenv("COLIBRI_MODEL_ID", "qwen3.6-colibri")
_colibri_id_state = {"id": COLIBRI_MODEL_ID, "at": 0.0}
_COLIBRI_ID_TTL = int(os.getenv("COLIBRI_ID_TTL", "600"))

# OpenCode free-tier models. The picker lists these (free only) instead of one
# generic "opencode" entry; refreshed from `opencode models`, which is also the
# set of ids `opencode run -m` accepts.
OPENCODE_FREE_TTL = int(os.getenv("OPENCODE_FREE_TTL", "600"))
OPENCODE_FREE_FALLBACK = [
    "ling-3.0-flash-fin-free",
    "longcat-2.5-preview-free",
    "mimo-v2.6-flash-free",
    "muse-spark-1.3-contributor-free",
    "nemotron-3-ultra-free",
    "nemotron-3.5-lightning-free",
    "space-bunny-free",
]
_opencode_free_state = {"ids": list(OPENCODE_FREE_FALLBACK), "at": 0.0}
_OPENCODE_BIN: Optional[str] = None

def opencode_bin() -> Optional[str]:
    """Locate opencode.exe - the spawned console process may not have the npm
    shim directory on PATH (the shim is .cmd, unusable by CreateProcess)."""
    global _OPENCODE_BIN
    if _OPENCODE_BIN:
        return _OPENCODE_BIN
    candidates = []
    if os.getenv("OPENCODE_BIN"):
        candidates.append(os.environ["OPENCODE_BIN"])
    found = shutil.which("opencode")
    if found:
        candidates.append(found)
    appdata = os.getenv("APPDATA")
    if appdata:
        candidates.append(os.path.join(appdata, "npm", "node_modules",
                                       "opencode-ai", "bin", "opencode.exe"))
    for cand in candidates:
        if cand.lower().endswith(".exe") and os.path.isfile(cand):
            _OPENCODE_BIN = cand
            return cand
    return None

# Model routing map
MODEL_ROUTES = {
    # Groq models -> Groq Bridge (free tier: 8k tokens/min — small payloads only)
    "qwen/qwen3.8-27b": "groq",
    "allam-2-7b": "groq",
    "canopylabs/orpheus-v1-english": "groq",
    "whisper-large-v3": "groq",
    "whisper-large-v3-turbo": "groq",
    "openai/gpt-oss-120b": "groq",
    "super-soldier": "supersoldier",
    # Local ColiBRI engine (coli serve on :9002)
    "colibri": "colibri",
    "qwen3.6-colibri": "colibri",
    # OpenCode models -> subprocess
    "opencode": "opencode",
    "opencode-zen": "opencode",
    "openai/gpt-oss-20b": "groq",
    # Everything else -> OpenRouter
    }

class Model(BaseModel):
    id: str
    object: str = "model"
    owned_by: str = "bruceai"

class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[Model]

class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str
    content: Optional[Any] = None
    name: Optional[str] = None
    tool_calls: Optional[List[Any]] = None
    tool_call_id: Optional[str] = None

class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    tools: Optional[List[Any]] = None
    tool_choice: Optional[Any] = None
    top_p: Optional[float] = None
    stop: Optional[Any] = None
    response_format: Optional[Any] = None

async def discover_opencode_free_models() -> List[str]:
    """Free models only: read the OpenCode catalog so the picker shows exactly
    what `opencode run -m` accepts."""
    exe = opencode_bin()
    if not exe:
        return []
    try:
        proc = await asyncio.create_subprocess_exec(
            exe, "models",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=25)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return []
        ids: List[str] = []
        for line in stdout.decode("utf-8", "replace").splitlines():
            mid = line.strip()
            if mid.endswith("-free") and "/" in mid:
                bare = mid.split("/", 1)[1]
                if bare not in ids:
                    ids.append(bare)
        if ids:
            return ids
    except Exception:
        pass
    return []

async def opencode_free_models() -> List[str]:
    now = time.time()
    if now - float(_opencode_free_state["at"]) > OPENCODE_FREE_TTL:
        ids = await discover_opencode_free_models()
        if ids:
            _opencode_free_state["ids"] = ids
        _opencode_free_state["at"] = now
    return list(_opencode_free_state["ids"])

def get_route(model: str) -> str:
    """Determine which backend to route to"""
    if model in MODEL_ROUTES:
        return MODEL_ROUTES[model]
    if model.endswith("-free") or model.startswith(("opencode/", "opencode-go/")):
        return "opencode"
    return "openrouter"

def colibri_base_url() -> str:
    """Engine root (no /v1): /health and the dashboard live there."""
    return COLIBRI_URL[:-3] if COLIBRI_URL.endswith("/v1") else COLIBRI_URL

async def colibri_model_id() -> str:
    """Ask the engine what it calls itself. A stale id comes back as a bare
    HTTP 404 (no body), which reads as a crash to callers."""
    now = time.time()
    if now - float(_colibri_id_state["at"]) > _COLIBRI_ID_TTL:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{COLIBRI_URL}/models")
                if resp.status_code == 200:
                    data = resp.json().get("data") or []
                    if data and data[0].get("id"):
                        _colibri_id_state["id"] = data[0]["id"]
                        _colibri_id_state["at"] = now
        except (httpx.HTTPError, ValueError):
            pass
    return str(_colibri_id_state["id"])

async def colibri_status() -> str:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{colibri_base_url()}/health")
            if resp.status_code == 200:
                return "healthy"
            return f"degraded ({resp.status_code})"
    except httpx.HTTPError as e:
        return f"unreachable ({e.__class__.__name__})"

@app.get("/health")
async def health():
    # Check Groq bridge connectivity
    groq_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            # Try the base URL health endpoint (groq_bridge.py uses /health not /v1/health)
            base_url = GROQ_BRIDGE_URL.replace("/v1", "")
            resp = await client.get(f"{base_url}/health")
            if resp.status_code == 200:
                groq_status = "healthy"
            else:
                groq_status = f"degraded ({resp.status_code})"
    except Exception as e:
        groq_status = f"unreachable ({e})"
    
    return {
        "status": "ok",
        "port": 9001,
        "groq_bridge": groq_status,
        "colibri": await colibri_status(),
        "colibri_model": await colibri_model_id(),
        "openrouter_configured": bool(OPENROUTER_API_KEY),
        "opencode_configured": bool(OPENCODE_KEY)
    }

def dedupe_models(models: List[Model]) -> List[Model]:
    # An id served by two backends (e.g. a Groq model that is also in the OpenRouter list)
    # otherwise shows up twice in the model picker. First entry wins.
    unique: Dict[str, Model] = {}
    for m in models:
        unique.setdefault(m.id, m)
    return list(unique.values())

@app.get("/v1/models")
async def list_models():
    # Aggregate models from all backends
    models = []
    
    # Groq models
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{GROQ_BRIDGE_URL}/models")
            if resp.status_code != 200:
                resp = await client.get(f"{GROQ_BRIDGE_URL}/v1/models")
            if resp.status_code == 200:
                data = resp.json()
                for m in data.get("data", []):
                    models.append(Model(id=m["id"], owned_by="groq"))
    except Exception:
        pass
    
    # OpenCode free-tier models (free only - no generic "opencode" entry)
    for mid in await opencode_free_models():
        models.append(Model(id=mid, owned_by="opencode"))

    # LLM Super-Soldier gateway (local, :8082)
    models.append(Model(id="super-soldier", owned_by="bruceai"))

    # Local ColiBRI engine (coli serve, :9002)
    models.append(Model(id=await colibri_model_id(), owned_by="colibri"))
    
    # OpenRouter models (common ones)
    openrouter_models = [
        "anthropic/claude-3.5-sonnet",
        "anthropic/claude-3-opus",
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "google/gemini-pro-1.5",
        "meta-llama/llama-3.1-405b",
        "nvidia/nemotron-3-ultra",
        "qwen/qwen-2.5-72b-instruct",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "qwen/qwen3.8-27b:free",
        "google/gemma-4-31b-it:free",
    ]
    for m in openrouter_models:
        models.append(Model(id=m, owned_by="openrouter"))
    
    return ModelsResponse(data=dedupe_models(models))

async def call_groq_bridge(request: ChatCompletionRequest, authorization: Optional[str]):
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    
    payload = request.model_dump(exclude_none=True)
    for _m in payload.get("messages", []):
        if isinstance(_m, dict):
            for _k in ("reasoning_details", "reasoning", "reasoning_content", "reasoning_tokens"):
                _m.pop(_k, None)
    payload["stream"] = request.stream
    if request.max_tokens:
        payload["max_tokens"] = request.max_tokens
    
    if request.stream:
        async def stream_response():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", f"{GROQ_BRIDGE_URL}/chat/completions", json=payload, headers=headers) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode("utf-8", "replace")
                        yield f"data: {json.dumps({'error': {'message': body, 'type': 'upstream_error', 'code': resp.status_code}})}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if line:
                            yield f"{line}\n\n"
        return StreamingResponse(stream_response(), media_type="text/event-stream")
    else:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{GROQ_BRIDGE_URL}/chat/completions", json=payload, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        return resp.json()

async def call_openrouter(request: ChatCompletionRequest, authorization: Optional[str]):
    if not OPENROUTER_API_KEY:
        raise HTTPException(500, "OpenRouter API key not configured")
    
    # Free-models-only policy: paid models are blocked at the console so no
    # request can ever reach OpenRouter billing.
    if not request.model.endswith(":free"):
        raise HTTPException(403, f"Paid model '{request.model}' is blocked (free models only)")
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://bruceai.local",
        "X-Title": "BruceAI Console"
    }
    
    payload = request.model_dump(exclude_none=True)
    payload["stream"] = request.stream
    if request.max_tokens:
        payload["max_tokens"] = request.max_tokens
    
    if request.stream:
        async def stream_response():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", f"{OPENROUTER_BASE_URL}/chat/completions", json=payload, headers=headers) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode("utf-8", "replace")
                        yield f"data: {json.dumps({'error': {'message': body, 'type': 'upstream_error', 'code': resp.status_code}})}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if line:
                            yield f"{line}\n\n"
        return StreamingResponse(stream_response(), media_type="text/event-stream")
    else:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{OPENROUTER_BASE_URL}/chat/completions", json=payload, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        return resp.json()

async def call_opencode(request: ChatCompletionRequest):
    if not OPENCODE_KEY:
        raise HTTPException(500, "OpenCode key not configured")

    # `opencode run -m` wants provider/model; picker ids are bare free-model ids.
    model = request.model
    if model in ("opencode", "opencode-zen"):
        free = await opencode_free_models()
        model = f"opencode/{free[0]}" if free else "opencode/space-bunny-free"
    elif "/" not in model:
        model = f"opencode/{model}"

    prompt = "\n".join([f"{m.role}: {m.content}" for m in request.messages if m.content is not None])
    if len(prompt) > 20000:
        prompt = prompt[:20000]

    exe = opencode_bin()
    if not exe:
        raise HTTPException(500, "OpenCode CLI not found (opencode.exe missing)")

    # The free CLI occasionally exits 0 with empty stdout; a 200-with-empty here
    # makes hermes fall back to the (exhausted) openrouter pool after 1 retry,
    # which stalls Luke's turns in a 429 loop. Retry once, then fail loudly so
    # hermes retries this provider instead of falling back.
    content = ""
    for attempt in (1, 2):
        try:
            proc = await asyncio.create_subprocess_exec(
                exe, "run", "-m", model, prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "OPENCODE_API_KEY": OPENCODE_KEY}
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise HTTPException(504, "OpenCode timeout")
        except FileNotFoundError:
            raise HTTPException(500, "OpenCode CLI not installed")

        if proc.returncode != 0:
            raise HTTPException(500, f"OpenCode error ({model}): {stderr.decode('utf-8', 'replace')[:400]}")

        content = stdout.decode("utf-8", "replace").strip()
        if content:
            break
        if attempt == 1:
            await asyncio.sleep(1)

    if not content:
        raise HTTPException(503, f"OpenCode empty completion after retry ({model})")
    completion_id = f"opencode-{os.urandom(8).hex()}"
    created = int(time.time())
    if request.stream:
        async def stream_response():
            head = {"id": completion_id, "object": "chat.completion.chunk", "created": created,
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {"role": "assistant", "content": content},
                                 "finish_reason": None}],
                    "opencode": {"model": model}}
            tail = {"id": completion_id, "object": "chat.completion.chunk", "created": created,
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            yield f"data: {json.dumps(head)}\n\n"
            yield f"data: {json.dumps(tail)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(stream_response(), media_type="text/event-stream")

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop"
        }],
        "model": request.model,
        "opencode": {"model": model}
    }

async def call_supersoldier(request: ChatCompletionRequest):
    # Super-Soldier is a single-turn specialist (max_tokens 500): forward a
    # bounded excerpt — persona + recent turns, filled newest-first — never the
    # whole history (full history blew Groq's free payload cap and fed the
    # python-intel fast paths enough text to echo the entire chat back: 247K/
    # 495K char replies, Telegram flood control). Newest-first fill guarantees
    # the current user turn always survives the budget.
    persona = ("You are Luke, Bruce's assistant on Telegram, served by the super-soldier "
               "gateway. Plain, direct English; short answers. You share one ongoing "
               "conversation with Bruce, shown below. Never claim to be ChatGPT or "
               "another AI, and never say you cannot see the conversation.\n\n")
    header = "Recent conversation:\n"
    convo = [m for m in request.messages
             if m.role in ("user", "assistant") and m.content]
    sys_msgs = [m for m in request.messages if m.role == "system" and m.content]
    ordered = sys_msgs[:1] + convo
    if ordered:
        budget = SUPER_SOLDIER_TASK_LIMIT - len(persona) - len(header)
        lines, used = [], 0
        for m in reversed(ordered):          # newest first: current turn always kept
            line = f"{m.role}: {str(m.content)[:600]}"
            if lines and used + len(line) + 1 > budget:
                break
            lines.append(line[:max(1, budget - used)])
            used += len(lines[-1]) + 1
            if used >= budget:
                break
        lines.reverse()
        prompt = persona + header + "\n".join(lines)
    else:
        prompt = persona + "\n".join(str(m.content) for m in request.messages[::-1]
                                     if m.content)
    if len(prompt) > SUPER_SOLDIER_TASK_LIMIT:
        prompt = prompt[:SUPER_SOLDIER_TASK_LIMIT]
    payload = {"task": prompt, "model": SUPER_SOLDIER_GROQ_MODEL}
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(SUPER_SOLDIER_URL, json=payload)
    except Exception as exc:
        raise HTTPException(502, f"Super-Soldier unreachable at {SUPER_SOLDIER_URL}: {exc}")
    if resp.status_code != 200:
        raise HTTPException(502, f"Super-Soldier HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if not data.get("success"):
        raise HTTPException(502, f"Super-Soldier failed: {data.get('result')}")

    content = data.get("result") or ""
    completion_id = f"supersoldier-{os.urandom(6).hex()}"
    created = int(time.time())
    if request.stream:
        async def stream_response():
            head = {"id": completion_id, "object": "chat.completion.chunk", "created": created,
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {"role": "assistant", "content": content},
                                 "finish_reason": None}],
                    "supersoldier": {"provider": data.get("provider"), "latency": data.get("latency")}}
            tail = {"id": completion_id, "object": "chat.completion.chunk", "created": created,
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            yield f"data: {json.dumps(head)}\n\n"
            yield f"data: {json.dumps(tail)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(stream_response(), media_type="text/event-stream")

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": request.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
        "supersoldier": {"provider": data.get("provider"), "latency": data.get("latency")},
    }

async def call_colibri(request: ChatCompletionRequest, authorization: Optional[str]):
    """Local ColiBRI engine (coli serve). Full pass-through: messages, tools,
    tool_choice and streaming all reach the engine untouched, so agent clients
    (Hermes) keep their entire tool loop on this model."""
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization

    payload = request.model_dump(exclude_none=True)
    for _m in payload.get("messages", []):
        if isinstance(_m, dict):
            for _k in ("reasoning_details", "reasoning", "reasoning_content", "reasoning_tokens"):
                _m.pop(_k, None)
    payload["model"] = await colibri_model_id()
    payload["stream"] = request.stream

    if request.stream:
        async def stream_response():
            try:
                async with httpx.AsyncClient(timeout=600) as client:
                    async with client.stream("POST", f"{COLIBRI_URL}/chat/completions", json=payload, headers=headers) as resp:
                        if resp.status_code != 200:
                            body = (await resp.aread()).decode("utf-8", "replace")
                            yield f"data: {json.dumps({'error': {'message': body, 'type': 'upstream_error', 'code': resp.status_code}})}\n\n"
                            yield "data: [DONE]\n\n"
                            return
                        async for line in resp.aiter_lines():
                            if line:
                                yield f"{line}\n\n"
            except httpx.HTTPError as exc:
                # Engine down mid-stream: report it instead of dropping the
                # socket, so the caller retries this provider rather than
                # falling through to a rate-limited pool.
                msg = f"colibri unreachable at {COLIBRI_URL}: {exc.__class__.__name__}: {exc}"
                yield f"data: {json.dumps({'error': {'message': msg, 'type': 'upstream_error', 'code': 503}})}\n\n"
                yield "data: [DONE]\n\n"
        return StreamingResponse(stream_response(), media_type="text/event-stream")
    else:
        try:
            async with httpx.AsyncClient(timeout=600) as client:
                resp = await client.post(f"{COLIBRI_URL}/chat/completions", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise HTTPException(503, f"colibri unreachable at {COLIBRI_URL}: {exc.__class__.__name__}: {exc}")
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        return resp.json()

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, authorization: Optional[str] = Header(None)):
    route = get_route(request.model)
    logger.info(f"Routing {request.model} -> {route}")
    
    if route == "groq":
        return await call_groq_bridge(request, authorization)
    elif route == "openrouter":
        return await call_openrouter(request, authorization)
    elif route == "opencode":
        return await call_opencode(request)
    elif route == "supersoldier":
        return await call_supersoldier(request)
    elif route == "colibri":
        return await call_colibri(request, authorization)
    else:
        raise HTTPException(400, f"Unknown route for model: {request.model}")

@app.on_event("startup")
async def warm_opencode_free_models():
    ids = await opencode_free_models()
    logger.info(f"OpenCode free models ({len(ids)}): {', '.join(ids)}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 9001))
    logger.info(f"Starting Provider Console on port {port}")
    logger.info(f"Groq Bridge: {GROQ_BRIDGE_URL}")
    logger.info(f"OpenRouter: {'configured' if OPENROUTER_API_KEY else 'NOT CONFIGURED'}")
    logger.info(f"OpenCode: {'configured' if OPENCODE_KEY else 'NOT CONFIGURED'}")
    uvicorn.run(app, host="0.0.0.0", port=port)