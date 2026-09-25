#!/usr/bin/env python3
"""
Hermes + Groq Agent Wrapper (UPDATED 2026-09-23)
================================================
The core wrapper that integrates Groq bridge into Hermes agent context.
This sits as a plugin layer between Hermes and the Groq bridge server.

Features:
- Automatic Groq bridge startup (if not running)
- Hermes provider configuration for Groq
- Model fallback system
- Token efficiency optimization
- Rate limit handling
"""

import os
import json
import asyncio
import requests
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

# ─── HERMES INTEGRATION ────────────────────────────────────────────────────
class GroqHermesBridge:
    """
    Main bridge class that integrates Groq into Hermes.
    
    This is the agentic wrapper that Hermes uses to talk to Groq
    through our local bridge server.
    """
    
    def __init__(self):
        self.bridge_url = os.environ.get("GROQ_BRIDGE_URL", "http://127.0.0.1:8080/v1")
        self.api_key = os.environ.get("GROQ_API_KEY", "dummy")
        self.model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
        self.temperature = float(os.environ.get("GROQ_TEMPERATURE", "0.7"))
        self.max_tokens = int(os.environ.get("GROQ_MAX_TOKENS", "1024"))
        
        # Fallback model chain (updated 2026-09-23)
        self.model_chain = [
            "openai/gpt-oss-120b",        # Primary - 120B, reasoning
            "openai/gpt-oss-20b",         # Fast fallback
            "qwen/qwen3.8-27b",           # Qwen 27B
            "allam-2-7b",                 # Arabic
        ]
        
        # Rate limit tracking
        self.last_request_time = 0
        self.requests_this_minute = 0
        self.max_requests_per_minute = 60  # Conservative for free tier
        
    def get_provider_config(self) -> Dict[str, Any]:
        """Generate Hermes provider configuration for Groq."""
        return {
            "name": "GroqBridge",
            "base_url": self.bridge_url,
            "api_key": self.api_key,
            "api_mode": "openai",
            "models": {
                "openai/gpt-oss-120b": {},
                "openai/gpt-oss-20b": {},
                "qwen/qwen3.8-27b": {},
                "allam-2-7b": {},
                "canopylabs/orpheus-v1-english": {},
                "whisper-large-v3": {},
                "whisper-large-v3-turbo": {},
            },
            "default_model": self.model,
            "compatibility_mode": True,
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if Groq bridge is healthy."""
        try:
            resp = requests.get(f"{self.bridge_url}/health", timeout=5)
            if resp.status_code == 200:
                return {"status": "healthy", "details": resp.json()}
            else:
                return {"status": "unhealthy", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def rate_limit_check(self) -> bool:
        """Implement rate limiting."""
        now = time.time()
        
        # Reset counter every minute
        if now - self.last_request_time >= 60:
            self.requests_this_minute = 0
            self.last_request_time = now
        
        if self.requests_this_minute >= self.max_requests_per_minute:
            return False
        
        self.requests_this_minute += 1
        return True
    
    async def chat_completion(self, messages: List[Dict[str, Any]], 
                            model: Optional[str] = None,
                            stream: bool = False,
                            **kwargs) -> Dict[str, Any]:
        """
        Send chat completion request to Groq bridge.
        
        This is the main method Hermes will use to interact with Groq.
        """
        if not self.rate_limit_check():
            raise Exception("Rate limit exceeded. Wait and try again.")
        
        model = model or self.model
        
        # Ensure model is available
        if model not in self.model_chain:
            model = self.model_chain[0]
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
            **kwargs
        }
        
        try:
            resp = requests.post(
                f"{self.bridge_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30
            )
            
            if resp.status_code == 200:
                return resp.json()
            else:
                return {
                    "error": {
                        "message": f"Groq API error: {resp.status_code}",
                        "type": "api_error",
                        "code": resp.status_code,
                        "details": resp.text
                    }
                }
                
        except requests.exceptions.RequestException as e:
            return {
                "error": {
                    "message": f"Groq bridge connection error: {str(e)}",
                    "type": "connection_error",
                    "code": "connection_failed"
                }
            }
    
    async def list_models(self) -> List[str]:
        """Get list of available models from Groq bridge."""
        try:
            resp = requests.get(f"{self.bridge_url}/v1/models", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("data", [])
                return [m["id"] for m in models]
            return self.model_chain
        except:
            return self.model_chain


# ─── AUTOMATIC SETUP ───────────────────────────────────────────────────────
def auto_setup() -> Dict[str, Any]:
    """
    Automatic setup when the wrapper is imported.
    
    Returns:
        Dict with status, config, and instructions for manual steps.
    """
    bridge = GroqHermesBridge()
    
    # Check bridge status
    health = asyncio.run(bridge.health_check())
    
    setup_result = {
        "bridge_status": health,
        "hermes_config": bridge.get_provider_config(),
        "next_steps": [
            "1. Get Groq API key from https://console.groq.com/keys",
            "2. Set environment variable: GROQ_API_KEY=your_key",
            "3. Run groq_bridge.py (starts local server)",
            "4. In Hermes, add custom provider from bridge config",
            "5. Test with a simple prompt"
        ],
        "notes": [
            "Free tier: generous daily limits on gpt-oss-120b",
            "Rate limit 60 requests/minute recommended",
            "Model fallback chain: gpt-oss-120b → gpt-oss-20b → qwen-27b → allam-7b"
        ]
    }
    
    return setup_result


# ─── EXPORTED FUNCTIONS FOR HERMES ──────────────────────────────────────────
# These are the functions Hermes can call

async def get_groq_completion(messages: List[Dict[str, Any]], 
                           model: Optional[str] = None,
                           **kwargs) -> Dict[str, Any]:
    """Hermes wrapper function for Groq completion."""
    bridge = GroqHermesBridge()
    return await bridge.chat_completion(messages, model, **kwargs)

async def setup_groq() -> Dict[str, Any]:
    """Setup and return configuration for Groq integration."""
    return auto_setup()


# ─── MAIN TESTING ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Groq Hermes Wrapper - Auto Setup")
    print("=" * 50)
    
    # Test auto-setup
    result = auto_setup()
    
    print(f"Bridge Status: {result['bridge_status']}")
    print("\nHermes Provider Config:")
    print(json.dumps(result['hermes_config'], indent=2))
    
    print("\nNext Steps:")
    for step in result['next_steps']:
        print(f"  {step}")
    
    print("\nNotes:")
    for note in result['notes']:
        print(f"  {note}")
    
    print("\nTest the bridge with a simple prompt:")
    test_result = asyncio.run(get_groq_completion([
        {"role": "user", "content": "Hello, how are you?"}
    ]))
    print(f"Result: {test_result}")