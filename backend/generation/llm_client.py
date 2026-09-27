"""LLM back-ends behind one tiny interface.

anthropic  - Claude via the Anthropic API (needs ANTHROPIC_API_KEY)
gemini     - Google Gemini via REST (needs GEMINI_API_KEY; gemini-2.5-flash is free)
ollama     - local models (Llama / Mistral / Qwen ...) via an Ollama server
extractive - no LLM at all: returns the top retrieved code with citations (offline dev / tests)
"""
from __future__ import annotations

import logging
import os
import time

import httpx

from .prompt_templates import Prompt

log = logging.getLogger("repomind.llm")


class LLMError(RuntimeError):
    pass


class LLMClient:
    name = "base"
    can_chat = True     # supports free-form chat (used for follow-up question rewriting)

    def chat(self, system: str, messages: list[dict], max_tokens: int = 1024) -> str:  # pragma: no cover
        raise NotImplementedError

    def answer(self, prompt: Prompt, max_tokens: int = 1024) -> str:
        return self.chat(prompt.system, prompt.messages, max_tokens)


class AnthropicClient(LLMClient):
    def __init__(self, model: str):
        import anthropic

        self.name = f"anthropic:{model}"
        self.model = model
        self.client = anthropic.Anthropic()          # reads ANTHROPIC_API_KEY

    def chat(self, system: str, messages: list[dict], max_tokens: int = 1024) -> str:
        try:
            resp = self.client.messages.create(model=self.model, max_tokens=max_tokens, system=system,
                                               messages=messages)
        except Exception as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()


class OllamaClient(LLMClient):
    def __init__(self, model: str, url: str):
        self.name = f"ollama:{model}"
        self.model, self.url = model, url.rstrip("/")

    def chat(self, system: str, messages: list[dict], max_tokens: int = 1024) -> str:
        payload = {"model": self.model, "stream": False,
                   "messages": [{"role": "system", "content": system}, *messages],
                   "options": {"num_predict": max_tokens, "temperature": 0.1}}
        try:
            r = httpx.post(f"{self.url}/api/chat", json=payload, timeout=300)
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
        except Exception as exc:
            raise LLMError(f"Ollama error: {exc}") from exc


class GeminiClient(LLMClient):
    """Google Gemini via the generativelanguage REST API (needs GEMINI_API_KEY).
    Default model is "gemini-flash-latest" - Google's rolling alias to their current
    fast/free model, rather than a dated name like "gemini-2.5-flash" (Google has been
    retiring dated model names from the generateContent endpoint even while they still
    show up in ListModels, which breaks pinned model names without warning).
    Free tier - no billing account required, just an API key from
    https://aistudio.google.com/apikey.
    As of mid-2026 AI Studio issues "AQ." authentication keys (replacing the older
    AIzaSy... traffic keys), which must be sent as the x-goog-api-key header rather
    than a ?key= query parameter."""

    def __init__(self, model: str):
        self.name = f"gemini:{model}"
        self.model = model
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY is not set")

    def chat(self, system: str, messages: list[dict], max_tokens: int = 1024) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {"role": "model" if m["role"] == "assistant" else "user",
                 "parts": [{"text": m["content"]}]}
                for m in messages
            ],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.1},
        }
        headers = {"x-goog-api-key": self.api_key}
        last_exc: Exception | None = None
        # Free-tier Gemini models occasionally return 429/503 under load; these are
        # transient, so retry a few times with backoff before giving up.
        for attempt, delay in enumerate((0, 2, 5)):
            if delay:
                time.sleep(delay)
            try:
                r = httpx.post(url, json=payload, timeout=60, headers=headers)
                if r.status_code in (429, 503) and attempt < 2:
                    log.warning("Gemini returned %s (attempt %d/3), retrying...",
                                r.status_code, attempt + 1)
                    continue
                r.raise_for_status()
                data = r.json()
                parts = data["candidates"][0]["content"]["parts"]
                return "".join(p.get("text", "") for p in parts).strip()
            except Exception as exc:
                last_exc = exc
                if not (isinstance(exc, httpx.HTTPStatusError)
                        and exc.response.status_code in (429, 503)):
                    break
        raise LLMError(f"Gemini API error: {last_exc}") from last_exc


class ExtractiveClient(LLMClient):
    name = "extractive"
    can_chat = False

    def answer(self, prompt: Prompt, max_tokens: int = 1024) -> str:
        lines = ["No LLM is configured, so here are the most relevant parts of the code:", ""]
        for s in prompt.sources[:5]:
            summary = s.docstring.strip().splitlines()[0] if s.docstring.strip() else \
                next((ln.strip() for ln in s.text.splitlines() if ln.strip()), "")
            rel = f" ({s.relation})" if s.relation else ""
            lines.append(f"- `{s.name}`{rel} in {s.path}: {summary[:160]} [{s.n}]")
        return "\n".join(lines)


def _ollama_reachable(url: str) -> bool:
    try:
        r = httpx.get(f"{url.rstrip('/')}/api/tags", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False


def get_llm(cfg: dict) -> LLMClient:
    g = cfg["generation"]
    provider = g.get("provider", "auto")
    if provider == "auto":
        if os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.getenv("GEMINI_API_KEY"):
            provider = "gemini"
        elif _ollama_reachable(g["ollama_url"]):
            provider = "ollama"
            log.info("provider=auto -> using local Ollama server at %s", g["ollama_url"])
        else:
            provider = "extractive"
            log.warning("provider=auto: no ANTHROPIC_API_KEY/GEMINI_API_KEY and no Ollama server "
                        "reachable at %s -> extractive answers only.", g["ollama_url"])
    if provider == "anthropic":
        return AnthropicClient(g["anthropic_model"])
    if provider == "gemini":
        return GeminiClient(g.get("gemini_model", "gemini-flash-latest"))
    if provider == "ollama":
        return OllamaClient(g["ollama_model"], g["ollama_url"])
    if provider == "extractive":
        return ExtractiveClient()
    raise ValueError(f"Unknown LLM provider: {provider}")
