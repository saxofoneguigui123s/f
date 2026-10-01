"""Contrato, erros e utilidades comuns a todos os provedores de IA.

Um "provedor" e a ponte entre o robo (AIEngine) e um servico de IA:
APInex, OpenAI, Gemini, Anthropic ou o modo offline (sem internet).
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field


# --------------------------------------------------------------------------
# Erros
# --------------------------------------------------------------------------
class ProviderError(RuntimeError):
    """Erro generico de um provedor de IA."""

    retryable = False
    hint = ""

    def __init__(self, message, *, provider=None, status=None, retry_after=None, raw=None):
        super().__init__(message)
        self.provider = provider
        self.status = status
        self.retry_after = retry_after
        self.raw = raw


class MissingAPIKey(ProviderError):
    """Nenhuma chave de API foi encontrada no config nem nas variaveis de ambiente."""

    hint = "Crie uma key e coloque em APINEX_API_KEY (ou no .env)."


class InvalidAPIKey(ProviderError):
    """A chave existe mas o provedor recusou (401/403)."""

    hint = "Confira a key e se ela ainda esta ativa no painel do provedor."


class InsufficientBalance(ProviderError):
    """Saldo/cota insuficiente (402)."""

    hint = "Coloque creditos no provedor ou use um modelo gratuito (free/...)."


class RateLimited(ProviderError):
    """Limite de requisicoes por minuto estourado (429)."""

    retryable = True
    hint = "Aguarde alguns segundos ou reduza a frequencia de respostas do robo."


class UpstreamError(ProviderError):
    """Falha temporaria do provedor ou do modelo (500/502/503)."""

    retryable = True
    hint = "Normalmente passa sozinho: o robo tenta de novo com backoff."


class BadRequest(ProviderError):
    """Pedido invalido: modelo errado, parametro errado, etc (400/404/422)."""

    hint = "Confira o nome do modelo (ex.: free/gpt-6-luna) e os parametros no config.json."


class ProviderUnavailable(ProviderError):
    """O provedor nao esta configurado/instalado nesta maquina."""


def default_error(status, message, headers=None, provider=None):
    """Converte um status HTTP do provedor no erro mais especifico possivel."""
    headers = headers or {}
    retry_after = _header(headers, "retry-after")
    if status in (401, 403):
        return InvalidAPIKey(message or "chave de API invalida", provider=provider, status=status)
    if status == 402:
        return InsufficientBalance(message or "saldo insuficiente", provider=provider, status=status)
    if status == 429:
        delay = None
        try:
            delay = float(retry_after)
        except (TypeError, ValueError):
            delay = None
        return RateLimited(message or "limite de requisicoes atingido", provider=provider,
                           status=status, retry_after=delay)
    if status in (400, 404, 405, 422):
        return BadRequest(message or "pedido invalido", provider=provider, status=status)
    if status >= 500:
        return UpstreamError(message or "falha temporaria do provedor", provider=provider, status=status)
    return ProviderError(message or f"erro HTTP {status}", provider=provider, status=status)


# --------------------------------------------------------------------------
# Resultado de uma conversa
# --------------------------------------------------------------------------
@dataclass
class ChatResult:
    """Resposta normalizada de qualquer provedor."""

    text: str
    model: str = ""
    provider: str = ""
    usage: dict = field(default_factory=dict)
    finish_reason: str = ""
    raw: dict = field(default_factory=dict)

    def __str__(self):  # pragma: no cover - conveniencia
        return self.text


# --------------------------------------------------------------------------
# Classe base
# --------------------------------------------------------------------------
class BaseProvider:
    """Interface minima que todo provedor precisa implementar."""

    name = "base"
    label = "Base"
    default_base_url = ""
    default_model = ""
    default_env = ()
    default_models = ()
    supports_search = False
    supports_balance = False

    def __init__(self, config=None, transport=None, logger=None):
        self.config = dict(config or {})
        self.transport = transport
        self.logger = logger
        self.last_error = None
        self.model = self.config.get("model") or self.default_model

    # -- estado ---------------------------------------------------------
    def available(self):
        """True quando da para usar o provedor agora (ex.: tem chave)."""
        return True

    def missing_key_message(self):
        envs = ", ".join(self.default_env) or "(nenhuma)"
        return (f"Nenhuma chave configurada para o provedor '{self.name}'. "
                f"Defina uma destas variaveis de ambiente: {envs} - ou use \"api_key\" no config.json.")

    def status(self):
        """Dicionario com o estado do provedor (usado no painel/CLI)."""
        return {
            "provider": self.name,
            "label": self.label,
            "model": self.default_model,
            "available": self.available(),
            "supports_search": self.supports_search,
        }

    # -- conversa -------------------------------------------------------
    def chat(self, messages, **kwargs):  # pragma: no cover - interface
        raise NotImplementedError

    def chat_stream(self, messages, **kwargs):  # pragma: no cover - interface
        raise NotImplementedError

    def list_models(self):
        return list(self.default_models)

    def search(self, query, count=5):  # pragma: no cover - opcional
        raise ProviderUnavailable(f"o provedor '{self.name}' nao tem busca web", provider=self.name)

    def close(self):
        pass


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def _header(headers, name):
    """Le um header sem depender de maiusculas/minusculas."""
    name = name.lower()
    for key, value in (headers or {}).items():
        if str(key).lower() == name:
            return value
    return None


def coerce_text(content):
    """Aceita string, lista de partes (OpenAI/Gemini) ou None e devolve texto."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, (int, float)):
        return str(content)
    if isinstance(content, dict):
        for key in ("text", "content", "value"):
            if key in content:
                return coerce_text(content[key])
        return ""
    if isinstance(content, (list, tuple)):
        parts = []
        for item in content:
            text = coerce_text(item)
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    return str(content).strip()


