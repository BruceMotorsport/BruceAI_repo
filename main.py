#!/usr/bin/env python3
"""
Provider Console - FastAPI server on port 9001
Routes to: Groq Bridge (8080), NVIDIA NIM (8081), Z.AI (8082), Hetzner (8083),
Google AI Studio (8084), Cloudflare (8085), OVH (8086), Kilo (8087), OpenRouter direct
Standalone version - no external dependencies
"""
import os
import re
import json
import time
import shutil
import logging
import asyncio
from typing import List, Optional, Dict, Any
from functools import lru_cache
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
import httpx
import uvicorn

try:
    from env_loader import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return {}

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("provider_console")

app = FastAPI(title="BruceAI Provider Console", version="1.1")

# Configuration from environment
GROQ_BRIDGE_URL = os.getenv("GROQ_BRIDGE_URL", "http://127.0.0.1:8080/v1")
NVIDIA_BRIDGE_URL = os.getenv("NVIDIA_BRIDGE_URL", "http://127.0.0.1:8081/v1")
ZAI_BRIDGE_URL = os.getenv("ZAI_BRIDGE_URL", "http://127.0.0.1:8082/v1")
HETZNER_BRIDGE_URL = os.getenv("HETZNER_BRIDGE_URL", "http://127.0.0.1:8083/v1")
GOOGLE_BRIDGE_URL = os.getenv("GOOGLE_BRIDGE_URL", "http://127.0.0.1:8084/v1")
CLOUDFLARE_BRIDGE_URL = os.getenv("CLOUDFLARE_BRIDGE_URL", "http://127.0.0.1:8085/v1")
OVH_BRIDGE_URL = os.getenv("OVH_BRIDGE_URL", "http://127.0.0.1:8086/v1")
KILO_BRIDGE_URL = os.getenv("KILO_BRIDGE_URL", "http://127.0.0.1:8087/v1")
# Groq account pool (groq_pool.py). Rotates several free Groq accounts and
# handles 413/429/401 per key. Optional: when it is not answering, chat falls
# back to the single-key bridge on 8080.
GROQ_POOL_URL = os.getenv("GROQ_POOL_URL", "http://127.0.0.1:8089/v1")
GROQ_POOL_MODELS = {"openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "allam-2-7b"}
_groq_pool_state = {"ok": False, "at": 0.0}
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Model aliases for Groq (accept short names)
GROQ_MODEL_ALIASES = {
    "gpt-oss-120b": "openai/gpt-oss-120b",
    "gpt-oss-20b": "openai/gpt-oss-20b",
}

# Model aliases for NVIDIA
NVIDIA_MODEL_ALIASES = {
    "nemotron-3-ultra": "nvidia/nemotron-3-ultra-550b-a55b",
    "nemotron-3.5-lightning": "nvidia/nemotron-3.5-lightning-30b-a3b",
    "deepseek-v4.1-flash": "deepseek-ai/deepseek-v4.1-flash",
    "nemotron-3-super": "nvidia/nemotron-3-super-120b-a12b",
}

# Model aliases for Z.AI
ZAI_MODEL_ALIASES = {
    "glm-4.6v-flash": "glm-4.6v-flash",
    "glm-4.5-flash": "glm-4.5-flash",
    "glm-4.7-flash": "glm-4.7-flash",
}

# Model aliases for Hetzner
HETZNER_MODEL_ALIASES = {
    "qwen3.8-27b": "Qwen/Qwen3.8-27B-FP8",
    "qwen3.6-35b": "Qwen/Qwen3.6-35B-A3B-FP8",
}

# Model aliases for Google AI Studio
GOOGLE_MODEL_ALIASES = {
    "gemini-3.8-flash": "gemini-3.8-flash-preview",
    "gemini-2.5-flash": "gemini-2.5-flash-lite",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-flash": "gemini-3.8-flash-preview",
}

# Model aliases for Cloudflare
CLOUDFLARE_MODEL_ALIASES = {
    "llama-3.3-70b": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "llama-3.1-8b": "@cf/meta/llama-3.1-8b-instruct-fp8",
    "qwen3.8-27b": "@cf/qwen/qwen3.8-27b-fp8",
    "deepseek-v4.1-flash": "@cf/deepseek-ai/deepseek-v4.1-flash",
    "mistral-7b": "@cf/mistral/mistral-7b-instruct-v0.2",
    "gemma-2-9b": "@cf/google/gemma-2-9b-it",
    "phi-3.5-mini": "@cf/microsoft/phi-3.5-mini-instruct",
    "llama-3-8b": "@cf/meta/llama-3-8b-instruct",
}

# Model aliases for OVH
OVH_MODEL_ALIASES = {
    "llama-3.3-70b": "llama-3.3-70b-instruct",
    "gpt-oss-20b": "gpt-oss-20b",
    "gpt-oss-120b": "gpt-oss-120b",
    "qwen3.5-9b": "qwen3.5-9b",
}

# Model aliases for Kilo
KILO_MODEL_ALIASES = {
    "nemotron-3-nano": "nemotron-3-nano-omni-30b-a3b-reasoning",
    "lfm-2.5": "liquid/lfm-2.5-2.6b",
    "xing4.0": "xingchen-agi/xing4.0-29b-a4b:free",
    "laguna-s": "poolside/laguna-s-2.1:free",
    "laguna-xs": "poolside/laguna-xs-2.1:free",
}

# Working model routes (only verified working models)
MODEL_ROUTES = {
    # Groq models -> Groq Bridge (free tier)
    "openai/gpt-oss-120b": "groq",
    "openai/gpt-oss-20b": "groq",
    "qwen/qwen3.8-27b": "groq",
    "allam-2-7b": "groq",
    "canopylabs/orpheus-v1-english": "groq",
    "whisper-large-v3": "groq",
    "whisper-large-v3-turbo": "groq",
    # NVIDIA NIM models -> NVIDIA Bridge
    "nvidia/nemotron-3-ultra-550b-a55b": "nvidia",
    "nvidia/nemotron-3.5-lightning-30b-a3b": "nvidia",
    "deepseek-ai/deepseek-v4.1-flash": "nvidia",
    "nvidia/nemotron-3-super-120b-a12b": "nvidia",
    # Z.AI models -> Z.AI Bridge
    "glm-4.6v-flash": "zai",
    "glm-4.5-flash": "zai",
    "glm-4.7-flash": "zai",
    # Hetzner models -> Hetzner Bridge
    "Qwen/Qwen3.8-27B-FP8": "hetzner",
    "Qwen/Qwen3.6-35B-A3B-FP8": "hetzner",
    # Google AI Studio models -> Google Bridge
    "gemini-3.8-flash-preview": "google",
    "gemini-2.5-flash-lite": "google",
    "gemini-2.5-pro": "google",
    "gemini-3.1-flash-lite": "google",
    "gemini-3.5-flash-lite": "google",
    # Cloudflare models -> Cloudflare Bridge
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast": "cloudflare",
    "@cf/meta/llama-3.1-8b-instruct-fp8": "cloudflare",
    "@cf/qwen/qwen3.8-27b-fp8": "cloudflare",
    "@cf/deepseek-ai/deepseek-v4.1-flash": "cloudflare",
    "@cf/mistral/mistral-7b-instruct-v0.2": "cloudflare",
    "@cf/google/gemma-2-9b-it": "cloudflare",
    "@cf/microsoft/phi-3.5-mini-instruct": "cloudflare",
    "@cf/meta/llama-3-8b-instruct": "cloudflare",
    # OVH models -> OVH Bridge
    "llama-3.3-70b-instruct": "ovh",
    "gpt-oss-20b": "ovh",
    "gpt-oss-120b": "ovh",
    "qwen3.5-9b": "ovh",
    # Kilo models -> Kilo Bridge
    "nemotron-3-nano-omni-30b-a3b-reasoning": "kilo",
    "liquid/lfm-2.5-2.6b": "kilo",
    "xingchen-agi/xing4.0-29b-a4b:free": "kilo",
    "poolside/laguna-s-2.1:free": "kilo",
    "poolside/laguna-xs-2.1:free": "kilo",
    # OpenRouter (verified free models only)
    "nvidia/nemotron-3-ultra-550b-a55b:free": "openrouter",
    # Everything else -> OpenRouter (will be blocked if not :free)
}

# OpenRouter free models that are currently working
# (verified against OpenRouter free-tier routes; ":free" suffix is required)
OPENROUTER_FREE_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-31b-it:free",
]

