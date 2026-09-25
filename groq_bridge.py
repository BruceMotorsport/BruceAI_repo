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
import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
import httpx


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


# ─── MODELS ──────────────────────────────────────────────────────────────
class Message(BaseModel):
    role: str
    content: str
    name: Optional[str] = None

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    top_p: Optional[float] = 1.0
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0
    stop: Optional[List[str]] = None

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
    
    async def chat_completion(self, request: ChatCompletionRequest) -> Dict[str, Any]:
        model = request.model
        if model not in GROQ_MODELS and model != "auto":
            model = DEFAULT_MODEL
        
        payload = request.model_dump(exclude_none=True)
        payload["model"] = model
        
        resp = await self.client.post("/chat/completions", json=payload)
        
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        
        return resp.json()
    
    async def chat_completion_stream(self, request: ChatCompletionRequest):
        model = request.model
        if model not in GROQ_MODELS and model != "auto":
            model = DEFAULT_MODEL
        
        payload = request.model_dump(exclude_none=True)
        payload["model"] = model
        payload["stream"] = True
        
        async with self.client.stream("POST", "/chat/completions", json=payload) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise HTTPException(status_code=resp.status_code, detail=body.decode())
            
            async for line in resp.aiter_lines():
                if line.strip():
                    yield f"data: {line}\n\n"
            yield "data: [DONE]\n\n"
    
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
        return StreamingResponse(
            groq_client.chat_completion_stream(request),
            media_type="text/event-stream",
        )
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