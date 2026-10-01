"""Cliente HTTP com retry/backoff usado por todos os provedores.

O transporte e injetavel (`transport=`) para os testes rodarem sem internet.
Assinatura do transporte:
    transport(method, url, payload, headers, timeout, stream)
        -> (status:int, headers:dict, body: bytes | Iterable[bytes])
"""

from __future__ import annotations

import json
import time

from .base import (
    ProviderError,
    UpstreamError,
    backoff_delay,
    default_error,
)

try:  # requests e opcional: existe fallback com a biblioteca padrao
    import requests
except Exception:  # pragma: no cover - ambiente sem requests
    requests = None


def default_transport(method, url, payload, headers, timeout, stream=False):
    """Faz a requisicao de verdade (requests se existir, senao urllib)."""
    if requests is not None:
        response = requests.request(
            method, url, json=payload, headers=headers, timeout=timeout, stream=stream
        )
        if stream:
            return response.status_code, dict(response.headers), response.iter_lines()
        return response.status_code, dict(response.headers), response.content

    import urllib.error
    import urllib.request

    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers or {}), error.read()


def parse_sse_lines(lines):
    """Extrai os pedacos de texto de um stream SSE no formato OpenAI."""
    for raw in lines:
        if raw is None:
            continue
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", "replace")
        line = raw.strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line or line == "[DONE]":
            if line == "[DONE]":
                return
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        for choice in event.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta") or {}
            text = delta.get("content")
            if text is None:
                text = (choice.get("message") or {}).get("content")
            if text:
                yield text


class HTTPClient:
    """Requisicoes JSON com retry automatico em 429 e erros 5xx."""

    def __init__(self, base_url="", *, timeout=30.0, max_retries=3, transport=None,
                 error_factory=None, headers_provider=None, label="", logger=None):
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = float(timeout or 30)
        self.max_retries = max(0, int(max_retries or 0))
        self.transport = transport or default_transport
        self.error_factory = error_factory or default_error
        self.headers_provider = headers_provider or (lambda: {})
        self.label = label
        self.logger = logger
        self.last_headers = {}

    # -- helpers --------------------------------------------------------
    def url(self, path):
        path = str(path or "").lstrip("/")
        return f"{self.base_url}/{path}" if path else self.base_url

    def _log(self, message):
        if self.logger:
            self.logger(message)

    def _network_error(self, error):
        """Converte erro de rede/timeout/SSL em um ProviderError amigavel."""
        name = type(error).__name__
        detail = str(error).strip().splitlines()[0][:200]
        if "SSL" in name.upper() or "SSL" in detail.upper():
            message = (f"nao consegui abrir HTTPS com {self.label} ({name}). "
                       "Proxy, antivirus ou firewall podem estar bloqueando.")
        elif "Timeout" in name or "timed out" in detail.lower():
            message = f"{self.label} demorou demais para responder ({self.timeout:.0f}s)."
        else:
            message = f"falha de conexao com {self.label}: {detail}"
        error_out = UpstreamError(message, provider=self.label)
        error_out.hint = ("Confira sua internet e se o host esta acessivel; "
                          "tente de novo em alguns segundos.")
        return error_out

    def _sleep(self, seconds):
        if seconds and seconds > 0:
            self._log(f"[{self.label}] aguardando {seconds:.1f}s antes de tentar de novo...")
            time.sleep(seconds)

    # -- requisicoes ----------------------------------------------------
    def request(self, method, path, payload=None, headers=None, stream=False, retries=None):
        """Executa a requisicao e devolve (status, headers, body). Levanta ProviderError no fim."""
        url = path if str(path).startswith("http") else self.url(path)
        final_headers = dict(self.headers_provider() or {})
        final_headers.setdefault("Content-Type", "application/json")
        final_headers.update(headers or {})
        max_retries = self.max_retries if retries is None else max(0, int(retries))

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                status, response_headers, body = self.transport(
                    method, url, payload, final_headers, self.timeout, stream
                )
            except ProviderError:
                raise
            except Exception as error:  # rede/DNS/TLS/timeout
                network_error = self._network_error(error)
                last_error = network_error
                if attempt < max_retries:
                    self._sleep(backoff_delay(attempt))
                    continue
                raise network_error from error
            self.last_headers = response_headers or {}
            if status < 400:
                return status, response_headers or {}, body

            message = self._error_message(body)
            error = self.error_factory(status, message, response_headers or {}, self.label)
            last_error = error
            if getattr(error, "retryable", False) and attempt < max_retries:
                delay = backoff_delay(attempt, getattr(error, "retry_after", None))
                self._sleep(delay)
                continue
            raise error
        raise last_error or ProviderError("falha desconhecida", provider=self.label)

    def json_request(self, method, path, payload=None, headers=None, retries=None):
        """Como request(), mas devolve o JSON decodificado."""
        _, _, body = self.request(method, path, payload, headers, stream=False, retries=retries)
        return self.decode_json(body)

    @staticmethod
    def decode_json(body):
        if body is None or body == b"":
            return {}
        if isinstance(body, (bytes, bytearray)):
            body = body.decode("utf-8", "replace")
        if isinstance(body, str):
            try:
                return json.loads(body)
            except ValueError:
                raise ProviderError(f"resposta nao era JSON: {body[:200]!r}") from None
        if isinstance(body, dict):
            return body
        raise ProviderError(f"resposta inesperada: {type(body).__name__}")

    @staticmethod
    def _error_message(body):
        """Tenta extrair a mensagem de erro no padrao OpenAI/Anthropic."""
        if not body:
            return ""
        try:
            if isinstance(body, (bytes, bytearray)):
                body = body.decode("utf-8", "replace")
            data = json.loads(body) if isinstance(body, str) else body
        except ValueError:
            return str(body)[:300]
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("type") or error)[:300]
            if isinstance(error, str):
                return error[:300]
            if data.get("message"):
                return str(data["message"])[:300]
        return str(data)[:300]