# OpenCode free tier. The CLI owns its own auth (`opencode auth login`), so no
# key gate here: injecting an expired OPENCODE_API_KEY makes every free model
# fail with "This API key has expired" - it is stripped from the child env.
OPENCODE_FREE_TTL = int(os.getenv("OPENCODE_FREE_TTL", "600"))
# Verified live against `opencode models` + a real completion on 2026-11-17.
# Removed since: crouton-alpha-free (Nov 9), pulse-alpha-free (Nov 6),
# nemotron-3-ultra-free and jev-1.13-free (both now "Model unavailable"),
# minimax-m3.1-flash-free (yanked same day, ~30 min after verification).
# NOTE: `iceman-free` is upstream-flaky (roughly 1 in 3) - it fails with a
# server-side "Invalid mai-internal-deployment-override" error, not a local one.
OPENCODE_FREE_FALLBACK = [
    "opencode/big-pickle",
    "opencode/inkling-2-small-free",
    "opencode/glm-5.3-flash-free",
    "opencode/deepseek-v4.1-flash-free",
    "opencode/beam-free",
    "opencode/flint-40b-free",
    "opencode/longcat-2.5-free",
    "opencode/hy4-flash-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/nemotron-3.5-lightning-free",
    "opencode/nemotron-3.5-super-vl-free",
]
_opencode_free_state = {"ids": list(OPENCODE_FREE_FALLBACK), "at": 0.0}
# Full CLI catalog (every provider id it accepts), same TTL as the free list.
# Used to answer stale picker entries with a real 404 instead of a CLI failure.
_opencode_catalog_state = {"ids": [], "at": 0.0}
_OPENCODE_BIN: Optional[str] = None

