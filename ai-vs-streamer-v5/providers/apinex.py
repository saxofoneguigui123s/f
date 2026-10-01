"""Provedor APInex - gateway de IA com uma key para varios modelos.

Site/painel : https://apinex.bond
Docs        : https://apinex.bond/docs
Base URL    : https://api.apinex.bond/v1
Auth        : Authorization: Bearer sk-apx...   (x-api-key tambem funciona)

Vantagens para o robo:
- endpoint compativel com OpenAI (/chat/completions) -> codigo simples;
- varios modelos (GPT, Claude, Gemini, DeepSeek, GLM, Kimi, Grok) na mesma key;
- modelos gratuitos com prefixo "free/" (ex.: free/gpt-6-luna, free/gemini-3.8-flash);
- ferramentas extras na mesma key: busca web (/tools/web/search), TTS/STT, Twitter/X;
- saldo em dolar unico (/balance).

Atencao ao limite: o plano gratuito permite ~5 requisicoes por minuto por IP e a
assinatura ~30 RPM. Por isso o robo limita as respostas automaticas (ai.max_per_minute).
"""

from __future__ import annotations

from .base import InsufficientBalance, InvalidAPIKey, RateLimited, UpstreamError, default_error
from .openai_compat import OpenAICompatProvider


class APInexProvider(OpenAICompatProvider):
    """Cliente do APInex (OpenAI-compatible) com saldo, catalogo e busca web."""

    name = "apinex"
    label = "APInex"
    default_base_url = "https://api.apinex.bond/v1"
    default_env = ("APINEX_API_KEY", "APINEX_KEY")
    default_model = "free/gpt-6-luna"
    default_models = (
        "free/gpt-6-luna",
        "free/gemini-3.8-flash",
        "free/deepseek-v4.1-flash",
        "free/glm-5.3-flash",
        "free/kimi-k3",
        "free/minimax-m3.1",
        "gpt-5.6-terra",
        "gemini-3.8-flash",
        "deepseek-v4-pro",
        "claude-sonnet-5",
        "kimi-k3",
        "glm-5.3",
    )
    supports_search = True
    supports_balance = True
    dashboard_url = "https://apinex.bond/keys"

    # -- erros com dica em portugues -------------------------------------
    def _error_for(self, status, message, headers, label=None):
        error = default_error(status, message, headers, label or self.name)
        if isinstance(error, InvalidAPIKey):
            error.hint = ("Key ausente/invalida. Crie uma em " + self.dashboard_url +
                          " e defina APINEX_API_KEY (veja .env.example).")
        elif isinstance(error, InsufficientBalance):
            error.hint = ("Saldo APInex insuficiente. Use um modelo 'free/...' "
                          "(ex.: free/gpt-6-luna) ou recarregue em https://apinex.bond")
        elif isinstance(error, RateLimited):
            error.hint = ("Limite de requisicoes do APInex (~5 RPM no gratuito, 30 RPM com "
                          "assinatura). Reduza ai.responses_per_minute no config.json.")
        elif isinstance(error, UpstreamError):
            error.hint = "O APInex ou o modelo falhou: retry automatico ja foi tentado."
        return error

    def missing_key_message(self):
        return ("O provedor APInex esta sem chave de API.\n"
                "  1) Crie uma key em " + self.dashboard_url + "\n"
                "  2) Copie o .env.example para .env e cole: APINEX_API_KEY=sk-apx...\n"
                "     (ou exporte a variavel APINEX_API_KEY no sistema)\n"
                "  3) Rode: python main.py --check")

    # -- recursos exclusivos do APInex -----------------------------------
    def balance(self):
        """Saldo em dolar da conta (GET /balance). None se nao der para consultar."""
        try:
            data = self.client.json_request("GET", "balance")
        except Exception:
            return None
        if isinstance(data, dict):
            for key in ("balance_usd", "balance", "usd", "credits_usd"):
                if key in data and isinstance(data[key], (int, float, str)):
                    try:
                        data["balance_usd"] = float(data[key])
                    except (TypeError, ValueError):
                        pass
                    break
        return data

    def balance_usd(self):
        data = self.balance()
        if isinstance(data, dict):
            value = data.get("balance_usd")
            if isinstance(value, (int, float)):
                return float(value)
        return None

    def models(self, only_free=False, limit=0):
        """Lista os modelos do catalogo (GET /models)."""
        models = self.list_models()
        if only_free:
            models = [model for model in models if str(model).startswith("free/")]
        return models[:limit] if limit else models

    def free_models(self):
        return self.models(only_free=True)

    def search(self, query, count=5):
        """Busca web do APInex (POST /tools/web/search)."""
        data = self.client.json_request(
            "POST", "tools/web/search", {"query": str(query), "count": int(count or 5)}
        )
        return extract_results(data)

    def research(self, query):
        """Pesquisa aprofundada (POST /tools/web/research) - mais lenta, mais completa."""
        data = self.client.json_request("POST", "tools/web/research", {"query": str(query)})
        return data


def extract_results(data):
    """Normaliza a resposta de busca do APInex em uma lista de dicionarios."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("results", "data", "items", "web", "organic"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            for inner in ("results", "items", "data"):
                if isinstance(value.get(inner), list):
                    return [item for item in value[inner] if isinstance(item, dict)]
    return []
