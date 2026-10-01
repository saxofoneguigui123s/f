"""Provedor OpenAI (oficial) - tambem serve para qualquer API OpenAI-compatible.

Para usar outros gateways basta copiar este arquivo (ou criar um bloco
"providers.meu_gateway" no config.json) mudando base_url e a variavel da key.
"""

from __future__ import annotations

from .openai_compat import OpenAICompatProvider


class OpenAIProvider(OpenAICompatProvider):
    name = "openai"
    label = "OpenAI"
    default_base_url = "https://api.openai.com/v1"
    default_env = ("OPENAI_API_KEY",)
    default_model = "gpt-4o-mini"
    default_models = ("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "o4-mini")