# Health check cache (30 second TTL)
_health_cache = {"groq_status": None, "last_check": 0}
HEALTH_CACHE_TTL = 30

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

def normalize_groq_model(model: str) -> str:
    """Resolve Groq model aliases."""
    return GROQ_MODEL_ALIASES.get(model, model)

def normalize_nvidia_model(model: str) -> str:
    """Resolve NVIDIA model aliases."""
    return NVIDIA_MODEL_ALIASES.get(model, model)

def normalize_zai_model(model: str) -> str:
    """Resolve Z.AI model aliases."""
    return ZAI_MODEL_ALIASES.get(model, model)

def normalize_hetzner_model(model: str) -> str:
    """Resolve Hetzner model aliases."""
    return HETZNER_MODEL_ALIASES.get(model, model)

def normalize_google_model(model: str) -> str:
    """Resolve Google AI Studio model aliases."""
    return GOOGLE_MODEL_ALIASES.get(model, model)

def normalize_cloudflare_model(model: str) -> str:
    """Resolve Cloudflare model aliases."""
    return CLOUDFLARE_MODEL_ALIASES.get(model, model)

def normalize_ovh_model(model: str) -> str:
    """Resolve OVH model aliases."""
    return OVH_MODEL_ALIASES.get(model, model)

def normalize_kilo_model(model: str) -> str:
    """Resolve Kilo model aliases."""
    return KILO_MODEL_ALIASES.get(model, model)

