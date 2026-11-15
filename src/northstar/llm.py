"""OpenRouter chat helper. Jev is the fast decision engine: one call must return one JSON object."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

URL = "https://openrouter.ai/api/v1/chat/completions"


def jev_model() -> str:
    return os.environ.get("JEV_MODEL", "typesafe/jev-router")


class LLMError(RuntimeError):
    pass


def _parse(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text).strip()
    try:
        return json.loads(text)
    except ValueError:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            return json.loads(text[a : b + 1])
        raise


def chat_json(messages: list[dict], model: str | None = None, max_tokens: int = 1500, timeout: int = 90) -> tuple[dict, dict]:
    """Returns (parsed JSON object, info) where info has model, seconds and usage."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise LLMError("OPENROUTER_API_KEY is not set (copy .env.example to .env at the repo root)")
    body = {"model": model or jev_model(), "messages": messages, "max_tokens": max_tokens, "temperature": 0.1,
            "response_format": {"type": "json_object"}}
    effort = os.environ.get("JEV_REASONING_EFFORT", "default")
    if effort and effort != "default":
        body["reasoning"] = {"effort": effort}
    t0 = time.time()
    last = "no attempt"
    for attempt in range(3):
        req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "North star intake"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}"
            if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise LLMError(f"OpenRouter {last}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise LLMError(f"could not reach OpenRouter: {e}") from None
        if "error" in data:
            last = str(data["error"])[:300]
            time.sleep(1)
            continue
        text = data["choices"][0]["message"].get("content") or ""
        try:
            return _parse(text), {"model": data.get("model", body["model"]), "seconds": round(time.time() - t0, 2),
                                  "usage": data.get("usage", {})}
        except ValueError:
            last = f"model did not return JSON: {text[:160]}"
            body["messages"] = messages + [{"role": "assistant", "content": text},
                                           {"role": "user", "content": "Return ONLY the JSON object."}]
    raise LLMError(last)
