"""Ajudantes dos testes: transporte HTTP falso e provedores de mentira."""

from __future__ import annotations

import json

from providers.base import BaseProvider, ChatResult, ProviderError


def json_body(payload):
    return json.dumps(payload).encode("utf-8")


def completion(text="Oi! Tudo certo por aqui.", model="free/gpt-6-luna", usage=None):
    return {
        "id": "chatcmpl-teste",
        "object": "chat.completion",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                     "finish_reason": "stop"}],
        "usage": usage or {"prompt_tokens": 42, "completion_tokens": 7, "total_tokens": 49},
    }


class FakeTransport:
    """Transporte falso: devolve respostas na ordem e guarda o que foi enviado."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, payload, headers, timeout, stream=False):
        self.calls.append({
            "method": method, "url": url, "payload": payload,
            "headers": dict(headers or {}), "timeout": timeout, "stream": stream,
        })
        if not self.responses:
            raise AssertionError(f"transporte falso sem resposta para {method} {url}")
        status, response_headers, body = self.responses.pop(0)
        if callable(body):
            body = body()
        return status, dict(response_headers or {}), body

    @property
    def last_call(self):
        return self.calls[-1] if self.calls else None


class FakeProvider(BaseProvider):
    """Provedor de mentira que responde sempre a mesma coisa."""

    name = "fake"
    label = "Fake"
    default_model = "fake-1"

    def __init__(self, answer="Resposta de teste, chat!", **kwargs):
        super().__init__(kwargs.get("config"))
        self.answer = answer
        self.received = []

    def available(self):
        return True

    def chat(self, messages, **kwargs):
        self.received.append(list(messages))
        return ChatResult(text=self.answer, model=self.default_model, provider=self.name)


class FailingProvider(BaseProvider):
    """Provedor de mentira que sempre falha (para testar a reserva)."""

    name = "failing"
    label = "Failing"
    default_model = "nada"

    def available(self):
        return True

    def chat(self, messages, **kwargs):
        raise ProviderError("provedor caiu de proposito", provider=self.name)
