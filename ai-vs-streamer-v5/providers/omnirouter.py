"""Provedor OmniRouter / OmniRoute - um endpoint para varios modelos.

Existem TRES servicos com esse nome, todos compativeis com a API da OpenAI
(/v1/chat/completions). Este provedor funciona com os tres:

1. OmniRoute (open-source, roda na sua maquina)
       base_url: http://localhost:20128/v1
       key:      qualquer coisa (ou nada, se REQUIRE_API_KEY=false)
       modelo:   "oc/deepseek-v4-flash-free"  (OpenCode Free: gratis e keyless)
                 ou "auto" para o gateway escolher sozinho

2. omnirouter.li (SaaS)
       base_url: https://omnirouter.li/v1
       key:      sk_live_...  (variavel OMNI_API_KEY)

3. omnirouter.cc (SaaS)
       base_url: https://omnirouter-api.cc/v1
       key:      Bearer $OMNI_KEY

Configuracao no config.json:

    "provider": "omnirouter",
    "providers": {
        "omnirouter": {
            "base_url": "http://localhost:20128/v1",   // opcional: sem isso, ele detecta
            "api_key_env": "OMNIROUTER_API_KEY",
            "model": "oc/deepseek-v4-flash-free",   // rota gratuita (OpenCode Free)
            "auto_detect": true,     // procura o gateway local antes de usar a nuvem
            "allow_keyless": true,   // aceita gateway local sem key
            "timeout": 60
        }
    }

Variaveis de chave aceitas: OMNIROUTER_API_KEY, OMNI_API_KEY, OMNIROUTE_API_KEY,
OMNI_KEY (a primeira que existir vence).
"""

from __future__ import annotations

from .base import (
    InvalidAPIKey,
    InsufficientBalance,
    RateLimited,
    UpstreamError,
    default_error,
)
from .openai_compat import OpenAICompatProvider


