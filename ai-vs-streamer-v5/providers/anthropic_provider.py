"""Provedor Anthropic Claude (API Messages, via REST).

Nao depende do SDK: usa /v1/messages direto, entao funciona com qualquer
versao do pacote anthropic instalada (ou nenhuma).
"""

from __future__ import annotations

from .base import BaseProvider, ChatResult, ProviderError, coerce_text, default_error, resolve_api_key
from .http_client import HTTPClient


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    label = "Anthropic Claude"
    default_base_url = "https://api.anthropic.com/v1"
    default_env = ("ANTHROPIC_API_KEY",)
    default_model = "claude-3-5-haiku-latest"
    default_models = ("claude-3-5-haiku-latest", "claude-3-5-sonnet-latest", "claude-sonnet-4-20250514")

    def __init__(self, config=None, transport=None, logger=None, **overrides):
        super().__init__(config, transport)
        cfg = dict(config or {})
        cfg.update({key: value for key, value in overrides.items() if value is not None})

        self.base_url = (cfg.get("base_url") or self.default_base_url).rstrip("/")
        self.model = cfg.get("model") or self.default_model
        self.max_tokens = int(cfg.get("max_tokens") or 300)
        self.temperature = cfg.get("temperature")
        self.api_key_env = cfg.get("api_key_env")
        self.anthropic_version = cfg.get("anthropic_version", "2023-06-01")
        self._api_key = None
        self.client = HTTPClient(
            base_url=self.base_url,
            timeout=float(cfg.get("timeout", 30)),
            max_retries=int(cfg.get("max_retries", 2)),
            transport=transport,
            error_factory=lambda status, message, headers, label=None: default_error(
                status, message, headers, label or self.name),
            headers_provider=self._headers,
            label=self.name,
            logger=logger,
        )

    @property
    def api_key(self):
        if self._api_key is None:
            self._api_key = resolve_api_key(self.config, self.name, self.default_env)
        return self._api_key

    def available(self):
        return bool(self.api_key)

    def missing_key_message(self):
        return ("Provedor Anthropic sem chave. Defina ANTHROPIC_API_KEY no ambiente/.env "
                "ou \"api_key\" no bloco providers.anthropic do config.json.")

    def _headers(self):
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
            "Content-Type": "application/json",
        }

    def _payload(self, messages):
        system_parts = []
        chat_messages = []
        for message in messages:
            role = message.get("role")
            text = coerce_text(message.get("content"))
            if not text:
                continue
            if role == "system":
                system_parts.append(text)
            else:
                chat_messages.append({
                    "role": "assistant" if role == "assistant" else "user",
                    "content": text,
                })
        payload = {"model": self.model, "max_tokens": self.max_tokens, "messages": chat_messages}
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        return payload

    def chat(self, messages, **kwargs):
        data = self.client.json_request("POST", "messages", self._payload(messages))
        blocks = data.get("content") or []
        text = coerce_text(blocks)
        if not text:
            raise ProviderError("Claude respondeu vazio", provider=self.name, raw=data)
        return ChatResult(text=text, model=data.get("model") or self.model, provider=self.name,
                          usage=data.get("usage") or {}, finish_reason=data.get("stop_reason") or "",
                          raw=data)

    def chat_stream(self, messages, **kwargs):  # streaming simples: devolve de uma vez
        result = self.chat(messages, **kwargs)
        if result.text:
            yield result.text
