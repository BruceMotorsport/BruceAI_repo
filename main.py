#!/usr/bin/env python3
"""
Provider Console — Multi-Account LLM Router
===============================================
Main entry point: FastAPI server that presents a single
OpenAI-compatible endpoint to Hermes while internally
routing across multiple provider accounts.

Optimizations to reduce LLM calls:
- Model cascading (tiered inference)
- Local-first processing (no-LLM tasks)
- Streaming with early stop
- Prompt compression
- Tool result caching

Author: Buddy (Crab) 🦀
For: Hermes Agent Integration
"""

import os
import sys
import json
import time
import hashlib
import logging
import argparse
import asyncio
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict

# ---- FastAPI ----
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, APIRouter
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn
import httpx

# ---- Optional deps (graceful) ----
import subprocess
HAS_SUBPROCESS = True

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ---- Local Agents ----
from agents.debate import DebateOrchestrator, AgentRole, SpecialistAgent, ChallengerAgent, DefenderAgent, SynthesizerAgent
from agents.executor import ParallelExecutor, SubTask, TaskType, SubTaskResult

# ---- Setup Logging ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("provider-console.log")
    ]
)
log = logging.getLogger("ProviderConsole")

# ----------------------------------------------------------------
# DATA MODELS
# ----------------------------------------------------------------

@dataclass
class Account:
    """One registered LLM account."""
    id: str
    provider: str              # "groq" | "opencode" | "openrouter"
    api_key: str               # Encrypted in production
    model: str                 # Primary model for this account
    rate_limit_rpm: int = 60   # Requests per minute
    active: bool = True
    requests_count: int = 0
    last_request_time: float = 0.0
    cooldown_until: float = 0.0

@dataclass
class ChatCompletion:
    """OpenAI-compatible chat completion request (for /api/test)."""
    model: str
    messages: List[Dict[str, str]]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    tools: Optional[List[Dict]] = None
    tool_choice: Optional[str] = None
    top_p: Optional[float] = 1.0
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0
    stop: Optional[List[str]] = None

@dataclass
class TaskType:
    """Classified task from user prompt."""
    type: str                  # "coding" | "reasoning" | "fast" | "vision" | "general"
    confidence: float = 1.0

@dataclass
class ChatRequest:
    model: str
    messages: List[Dict[str, str]]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    tools: Optional[List[Dict]] = None
    tool_choice: Optional[str] = None
    top_p: Optional[float] = 1.0
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0
    stop: Optional[List[str]] = None

@dataclass
class ProviderInfo:
    """Info about a registered provider."""
    name: str
    endpoint: str
    models: List[str]
    account_count: int
    rate_limit: int

@dataclass
class UsageStats:
    """Runtime usage statistics."""
    total_requests: int = 0
    requests_by_provider: Dict[str, int] = field(default_factory=dict)
    requests_by_model: Dict[str, int] = field(default_factory=dict)
    errors: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    start_time: float = field(default_factory=time.time)

# ----------------------------------------------------------------
# PROVIDER BASE
# ----------------------------------------------------------------

class BaseProvider:
    """Abstract provider interface."""
    
    def __init__(self, name: str, models: List[str], endpoint: str):
        self.name = name
        self.models = models
        self.endpoint = endpoint
    
    def get_context_window(self, model: str) -> int:
        """Return context window size in tokens."""
        contexts = {
            "gpt-oss-120b": 128000,
            "gpt-oss-20b": 128000,
            "qwen/qwen3.8-27b": 128000,
            "allam-2-7b": 32000,
            "mimo-v2.6-flash-free": 128000,
            "nemotron-3-ultra-free": 128000,
            "nemotron-3.5-lightning-free": 128000,
            "ling-3.0-flash-fin-free": 128000,
            "muse-spark-1.3-contributor-free": 128000,
            "jev-1.13-free": 128000,
            "whisper-large-v3": 100000000,  # Audio — effectively unlimited
            "whisper-large-v3-turbo": 100000000,
        }
        return contexts.get(model, 8000)  # Default 8K safety
    
    def supports_tool_calling(self, model: str) -> bool:
        tc = ["gpt-oss-120b", "gpt-oss-20b", "qwen/qwen3.8-27b",
              "mimo-v2.6-flash-free", "nemotron-3-ultra-free",
              "nemotron-3.5-lightning-free", "ling-3.0-flash-fin-free",
              "jev-1.13-free"]
        return model in tc or "gpt-oss" in model or "qwen" in model
    
    def is_small_context(self, model: str) -> bool:
        return self.get_context_window(model) < 32000

