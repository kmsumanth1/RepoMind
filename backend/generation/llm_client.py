"""LLM back-ends behind one tiny interface.

anthropic  - Claude via the Anthropic API (needs ANTHROPIC_API_KEY)
ollama     - local models (Llama / Mistral / Qwen ...) via an Ollama server
extractive - no LLM at all: returns the top retrieved code with citations (offline dev / tests)
"""
from __future__ import annotations

import logging
import os

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


def get_llm(cfg: dict) -> LLMClient:
    g = cfg["generation"]
    provider = g.get("provider", "auto")
    if provider == "auto":
        provider = "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "extractive"
        if provider == "extractive":
            log.warning("No ANTHROPIC_API_KEY and provider=auto -> extractive answers only.")
    if provider == "anthropic":
        return AnthropicClient(g["anthropic_model"])
    if provider == "ollama":
        return OllamaClient(g["ollama_model"], g["ollama_url"])
    if provider == "extractive":
        return ExtractiveClient()
    raise ValueError(f"Unknown LLM provider: {provider}")
