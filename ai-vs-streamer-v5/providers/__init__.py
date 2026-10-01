"""Registro de provedores de IA do AI vs Streamer.

Uso:
    from providers import build_provider, PROVIDER_NAMES

    provider = build_provider(CONFIG)          # usa CONFIG["provider"]
    provider = build_provider(CONFIG, "apinex")  # forca o APInex

Provedores inclusos:
    apinex     -> gateway com varios modelos numa key (padrao do projeto)
    openai     -> API oficial da OpenAI
    gemini     -> Google Gemini
    anthropic  -> Claude
    offline    -> frases prontas (sem internet/chave)
"""

from __future__ import annotations

import os

from .base import (
    BadRequest,
    BaseProvider,
    ChatResult,
    InsufficientBalance,
    InvalidAPIKey,
    MissingAPIKey,
    ProviderError,
    ProviderUnavailable,
    RateLimited,
    RateLimiter,
    UpstreamError,
    backoff_delay,
    coerce_text,
    default_error,
    resolve_api_key,
    resolve_secret,
)

from .apinex import APInexProvider, extract_results
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider
from .anthropic_provider import AnthropicProvider
from .offline_provider import OfflineProvider

# Ordem importa apenas para a listagem na CLI/README.
PROVIDERS = {
    APInexProvider.name: APInexProvider,
    OpenAIProvider.name: OpenAIProvider,
    GeminiProvider.name: GeminiProvider,
    AnthropicProvider.name: AnthropicProvider,
    OfflineProvider.name: OfflineProvider,
}

PROVIDER_NAMES = tuple(PROVIDERS.keys())

ALIASES = {
    "apx": "apinex",
    "api-nex": "apinex",
    "apinex.bond": "apinex",
    "openai-compatible": "openai",
    "open-ai": "openai",
    "gpt": "openai",
    "google": "gemini",
    "claude": "anthropic",
    "local": "offline",
    "none": "offline",
    "templates": "offline",
}


def load_env(path=".env"):
    """Carrega o .env (se python-dotenv estiver instalado). Silencioso se faltar."""
    try:
        from dotenv import load_dotenv
    except Exception:
        return False
    try:
        load_dotenv(path if os.path.exists(path) else None, override=False)
        return True
    except Exception:
        return False


def normalize_name(name):
    """Aceita apelidos ("apx", "claude") e devolve o nome canonico."""
    name = str(name or "").strip().lower()
    return ALIASES.get(name, name)


def provider_config(config, name=None):
    """Junta o bloco providers.<nome> com os atalhos do topo do config.json.

    Exemplo de config:
        "provider": "apinex",
        "model": "free/gpt-6-luna",
        "api_key_env": "APINEX_API_KEY",
        "providers": {"apinex": {"base_url": "...", "max_retries": 3}}
    """
    config = config or {}
    selected = normalize_name(name or config.get("provider") or "apinex")
    name = selected
    block = dict((config.get("providers") or {}).get(name) or {})

    # atalhos no topo do config.json valem so para o provedor principal
    # (assim trocar de provedor nao herda o modelo do APInex, por exemplo)
    if selected == normalize_name(config.get("provider") or "apinex"):
        for key in ("model", "api_key", "api_key_env", "base_url", "temperature", "max_tokens",
                    "timeout", "max_retries", "reasoning_effort"):
            value = config.get(key)
            if value not in (None, ""):
                block[key] = value

    # config["ai"] e usado como padrao quando o bloco nao define
    ai_block = config.get("ai") or {}
    for key in ("temperature", "max_tokens", "timeout", "reasoning_effort"):
        if block.get(key) is None and ai_block.get(key) is not None:
            block.setdefault(key, ai_block[key])

    block["provider_name"] = name
    return block


def build_provider(config, name=None, transport=None, logger=None):
    """Cria a instancia do provedor pedido no config."""
    name = normalize_name(name or (config or {}).get("provider") or "apinex")
    if name not in PROVIDERS:
        raise ProviderUnavailable(
            f"provedor desconhecido: '{name}'. Opcoes: {', '.join(PROVIDER_NAMES)}"
        )
    block = provider_config(config, name)
    provider_class = PROVIDERS[name]
    return provider_class(config=block, transport=transport, logger=logger)


def provider_info(config=None, name=None):
    """Metadados do provedor (sem instanciar) - util para CLI/README."""
    name = normalize_name(name or (config or {}).get("provider") or "apinex")
    provider_class = PROVIDERS.get(name)
    if not provider_class:
        return None
    block = provider_config(config, name) if config else {}
    return {
        "name": name,
        "label": provider_class.label,
        "model": block.get("model") or provider_class.default_model,
        "base_url": block.get("base_url") or provider_class.default_base_url,
        "env": provider_class.default_env,
        "has_key": bool(resolve_api_key(block, name, provider_class.default_env)),
    }


__all__ = [
    "APInexProvider",
    "AnthropicProvider",
    "BaseProvider",
    "BadRequest",
    "ChatResult",
    "GeminiProvider",
    "InsufficientBalance",
    "InvalidAPIKey",
    "MissingAPIKey",
    "OfflineProvider",
    "OpenAIProvider",
    "PROVIDERS",
    "PROVIDER_NAMES",
    "ProviderError",
    "ProviderUnavailable",
    "RateLimited",
    "RateLimiter",
    "UpstreamError",
    "backoff_delay",
    "build_provider",
    "coerce_text",
    "default_error",
    "extract_results",
    "load_env",
    "normalize_name",
    "provider_config",
    "provider_info",
    "resolve_api_key",
    "resolve_secret",
]