def opencode_bin() -> Optional[str]:
    """Locate the opencode CLI.

    The console may be spawned by the supervisor with a PATH that lacks the npm
    global dir, so probe the well-known install locations as well as PATH.
    """
    global _OPENCODE_BIN
    if _OPENCODE_BIN:
        return _OPENCODE_BIN
    candidates: List[str] = []
    if os.getenv("OPENCODE_BIN"):
        candidates.append(os.environ["OPENCODE_BIN"])
    for name in ("opencode.exe", "opencode", "opencode.cmd"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    npm_dir = os.path.join(os.environ.get("APPDATA", ""), "npm")
    for name in ("opencode.exe", "opencode.cmd", "opencode"):
        candidates.append(os.path.join(npm_dir, name))
    for cand in candidates:
        if cand and os.path.isfile(cand):
            _OPENCODE_BIN = cand
            return cand
    return None

def opencode_argv() -> Optional[List[str]]:
    """Runnable argv prefix for the OpenCode CLI (.cmd shims need cmd.exe /c)."""
    path = opencode_bin()
    if not path:
        return None
    if path.lower().endswith((".cmd", ".bat")):
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", path]
    return [path]

def _opencode_local_file(name: str) -> str:
    """Path to a small optional config file next to main.py."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)

def _read_opencode_local_file(name: str) -> str:
    """First non-empty line of an optional config file ('' when absent)."""
    try:
        with open(_opencode_local_file(name), "r", encoding="utf-8") as fh:
            for line in fh:
                value = line.strip()
                if value and not value.startswith("#"):
                    return value
    except OSError:
        pass
    return ""

def opencode_server_url() -> str:
    """Optional OpenCode server on another LAN machine (its quota, not ours).

    OPENCODE_SERVER_URL wins; otherwise opencode_server.txt next to main.py,
    so the setting survives restarts launched without a custom environment.
    """
    return os.getenv("OPENCODE_SERVER_URL", "").strip() or _read_opencode_local_file("opencode_server.txt")

def opencode_child_env() -> dict:
    """Child env for the CLI: no stale API key; remote-server password if set.

    `opencode --server <url>` refuses an instance protected by service.json and
    asks for OPENCODE_PASSWORD, so an optional OPENCODE_SERVER_PASSWORD (this
    console's name for it) is forwarded under the CLI's expected name. The
    secret is only ever read from the environment or the gitignored
    opencode_server_password.txt, never logged.
    """
    env = {k: v for k, v in os.environ.items() if k != "OPENCODE_API_KEY"}
    secret = os.getenv("OPENCODE_SERVER_PASSWORD", "").strip() or os.getenv("OPENCODE_PASSWORD", "").strip()
    if not secret:
        secret = _read_opencode_local_file(
            os.getenv("OPENCODE_SERVER_PASSWORD_FILE", "").strip() or "opencode_server_password.txt"
        )
    if secret:
        env["OPENCODE_PASSWORD"] = secret
    return env

def opencode_models_argv(argv: List[str]) -> List[str]:
    """`opencode models`, pointed at the remote server when one is configured.

    The flag must follow the subcommand: `opencode --server ... models` is
    parsed as the top-level form and prints the subcommand help instead.
    """
    cmd = [*argv, "models"]
    server_url = opencode_server_url()
    if server_url:
        cmd += ["--server", server_url]
    return cmd

def normalize_opencode_model(model: str) -> str:
    """Legacy ids alias the default free model; bare names get the opencode/ prefix."""
    if model in ("opencode", "opencode-zen", ""):
        return OPENCODE_FREE_FALLBACK[0]
    return model if "/" in model else f"opencode/{model}"

async def discover_opencode_free_models() -> List[str]:
    """Read the live free catalog from `opencode models`.

    The free set churns (models are added and yanked without notice), so the
    hardcoded list is only a fallback for when the CLI is missing or slow.
    """
    argv = opencode_argv()
    if not argv:
        return list(OPENCODE_FREE_FALLBACK)
    try:
        proc = await asyncio.create_subprocess_exec(
            *opencode_models_argv(argv),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=opencode_child_env(),
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
    except Exception:
        return list(OPENCODE_FREE_FALLBACK)
    if proc.returncode != 0:
        return list(OPENCODE_FREE_FALLBACK)
    ids: List[str] = []
    for line in stdout.decode("utf-8", "replace").splitlines():
        mid = line.strip()
        # Only the free console namespace; opencode-go/ and other providers are
        # separate catalogs with their own billing.
        if mid.startswith("opencode/") and mid not in ids:
            ids.append(mid)
    return ids or list(OPENCODE_FREE_FALLBACK)

async def opencode_free_models() -> List[str]:
    """Cached live free-model ids (TTL: OPENCODE_FREE_TTL seconds)."""
    now = time.time()
    if now - float(_opencode_free_state["at"]) > OPENCODE_FREE_TTL:
        ids = await discover_opencode_free_models()
        _opencode_free_state["ids"] = ids
        _opencode_free_state["at"] = now
    return list(_opencode_free_state["ids"])

async def opencode_catalog() -> List[str]:
    """Cached list of every model id `opencode models` currently accepts.

    Lets the console answer a stale picker entry (an id the CLI no longer
    knows, e.g. a leftover local provider) with a clear 404 instead of
    spawning the CLI and turning its opaque failure into a 500.
    """
    now = time.time()
    if now - float(_opencode_catalog_state["at"]) <= OPENCODE_FREE_TTL:
        return list(_opencode_catalog_state["ids"])
    argv = opencode_argv()
    ids: List[str] = []
    if argv:
        try:
            proc = await asyncio.create_subprocess_exec(
                *opencode_models_argv(argv),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=opencode_child_env(),
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            for line in stdout.decode("utf-8", "replace").splitlines():
                mid = line.strip()
                if "/" in mid and mid not in ids:
                    ids.append(mid)
        except Exception:
            ids = []
    if ids:
        _opencode_catalog_state["ids"] = ids
    _opencode_catalog_state["at"] = now
    return list(_opencode_catalog_state["ids"])

def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)

def get_route(model: str) -> str:
    """Determine which backend to route to."""
    # OpenCode free tier: aliases, explicit opencode/ ids, and bare ids that we
    # advertise in /v1/models (checked before the OpenRouter catch-all).
    if model in ("opencode", "opencode-zen") or model.startswith("opencode/"):
        return "opencode"
    if "/" not in model and any(m.split("/", 1)[-1] == model for m in _opencode_free_state["ids"]):
        return "opencode"
    # Try each normalization
    normalized = normalize_groq_model(model)
    if normalized in MODEL_ROUTES:
        return MODEL_ROUTES[normalized]
    normalized = normalize_nvidia_model(model)
    if normalized in MODEL_ROUTES:
        return MODEL_ROUTES[normalized]
    normalized = normalize_zai_model(model)
    if normalized in MODEL_ROUTES:
        return MODEL_ROUTES[normalized]
    normalized = normalize_hetzner_model(model)
    if normalized in MODEL_ROUTES:
        return MODEL_ROUTES[normalized]
    normalized = normalize_google_model(model)
    if normalized in MODEL_ROUTES:
        return MODEL_ROUTES[normalized]
    normalized = normalize_cloudflare_model(model)
    if normalized in MODEL_ROUTES:
        return MODEL_ROUTES[normalized]
    normalized = normalize_ovh_model(model)
    if normalized in MODEL_ROUTES:
        return MODEL_ROUTES[normalized]
    normalized = normalize_kilo_model(model)
    if normalized in MODEL_ROUTES:
        return MODEL_ROUTES[normalized]
    # Direct lookup
    return MODEL_ROUTES.get(model, "openrouter")

@app.get("/health")
async def health():
    import time
    now = time.time()

    # Return cached health if within TTL
    if now - _health_cache["last_check"] < HEALTH_CACHE_TTL and _health_cache["groq_status"]:
        pool_ok = await groq_pool_available()
        return {
            "status": "ok",
            "port": 9001,
            "groq_bridge": _health_cache["groq_status"],
            "groq_pool": "healthy" if pool_ok else "unavailable",
            "openrouter_configured": bool(OPENROUTER_API_KEY),
            "opencode_configured": bool(opencode_bin()),
            "opencode_free_models": len(_opencode_free_state["ids"]),
            "cached": True
        }

    # Check Groq bridge connectivity
    groq_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            base_url = GROQ_BRIDGE_URL.replace("/v1", "")
            resp = await client.get(f"{base_url}/health")
            if resp.status_code == 200:
                groq_status = "healthy"
            else:
                groq_status = f"degraded ({resp.status_code})"
    except Exception as e:
        groq_status = f"unreachable ({e})"

    # Update cache
    _health_cache["groq_status"] = groq_status
    _health_cache["last_check"] = now

    return {
        "status": "ok",
        "port": 9001,
        "groq_bridge": groq_status,
        "groq_pool": "healthy" if await groq_pool_available() else "unavailable",
        "openrouter_configured": bool(OPENROUTER_API_KEY),
        "opencode_configured": bool(opencode_bin()),
        "opencode_free_models": len(_opencode_free_state["ids"]),
        "cached": False
    }

def dedupe_models(models: List[Model]) -> List[Model]:
    unique: Dict[str, Model] = {}
    for m in models:
        unique.setdefault(m.id, m)
    return list(unique.values())

@app.get("/v1/models")
async def list_models():
    # Only return verified working models
    models = []

    # Groq models (from bridge)
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
        # Fallback when the bridge is unreachable: advertise only the model that
        # the Groq project actually serves (others are blocked at project level).
        for m in ["openai/gpt-oss-120b"]:
            models.append(Model(id=m, owned_by="groq"))

    # OpenRouter free models (verified working)
    for m in OPENROUTER_FREE_MODELS:
        models.append(Model(id=m, owned_by="openrouter"))

    # OpenCode free models - live catalog (TTL-cached), so the picker shows
    # exactly what `opencode run -m` will accept.
    for mid in await opencode_free_models():
        models.append(Model(id=mid, owned_by="opencode"))

    return ModelsResponse(data=dedupe_models(models))

async def groq_pool_available() -> bool:
    """Cached (20 s) probe of the multi-account Groq pool's /health."""
    now = time.time()
    if now - float(_groq_pool_state["at"]) > 20:
        base_url = GROQ_POOL_URL.rsplit("/v1", 1)[0]
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{base_url}/health")
            body = resp.json() if resp.status_code == 200 else {}
            _groq_pool_state["ok"] = resp.status_code == 200 and body.get("status") == "ok"
        except Exception:
            _groq_pool_state["ok"] = False
        _groq_pool_state["at"] = now
    return bool(_groq_pool_state["ok"])

async def call_groq_bridge(request: ChatCompletionRequest, authorization: str = Header(None)):
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization

    # Normalize model name for Groq Bridge
    payload = request.model_dump(exclude_none=True)
    payload["model"] = normalize_groq_model(request.model)
    payload["stream"] = request.stream
    if request.max_tokens:
        payload["max_tokens"] = request.max_tokens

    # Prefer the multi-account pool for its model set; it rotates keys on
    # 429/401/403/5xx and hops long turns to a same-model fallback.
    base = GROQ_BRIDGE_URL
    if payload["model"] in GROQ_POOL_MODELS and await groq_pool_available():
        base = GROQ_POOL_URL

    if request.stream:
        async def stream_response():
            async with httpx.AsyncClient(timeout=180) as client:
                async with client.stream("POST", f"{base}/chat/completions", json=payload, headers=headers) as resp:
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
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(f"{base}/chat/completions", json=payload, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        return resp.json()

async def call_openrouter(request: ChatCompletionRequest, authorization: str = Header(None)):
    if not OPENROUTER_API_KEY:
        raise HTTPException(500, "OpenRouter API key not configured")

    # Free-models-only policy. "openrouter/free" is OpenRouter's own
    # free-only router, so the suffix check alone wrongly blocked it.
    if not (request.model.endswith(":free") or request.model == "openrouter/free"):
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

async def call_nvidia_bridge(request: ChatCompletionRequest, authorization: str = Header(None)):
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization

    payload = request.model_dump(exclude_none=True)
    payload["model"] = normalize_nvidia_model(request.model)
    payload["stream"] = request.stream
    if request.max_tokens:
        payload["max_tokens"] = request.max_tokens

    if request.stream:
        async def stream_response():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", f"{NVIDIA_BRIDGE_URL}/chat/completions", json=payload, headers=headers) as resp:
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
            resp = await client.post(f"{NVIDIA_BRIDGE_URL}/chat/completions", json=payload, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        return resp.json()

async def call_zai_bridge(request: ChatCompletionRequest, authorization: str = Header(None)):
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization

    payload = request.model_dump(exclude_none=True)
    payload["model"] = normalize_zai_model(request.model)
    payload["stream"] = request.stream
    if request.max_tokens:
        payload["max_tokens"] = request.max_tokens

    if request.stream:
        async def stream_response():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", f"{ZAI_BRIDGE_URL}/chat/completions", json=payload, headers=headers) as resp:
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
            resp = await client.post(f"{ZAI_BRIDGE_URL}/chat/completions", json=payload, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        return resp.json()

async def call_hetzner_bridge(request: ChatCompletionRequest, authorization: str = Header(None)):
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization

    payload = request.model_dump(exclude_none=True)
    payload["model"] = normalize_hetzner_model(request.model)
    payload["stream"] = request.stream
    if request.max_tokens:
        payload["max_tokens"] = request.max_tokens

    if request.stream:
        async def stream_response():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", f"{HETZNER_BRIDGE_URL}/chat/completions", json=payload, headers=headers) as resp:
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
            resp = await client.post(f"{HETZNER_BRIDGE_URL}/chat/completions", json=payload, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        return resp.json()

async def call_google_bridge(request: ChatCompletionRequest, authorization: str = Header(None)):
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization

    payload = request.model_dump(exclude_none=True)
    payload["model"] = normalize_google_model(request.model)
    payload["stream"] = request.stream
    if request.max_tokens:
        payload["max_tokens"] = request.max_tokens

    if request.stream:
        async def stream_response():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", f"{GOOGLE_BRIDGE_URL}/chat/completions", json=payload, headers=headers) as resp:
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
            resp = await client.post(f"{GOOGLE_BRIDGE_URL}/chat/completions", json=payload, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        return resp.json()

async def call_cloudflare_bridge(request: ChatCompletionRequest, authorization: str = Header(None)):
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization

    payload = request.model_dump(exclude_none=True)
    payload["model"] = normalize_cloudflare_model(request.model)
    payload["stream"] = request.stream
    if request.max_tokens:
        payload["max_tokens"] = request.max_tokens

    if request.stream:
        async def stream_response():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", f"{CLOUDFLARE_BRIDGE_URL}/chat/completions", json=payload, headers=headers) as resp:
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
            resp = await client.post(f"{CLOUDFLARE_BRIDGE_URL}/chat/completions", json=payload, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        return resp.json()

async def call_ovh_bridge(request: ChatCompletionRequest, authorization: str = Header(None)):
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization

    payload = request.model_dump(exclude_none=True)
    payload["model"] = normalize_ovh_model(request.model)
    payload["stream"] = request.stream
    if request.max_tokens:
        payload["max_tokens"] = request.max_tokens

    if request.stream:
        async def stream_response():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", f"{OVH_BRIDGE_URL}/chat/completions", json=payload, headers=headers) as resp:
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
            resp = await client.post(f"{OVH_BRIDGE_URL}/chat/completions", json=payload, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        return resp.json()

async def call_kilo_bridge(request: ChatCompletionRequest, authorization: str = Header(None)):
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization

    payload = request.model_dump(exclude_none=True)
    payload["model"] = normalize_kilo_model(request.model)
    payload["stream"] = request.stream
    if request.max_tokens:
        payload["max_tokens"] = request.max_tokens

    if request.stream:
        async def stream_response():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", f"{KILO_BRIDGE_URL}/chat/completions", json=payload, headers=headers) as resp:
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
            resp = await client.post(f"{KILO_BRIDGE_URL}/chat/completions", json=payload, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)
        return resp.json()

# Character budget for the prompt piped into `opencode run`.
OPENCODE_PROMPT_LIMIT = 400000

def _content_text(value: Any) -> str:
    """Flatten OpenAI message content (string or content-block list) to text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: List[str] = []
        for block in value:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") in (None, "text", "input_text", "output_text"):
                    parts.append(str(block.get("text") or block.get("content") or ""))
        return "\n".join(p for p in parts if p)
    return str(value)

def build_opencode_prompt(messages, limit: int = OPENCODE_PROMPT_LIMIT) -> str:
    """Serialise a conversation for `opencode run`, keeping the newest turn.

    The prompt is piped in on stdin, but it still has to be bounded: the model
    behind the CLI has its own window. Qoder's agent system prompt alone can be
    ~35-43k chars, so cutting from the tail deletes the user's message and the
    model answers with a greeting. Reserve the newest turns first, then give
    whatever space is left to the system prompt.
    """
    system_parts: List[str] = []
    turns: List[tuple] = []
    for message in messages:
        text = _content_text(message.content).strip()
        if not text:
            continue
        if message.role == "system":
            system_parts.append(text)
        else:
            turns.append((message.role, text))

    selected: List[str] = []
    used = 0
    for role, text in reversed(turns):          # newest first: current turn survives
        room = limit - used
        if room <= len(role) + 3:
            break
        line = f"{role}: {text}"[:room]
        selected.append(line)
        used += len(line) + 1
        if used >= limit:
            break
    selected.reverse()

    prompt = "\n".join(selected)
    system_text = "\n\n".join(system_parts)
    prefix = "system: "
    room = limit - len(prompt) - len(prefix) - (2 if prompt else 0)
    if system_text and room > 40:
        if len(system_text) > room:
            marker = "\n[...system prompt truncated...]"
            system_text = system_text[:max(0, room - len(marker))].rstrip() + marker
        prompt = prefix + system_text + ("\n\n" + prompt if prompt else "")
    return prompt[:limit]

async def call_opencode(request: ChatCompletionRequest):
    """Serve a free OpenCode model by spawning the OpenCode CLI.

    No key gate: the free models answer without credentials and the CLI owns
    its own auth (`opencode auth login`). Injecting an expired
    OPENCODE_API_KEY makes every free model fail with "This API key has
    expired", so it is stripped from the child env.

    The prompt goes in on stdin. Windows caps a CreateProcess command line at
    32767 characters, so passing an agent-sized prompt as an argv string made
    the CLI exit with "The command line is too long" and the whole Qoder turn
    failed as HTTP 500. `opencode run` reads stdin when no message is given.
    """
    model = normalize_opencode_model(request.model)
    if request.model in ("opencode", "opencode-zen"):
        free = await opencode_free_models()
        model = free[0] if free else OPENCODE_FREE_FALLBACK[0]

    # Reject stale picker entries before spawning the CLI, so an id the CLI no
    # longer knows answers 404 with the live list instead of an opaque 500.
    catalog = await opencode_catalog()
    if catalog and model not in catalog:
        free = await opencode_free_models()
        raise HTTPException(
            404,
            f"'{request.model}' is not in the current OpenCode catalog (stale entry). "
            f"Available free ids: {', '.join(free)}",
        )

    prompt = build_opencode_prompt(request.messages)
    if not prompt:
        prompt = "continue"

    argv = opencode_argv()
    if not argv:
        raise HTTPException(500, "OpenCode CLI not found (opencode missing)")
    # Optional: use another machine's OpenCode server (e.g. one whose free
    # allowance is not spent yet). The model call then leaves from THAT host,
    # so its quota is the one consumed. Set OPENCODE_SERVER_URL=http://host:4096.
    run_argv = [*argv, "run"]
    server_url = opencode_server_url()
    if server_url:
        # After the subcommand: `opencode --server ... run` only prints help.
        run_argv += ["--server", server_url]
    run_argv += ["-m", model]

    # The free CLI occasionally exits 0 with empty stdout. A 200-with-empty
    # makes callers fall back to the exhausted OpenRouter pool (429 loop), so
    # retry once, then fail loudly so they retry this provider instead.
    content = ""
    for attempt in (1, 2):
        try:
            proc = await asyncio.create_subprocess_exec(
                *run_argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=opencode_child_env(),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")), timeout=300
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise HTTPException(504, "OpenCode timeout")
        except FileNotFoundError:
            raise HTTPException(500, "OpenCode CLI not installed")
        except OSError as exc:
            raise HTTPException(502, f"OpenCode spawn failed: {exc}")

        err = strip_ansi(stderr.decode("utf-8", "replace"))
        if proc.returncode != 0:
            # A yanked free model is a client-side 404, not a server fault;
            # leaving it as 500 made the desktop app say "Internal Server Error".
            if "Model unavailable" in err:
                raise HTTPException(404, f"Model unavailable upstream ({model})")
            # The free tier meters usage per model/IP. When it is spent the CLI
            # exits non-zero with "Free usage limit reached"; surfacing that as a
            # 502 made Qoder show a phantom "Internal server error" instead of
            # telling the user to pick another model. 429 with the real reason.
            if "usage limit" in err.lower():
                raise HTTPException(
                    429,
                    f"OpenCode free usage limit reached for {model} - switch to another free model or wait for the limit to reset",
                )
            raise HTTPException(502, f"OpenCode error ({model}): {err[:400]}")

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
            head = {
                "id": completion_id, "object": "chat.completion.chunk",
                "created": created, "model": request.model,
                "choices": [{"index": 0,
                             "delta": {"role": "assistant", "content": content},
                             "finish_reason": None}],
                "opencode": {"model": model},
            }
            tail = {
                "id": completion_id, "object": "chat.completion.chunk",
                "created": created, "model": request.model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(head)}\n\n"
            yield f"data: {json.dumps(tail)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(stream_response(), media_type="text/event-stream")

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": request.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "opencode": {"model": model},
    }

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, authorization: str = Header(None)):
    route = get_route(request.model)
    logger.info(f"Routing {request.model} -> {route}")

    if route == "opencode":
        return await call_opencode(request)
    elif route == "groq":
        return await call_groq_bridge(request, authorization)
    elif route == "nvidia":
        return await call_nvidia_bridge(request, authorization)
    elif route == "zai":
        return await call_zai_bridge(request, authorization)
    elif route == "hetzner":
        return await call_hetzner_bridge(request, authorization)
    elif route == "google":
        return await call_google_bridge(request, authorization)
    elif route == "cloudflare":
        return await call_cloudflare_bridge(request, authorization)
    elif route == "ovh":
        return await call_ovh_bridge(request, authorization)
    elif route == "kilo":
        return await call_kilo_bridge(request, authorization)
    elif route == "openrouter":
        return await call_openrouter(request, authorization)
    else:
        raise HTTPException(400, f"Unknown route for model: {request.model}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 9001))
    logger.info(f"Starting Provider Console on port {port}")
    logger.info(f"Groq Bridge: {GROQ_BRIDGE_URL}")
    logger.info(f"NVIDIA Bridge: {NVIDIA_BRIDGE_URL}")
    logger.info(f"Z.AI Bridge: {ZAI_BRIDGE_URL}")
    logger.info(f"Hetzner Bridge: {HETZNER_BRIDGE_URL}")
    logger.info(f"Google Bridge: {GOOGLE_BRIDGE_URL}")
    logger.info(f"Cloudflare Bridge: {CLOUDFLARE_BRIDGE_URL}")
    logger.info(f"OVH Bridge: {OVH_BRIDGE_URL}")
    logger.info(f"Kilo Bridge: {KILO_BRIDGE_URL}")
    logger.info(f"OpenRouter: {'configured' if OPENROUTER_API_KEY else 'NOT CONFIGURED'}")
    logger.info(f"OpenCode: {opencode_bin() or 'NOT FOUND'} ({len(OPENCODE_FREE_FALLBACK)} free models)")
    uvicorn.run(app, host="0.0.0.0", port=port)