"""OpenRouter chat client. Tracks cost per run."""
from __future__ import annotations

import json
import logging
import time

import httpx

from .config import env

log = logging.getLogger(__name__)
URL = "https://openrouter.ai/api/v1/chat/completions"
COST = {"usd": 0.0}


def _call(system: str, user: str, *, max_tokens: int, temperature: float, as_json: bool) -> str:
    body = {
        "model": env("LLM_MODEL", "deepseek/deepseek-v4.1-flash"),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "reasoning": {"enabled": False},
        "usage": {"include": True},
    }
    if as_json:
        body["response_format"] = {"type": "json_object"}
    r = httpx.post(URL, json=body, timeout=420,
                   headers={"Authorization": f"Bearer {env('OPENROUTER_API_KEY')}"})
    if r.status_code >= 400:
        raise RuntimeError(f"OpenRouter {r.status_code}: {r.text[:400]}")
    d = r.json()
    COST["usd"] += float((d.get("usage") or {}).get("cost") or 0)
    ch = d["choices"][0]
    if ch.get("finish_reason") == "length":
        raise RuntimeError(f"output truncated at {max_tokens} tokens")
    return (ch["message"].get("content") or "").strip()


def _retry(fn):
    for attempt in range(3):
        try:
            return fn()
        except Exception as ex:
            if attempt == 2:
                raise
            log.warning("llm attempt %d failed: %s", attempt + 1, str(ex)[:200])
            time.sleep(5 * (attempt + 1))


def complete_json(system: str, user: str, *, max_tokens: int, temperature: float = 0.4, validate=None) -> dict:
    def go():
        t = _call(system, user, max_tokens=max_tokens, temperature=temperature, as_json=True)
        if t.startswith("```"):
            t = t.split("\n", 1)[1].rsplit("```", 1)[0]
        d = json.loads(t)
        if validate:
            validate(d)
        return d
    return _retry(go)


def complete_text(system: str, user: str, *, max_tokens: int, temperature: float = 0.5) -> str:
    def go():
        t = _call(system, user, max_tokens=max_tokens, temperature=temperature, as_json=False)
        if not t:
            raise RuntimeError("empty completion")
        return t
    return _retry(go)
