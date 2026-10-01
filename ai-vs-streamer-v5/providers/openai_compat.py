"""Cliente base para qualquer endpoint compativel com a API da OpenAI.

Serve para APInex, OpenAI, Groq, DeepSeek, OpenRouter, Ollama, LM Studio...
Basta trocar `base_url`, `model` e a variavel de ambiente da chave.
"""

from __future__ import annotations

from .base import (
    BaseProvider,
    ChatResult,
    ProviderError,
    coerce_text,
    default_error,
    resolve_api_key,
)
from .http_client import HTTPClient, parse_sse_lines


class OpenAICompatProvider(BaseProvider):
    """Provedor generico de /chat/completions (formato OpenAI)."""

    name = "openai_compat"
    label = "OpenAI-compatible"
    default_base_url = "https://api.openai.com/v1"
    default_env = ("OPENAI_API_KEY",)
    default_model = "gpt-4o-mini"
    default_models = ()

    def __init__(self, config=None, transport=None, logger=None, **overrides):
        super().__init__(config, transport)
        cfg = dict(config or {})
        cfg.update({key: value for key, value in overrides.items() if value is not None})

        self.base_url = (cfg.get("base_url") or self.default_base_url).rstrip("/")
        self.model = cfg.get("model") or self.default_model
        self.timeout = float(cfg.get("timeout", 30))
        self.max_retries = int(cfg.get("max_retries", 3))
        self.temperature = cfg.get("temperature")
        self.max_tokens = cfg.get("max_tokens")
        self.reasoning_effort = cfg.get("reasoning_effort")
        self.extra_body = dict(cfg.get("extra_body") or {})
        self.extra_headers = dict(cfg.get("extra_headers") or {})
        self.api_key_env = cfg.get("api_key_env")
        self.logger = logger
        self._api_key = None

        self.client = HTTPClient(
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=self.max_retries,
            transport=transport,
            error_factory=self._error_for,
            headers_provider=self._headers,
            label=self.name,
            logger=logger,
        )

    # -- autenticacao ---------------------------------------------------
    @property
    def api_key(self):
        if self._api_key is None:
            self._api_key = resolve_api_key(
                {**self.config, "api_key_env": self.api_key_env or self.config.get("api_key_env")},
                provider_name=self.name,
                env_names=self.default_env,
            )
        return self._api_key

    def available(self):
        return bool(self.api_key)

    def missing_key_message(self):
        envs = ", ".join(self.default_env) or "(nenhuma)"
        return (f"O provedor '{self.name}' esta sem chave de API.\n"
                f"  1) Crie uma key no painel do provedor\n"
                f"  2) Defina a variavel de ambiente: {envs}\n"
                f"     (ou crie um arquivo .env com a key)\n"
                f"  3) Rode: python main.py --check")

    def _headers(self):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "ai-vs-streamer-v5 (+apinex)",
        }
        headers.update(self.extra_headers)
        return headers

    def _error_for(self, status, message, headers, label=None):
        return default_error(status, message, headers, label or self.name)

    # -- montagem do pedido ----------------------------------------------
    def _build_payload(self, messages, stream=False, **kwargs):
        payload = {"model": kwargs.get("model") or self.model, "messages": list(messages)}
        temperature = kwargs.get("temperature", self.temperature)
        if temperature is not None:
            payload["temperature"] = temperature
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        if max_tokens:
            payload["max_tokens"] = int(max_tokens)
        effort = kwargs.get("reasoning_effort", self.reasoning_effort)
        if effort:
            payload["reasoning_effort"] = effort
        if stream:
            payload["stream"] = True
        payload.update(self.extra_body)
        payload.update(kwargs.get("extra_body") or {})
        return payload

    # -- conversa --------------------------------------------------------
    def chat(self, messages, **kwargs):
        payload = self._build_payload(messages, stream=False, **kwargs)
        data = self.client.json_request("POST", "chat/completions", payload)
        return self._parse_completion(data)

    def chat_stream(self, messages, **kwargs):
        """Gera pedacos de texto conforme chegam (SSE)."""
        payload = self._build_payload(messages, stream=True, **kwargs)
        _, _, body = self.client.request("POST", "chat/completions", payload, stream=True)

        # Sem suporte a stream no transporte: devolve tudo de uma vez.
        if isinstance(body, (bytes, bytearray, str)):
            data = self.client.decode_json(body)
            text = self._parse_completion(data).text
            if text:
                yield text
            return

        for chunk in parse_sse_lines(body):
            if chunk:
                yield chunk

    @staticmethod
    def _parse_completion(data):
        if not isinstance(data, dict):
            raise ProviderError(f"resposta inesperada do provedor: {type(data).__name__}")
        if data.get("error"):
            error = data["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise ProviderError(str(message or "erro do provedor"), raw=data)

        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("o provedor respondeu sem 'choices'", raw=data)

        choice = choices[0] or {}
        message = choice.get("message") or {}
        text = coerce_text(message.get("content"))
        if not text:
            # alguns modelos devolvem o texto direto em 'text'
            text = coerce_text(choice.get("text"))
        return ChatResult(
            text=text,
            model=data.get("model") or "",
            provider=data.get("provider") or "",
            usage=data.get("usage") or {},
            finish_reason=choice.get("finish_reason") or "",
            raw=data,
        )

    # -- catalogo --------------------------------------------------------
    def list_models(self):
        try:
            data = self.client.json_request("GET", "models")
        except ProviderError:
            return list(self.default_models)
        items = data.get("data") if isinstance(data, dict) else data
        if isinstance(items, dict):
            items = items.get("models") or []
        ids = []
        for item in items or []:
            if isinstance(item, dict):
                model_id = item.get("id") or item.get("name") or item.get("model")
            else:
                model_id = str(item)
            if model_id:
                ids.append(model_id)
        return ids or list(self.default_models)

    def close(self):
        session = getattr(self.client, "session", None)
        if session is not None:  # pragma: no cover - so quando usa requests.Session
            session.close()
