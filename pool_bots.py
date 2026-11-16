"""Local answer hook for the Groq Pool Bridge.

`answer(payload)` runs before any Groq call. Return an OpenAI-compatible
chat-completion dict and the bridge replays it to the client (streamed or not)
without spending tokens; return None to let the request go upstream.

This is where the harness's Python bots live: deterministic replies, tool-call
stubs, and anything backed by an internal database. Keep it fast; it runs inline.

Example
-------
    def answer(payload):
        text = payload["messages"][-1]["content"]
        if isinstance(text, str) and text.strip().lower() == "ping":
            return {
                "id": "chatcmpl-local-1",
                "object": "chat.completion",
                "created": 0,
                "model": payload["model"],
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "pong"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        return None
"""


def answer(payload):
    return None
