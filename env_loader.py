"""Load BruceAI `.env` into ``os.environ`` using only the standard library.

Rules:
  * Existing, usable environment variables always win over the file.
  * Placeholder values (``<...>``, ``YOUR_...``, ``changeme``, too short, ...) are never
    exported, so callers can reliably test ``os.environ.get(...)`` for "configured".
  * Secrets are read from disk at run time - nothing is hardcoded here.

Usage:
    from env_loader import load_dotenv, real_key
    load_dotenv()                     # side effect: populates os.environ
    key = real_key("GROQ_API_KEY")    # None when missing/placeholder
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / ".env"

# Same machine-local fallbacks the PowerShell launcher uses: the Hermes profile .env files
# already hold this machine's own real Groq / OpenRouter keys.
_HERMES_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"
_FALLBACK_KEYS = ("GROQ_API_KEY", "OPENROUTER_API_KEY")

_PLACEHOLDER_TOKENS = ("<", ">", "your_", "changeme", "placeholder", "test_key", "dummy")


def is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    v = value.strip()
    if not v or len(v) < 12:
        return True
    low = v.lower()
    return any(tok in low for tok in _PLACEHOLDER_TOKENS)


def _parse(path: Path) -> dict:
    out = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def _fallback_files():
    files = []
    profiles = _HERMES_ROOT / "profiles"
    if profiles.is_dir():
        files.extend(sorted(p / ".env" for p in profiles.iterdir() if p.is_dir()))
    files.append(_HERMES_ROOT / ".env")
    return files


def load_dotenv(path=None, verbose: bool = False) -> dict:
    """Populate ``os.environ`` from ``path`` (default: ``.env`` next to this file)."""
    env_file = Path(path) if path else DEFAULT_PATH
    values = _parse(env_file)
    applied = {}

    for key, value in values.items():
        if is_placeholder(value):
            if verbose:
                print(f"[env_loader] {key}: placeholder ignored")
            continue
        current = os.environ.get(key)
        if current and not is_placeholder(current):
            continue
        os.environ[key] = value
        applied[key] = value

    for key in _FALLBACK_KEYS:
        if not is_placeholder(os.environ.get(key)):
            continue
        for candidate in _fallback_files():
            value = _parse(candidate).get(key)
            if not is_placeholder(value):
                os.environ[key] = value
                applied[key] = value
                if verbose:
                    print(f"[env_loader] {key}: loaded from {candidate}")
                break

    # main.py reads OPENCODE_KEY; the file (and the opencode subprocess) use OPENCODE_API_KEY.
    opencode = os.environ.get("OPENCODE_API_KEY")
    if not is_placeholder(opencode) and not is_placeholder(os.environ.get("OPENCODE_KEY")):
        os.environ.setdefault("OPENCODE_KEY", opencode)

    os.environ.setdefault("GROQ_BRIDGE_URL", "http://127.0.0.1:8080/v1")
    return applied


def real_key(name: str) -> str | None:
    """Return the usable value of ``name``, or ``None`` when missing/placeholder."""
    value = os.environ.get(name)
    return None if is_placeholder(value) else value