class OmniRouterProvider(OpenAICompatProvider):
    """Cliente do OmniRouter/OmniRoute (OpenAI-compatible, com deteccao do gateway local)."""

    name = "omnirouter"
    label = "OmniRouter"
    default_base_url = "http://localhost:20128/v1"
    default_env = ("OMNIROUTER_API_KEY", "OMNI_API_KEY", "OMNIROUTE_API_KEY", "OMNI_KEY")
    # oc/ = OpenCode Free (rota gratuita e keyless do OmniRoute). Este modelo nao
    # gasta credito nenhum e funciona em instalacao nova, sem configurar provider.
    default_model = "oc/deepseek-v4-flash-free"
    default_models = (
        "oc/deepseek-v4-flash-free",   # OpenCode Free - DeepSeek V4 Flash (gratis)
        "oc/big-pickle",
        "auto",                        # o gateway escolhe sozinho
        "auto/cheap",
        "cc/claude-opus-4-6",
        "gg/gemini-2.5-pro",
        "if/kimi-k2-thinking",
    )
    # gateways que o robo conhece (usados na deteccao automatica, em ordem)
    candidates = (
        ("OmniRoute local", "http://localhost:20128/v1"),
        ("OmniRoute local (127.0.0.1)", "http://127.0.0.1:20128/v1"),
        ("omnirouter.li", "https://omnirouter.li/v1"),
        ("omnirouter.cc", "https://omnirouter-api.cc/v1"),
    )
    dashboard_url = "http://localhost:20128"
    placeholder_key = "omniroute-local"

    def __init__(self, config=None, transport=None, logger=None, **overrides):
        cfg = dict(config or {})
        explicit_base_url = str(cfg.get("base_url") or "").strip()
        self.auto_detect = bool(cfg.get("auto_detect", True))
        self.allow_keyless = bool(cfg.get("allow_keyless", True))
        self.probe_timeout = float(cfg.get("probe_timeout", 1.0))
        self.detected = ""

        if isinstance(cfg.get("candidates"), (list, tuple)) and cfg["candidates"]:
            self.candidates = tuple(
                (item, item) if isinstance(item, str) else tuple(item)
                for item in cfg["candidates"]
            )

        super().__init__(cfg, transport=transport, logger=logger, **overrides)

        if not explicit_base_url and self.auto_detect:
            detected = self.detect_base_url()
            if detected:
                self.base_url = detected
                self.client.base_url = detected.rstrip("/")
                self.detected = detected

    # ------------------------------------------------------------------
    # deteccao do gateway
    # ------------------------------------------------------------------
    def detect_base_url(self):
        """Procura um gateway respondendo. Devolve a URL ou ''.

        401/403 tambem valem: significam que o gateway esta no ar e so pede key.
        """
        for label, url in self.candidates:
            if self._probe(url):
                self._log(f"[omnirouter] gateway encontrado: {label} ({url})")
                return url
        self._log("[omnirouter] nenhum gateway respondeu; usando "
                  f"{self.default_base_url} (ajuste providers.omnirouter.base_url se preciso)")
        return ""

    def _probe(self, base_url):
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.placeholder_key}"}
        try:
            status, _, _ = self.client.transport(
                "GET", f"{base_url.rstrip('/')}/models", None, headers, self.probe_timeout, False
            )
        except Exception:
            return False
        return isinstance(status, int) and 0 < status < 500

    def _log(self, message):
        if self.logger:
            self.logger(message)

    # ------------------------------------------------------------------
    # chave / disponibilidade
    # ------------------------------------------------------------------
    @property
    def is_local(self):
        """True quando o endpoint e a propria maquina/rede (gateway auto-hospedado)."""
        return is_loopback(self.base_url)

    def available(self):
        if self.api_key:
            return True
        # gateway local costuma rodar sem key (REQUIRE_API_KEY=false)
        if self.allow_keyless and self.is_local:
            return True
        return False

    def _headers(self):
        key = self.api_key or (self.placeholder_key if self.is_local else "")
        headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "ai-vs-streamer-v5 (+omnirouter)",
        }
        headers.update(self.extra_headers)
        return headers

    def missing_key_message(self):
        return (
            "O provedor OmniRouter esta sem chave, e o endpoint configurado "
            f"({self.base_url}) nao e local.\n"
            "  - Gateway local (OmniRoute): rode `omniroute` na sua maquina "
            "(API em http://localhost:20128/v1) - normalmente nao precisa de key.\n"
            "  - Servico na nuvem: crie uma key no painel e coloque no .env como\n"
            "    OMNIROUTER_API_KEY=... (tambem aceito: OMNI_API_KEY, OMNIROUTE_API_KEY, OMNI_KEY)\n"
            "  - Para apontar para outro endereco, use "
            "\"providers\": {\"omnirouter\": {\"base_url\": \"https://seu-gateway/v1\"}}"
        )

    # ------------------------------------------------------------------
    # erros com dica
    # ------------------------------------------------------------------
    def _error_for(self, status, message, headers, label=None):
        error = default_error(status, message, headers, label or self.name)
        if isinstance(error, InvalidAPIKey):
            error.hint = ("Key recusada pelo OmniRouter. Confira a key no painel do gateway "
                          f"({self.dashboard_url}) e a variavel OMNIROUTER_API_KEY/OMNI_API_KEY.")
        elif isinstance(error, InsufficientBalance):
            error.hint = ("Saldo/creditos acabaram no OmniRouter. Recarregue no painel "
                          f"({self.dashboard_url}) ou troque de modelo (ex.: \"auto\").")
        elif isinstance(error, RateLimited):
            error.hint = ("Limite de requisicoes do gateway. Reduza "
                          "ai.responses_per_minute ou use outro modelo no painel.")
        elif isinstance(error, UpstreamError):
            error.hint = ("O OmniRouter nao conseguiu responder. Se for o gateway local, "
                          "veja se ele ainda esta rodando (painel: " + self.dashboard_url + ").")
        return error

    # ------------------------------------------------------------------
    # status
    # ------------------------------------------------------------------
    def status(self):
        info = super().status()
        info.update({
            "base_url": self.base_url,
            "detected": self.detected or None,
            "local": self.is_local,
            "keyless": not bool(self.api_key) and self.available(),
        })
        return info

    # ------------------------------------------------------------------
    # validacao do modelo (o gateway tem catalogo em /models)
    # ------------------------------------------------------------------
    def validate_model(self, model=None):
        """Confere se o modelo configurado existe no catalogo do gateway.

        Devolve {"ok": bool|None, "model": str, "catalog_size": int,
        "suggestions": [...], "examples": [...]}. ok=None quando o gateway nao
        expoe /models (nao da para saber).
        """
        model = (model or self.model or "").strip()
        catalogo = self.list_models(fallback=False)   # so o catalogo do gateway
        if not catalogo:
            return {"ok": None, "model": model, "catalog_size": 0,
                    "suggestions": [], "examples": []}

        if model in catalogo:
            return {"ok": True, "model": model, "catalog_size": len(catalogo),
                    "suggestions": [], "examples": []}

        import difflib

        sugestoes = difflib.get_close_matches(model, catalogo, n=3, cutoff=0.55)
        if not sugestoes:
            base = model.split("/")[-1]
            sugestoes = [item for item in catalogo if base and base in item][:3]
        if not sugestoes:
            sugestoes = [item for item in catalogo if str(item).startswith("oc/")][:3]
        exemplos = [item for item in catalogo if str(item).startswith("oc/")][:5] or catalogo[:5]
        return {"ok": False, "model": model, "catalog_size": len(catalogo),
                "suggestions": sugestoes, "examples": exemplos}

    def explain(self):
        """Texto curto de como o provedor esta configurado (usado no --check)."""
        if self.api_key:
            origem = "chave configurada"
        elif self.is_local and self.allow_keyless:
            origem = "gateway local sem chave"
        else:
            origem = "SEM CHAVE"
        deteccao = "" if self.detected == self.base_url else (
            f" (detectado: {self.detected})" if self.detected else "")
        return f"{self.base_url} ({origem}){deteccao}"


def is_loopback(address):
    """Diz se um endereco aponta para a propria maquina ou para a rede local.

    Gateways auto-hospedados (OmniRoute em http://localhost:20128/v1) normalmente
    dispensam chave - so nesses enderecos o robo aceita rodar sem key.
    """
    from urllib.parse import urlparse

    host = (urlparse(str(address)).hostname or "").lower()
    if not host:
        return False
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "[::1]"):
        return True
    if host.endswith(".local"):
        return True
    return host.startswith("192.168.") or host.startswith("10.")