class GroqProvider(BaseProvider):
    """Groq provider — multiple API keys."""
    
    def __init__(self, endpoint: str = "http://127.0.0.1:8080/v1"):
        super().__init__("groq", [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
            "allam-2-7b",
            "canopylabs/orpheus-v1-english",
            "whisper-large-v3",
            "whisper-large-v3-turbo",
        ], endpoint)
        self.accounts: List[Account] = []
        self._client = httpx.AsyncClient(timeout=60.0)
    
    def add_account(self, api_key: str, model: str = "openai/gpt-oss-120b") -> Account:
        acc_id = f"groq_{hashlib.sha256(api_key.encode()).hexdigest()[:8]}"
        acc = Account(id=acc_id, provider="groq", api_key=api_key, model=model)
        self.accounts.append(acc)
        log.info(f"Groq account added: {acc_id} model={model}")
        return acc
    
    async def chat_completion(self, request: ChatRequest, account: Account) -> Dict:
        headers = {
            "Content-Type": "application/json",
        }
        # ChatRequest is a dataclass, not Pydantic - convert to dict
        payload = {
            "model": request.model,
            "messages": request.messages,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.stream is not None:
            payload["stream"] = request.stream
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.frequency_penalty is not None:
            payload["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty is not None:
            payload["presence_penalty"] = request.presence_penalty
        if request.stop is not None:
            payload["stop"] = request.stop
        if request.tools is not None:
            payload["tools"] = request.tools
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice
            
        resp = await self._client.post(
            f"{self.endpoint}/chat/completions",
            headers=headers, json=payload
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()
    
    async def health_check(self, account: Account) -> bool:
        try:
            resp = await self._client.get(
                f"{self.endpoint}/models", timeout=5
            )
            return resp.status_code == 200
        except:
            return False

class OpenCodeProvider(BaseProvider):
    """OpenCode provider — subprocess bridge."""
    
    def __init__(self):
        super().__init__("opencode", [
            "opencode/mimo-v2.6-flash-free",
            "opencode/nemotron-3-ultra-free",
            "opencode/nemotron-3.5-lightning-free",
            "opencode/ling-3.0-flash-fin-free",
            "opencode/muse-spark-1.3-contributor-free",
            "opencode/jev-1.13-free",
        ], "subprocess://opencode")
        self.accounts: List[Account] = []
    
    async def chat_completion(self, request: ChatRequest, account: Account) -> Dict:
        import subprocess
        model = request.model
        user_msg = request.messages[-1]["content"]
        
        cmd = ["C:\\Users\\Bruce\\nodejs\\opencode.cmd", "run", "-m", model, user_msg]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                             cwd=os.environ.get('USERPROFILE', os.getcwd()))
        response_text = proc.stdout.strip() if proc.returncode == 0 else proc.stderr[:200]
        
        return {"choices": [{"message": {"role": "assistant", "content": response_text}}]}
    
    async def health_check(self, account: Account) -> bool:
            try:
                proc = subprocess.run(
                    ["C:\\Users\\Bruce\\nodejs\\opencode.cmd", "--version"],
                    capture_output=True, text=True, timeout=10,
                    cwd=os.environ.get('USERPROFILE', os.getcwd())
                )
                print(f"DEBUG OpenCode health_check: returncode={proc.returncode}, stdout={proc.stdout[:50]}, stderr={proc.stderr[:50]}")
                return proc.returncode == 0
            except Exception as e:
                print(f"DEBUG OpenCode health_check ERROR: {e}")
                return False

class OpenRouterProvider(BaseProvider):
    """OpenRouter provider — multiple API keys."""
    
    def __init__(self, endpoint: str = "https://openrouter.ai/api/v1"):
        super().__init__("openrouter", ["openrouter/free"], endpoint)
        self.accounts: List[Account] = []
        self._client = httpx.AsyncClient(timeout=60.0)
    
    def add_account(self, api_key: str) -> Account:
        acc_id = f"or_{hashlib.sha256(api_key.encode()).hexdigest()[:8]}"
        acc = Account(id=acc_id, provider="openrouter", api_key=api_key, model="openrouter/free")
        self.accounts.append(acc)
        return acc
    
    async def chat_completion(self, request: ChatRequest, account: Account) -> Dict:
        headers = {
            "Authorization": f"Bearer {account.api_key}",
            "HTTP-Referer": "https://hermes.agent",
            "X-Title": "Hermes Agent",
            "Content-Type": "application/json",
        }
        # ChatRequest is a dataclass, not Pydantic - convert to dict
        payload = {
            "model": request.model,
            "messages": request.messages,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.stream is not None:
            payload["stream"] = request.stream
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.frequency_penalty is not None:
            payload["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty is not None:
            payload["presence_penalty"] = request.presence_penalty
        if request.stop is not None:
            payload["stop"] = request.stop
        if request.tools is not None:
            payload["tools"] = request.tools
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice
            
        resp = await self._client.post(
            f"{self.endpoint}/chat/completions",
            headers=headers, json=payload
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()
    
    async def health_check(self, account: Account) -> bool:
        try:
            headers = {"Authorization": f"Bearer {account.api_key}"}
            resp = await self._client.get(
                f"{self.endpoint}/models", headers=headers, timeout=5
            )
            return resp.status_code == 200
        except:
            return False

# ----------------------------------------------------------------
# CONTEXT WINDOW EXPANSION
# ----------------------------------------------------------------

class ContextExpander:
    """
    Expands effective context for models with small windows.
    Uses summarization buffer + sliding window strategy.
    """
    
    def __init__(self, max_summary_tokens: int = 2048, sliding_window_ratio: float = 0.5):
        self.max_summary_tokens = max_summary_tokens
        self.sliding_window_ratio = sliding_window_ratio
    
    def needs_expansion(self, model: str, messages: List[Dict]) -> bool:
        """Check if context expansion is needed."""
        provider = getattr(self, '_provider', None)
        if not provider:
            return False
        window = provider.get_context_window(model)
        estimated_tokens = self._estimate_tokens(messages)
        return estimated_tokens > (window * 0.7)  # 70% threshold
    
    def expand_messages(self, model: str, messages: List[Dict]) -> List[Dict]:
        """
        If messages exceed 70% of context:
        1. Keep all recent messages in sliding window (50%)
        2. Summarize older messages into single system message
        3. Return expanded message list
        """
        provider = getattr(self, '_provider', None)
        if not provider:
            return messages
        
        window = provider.get_context_window(model)
        estimated = self._estimate_tokens(messages)
        
        if estimated <= (window * 0.7):
            return messages  # No expansion needed
        
        # Split: recent (sliding window) + older (summarize)
        window_size = int(len(messages) * self.sliding_window_ratio)
        recent = messages[-window_size:]
        older = messages[:-window_size]
        
        # Summarize older messages
        summary = self._summarize(older)
        
        # Build expanded list: summary as system message + recent messages
        expanded = [{"role": "system", "content": summary}] + recent
        return expanded
    
    def _estimate_tokens(self, messages: List[Dict]) -> int:
        """Rough token estimate."""
        total = 0
        for msg in messages:
            text = msg.get("content", "") or ""
            total += len(text.split()) * 1.33  # ~1.33 tokens per word
        return int(total)
    
    def _summarize(self, messages: List[Dict]) -> str:
        """Summarize a list of messages into key facts."""
        if not messages:
            return ""
        
        # Extract key information from each message
        key_points = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            # Keep tool results that are short enough
            if role == "tool" and len(content) < 500:
                key_points.append(f"[{msg.get('tool_name', 'tool')}]: {content[:200]}")
            elif role == "user" and len(content) < 1000:
                key_points.append(f"User asked: {content[:200]}")
            elif role == "assistant" and len(content) < 1000:
                key_points.append(f"Assistant: {content[:200]}")
        
        if not key_points:
            return "[Earlier conversation summarized]"
        
        summary = "[Earlier conversation summary]\n" + "\n".join(key_points)
        return summary[:4000]  # Cap summary size

# ----------------------------------------------------------------
# RATE LIMITER (Per Account)
# ----------------------------------------------------------------

class RateLimiter:
    """Tracks rate limits per account."""
    
    def __init__(self):
        self.accounts_usage: Dict[str, List[float]] = {}  # timestamps
    
    def check(self, account_id: str, limit_rpm: int) -> bool:
        now = time.time()
        if account_id not in self.accounts_usage:
            self.accounts_usage[account_id] = []
        
        # Prune timestamps older than 1 minute
        self.accounts_usage[account_id] = [
            t for t in self.accounts_usage[account_id]
            if now - t < 60
        ]
        
        if len(self.accounts_usage[account_id]) >= limit_rpm:
            return False
        
        self.accounts_usage[account_id].append(now)
        return True
    
    def wait_time(self, account_id: str, limit_rpm: int) -> float:
        """Returns seconds to wait."""
        now = time.time()
        if account_id not in self.accounts_usage:
            return 0
        self.accounts_usage[account_id] = [
            t for t in self.accounts_usage[account_id]
            if now - t < 60
        ]
        if len(self.accounts_usage[account_id]) >= limit_rpm:
            oldest = self.accounts_usage[account_id][0]
            return max(0, 60 - (now - oldest))
        return 0
    
    def reset(self, account_id: str):
        if account_id in self.accounts_usage:
            del self.accounts_usage[account_id]

# ----------------------------------------------------------------
# TASK ROUTER (Prompt Classification)
# ----------------------------------------------------------------

TASK_KEYWORDS = {
    "coding": ["code", "function", "class", "python", "script", "program", "debug", "error", "implement", "refactor", "test"],
    "reasoning": ["analyze", "explain", "why", "how does", "diagnosis", "diagnose", "understand", "reasoning", "logic", "think through"],
    "vision": ["image", "picture", "photo", "visual", "describe", "what's in"],
    "fast": ["quick", "short", "brief", "simple", "fast", "one line", "summary"],
    "audio": ["audio", "speech", "transcribe", "voice", "sound", "record"],
}

class TaskClassifier:
    """Classify user prompts into task types."""
    
    def classify(self, messages: List[Dict]) -> TaskType:
        if not messages:
            return TaskType("general")
        
        prompt = messages[-1].get("content", "").lower()
        
        scores = {}
        for task, keywords in TASK_KEYWORDS.items():
            scores[task] = sum(1 for kw in keywords if kw in prompt)
        
        if not any(scores.values()):
            return TaskType("general")
        
        best = max(scores, key=scores.get)
        confidence = scores[best] / max(len(TASK_KEYWORDS[best]), 1)
        return TaskType(best, confidence)

# ----------------------------------------------------------------
# RESPONSE CACHE
# ----------------------------------------------------------------

class ResponseCache:
    """Simple in-memory + optional SQLite cache."""
    
    def __init__(self, max_size: int = 1000):
        self.cache: Dict[str, Dict] = {}
        self.max_size = max_size
    
    def _key(self, provider: str, model: str, messages: List[Dict], temperature: float) -> str:
        raw = f"{provider}:{model}:{temperature}:" + json.dumps(messages, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()
    
    def get(self, provider: str, model: str, messages: List[Dict], temperature: float) -> Optional[Dict]:
        key = self._key(provider, model, messages, temperature)
        return self.cache.get(key)
    
    def set(self, provider: str, model: str, messages: List[Dict], temperature: float, response: Dict):
        if len(self.cache) >= self.max_size:
            oldest = list(self.cache.keys())[:self.max_size // 5]
            for k in oldest:
                del self.cache[k]
        key = self._key(provider, model, messages, temperature)
        self.cache[key] = response

# ----------------------------------------------------------------
# MAIN APP
# ----------------------------------------------------------------

app_state = {"providers": {}, "accounts": [], "stats": UsageStats(), "task_classifier": TaskClassifier(),
             "rate_limiter": RateLimiter(), "response_cache": ResponseCache(2000),
             "context_expander": ContextExpander(), "usage_history": [],
             "debate_cache": {},
             "parallel_executor": None}

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 60)
    log.info("Provider Console Starting")
    log.info("=" * 60)
    
    # Initialize providers
    groq = GroqProvider()
    opencode = OpenCodeProvider()
    or_provider = OpenRouterProvider()
    
    app_state["providers"] = {
        "groq": groq,
        "opencode": opencode,
        "openrouter": or_provider,
    }
    
    # Load accounts from env or config
    _load_accounts()
    
    # Initialize parallel executor
    app_state["parallel_executor"] = ParallelExecutor(
        providers=app_state["providers"],
        accounts=app_state["accounts"]
    )
    
    log.info(f"Providers loaded: {list(app_state['providers'].keys())}")
    log.info(f"Accounts loaded: {len(app_state['accounts'])}")
    log.info(f"Endpoint: http://localhost:{PORT}/v1")
    log.info("=" * 60)
    yield
    
    log.info("Provider Console Shutdown")

PORT = int(os.environ.get("PROVIDER_PORT", 9001))

app = FastAPI(title="Provider Console", version="1.0", lifespan=lifespan)

def _load_accounts():
    """Load accounts from environment variables."""
    # Groq — multiple keys supported via comma-separated env var
    groq_keys = os.environ.get("GROQ_API_KEYS", os.environ.get("GROQ_API_KEY", ""))
    if groq_keys:
        for key in groq_keys.split(","):
            key = key.strip()
            if key and key != "dummy" and not key.startswith("***"):
                provider = app_state["providers"].get("groq")
                if provider:
                    provider.add_account(key)
                    app_state["accounts"].append(provider.accounts[-1])
    
    # OpenCode — single session (always available locally)
    provider = app_state["providers"].get("opencode")
    if provider:
        acc = Account(
            id="opencode_default",
            provider="opencode",
            api_key="local_session",
            model="opencode/mimo-v2.6-flash-free"
        )
        provider.accounts.append(acc)
        app_state["accounts"].append(acc)
    
    # OpenRouter — keys from env
    or_keys = os.environ.get("OPENROUTER_API_KEYS", os.environ.get("OPENROUTER_API_KEY", ""))
    if or_keys:
        provider = app_state["providers"].get("openrouter")
        if provider:
            for key in or_keys.split(","):
                key = key.strip()
                if key and key != "dummy" and not key.startswith("***"):
                    provider.add_account(key)
                    app_state["accounts"].append(provider.accounts[-1])

# --- HEALTH ---
@app.get("/health")
async def health():
    accounts_healthy = []
    for acc in app_state["accounts"]:
        provider = app_state["providers"].get(acc.provider)
        if provider:
            ok = await provider.health_check(acc)
            accounts_healthy.append({"account": acc.id, "provider": acc.provider, "healthy": ok})
    
    return {
        "status": "ok",
        "port": PORT,
        "providers": list(app_state["providers"].keys()),
        "accounts": len(app_state["accounts"]),
        "accounts_healthy": accounts_healthy,
        "uptime_seconds": int(time.time() - app_state["stats"].start_time)
    }

# --- PROVIDER LISTS ---
@app.get("/v1/models")
async def list_models():
    """Return all models from all providers."""
    models = []
    seen = set()
    for name, provider in app_state["providers"].items():
        for model in provider.models:
            if model not in seen:
                seen.add(model)
                models.append({
                    "id": model,
                    "object": "model",
                    "created": 1677610602,
                    "owned_by": name,
                    "context_window": provider.get_context_window(model),
                    "supports_tool_calling": provider.supports_tool_calling(model),
                })
    return {"object": "list", "data": models}

# --- MAIN COMPLETION ---
@app.post("/v1/chat/completions")
async def chat_completion(request: ChatRequest):
    """
    Main endpoint. Hermes sends ONE request here.
    We route to the best provider/account internally.
    """
    stats = app_state["stats"]
    stats.total_requests += 1
    
    # 1. Check cache
    cached = app_state["response_cache"].get(
        "route", request.model, request.messages, request.temperature or 0.7
    )
    if cached:
        stats.cache_hits += 1
        return JSONResponse(content=cached)
    stats.cache_misses += 1
    
    # 2. Expand context if needed
    messages = request.messages
    provider_for_model = None
    for p in app_state["providers"].values():
        if p.get_context_window(request.model) > 0:
            provider_for_model = p
            break
    
    if provider_for_model and provider_for_model.is_small_context(request.model):
        app_state["context_expander"]._provider = provider_for_model
        messages = app_state["context_expander"].expand_messages(request.model, messages)
    
    # 3. Classify task
    task = app_state["task_classifier"].classify(messages)
    
    # Check if debate/parallel mode is triggered
    if _should_use_debate(request.model, messages, task):
        return await _execute_debate_mode(request, messages, task)
    
    if _should_use_parallel(request.model, messages, task):
        return await _execute_parallel_mode(request, messages, task)
    
    # 4. Find best provider/account
    best = _select_account(request.model, task)
    if not best:
        stats.errors += 1
        raise HTTPException(status_code=503, detail="No healthy providers/accounts available")
    
    provider = app_state["providers"][best.provider]
    
    # 5. Rate limit check
    if not app_state["rate_limiter"].check(best.id, best.rate_limit_rpm):
        stats.errors += 1
        return JSONResponse(
            status_code=429,
            content={"error": {"message": f"Rate limited for account {best.id}. Try again."}}
        )
    
    # 6. Execute with stall detection and failover
    try:
        response = await _execute_with_failover(request, messages, best, task)
        stats.requests_by_provider[best.provider] = stats.requests_by_provider.get(best.provider, 0) + 1
        stats.requests_by_model[request.model] = stats.requests_by_model.get(request.model, 0) + 1
        return JSONResponse(content=response)
    except Exception as e:
        stats.errors += 1
        log.error(f"All accounts failed for model={request.model}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def _execute_with_failover(request: ChatRequest, messages: List[Dict], first_account: Account, task: TaskType) -> Dict:
    """Execute with stall detection (25s timeout) and automatic failover to next healthy account."""
    attempted = set()
    current_account = first_account
    max_attempts = 2
    
    for attempt in range(max_attempts):
        if current_account.id in attempted:
            break
        attempted.add(current_account.id)
        
        provider = app_state["providers"][current_account.provider]
        
        # Rate limit check
        if not app_state["rate_limiter"].check(current_account.id, current_account.rate_limit_rpm):
            log.warning(f"Rate limited: {current_account.id}")
            current_account.cooldown_until = time.time() + 30
        else:
            try:
                # Stall detection: 25s hard timeout
                if current_account.provider == "opencode":
                    response = await asyncio.wait_for(
                        provider.chat_completion(request, current_account),
                        timeout=30.0
                    )
                else:
                    response = await asyncio.wait_for(
                        provider.chat_completion(request, current_account),
                        timeout=25.0
                    )
                
                current_account.requests_count += 1
                current_account.last_request_time = time.time()
                
                # Cache it
                app_state["response_cache"].set(
                    current_account.provider, request.model, messages, request.temperature or 0.7, response
                )
                
                log.info(f"Success on attempt {attempt + 1}: {current_account.id}")
                return response
                
            except asyncio.TimeoutError:
                log.warning(f"Stall detected: {current_account.id} (attempt {attempt + 1}/{max_attempts})")
                current_account.cooldown_until = time.time() + 60
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    log.warning(f"Rate limited 429: {current_account.id}")
                    current_account.cooldown_until = time.time() + 30
                elif e.response.status_code == 401:
                    log.error(f"Auth failed: {current_account.id}")
                    current_account.active = False
                else:
                    log.warning(f"HTTP {e.response.status_code}: {current_account.id}")
            except Exception as e:
                log.warning(f"Error on {current_account.id}: {e}")
        
        # Pick next best account for retry
        if attempt < max_attempts - 1:
            current_account = _select_account(request.model, task)
            if current_account and current_account.id not in attempted:
                log.info(f"Failover to: {current_account.id}")
                continue
    
    raise HTTPException(status_code=503, detail="All providers failed or stalled")

def _select_account(model: str, task: TaskType) -> Optional[Account]:
    """Select best available account based on model + task type."""
    
    # If model is specific (e.g., starts with "openai/" or "opencode/"), find provider for it
    for account in sorted(app_state["accounts"], key=lambda a: a.requests_count):
        if not account.active:
            continue
        if account.model == model or model == "auto" or model == "ProviderConsole/auto":
            if app_state["rate_limiter"].check(account.id, account.rate_limit_rpm):
                return account
    
    # Fallback: any provider that supports tool calling for the task type
    task_map = {
        "coding": ["opencode", "groq"],
        "reasoning": ["groq", "openrouter"],
        "fast": ["groq"],
        "general": ["groq", "opencode", "openrouter"],
    }
    
    preferred_providers = task_map.get(task.type, ["groq", "opencode", "openrouter"])
    
    for provider_name in preferred_providers:
        for account in sorted(
            [a for a in app_state["accounts"] if a.provider == provider_name],
            key=lambda a: a.requests_count
        ):
            if account.active and app_state["rate_limiter"].check(account.id, account.rate_limit_rpm):
                return account
    
    return None

# --- STREAMING (for models that support it) ---
@app.post("/v1/chat/completions/{model:path}")
async def chat_completion_stream(model: str, request: Request):
    """Streaming endpoint — delegates to regular endpoint."""
    body = await request.json()
    body["model"] = model
    body["stream"] = False  # Hermes handles it
    req = ChatRequest(**body)
    return await chat_completion(req)

# --- WEB UI ---
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Provider Console — Dashboard</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'SF Mono', 'Consolas', 'Monaco', monospace; background: #0a0a0f; color: #e0e0e0; padding: 20px; }
h1 { color: #e74c3c; font-size: 1.5rem; margin-bottom: 20px; }
h2 { color: #3498db; font-size: 1.1rem; margin: 20px 0 10px 0; border-bottom: 1px solid #1a1a2e; padding-bottom: 5px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px; margin-bottom: 20px; }
.card { background: #12121f; border: 1px solid #1a1a2e; border-radius: 8px; padding: 15px; }
.card h3 { color: #f39c12; margin-bottom: 10px; font-size: 0.95rem; }
.card .value { font-size: 1.4rem; font-weight: bold; color: #2ecc71; }
.card .label { color: #888; font-size: 0.8rem; }
.status { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
.status.ok { background: #2ecc71; color: #000; }
.status.warn { background: #f39c12; color: #000; }
.status.err { background: #e74c3c; color: #fff; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #1a1a2e; }
th { color: #3498db; font-size: 0.85rem; }
td { font-size: 0.85rem; }
.health-bar { height: 4px; background: #1a1a2e; border-radius: 2px; margin-top: 5px; overflow: hidden; }
.health-bar-fill { height: 100%; border-radius: 2px; transition: width 0.3s; }
.health-bar-fill.green { background: #2ecc71; }
.health-bar-fill.yellow { background: #f39c12; }
.health-bar-fill.red { background: #e74c3c; }
.model-tag { display: inline-block; background: #1a1a2e; padding: 2px 6px; border-radius: 3px; margin: 2px; font-size: 0.75rem; }
</style>
</head>
<body>
<h1>Cra  Provider Console Dashboard</h1>

<div id="stats"></div>
<div id="providers"></div>
<div id="accounts"></div>
<div id="models"></div>
<div id="tester"></div>

<script>
async function refresh() {
    const [healthRes, modelsRes] = await Promise.all([
        fetch('/health').then(r => r.json()),
        fetch('/v1/models').then(r => r.json())
    ]);
    
    document.getElementById('stats').innerHTML = `
        <h2>Statistics</h2>
        <div class="grid">
            <div class="card"><h3>Total Requests</h3><div class="value">${healthRes.total_requests || '—'}</div><span class="label">All time</span></div>
            <div class="card"><h3>Accounts</h3><div class="value">${healthRes.accounts}</div><span class="label">${healthRes.accounts_healthy.filter(a=>a.healthy).length} healthy</span></div>
            <div class="card"><h3>Providers</h3><div class="value">${healthRes.providers.join(', ')}</div><span class="label">Active</span></div>
            <div class="card"><h3>Uptime</h3><div class="value">${Math.floor(healthRes.uptime_seconds / 60)}m ${healthRes.uptime_seconds % 60}s</div><span class="label">Since start</span></div>
        </div>
    `;
    
    document.getElementById('accounts').innerHTML = `
        <h2>Accounts</h2>
        <table>
            <tr><th>ID</th><th>Provider</th><th>Model</th><th>Requests</th><th>Status</th></tr>
            ${healthRes.accounts_healthy.map(a => `
                <tr>
                    <td>${a.account}</td>
                    <td>${a.provider}</td>
                    <td>${a.provider}</td>
                    <td>—</td>
                    <td><span class="status ${a.healthy ? 'ok' : 'err'}">${a.healthy ? 'OK' : 'DOWN'}</span></td>
                </tr>
            `).join('')}
        </table>
    `;
    
    document.getElementById('models').innerHTML = `
        <h2>Models (${modelsRes.data.length})</h2>
        <div class="grid">
            ${modelsRes.data.slice(0, 12).map(m => `
                <div class="card">
                    <h3><span class="model-tag">${m.id}</span></h3>
                    <span class="label">Context: ${m.context_window.toLocaleString()} tokens</span><br>
                    <span class="label">Tool Calling: ${m.supports_tool_calling ? '✓' : '✗'}</span>
                </div>
            `).join('')}
        </div>
    `;
}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>"""

DEBATE_TRIGGERS = [
    "should i", "what's the real", "which is better", "trade.?off", "diagnose", 
    "root cause", "ambiguous", "multiple options", "weigh", "decide between",
    "best approach", "recommend", "pros and cons"
]

PARALLEL_TRIGGERS = [
    "review all", "analyze all", "refactor all", "test all", "multi.file",
    "full project", "comprehensive", "each file", "all files", "batch",
    "diagnose all", "check all"
]

def _should_use_debate(model: str, messages: List[Dict], task: TaskType) -> bool:
    """Determine if multi-agent debate should be used."""
    if not messages:
        return False
    prompt = messages[-1].get("content", "").lower()
    
    # Explicit trigger
    if any(t in prompt for t in DEBATE_TRIGGERS):
        return True
    
    # Task type triggers
    if task.type in ("reasoning", "diagnose"):
        return True
    
    return False


def _should_use_parallel(model: str, messages: List[Dict], task: TaskType) -> bool:
    """Determine if parallel subtask execution should be used."""
    if not messages:
        return False
    prompt = messages[-1].get("content", "").lower()
    
    return any(t in prompt for t in PARALLEL_TRIGGERS)


async def _execute_debate_mode(request: ChatRequest, messages: List[Dict], task: TaskType) -> JSONResponse:
    """Execute a multi-agent debate and return synthesized result."""
    prompt = messages[-1].get("content", "")
    topic_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    
    # Check debate cache
    if topic_hash in app_state["debate_cache"]:
        cached = app_state["debate_cache"][topic_hash]
        app_state["stats"].cache_hits += 1
        return JSONResponse(content=cached)
    app_state["stats"].cache_misses += 1
    
    # Build debate participants
    specialists = [
        SpecialistAgent("specialist_a", "groq", "openai/gpt-oss-120b", AgentRole.PROPOSE),
        SpecialistAgent("specialist_b", "opencode", "opencode/mimo-v2.6-flash-free", AgentRole.PROPOSE),
        SpecialistAgent("specialist_c", "groq", "openai/gpt-oss-20b", AgentRole.PROPOSE),
    ]
    
    referers = [
        ChallengerAgent("challenger", "groq", "openai/gpt-oss-120b", AgentRole.CHALLENGE),
    ]
    
    defenders = [
        DefenderAgent("defender", "opencode", "opencode/nemotron-3.5-lightning-free", AgentRole.REBUTT),
    ]
    
    # Run debate phases
    log.info(f"Starting debate on topic: {topic_hash}")
    
    # Phase 1: Propose (parallel)
    proposals = await asyncio.gather(*[
        s.respond(prompt, {"topic": topic_hash}) for s in specialists
    ])
    
    # Phase 2: Challenge (parallel)
    challenges = await asyncio.gather(*[
        c.respond(prompt, {"proposals": proposals}) for c in referers
    ])
    
    # Phase 3: Rebut (parallel)
    rebuttals = await asyncio.gather(*[
        d.respond(prompt, {"challenges": challenges}) for d in defenders
    ])
    
    # Phase 4: Vote (simple scoring)
    scores = {}
    for i, p in enumerate(proposals):
        scores[f"specialist_{i}"] = 1  # base
    for c in challenges:
        # penalize challenged
        for key in scores:
            scores[key] -= 0.5
    for r in rebuttals:
        for key in scores:
            scores[key] += 0.3
    
    winner = max(scores, key=scores.get) if scores else "specialist_0"
    
    # Phase 5: Synthesize
    synthesizer = SynthesizerAgent(
        "synthesizer", "groq", "openai/gpt-oss-120b", AgentRole.SYNTHESIZE
    )
    final = await synthesizer.respond(prompt, {
        "proposals": proposals,
        "challenges": challenges,
        "rebuttals": rebuttals,
        "winner": winner
    })
    
    # Build OpenAI-compatible response
    response = {
        "id": f"debate-{topic_hash}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "BruceAI/debate:gpt-oss-120b",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": final},
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "debate_meta": {
            "participants": len(specialists) + len(referers) + len(defenders),
            "rounds": 3,
            "winner": winner
        }
    }
    
    # Cache the full debate round
    app_state["debate_cache"][topic_hash] = response
    
    # Update stats
    stats = app_state["stats"]
    stats.total_requests += 1
    stats.requests_by_provider["debate"] = stats.requests_by_provider.get("debate", 0) + 1
    
    return JSONResponse(content=response)


async def _execute_parallel_mode(request: ChatRequest, messages: List[Dict], task: TaskType) -> JSONResponse:
    """Execute parallel subtasks across multiple models."""
    prompt = messages[-1].get("content", "")
    topic_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    
    executor = app_state["parallel_executor"]
    if not executor:
        # Fallback to single model
        return await _execute_single_model(request, messages, task)
    
    # Decompose into subtasks (simplified - in production use a decomposer)
    subtasks = [
        SubTask(
            id=f"{topic_hash}_1",
            topic="parallel",
            task_type=TaskType.DIAGNOSE,
            prompt=f"Analyze: {prompt} (part 1)",
        ),
        SubTask(
            id=f"{topic_hash}_2",
            topic="parallel",
            task_type=TaskType.REVIEW,
            prompt=f"Review: {prompt} (part 2)",
        ),
        SubTask(
            id=f"{topic_hash}_3",
            topic="parallel",
            task_type=TaskType.TEST,
            prompt=f"Test scenarios: {prompt} (part 3)",
        ),
    ]
    
    # Execute in parallel
    results = await executor.execute(subtasks)
    
    # Merge results
    merged = "\n\n---\n\n".join([f"**{r.agent_name}** ({r.model}): {r.response}" for r in results])
    
    response = {
        "id": f"parallel-{topic_hash}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "BruceAI/parallel:gpt-oss-120b",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": merged},
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "parallel_meta": {
            "subtasks": len(subtasks),
            "cached": sum(1 for r in results if r.cached),
            "latency_ms": max(r.latency_ms for r in results) if results else 0
        }
    }
    
    # Update stats
    stats = app_state["stats"]
    stats.total_requests += 1
    stats.requests_by_provider["parallel"] = stats.requests_by_provider.get("parallel", 0) + 1
    
    return JSONResponse(content=response)


async def _execute_single_model(request: ChatRequest, messages: List[Dict], task: TaskType) -> JSONResponse:
    """Fallback: single model execution with failover."""
    best = _select_account(request.model, task)
    if not best:
        raise HTTPException(status_code=503, detail="No healthy providers/accounts available")
    
    try:
        response = await _execute_with_failover(request, messages, best, task)
        stats = app_state["stats"]
        stats.requests_by_provider[best.provider] = stats.requests_by_provider.get(best.provider, 0) + 1
        stats.requests_by_model[request.model] = stats.requests_by_model.get(request.model, 0) + 1
        return JSONResponse(content=response)
    except Exception as e:
        stats = app_state["stats"]
        stats.errors += 1
        log.error(f"All accounts failed for model={request.model}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- API KEYS ENDPOINT (Manage accounts) ---
@app.post("/api/accounts/groq")
async def add_groq_account(key: str, model: str = "openai/gpt-oss-120b"):
    provider = app_state["providers"].get("groq")
    if not provider:
        raise HTTPException(503, "Groq provider not initialized")
    acc = provider.add_account(key, model)
    app_state["accounts"].append(acc)
    return {"success": True, "account_id": acc.id, "model": model}

@app.post("/api/accounts/openrouter")
async def add_or_account(key: str):
    provider = app_state["providers"].get("openrouter")
    if not provider:
        raise HTTPException(503, "OpenRouter provider not initialized")
    acc = provider.add_account(key)
    app_state["accounts"].append(acc)
    return {"success": True, "account_id": acc.id}

@app.get("/api/accounts")
async def list_accounts():
    return {"accounts": [asdict(a) for a in app_state["accounts"]]}

@app.delete("/api/accounts/{account_id}")
async def remove_account(account_id: str):
    app_state["accounts"] = [a for a in app_state["accounts"] if a.id != account_id]
    for p in app_state["providers"].values():
        p.accounts = [a for a in p.accounts if a.id != account_id]
    return {"success": True}

# --- MODEL TESTER ---
@app.post("/api/test")
async def test_model(provider: str, model: str, prompt: str):
    """Test a specific provider/model with a prompt."""
    test_req = ChatCompletion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=200,
        stream=False
    )
    try:
        p = app_state["providers"][provider]
        acc = p.accounts[0] if p.accounts else None
        if not acc:
            return {"error": "No accounts for this provider"}
        result = await p.chat_completion(test_req, acc)
        return {"success": True, "response": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- MAIN ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Provider Console")
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--config", default="config/settings.yaml")
    args = parser.parse_args()
    
    PORT = args.port
    log.info(f"Starting on http://{args.host}:{PORT}")
    uvicorn.run(app, host=args.host, port=PORT, log_level="info")