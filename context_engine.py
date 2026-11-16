"""Virtual context window for the BruceAI provider console.

The harness accepts prompts far larger than any single upstream model can hold.
This module breaks them down locally - sentence scoring, per-chunk digests and
structural grouping - so an agent still receives the relevant material while
the upstream sees a bounded prompt. Nothing here calls a model: compression is
extractive and deterministic, which keeps the console's promise that a call
only leaves the machine when the local answer library cannot answer.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple

try:  # optional; the heuristic below is good enough when absent
    import tiktoken
except Exception:  # pragma: no cover - tiktoken is optional
    tiktoken = None

_ENC: Any = None
_ENC_TRIED = False

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_'-]{1,}")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_FENCE = re.compile(r"```.*?```", re.S)
_LIST_OR_HEADING = re.compile(r"^(?:#{1,6}\s|\d+[.)]\s|[-*+]\s|>)")
_STOP = set(
    "the a an and or but if then than that this these those of to in on for with as at by "
    "from is are was were be been being it its their our your his her they we you i not no "
    "do does did can could should would may might will just also very more most much many "
    "some any about into over under out up down there here what which who whom whose when "
    "where why how".split()
)


def _encoder() -> Any:
    global _ENC, _ENC_TRIED
    if not _ENC_TRIED:
        _ENC_TRIED = True
        if tiktoken is not None:
            try:
                _ENC = tiktoken.get_encoding("cl100k_base")
            except Exception:
                _ENC = None
    return _ENC


def estimate_tokens(text: str) -> int:
    """Token estimate that never raises. Uses tiktoken when installed,
    otherwise the ~3.8 chars/token average for English + code."""
    if not text:
        return 0
    enc = _encoder()
    if enc is not None:
        try:
            return len(enc.encode(text, disallowed_special=()))
        except Exception:
            pass
    return max(1, int(len(text) / 3.8))


def content_text(content: Any) -> str:
    """Flatten OpenAI message content (string or multimodal parts) to text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (int, float, bool)):
        return str(content)
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                kind = part.get("type")
                if kind in (None, "text", "input_text", "output_text"):
                    txt = part.get("text", part.get("content", ""))
                    if txt:
                        parts.append(str(txt))
                elif kind in ("image_url", "input_image"):
                    parts.append("[image]")
                elif kind == "input_audio":
                    parts.append("[audio]")
            elif part is not None:
                parts.append(str(part))
        return "\n".join(parts)
    try:
        return json.dumps(content, ensure_ascii=False)
    except Exception:
        return str(content)


def message_tokens(message: Dict[str, Any]) -> int:
    text = content_text(message.get("content"))
    if message.get("tool_calls"):
        try:
            text += json.dumps(message["tool_calls"], ensure_ascii=False)
        except Exception:
            text += str(message["tool_calls"])
    return estimate_tokens(text) + 4


def total_tokens(messages: Iterable[Dict[str, Any]]) -> int:
    return sum(message_tokens(m) for m in messages)


def _split_sentences(text: str) -> List[str]:
    out: List[str] = []
    for block in _SENT_SPLIT.split(text):
        block = (block or "").strip()
        if block:
            out.append(block)
    return out


def _score_sentences(sentences: List[str]) -> List[Tuple[float, int, str]]:
    freq: Counter = Counter()
    for sentence in sentences:
        for word in _WORD.findall(sentence.lower()):
            if word not in _STOP:
                freq[word] += 1
    scored: List[Tuple[float, int, str]] = []
    for idx, sentence in enumerate(sentences):
        words = [w for w in _WORD.findall(sentence.lower()) if w not in _STOP]
        if words:
            score = sum(freq[w] for w in words) / math.sqrt(len(words))
        else:
            score = 0.1
        if _LIST_OR_HEADING.match(sentence):
            score *= 1.2
        if any(ch.isdigit() for ch in sentence):
            score *= 1.05
        scored.append((score, idx, sentence))
    return scored


def _extract(text: str, target_tokens: int) -> str:
    """Highest-scoring sentences, original order, bounded by target_tokens."""
    if estimate_tokens(text) <= target_tokens:
        return text
    sentences = _split_sentences(text)
    if not sentences:
        return text[: max(200, target_tokens * 4)]
    budget_chars = max(160, int(target_tokens * 3.8))
    chosen: set = set()
    used = 0
    # Keep the opening sentence (usually the topic) and the closing one
    # (usually the conclusion) before scoring the middle.
    for idx in (0, len(sentences) - 1):
        if idx >= 0 and len(sentences[idx]) + 1 <= budget_chars:
            chosen.add(idx)
            used += len(sentences[idx]) + 1
    for _score, idx, sentence in sorted(_score_sentences(sentences), reverse=True):
        if idx in chosen:
            continue
        if used + len(sentence) + 1 > budget_chars:
            continue
        chosen.add(idx)
        used += len(sentence) + 1
        if used >= budget_chars * 0.98:
            break
    if not chosen:
        chosen = {0}
    return " ".join(sentences[i] for i in sorted(chosen))


