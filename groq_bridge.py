#!/usr/bin/env python3
"""
Groq Free Tier Bridge — OpenAI-Compatible Local Server (UPDATED 2026-09-23)
============================================================================
Runs a local OpenAI-compatible API server that proxies to Groq free tier.
Hermes connects to this as a custom provider.

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
import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
import uvicorn
import httpx

try:
    from env_loader import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return {}

load_dotenv()


# ─── CONFIG ──────────────────────────────────────────────────────────────
GROQ_API_BASE = "https://api.groq.com/openai/v1"
CHAT_MODELS = [
    "openai/gpt-oss-120b",           # PRIMARY - 120B, reasoning
    "openai/gpt-oss-20b",            # fallback 1 - smaller, faster
    "qwen/qwen3.8-27b",              # fallback 2 - Qwen 27B
    "allam-2-7b",                    # fallback 3 - Arabic
]
AUDIO_MODELS = [
    "canopylabs/orpheus-v1-english", # TTS
    "whisper-large-v3",              # audio
    "whisper-large-v3-turbo",        # fast audio
]
GROQ_MODELS = CHAT_MODELS + AUDIO_MODELS

# Models the Groq project actually accepts are detected at startup: the key's
# /models endpoint returns 403, so the only honest check is a tiny request per
# chat model. Anything blocked at project level is dropped from /v1/models so
# clients (Hermes picker, BruceAI console, DeerFlow) stop offering it.
_available_chat_models: Optional[List[str]] = None

DEFAULT_MODEL = "openai/gpt-oss-120b"

# Model aliases for convenience
GROQ_MODEL_ALIASES = {
    "gpt-oss-120b": "openai/gpt-oss-120b",
    "gpt-oss-20b": "openai/gpt-oss-20b",
}


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
    
    def _resolve_model(self, model: str) -> str:
        """Resolve model name, accepting aliases."""
        if model in GROQ_MODEL_ALIASES:
            return GROQ_MODEL_ALIASES[model]
        if model not in GROQ_MODELS and model != "auto":
            return DEFAULT_MODEL
        return model

    async def chat_completion(self, request: ChatCompletionRequest) -> Dict[str, Any]:
        model = self._resolve_model(request.model)
        
        payload = request.model_dump(exclude_none=True)
        payload["model"] = model
        
        resp = await self.client.post("/chat/completions", json=payload)
        
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        
        return resp.json()
    
    async def chat_completion_stream(self, request: ChatCompletionRequest):
        model = self._resolve_model(request.model)
        
        payload = request.model_dump(exclude_none=True)
        payload["model"] = model
        payload["stream"] = True
        
        async with self.client.stream("POST", "/chat/completions", json=payload) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                detail = body.decode(errors="replace")
                print(f"[groq_bridge] upstream {resp.status_code} on stream: {detail[:500]}", flush=True)
                err = json.dumps({"error": {"message": detail[:500], "type": "upstream_error", "code": resp.status_code}})
                yield f"data: {err}\n\n"
                yield "data: [DONE]\n\n"
                return
            
            async for line in resp.aiter_lines():
                if line.strip():
                    if line.startswith("data:") or line.startswith("event:"):
                        yield f"{line}\n\n"
                    else:
                        yield f"data: {line}\n\n"
            yield "data: [DONE]\n\n"
    
    async def list_models(self) -> List[ModelInfo]:
        live = _available_chat_models if _available_chat_models is not None else CHAT_MODELS
        return [ModelInfo(id=m) for m in (live + AUDIO_MODELS)]

    async def probe_chat_models(self) -> List[str]:
        """Drop chat models this key's project rejects (403/404).

        A 403 here is a project-level block, so advertising the model only
        produces failures downstream. Other statuses (400, 429, timeouts) mean
        the model exists and is kept, so a transient error never hides it.
        """
        usable: List[str] = []
        for model in CHAT_MODELS:
            try:
                resp = await self.client.post(
                    "/chat/completions",
                    json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 4},
                )
                if resp.status_code in (403, 404):
                    print(f"[groq_bridge] dropping {model}: HTTP {resp.status_code} ({resp.text[:160]})", flush=True)
                    continue
                usable.append(model)
            except Exception as exc:
                print(f"[groq_bridge] probe {model} failed ({type(exc).__name__}); keeping it", flush=True)
                usable.append(model)
        return usable
    
    async def close(self):
        await self.client.aclose()


# ─── SERVER ──────────────────────────────────────────────────────────────
groq_client: Optional[GroqClient] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global groq_client, _available_chat_models
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("WARNING: GROQ_API_KEY not set. Set it in environment.")
    else:
        groq_client = GroqClient(api_key)
        _available_chat_models = await groq_client.probe_chat_models()
        print(f"Groq Bridge started. Chat models usable: {', '.join(_available_chat_models) or 'none'}", flush=True)
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
        return StreamingResponse(
            groq_client.chat_completion_stream(request),
            media_type="text/event-stream",
        )
    else:
        result = await groq_client.chat_completion(request)
        return result

@app.get("/health")
async def health():
    live = _available_chat_models if _available_chat_models is not None else CHAT_MODELS
    return {"status": "ok", "models": len(live) + len(AUDIO_MODELS), "chat_models": live}


# ─── AUDIO TRANSCRIPTION ─────────────────────────────────────────────────
@app.post("/v1/audio/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = "whisper-large-v3",
    language: str = None,
    prompt: str = None,
    response_format: str = "json",
    temperature: float = 0.0
):
    if not groq_client:
        raise HTTPException(503, "Groq client not initialized (missing API key)")
    
    # Normalize model name
    if model in GROQ_MODEL_ALIASES:
        model = GROQ_MODEL_ALIASES[model]
    if model not in ["whisper-large-v3", "whisper-large-v3-turbo"]:
        model = "whisper-large-v3"
    
    # Forward to Groq
    form_data = {"model": model, "response_format": response_format, "temperature": temperature}
    if language:
        form_data["language"] = language
    if prompt:
        form_data["prompt"] = prompt
    
    files = {"file": (file.filename, file.file, file.content_type)}
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{GROQ_API_BASE}/audio/transcriptions",
            data=form_data,
            files=files,
            headers={"Authorization": f"Bearer {groq_client.api_key}"}
        )
    
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    
    return resp.json()


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