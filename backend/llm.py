"""LLM wrapper that returns text or parsed JSON. Works with Anthropic (Claude) or OpenAI (GPT)."""
import json
import re

import httpx

from . import config

_anthropic = None


def available() -> bool:
    return config.llm_provider() is not None


def _anthropic_complete(system: str, prompt: str, max_tokens: int) -> str:
    global _anthropic
    if _anthropic is None:
        import anthropic

        _anthropic = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = _anthropic.messages.create(
        model=config.LLM_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _openai_complete(system: str, prompt: str, max_tokens: int, json_mode: bool) -> str:
    body = {
        "model": config.OPENAI_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        # GPT-5 models count reasoning tokens here too, so leave generous headroom.
        "max_completion_tokens": max_tokens * 4,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        json=body,
        headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
        timeout=180,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI API error {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"].get("content") or ""


def complete(system: str, prompt: str, max_tokens: int = 4000, json_mode: bool = False) -> str:
    provider = config.llm_provider()
    if provider == "anthropic":
        return _anthropic_complete(system, prompt, max_tokens)
    if provider == "openai":
        return _openai_complete(system, prompt, max_tokens, json_mode)
    raise RuntimeError("No LLM key set: add ANTHROPIC_API_KEY or OPENAI_API_KEY to .env")


def complete_json(system: str, prompt: str, max_tokens: int = 4000):
    """Ask for JSON and parse it, tolerating code fences or stray prose around it."""
    text = complete(system + "\nRespond with JSON only, no prose.", prompt, max_tokens, json_mode=True)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(1))