def _shrink_code(block: str, max_lines: int) -> str:
    lines = block.splitlines()
    if len(lines) <= max_lines:
        return block
    head = lines[: max(1, max_lines - 6)]
    tail = lines[-5:]
    return "\n".join(head + ["... [code truncated] ..."] + tail)


def summarize_text(text: str, target_tokens: int) -> str:
    """Extractive summary. Code fences are treated separately so agents keep
    signatures and endings instead of half-parsed punctuation."""
    target_tokens = max(24, int(target_tokens))
    if estimate_tokens(text) <= target_tokens:
        return text

    code_blocks = _FENCE.findall(text)
    prose = _FENCE.sub("\n[code block]\n", text)
    prose_budget = int(target_tokens * 0.72)
    prose_out = _extract(prose, prose_budget)

    kept_code: List[str] = []
    if code_blocks:
        remaining_lines = max(12, int((target_tokens - estimate_tokens(prose_out)) * 2.6))
        for block in reversed(code_blocks):  # newest code is usually most relevant
            if remaining_lines <= 6:
                break
            shrunk = _shrink_code(block, min(remaining_lines, 48))
            kept_code.append(shrunk)
            remaining_lines -= len(shrunk.splitlines()) + 1
        kept_code.reverse()

    out = prose_out
    if kept_code:
        out += "\n\n[code excerpts]\n" + "\n\n".join(kept_code)
    limit_chars = max(400, int(target_tokens * 4.4))
    if len(out) > limit_chars:
        out = out[:limit_chars].rstrip() + "\n... [truncated]"
    return out


def chunk_text(text: str, chunk_tokens: int = 2000) -> List[str]:
    """Paragraph-aware chunking with a sentence-level fallback for huge blocks."""
    limit = max(600, int(chunk_tokens * 3.8))
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf.strip():
            chunks.append(buf)
        buf = ""

    for para in re.split(r"\n{2,}", text):
        para = para or ""
        while len(para) > limit:
            cut = para.rfind("\n", 0, limit)
            if cut < limit // 3:
                cut = para.rfind(". ", 0, limit)
                cut = cut + 1 if cut > limit // 3 else limit
            head, para = para[:cut], para[cut:]
            if buf:
                flush()
            chunks.append(head)
        if len(buf) + len(para) + 2 <= limit:
            buf = f"{buf}\n\n{para}" if buf else para
        else:
            flush()
            buf = para
    flush()
    return chunks or [text]


