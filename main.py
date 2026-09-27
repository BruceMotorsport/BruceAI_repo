#!/usr/bin/env python3
"""
Provider Console - FastAPI server on port 9001
Routes to: Groq Bridge (8080), OpenCode subprocess, OpenRouter direct
Standalone version - no external dependencies
"""
import os
import json
import logging
import subprocess
import asyncio
from typing import List, Optional, Dict, Any
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

app = FastAPI(title="BruceAI Provider Console", version="1.0")

# Configuration from environment
GROQ_BRIDGE_URL = os.getenv("GROQ_BRIDGE_URL", "http://127.0.0.1:8080/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENCODE_KEY = os.getenv("OPENCODE_KEY")

# Model routing map
MODEL_ROUTES = {
    # Groq models -> Groq Bridge (free tier: 8k tokens/min — small payloads only)
    "qwen/qwen3.8-27b": "groq",
    "allam-2-7b": "groq",
    "canopylabs/orpheus-v1-english": "groq",
    "whisper-large-v3": "groq",
    "whisper-large-v3-turbo": "groq",
    # OpenCode models -> subprocess
    "opencode": "opencode",
    "opencode-zen": "opencode",
    # OpenRouter (paid) — agentic payloads
    "openai/gpt-oss-120b": "openrouter",
    "openai/gpt-oss-20b": "openrouter",
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

def get_route(model: str) -> str:
    """Determine which backend to route to"""
    return MODEL_ROUTES.get(model, "openrouter")

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
    
    # OpenCode models
    models.append(Model(id="opencode", owned_by="opencode"))
    models.append(Model(id="opencode-zen", owned_by="opencode"))
    
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
    
    # Call OpenCode CLI as subprocess
    prompt = "\n".join([f"{m.role}: {m.content}" for m in request.messages])
    
    try:
        proc = await asyncio.create_subprocess_exec(
            "opencode", "run", "--model", request.model, "--prompt", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "OPENCODE_API_KEY": OPENCODE_KEY}
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        
        if proc.returncode != 0:
            raise HTTPException(500, f"OpenCode error: {stderr.decode()}")
        
        return {
            "id": "opencode-" + os.urandom(8).hex(),
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": stdout.decode().strip()},
                "finish_reason": "stop"
            }],
            "model": request.model
        }
    except asyncio.TimeoutError:
        raise HTTPException(504, "OpenCode timeout")
    except FileNotFoundError:
        raise HTTPException(500, "OpenCode CLI not installed")

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
    else:
        raise HTTPException(400, f"Unknown route for model: {request.model}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 9001))
    logger.info(f"Starting Provider Console on port {port}")
    logger.info(f"Groq Bridge: {GROQ_BRIDGE_URL}")
    logger.info(f"OpenRouter: {'configured' if OPENROUTER_API_KEY else 'NOT CONFIGURED'}")
    logger.info(f"OpenCode: {'configured' if OPENCODE_KEY else 'NOT CONFIGURED'}")
    uvicorn.run(app, host="0.0.0.0", port=port)