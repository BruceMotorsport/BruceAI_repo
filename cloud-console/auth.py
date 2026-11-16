#!/usr/bin/env python3
"""Crypto primitives for Bruce AI Cloud Console.

Password hashing  : scrypt (stdlib) + per-password salt
Session tokens    : HMAC-SHA256 signed, expiring
API keys          : opaque bearer tokens, stored only as SHA-256
Stripe webhooks   : stdlib HMAC verification of the Stripe-Signature header
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional, Tuple

# --- scrypt password hashing -------------------------------------------------
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, dk_hex = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(dk_hex) // 2,
        )
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, TypeError):
        return False


# --- signed session tokens ---------------------------------------------------
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def sign(payload: dict, secret: bytes, ttl_seconds: int) -> str:
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl_seconds
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    token = _b64e(raw)
    sig = hmac.new(secret, token.encode("ascii"), hashlib.sha256).digest()
    return f"{token}.{_b64e(sig)}"


def verify(token: str, secret: bytes) -> Optional[dict]:
    """Return the payload when signature and expiry both check out."""
    try:
        token_part, sig_part = token.rsplit(".", 1)
    except ValueError:
        return None
    expect = hmac.new(secret, token_part.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(expect, _b64d(sig_part)):
        return None
    try:
        payload = json.loads(_b64d(token_part))
    except (ValueError, TypeError):
        return None
    if int(payload.get("exp", 0)) < time.time():
        return None
    return payload


# --- secrets -----------------------------------------------------------------
def load_or_create_secret(path: str) -> bytes:
    """Read the console signing secret, minting one on first boot."""
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            data = fh.read().strip()
        if len(data) >= 32:
            return data
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data = secrets.token_bytes(48)
    with open(path, "wb") as fh:
        fh.write(data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return data


# --- API keys ----------------------------------------------------------------
API_KEY_PREFIX = "bak_"


def new_api_key() -> Tuple[str, str]:
    """Return (plaintext key, sha256 hex digest). Plaintext is shown once."""
    plain = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return plain, hash_api_key(plain)


def hash_api_key(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def looks_like_api_key(value: str) -> bool:
    return value.startswith(API_KEY_PREFIX) and 20 <= len(value) <= 200


# --- Stripe signature verification (stdlib) ----------------------------------
def verify_stripe_signature(payload: bytes, header: str, secret: str,
                            tolerance: int = 300) -> bool:
    """Implements Stripe's v1 scheme: HMAC-SHA256(secret, t.payload)."""
    if not secret or not header:
        return False
    parts = {}
    for item in header.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            parts.setdefault(k.strip(), []).append(v.strip())
    try:
        timestamp = int(parts["t"][0])
    except (KeyError, ValueError, IndexError):
        return False
    if abs(int(time.time()) - timestamp) > tolerance:
        return False
    signed = f"{timestamp}.".encode("ascii") + payload
    expect = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expect, v) for v in parts.get("v1", []))