def resolve_secret(value):
    """Resolve \"env:MINHA_VAR\" e \"${MINHA_VAR}\" para o valor da variavel."""
    if not value:
        return ""
    value = str(value).strip()
    if value.startswith("env:"):
        return os.environ.get(value[4:].strip(), "")
    if value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1].strip(), "")
    return value


def resolve_api_key(config, provider_name="", env_names=(), extra_candidates=()):
    """Descobre a chave de API em: config -> api_key_env -> variaveis padrao.

    Retorna a string da chave ou "" quando nao existe.
    """
    config = config or {}
    candidates = []

    if config.get("api_key"):
        candidates.append(("config.json: api_key", resolve_secret(config["api_key"])))

    env_name = config.get("api_key_env")
    if env_name:
        candidates.append((f"env {env_name}", os.environ.get(str(env_name).strip(), "")))

    for name in list(extra_candidates) + list(env_names):
        if name:
            candidates.append((f"env {name}", os.environ.get(str(name).strip(), "")))

    for source, value in candidates:
        value = resolve_secret(value)
        if value:
            return value.strip()
    return ""


def backoff_delay(attempt, retry_after=None, base=1.5, cap=30.0):
    """Espera exponencial com jitter, respeitando o header Retry-After."""
    if retry_after:
        try:
            return max(0.0, min(float(retry_after), cap))
        except (TypeError, ValueError):
            pass
    delay = min(cap, base * (2 ** max(0, attempt)))
    return delay * (0.75 + random.random() * 0.5)


class RateLimiter:
    """Porteiro simples: no maximo N chamadas por minuto e intervalo minimo entre elas."""

    def __init__(self, max_per_minute=0, min_interval=0.0):
        self.max_per_minute = int(max_per_minute or 0)
        self.min_interval = float(min_interval or 0.0)
        self._calls = []
        self._last = float("-inf")

    def allow(self, now=None):
        now = time.monotonic() if now is None else now
        if self.min_interval and (now - self._last) < self.min_interval:
            return False
        if self.max_per_minute:
            self._calls = [t for t in self._calls if now - t < 60.0]
            if len(self._calls) >= self.max_per_minute:
                return False
        return True

    def allow_rpm(self, now=None):
        """So a cota por minuto (ignora o intervalo minimo entre chamadas)."""
        if not self.max_per_minute:
            return True
        now = time.monotonic() if now is None else now
        calls = [t for t in self._calls if now - t < 60.0]
        return len(calls) < self.max_per_minute

    def register(self, now=None):
        now = time.monotonic() if now is None else now
        self._last = now
        self._calls.append(now)

    def wait_time(self, now=None):
        """Quanto falta (em segundos) para a proxima chamada ser permitida."""
        now = time.monotonic() if now is None else now
        waits = []
        if self.min_interval and (now - self._last) < self.min_interval:
            waits.append(self.min_interval - (now - self._last))
        if self.max_per_minute:
            calls = [t for t in self._calls if now - t < 60.0]
            if len(calls) >= self.max_per_minute:
                waits.append(60.0 - (now - min(calls)))
        return max(waits) if waits else 0.0
