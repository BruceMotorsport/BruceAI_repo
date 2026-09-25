#!/usr/bin/env python3
"""
Sanitize user input before it reaches Groq bridge, database, or any backend.
Defends against: script injection, SQL injection, XSS payloads, command injection.
"""
import html
import re

FORBIDDEN_PATTERNS = [
    # XSS / script injection
    r"(?i)<script.*?>.*?</script>",
    r"(?i)<iframe.*?>.*?</iframe>",
    r"(?i)<object.*?>.*?</object>",
    r"(?i)<embed.*?>",
    r"(?i)javascript:",
    r"(?i)on\w+\s*=[^>]*",
    r"(?i)onload=",
    r"(?i)onerror=",
    # SQL injection (basic pattern blocking)
    r"(?i)(\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bDROP\b|\bUNION\b|\bALTER\b|\bCREATE\b)",
    # Command injection
    r"(?i)[;|`$\(\)\{\}\[\]\*\?]",
]

BLOCKED_MARKER = "[BLOCKED]"

def sanitize_input(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    # HTML entity escape first
    text = html.escape(text, quote=True)
    # Remove script tags entirely
    text = re.sub(r"(?i)<script.*?>.*?</script>", BLOCKED_MARKER, text, flags=re.DOTALL)
    # Block other dangerous tags
    for tag in ["iframe", "object", "embed", "form", "input", "meta", "link", "base"]:
        text = re.sub(rf"(?i)<{tag}.*?>.*?</{tag}>", BLOCKED_MARKER, text, flags=re.DOTALL)
        text = re.sub(rf"(?i)<{tag}.*?>", BLOCKED_MARKER, text)
    # Block event handlers
    text = re.sub(r"(?i)on\w+\s*=[^>]*", BLOCKED_MARKER, text)
    # Block javascript protocol
    text = re.sub(r"(?i)javascript:", BLOCKED_MARKER, text)
    # Block SQL keywords (prevent injection attempts)
    text = re.sub(r"(?i)(\bSELECT\b)", BLOCKED_MARKER, text)
    text = re.sub(r"(?i)(\bINSERT\b)", BLOCKED_MARKER, text)
    text = re.sub(r"(?i)(\bUPDATE\b)", BLOCKED_MARKER, text)
    text = re.sub(r"(?i)(\bDELETE\b)", BLOCKED_MARKER, text)
    text = re.sub(r"(?i)(\bDROP\b)", BLOCKED_MARKER, text)
    text = re.sub(r"(?i)(\bUNION\b)", BLOCKED_MARKER, text)
    # Basic shell meta removal
    text = text.replace(";", BLOCKED_MARKER).replace("|", BLOCKED_MARKER)
    return text

if __name__ == "__main__":
    # Quick self-test
    tests = [
        "Hello world",
        "<script>alert('xss')</script>",
        "SELECT * FROM users",
        "javascript:window.location='evil.com'",
        "onload=stealCookie()",
        "User input <iframe src=evil>",
        "Normal text with no injection",
    ]
    for t in tests:
        print(f"IN:  {t!r}")
        print(f"OUT: {sanitize_input(t)!r}")
        print()
