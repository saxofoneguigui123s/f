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


# nomes de variaveis que o robo entende (usado para achar erros de digitacao)
KNOWN_ENV_NAMES = (
    "APINEX_API_KEY", "APINEX_KEY", "TWITCH_OAUTH", "OPENAI_API_KEY",
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY",
)

# chave -> {"file": nome do arquivo, "value": valor que estava la}
# (preenchido pelo load_env; comparar o valor evita dizer que veio do .env
#  quando na verdade a variavel ja existia no sistema)
_ENV_SOURCES = {}


def env_sources():
    """Copia do registro 'de onde veio cada chave' (usado no --check)."""
    return {key: info["file"] for key, info in _ENV_SOURCES.items()}


def parse_env_file(path):
    """Le um arquivo .env sem depender de nenhuma biblioteca.

    Aceita comentarios (#), linhas em branco, "export CHAVE=valor",
    valores entre aspas e espacos em volta do "=". Ignora linhas invalidas.
    """
    data = {}
    try:
        with open(path, encoding="utf-8-sig") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return data

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            data[key] = value
    return data


def mask_secret(value, keep_start=6, keep_end=4):
    """Esconde o miolo de uma chave, deixando inicio/fim para conferencia."""
    value = str(value or "")
    if not value:
        return "(vazia)"
    if len(value) > keep_start + keep_end:
        return f"{value[:keep_start]}...{value[-keep_end:]}"
    if len(value) >= 4:
        return f"{value[:2]}...{value[-2:]}"
    return value[:1] + "*" * (len(value) - 1)


def _project_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path=".env", logger=None):
    """Carrega as chaves do .env e devolve um relatorio do que encontrou.

    - Procura o arquivo na pasta atual e na pasta do projeto (ai-vs-streamer-v5/).
    - Usa python-dotenv se estiver instalado, mas tem leitor proprio: sem o
      pacote instalado as chaves NAO ficam mais sendo ignoradas em silencio.
    - Nunca sobrescreve variaveis que ja existem no sistema.
    """
    report = {
        "path": None,
        "found": False,
        "keys": [],
        "sources": {},
        "warnings": [],
        "dotenv": False,
        "candidates": [],
    }

    candidates = []
    if path:
        candidates.append(path)
        if not os.path.isabs(path):
            # tambem procura na pasta do projeto e na pasta acima (raiz do repo),
            # porque e comum criar o .env no lugar errado
            candidates.append(os.path.join(_project_dir(), path))
            candidates.append(os.path.join(os.path.dirname(_project_dir()), path))

    checked = []
    target = None
    for candidate in candidates:
        absolute = os.path.abspath(candidate)
        if absolute in checked:
            continue
        checked.append(absolute)
        if os.path.isfile(absolute):
            target = absolute
            break
    report["candidates"] = checked
    report["path"] = target

    if not target:
        report["warnings"].append(
            "nao achei o arquivo .env (procurei em: " + ", ".join(checked) + ")")
        for alt in (" .env.txt", ".env.TXT", "env.txt", ".env.example"):
            alt_path = os.path.abspath(alt.strip())
            if os.path.isfile(alt_path):
                if alt.lower().endswith(".example"):
                    report["warnings"].append(
                        f"existe {os.path.basename(alt_path)} - copie ele para .env e preencha")
                else:
                    report["warnings"].append(
                        f"achei {os.path.basename(alt_path)} - no Windows o Bloco de Notas "
                        f"salva assim; renomeie para .env")
                break
        return report

    # 1) leitor proprio primeiro: garante que as chaves entram mesmo sem o
    #    python-dotenv e registra de onde cada uma veio
    for key, value in parse_env_file(target).items():
        report["keys"].append(key)
        if key in os.environ and os.environ[key]:
            # ja existia: se o valor e igual ao que este .env tem, a origem e o
            # arquivo (o main carrega o .env antes do --check); senao e o sistema
            conhecido = _ENV_SOURCES.get(key)
            mesma_coisa = conhecido and conhecido.get("value") == os.environ[key]
            report["sources"][key] = conhecido["file"] if mesma_coisa else "ambiente"
            continue
        os.environ[key] = value
        _ENV_SOURCES[key] = {"file": os.path.basename(target), "value": value}
        report["sources"][key] = os.path.basename(target)

    # 2) python-dotenv, se existir, para formatos exoticos (nao sobrescreve nada)
    try:
        from dotenv import load_dotenv

        load_dotenv(target, override=False)
        report["dotenv"] = True
    except Exception:
        report["dotenv"] = False

    report["found"] = True
    if report["keys"] and not report["dotenv"]:
        report["warnings"].append(
            "python-dotenv nao esta instalado (usei o leitor interno - funciona igual)")
    placeholders = [key for key in report["keys"]
                    if "coloque_sua" in os.environ.get(key, "").lower()]
    for key in placeholders:
        report["warnings"].append(f"{key} ainda esta com o valor de exemplo do .env.example")

    # nome digitado errado (ex.: APINEX_API= em vez de APINEX_API_KEY)
    import difflib

    for key in report["keys"]:
        if key in KNOWN_ENV_NAMES:
            continue
        parecida = difflib.get_close_matches(key, KNOWN_ENV_NAMES, n=1, cutoff=0.75)
        if parecida:
            report["warnings"].append(
                f"a chave {key} no .env nao e conhecida - quis dizer {parecida[0]}?")
    return report


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
    # e nunca para o 'offline', que nao usa modelo nem chave.
    if selected != "offline" and selected == normalize_name(config.get("provider") or "apinex"):
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
    "KNOWN_ENV_NAMES",
    "env_sources",
    "load_env",
    "mask_secret",
    "normalize_name",
    "parse_env_file",
    "provider_config",
    "provider_info",
    "resolve_api_key",
    "resolve_secret",
]
