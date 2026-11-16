"""Answer library + deterministic local resolver for the BruceAI console.

Agents retry, fan out the same question to several turns, and re-ask identical
prompts after a restart. Those are all answerable from Python without touching
a provider. This module keeps a SQLite library keyed by the normalised
conversation and replays stored completions when the question repeats; a tiny
resolver covers arithmetic, time and date questions outright.

Policy: a provider call is made only when no local answer is available.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[\s\u200b]+")


def _canon(text: str) -> str:
    text = _PUNCT.sub(" ", str(text or "")).strip().casefold()
    return text


def _loose(text: str) -> str:
    """Punctuation-insensitive form used only for near-duplicate detection."""
    return re.sub(r"[^\w\s]", "", _canon(text))


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") in (None, "text", "input_text", "output_text"):
                    parts.append(str(part.get("text", part.get("content", ""))))
            elif part is not None:
                parts.append(str(part))
        return "\n".join(p for p in parts if p)
    try:
        return json.dumps(content, ensure_ascii=False)
    except Exception:
        return str(content)


def _message_text(message: Dict[str, Any]) -> str:
    text = _content_text(message.get("content"))
    if message.get("tool_calls"):
        try:
            text += json.dumps(message["tool_calls"], sort_keys=True)
        except Exception:
            text += str(message["tool_calls"])
    return text


class AnswerLibrary:
    def __init__(self, path: str, ttl_seconds: int = 14 * 24 * 3600, max_entries: int = 10000):
        self.path = path
        self.ttl = max(60, int(ttl_seconds))
        self.max_entries = max(50, int(max_entries))
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._stores = 0
        self._local = 0
        self._init_db()

    # ------------------------------------------------------------------ setup
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS answers (
                    key TEXT PRIMARY KEY,
                    prefix_key TEXT NOT NULL,
                    model TEXT NOT NULL,
                    last_text TEXT NOT NULL,
                    roles INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    reasoning TEXT DEFAULT '',
                    usage TEXT DEFAULT '',
                    created REAL NOT NULL,
                    hits INTEGER DEFAULT 0
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_answers_prefix ON answers(prefix_key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_answers_created ON answers(created)")

    # ------------------------------------------------------------------- keys
    def _parts(
        self,
        model: str,
        messages: Sequence[Dict[str, Any]],
        temperature: Optional[float],
        top_p: Optional[float],
        max_tokens: Optional[int],
    ) -> Tuple[str, str, str, int]:
        canon = [(m.get("role"), _canon(_message_text(m))) for m in messages]
        last_text = canon[-1][1] if canon else ""
        prefix = hashlib.sha256(
            json.dumps(
                [model, round(float(temperature or 0), 2), round(float(top_p or 0), 2),
                 max_tokens, canon[:-1]],
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        key = hashlib.sha256(
            json.dumps([prefix, last_text], ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return key, prefix, last_text, len(canon)

    # ---------------------------------------------------------------- lookups
    def lookup(
        self,
        model: str,
        messages: Sequence[Dict[str, Any]],
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        fuzzy: bool = True,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        key, prefix, last_text, roles = self._parts(model, messages, temperature, top_p, max_tokens)
        used_key = key
        fuzzy_hit = False
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT content, reasoning, usage, created, hits FROM answers "
                "WHERE key=? AND created>=?",
                (key, now - self.ttl),
            ).fetchone()
            if row is None and fuzzy and last_text and len(last_text) <= 220:
                rows = conn.execute(
                    "SELECT key, last_text, content, reasoning, usage, created FROM answers "
                    "WHERE prefix_key=? AND roles=? AND created>=? "
                    "ORDER BY created DESC LIMIT 25",
                    (prefix, roles, now - self.ttl),
                ).fetchall()
                best = None
                best_ratio = 0.0
                current_loose = _loose(last_text)
                for cand in rows:
                    ratio = difflib.SequenceMatcher(None, current_loose, _loose(cand[1])).ratio()
                    if ratio > best_ratio:
                        best, best_ratio = cand, ratio
                # Only short, near-identical follow-ups qualify. Long prompts or
                # code must match exactly: a 0.985 match can still be a different
                # function or a different file.
                if best is not None and best_ratio >= 0.985:
                    used_key = best[0]
                    row = best[2:]
                    fuzzy_hit = True
            if row is None:
                self._misses += 1
                return None
            content, reasoning, usage, created = row[0], row[1], row[2], row[3]
            hits = row[4] if len(row) > 4 else 0
            conn.execute("UPDATE answers SET hits=hits+1 WHERE key=?", (used_key,))
            self._hits += 1
        return {
            "content": content,
            "reasoning": reasoning or "",
            "usage": json.loads(usage) if usage else {},
            "age_seconds": max(0, int(now - float(created))),
            "hits": int(hits) + 1,
            "fuzzy": fuzzy_hit,
        }

    def store(
        self,
        model: str,
        messages: Sequence[Dict[str, Any]],
        content: str,
        reasoning: str = "",
        usage: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> bool:
        content = (content or "").strip()
        # Empty or tool-shaped replies are not replayable answers.
        if not content or len(content) > 400_000:
            return False
        key, prefix, last_text, roles = self._parts(model, messages, temperature, top_p, max_tokens)
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO answers(key,prefix_key,model,last_text,roles,content,reasoning,usage,created,hits) "
                "VALUES(?,?,?,?,?,?,?,?,?,0) "
                "ON CONFLICT(key) DO UPDATE SET content=excluded.content, "
                "reasoning=excluded.reasoning, usage=excluded.usage, created=excluded.created",
                (key, prefix, model, last_text, roles, content, reasoning or "",
                 json.dumps(usage or {}, ensure_ascii=False), now),
            )
            total = conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
            if total > self.max_entries:
                conn.execute(
                    "DELETE FROM answers WHERE key IN ("
                    "SELECT key FROM answers ORDER BY created ASC LIMIT ?)",
                    (total - self.max_entries,),
                )
            self._stores += 1
        return True

    def note_local(self) -> None:
        self._local += 1

    def stats(self) -> Dict[str, Any]:
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute("SELECT COUNT(*), COALESCE(SUM(hits),0) FROM answers").fetchone()
                size = os.path.getsize(self.path) if os.path.exists(self.path) else 0
        except sqlite3.Error:
            rows, size = (0, 0), 0
        return {
            "entries": int(rows[0] or 0),
            "replayed_hits": int(rows[1] or 0),
            "session_hits": self._hits,
            "session_misses": self._misses,
            "session_stores": self._stores,
            "local_answers": self._local,
            "ttl_seconds": self.ttl,
            "max_entries": self.max_entries,
            "size_bytes": size,
        }

    def clear(self) -> int:
        with self._lock, self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
            conn.execute("DELETE FROM answers")
        return int(count or 0)


# --------------------------------------------------------------- local solver
_ARITH_PREFIX = re.compile(
    r"^(?:what(?:'s| is)|whats|calculate|compute|evaluate|solve|how much is)?\s*",
    re.I,
)
_ARITH_BODY = re.compile(r"^[\d\s+\-*/().%^]+$")
_TIME_Q = re.compile(
    r"^(?:what(?:'s| is) the time(?: now| right now)?|what time is it|current time|time now)\??$",
    re.I,
)
_DATE_Q = re.compile(
    r"^(?:what(?:'s| is) (?:the )?(?:date|day)(?: today)?|what day is it|today'?s date|"
    r"what(?:'s| is) today'?s date)\??$",
    re.I,
)


def _safe_eval(expr: str) -> Optional[float]:
    if len(expr) > 160 or expr.count("(") > 20:
        return None
    node = ast.parse(expr.replace("^", "**"), mode="eval")

    def walk(n: ast.AST) -> float:
        if isinstance(n, ast.Expression):
            return walk(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            value = walk(n.operand)
            return value if isinstance(n.op, ast.UAdd) else -value
        if isinstance(n, ast.BinOp):
            left, right = walk(n.left), walk(n.right)
            if isinstance(n.op, ast.Add):
                return left + right
            if isinstance(n.op, ast.Sub):
                return left - right
            if isinstance(n.op, ast.Mult):
                return left * right
            if isinstance(n.op, ast.Div):
                if right == 0:
                    raise ZeroDivisionError
                return left / right
            if isinstance(n.op, ast.FloorDiv):
                if right == 0:
                    raise ZeroDivisionError
                return left // right
            if isinstance(n.op, ast.Mod):
                if right == 0:
                    raise ZeroDivisionError
                return left % right
            if isinstance(n.op, ast.Pow):
                if abs(right) > 64 or abs(left) > 1e6:
                    raise ValueError
                return left ** right
        raise ValueError("unsupported expression")

    try:
        return walk(node)
    except (ValueError, ZeroDivisionError, SyntaxError, OverflowError):
        return None


def _fmt_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.10g}"


def local_answer(
    messages: Sequence[Dict[str, Any]],
    model: str = "",
) -> Optional[Dict[str, Any]]:
    """Answer a narrow, deterministic class of questions without a provider.
    Deliberately conservative: anything ambiguous falls through to the model."""
    if not messages:
        return None
    last = messages[-1]
    if last.get("role") != "user" or last.get("tool_calls"):
        return None
    text = _content_text(last.get("content")).strip()
    if not text or len(text) > 200 or "\n" in text:
        return None

    if _TIME_Q.match(text):
        now = datetime.now()
        return {
            "content": f"It is {now:%H:%M} on {now:%A}, {now:%d %B %Y}.",
            "source": "time",
        }
    if _DATE_Q.match(text):
        now = datetime.now()
        return {
            "content": f"Today is {now:%A}, {now:%d %B %Y}.",
            "source": "date",
        }

    if not re.search(r"[+\-*/%^]", text):
        return None
    body = _ARITH_PREFIX.sub("", text.strip().rstrip("?=").strip())
    if not body or not _ARITH_BODY.match(body) or not re.search(r"\d", body):
        return None
    value = _safe_eval(body)
    if value is None:
        return None
    return {"content": f"{body} = {_fmt_number(value)}", "source": "arithmetic"}
