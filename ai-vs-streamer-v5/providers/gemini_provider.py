"""Provedor Google Gemini (API REST do Google AI Studio).

Usa a API nativa (generateContent) para nao depender da versao do SDK
google-generativeai. A key sai de GEMINI_API_KEY ou GOOGLE_API_KEY.
"""

from __future__ import annotations

from .base import BaseProvider, ChatResult, ProviderError, coerce_text, default_error, resolve_api_key
from .http_client import HTTPClient


class GeminiProvider(BaseProvider):
    name = "gemini"
    label = "Google Gemini"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"
    default_env = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
    default_model = "gemini-2.0-flash"
    default_models = ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro")

    def __init__(self, config=None, transport=None, logger=None, **overrides):
        super().__init__(config, transport)
        cfg = dict(config or {})
        cfg.update({key: value for key, value in overrides.items() if value is not None})

        self.base_url = (cfg.get("base_url") or self.default_base_url).rstrip("/")
        self.model = cfg.get("model") or self.default_model
        self.max_tokens = cfg.get("max_tokens")
        self.temperature = cfg.get("temperature")
        self.api_key_env = cfg.get("api_key_env")
        self._api_key = None
        self.client = HTTPClient(
            base_url=self.base_url,
            timeout=float(cfg.get("timeout", 30)),
            max_retries=int(cfg.get("max_retries", 2)),
            transport=transport,
            error_factory=lambda status, message, headers, label=None: default_error(
                status, message, headers, label or self.name),
            headers_provider=lambda: {"Content-Type": "application/json"},
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
        return ("Provedor Gemini sem chave. Defina GEMINI_API_KEY (ou GOOGLE_API_KEY) "
                "no ambiente/.env, ou coloque \"api_key\" no bloco providers.gemini do config.json.")

    def _payload(self, messages):
        system_parts = []
        contents = []
        for message in messages:
            role = message.get("role")
            text = coerce_text(message.get("content"))
            if not text:
                continue
            if role == "system":
                system_parts.append(text)
            else:
                contents.append({
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": text}],
                })
        payload = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        generation = {}
        if self.temperature is not None:
            generation["temperature"] = self.temperature
        if self.max_tokens:
            generation["maxOutputTokens"] = int(self.max_tokens)
        if generation:
            payload["generationConfig"] = generation
        return payload

    def chat(self, messages, **kwargs):
        path = f"models/{self.model}:generateContent?key={self.api_key}"
        data = self.client.json_request("POST", path, self._payload(messages))
        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderError("Gemini respondeu sem candidatos", provider=self.name, raw=data)
        text = coerce_text((candidates[0].get("content") or {}).get("parts"))
        usage = data.get("usageMetadata") or {}
        return ChatResult(text=text, model=data.get("modelVersion") or self.model,
                          provider=self.name, usage=usage, raw=data)

    def chat_stream(self, messages, **kwargs):  # streaming simples: devolve de uma vez
        result = self.chat(messages, **kwargs)
        if result.text:
            yield result.text