def digest_text(text: str, allow_tokens: int, chunk_tokens: int = 2000) -> str:
    """Break a long single message into parts, digest each, then merge.
    This is the 'chunk, break down, reassemble' path the agent sees."""
    allow_tokens = max(32, int(allow_tokens))
    if estimate_tokens(text) <= allow_tokens:
        return text
    chunks = chunk_text(text, chunk_tokens)
    if len(chunks) == 1:
        return summarize_text(text, allow_tokens)
    # Collapse very large documents into a bounded number of groups before
    # digesting: 150 tiny part labels would crowd out the content itself.
    max_parts = max(4, min(40, allow_tokens // 64))
    if len(chunks) > max_parts:
        group_size = math.ceil(len(chunks) / max_parts)
        groups = [
            "\n\n".join(chunks[i : i + group_size])
            for i in range(0, len(chunks), group_size)
        ]
    else:
        groups = chunks
    per_chunk = max(32, allow_tokens // len(groups))
    parts = []
    for idx, group in enumerate(groups, 1):
        parts.append(f"[part {idx}/{len(groups)}] {summarize_text(group, per_chunk)}")
    merged = "\n".join(parts)
    if estimate_tokens(merged) > allow_tokens:
        merged = summarize_text(merged, allow_tokens)
    return merged


def _protected(message: Dict[str, Any]) -> bool:
    role = message.get("role")
    return role == "tool" or bool(message.get("tool_calls")) or bool(message.get("tool_call_id"))


def compress_messages(
    messages: List[Dict[str, Any]],
    budget_tokens: int,
    target_tokens: int,
    chunk_tokens: int = 2000,
    keep_tail: int = 6,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return (possibly compressed messages, report). Structure is preserved:
    every role, tool_call id and tool result stays present; only content is
    summarised and only plain old turns may be omitted."""
    original = total_tokens(messages)
    report: Dict[str, Any] = {
        "compressed": False,
        "original_tokens": original,
        "final_tokens": original,
        "budget_tokens": budget_tokens,
        "target_tokens": target_tokens,
        "messages_in": len(messages),
        "messages_out": len(messages),
        "messages_summarized": 0,
        "messages_omitted": 0,
        "chunks": 0,
    }
    if original <= budget_tokens or not messages:
        return messages, report

    target = max(512, min(int(target_tokens), int(budget_tokens)))
    working = [dict(m) for m in messages]
    count = len(working)
    tail_start = max(0, count - max(1, keep_tail))

    system_idx = next((i for i, m in enumerate(working) if m.get("role") == "system"), None)
    last_user_idx = max(
        (i for i, m in enumerate(working) if m.get("role") == "user"),
        default=count - 1,
    )

    allowances: Dict[int, int] = {}
    for idx, message in enumerate(working):
        role = message.get("role")
        if idx == system_idx:
            allowances[idx] = int(target * 0.15)
        elif idx == last_user_idx:
            allowances[idx] = int(target * 0.40)
        elif idx >= tail_start:
            allowances[idx] = int(target * 0.10)
        elif _protected(message):
            allowances[idx] = int(target * 0.08)
        else:
            allowances[idx] = 0

    floors = {system_idx: int(target * 0.05), last_user_idx: int(target * 0.22)}
    floors = {k: v for k, v in floors.items() if k is not None}

    def overage() -> int:
        return sum(allowances.values()) - target

    # Shrink every allowance proportionally, never below its floor, until the
    # allocation fits. Two passes are enough for realistic conversations.
    for _ in range(4):
        excess = overage()
        if excess <= 0:
            break
        reducible = [i for i, v in allowances.items() if v > floors.get(i, 0) + 8]
        if not reducible:
            break
        pool = sum(allowances[i] - floors.get(i, 0) for i in reducible)
        if pool <= 0:
            break
        take = min(excess, pool)
        for idx in reducible:
            room = allowances[idx] - floors.get(idx, 0)
            allowances[idx] -= int(round(take * room / pool))
    # Final pass: zero out unprotected middle turns if still over.
    while overage() > 0:
        candidates = [i for i in allowances if i not in floors and allowances[i] > 0]
        if not candidates:
            break
        idx = max(candidates, key=lambda i: allowances[i])
        allowances[idx] = 0

    # Water-fill the remaining budget: messages that need less than their
    # allowance release the difference, and it flows to messages that were
    # truncated. Without this a single huge document in a short conversation
    # kept only its initial slice of the window.
    for _ in range(6):
        effective = {
            idx: min(allowances.get(idx, 0), message_tokens(working[idx]))
            for idx in allowances
        }
        spare = target - sum(effective.values())
        if spare <= 48:
            break
        needs = []
        for idx, message in enumerate(working):
            need = message_tokens(message) - effective.get(idx, 0)
            if need > 24:
                needs.append((idx, need))
        if not needs:
            break
        # Newest first: when a conversation is over budget, coherent recent
        # turns are worth more than scattered fragments of old ones.
        for idx, need in sorted(needs, key=lambda item: item[0], reverse=True):
            extra = min(need, spare)
            allowances[idx] = effective.get(idx, 0) + extra
            spare -= extra
            if spare <= 24:
                break

    out: List[Dict[str, Any]] = []
    summarized = 0
    omitted = 0
    chunks_used = 0

    for idx, message in enumerate(working):
        allow = allowances.get(idx, 0)
        text = content_text(message.get("content"))
        protected = _protected(message) or idx in floors

        if allow <= 24 and not protected:
            omitted += 1
            continue

        new_text = text
        if text and estimate_tokens(text) > allow:
            new_text = digest_text(text, allow, chunk_tokens)
            summarized += 1
            chunks_used += max(1, len(chunk_text(text, chunk_tokens)))
        if message.get("content") is not None:
            message["content"] = new_text
        out.append(message)

    report.update(
        {
            "compressed": True,
            "messages_out": len(out),
            "messages_summarized": summarized,
            "messages_omitted": omitted,
            "chunks": chunks_used,
        }
    )

    note = compression_note(report)
    if note:
        first_system = next((m for m in out if m.get("role") == "system"), None)
        if first_system is not None:
            first_system["content"] = f"{content_text(first_system.get('content'))}\n\n{note}"
        else:
            out.insert(0, {"role": "system", "content": note})

    report["final_tokens"] = total_tokens(out)
    return out, report


def report_header(report: Dict[str, Any]) -> str:
    """Compact value for the x-bruceai-context response header."""
    if not report.get("compressed"):
        return f"none; {report.get('original_tokens', 0)} tokens"
    return (
        f"compressed; {report['original_tokens']}->{report['final_tokens']} tokens; "
        f"{report['chunks']} chunks; {report['messages_summarized']} summarized; "
        f"{report['messages_omitted']} omitted"
    )


def compression_note(report: Dict[str, Any]) -> str:
    """Text added to the leading system message so the agent knows the window
    it is reading is a digest, not the raw transcript."""
    if not report.get("compressed"):
        return ""
    return (
        "[bruceai-context] The request exceeded the upstream window and was broken into "
        f"{report['chunks']} chunk(s). Older material was summarised extractively "
        f"({report['messages_summarized']} message(s)) and {report['messages_omitted']} "
        "low-priority message(s) were omitted. Treat the digest as background and prefer "
        "the most recent turns when instructions conflict."
    )
