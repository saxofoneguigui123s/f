"""Testes do provedor APInex (e do cliente HTTP) - rodam sem internet."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers import (  # noqa: E402
    APInexProvider,
    InsufficientBalance,
    InvalidAPIKey,
    RateLimited,
    build_provider,
    provider_config,
    provider_info,
    resolve_api_key,
)
from providers.http_client import parse_sse_lines  # noqa: E402
from tests.helpers import FakeTransport, completion, json_body  # noqa: E402


class APInexProviderTests(unittest.TestCase):
    def setUp(self):
        self.old_env = dict(os.environ)
        os.environ["APINEX_API_KEY"] = "sk-apx_teste_123"
        self.transport = FakeTransport([])
        self.provider = APInexProvider(
            {"base_url": "https://api.apinex.bond/v1", "model": "free/gpt-6-luna",
             "max_retries": 0, "timeout": 5},
            transport=self.transport,
        )

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    # -- identidade / configuracao ---------------------------------------
    def test_defaults_do_apinex(self):
        provider = APInexProvider()
        self.assertEqual(provider.name, "apinex")
        self.assertEqual(provider.default_base_url, "https://api.apinex.bond/v1")
        self.assertEqual(provider.default_model, "free/gpt-6-luna")
        self.assertIn("APINEX_API_KEY", provider.default_env)
        self.assertTrue(provider.supports_search)
        self.assertTrue(provider.supports_balance)

    def test_atalhos_do_topo_so_valem_para_o_provedor_escolhido(self):
        config = {"provider": "apinex", "model": "meu/modelo", "api_key_env": "MINHA_KEY",
                  "providers": {"openai": {"model": "gpt-4o-mini"}}}
        self.assertEqual(provider_config(config, "apinex")["model"], "meu/modelo")
        self.assertEqual(provider_config(config, "openai")["model"], "gpt-4o-mini")
        info = provider_info(config, "apinex")
        self.assertEqual(info["model"], "meu/modelo")
        self.assertEqual(info["base_url"], "https://api.apinex.bond/v1")

    def test_chave_vem_da_variavel_de_ambiente(self):
        self.assertTrue(self.provider.available())
        self.assertEqual(self.provider.api_key, "sk-apx_teste_123")

    def test_chave_pode_estar_no_proprio_config(self):
        provider = APInexProvider({"api_key": "sk-apx_do_config"})
        self.assertEqual(provider.api_key, "sk-apx_do_config")

    def test_sem_chave_fica_indisponivel_com_mensagem_util(self):
        os.environ.pop("APINEX_API_KEY", None)
        os.environ.pop("APINEX_KEY", None)
        provider = APInexProvider()
        self.assertFalse(provider.available())
        message = provider.missing_key_message()
        self.assertIn("APINEX_API_KEY", message)
        self.assertIn("apinex.bond", message)

    # -- conversa ---------------------------------------------------------
    def test_chat_monta_pedido_e_le_resposta(self):
        self.transport.responses.append((200, {}, json_body(completion("Ola, chat!"))))
        result = self.provider.chat([{"role": "user", "content": "oi"}])

        self.assertEqual(result.text, "Ola, chat!")
        self.assertEqual(result.usage["total_tokens"], 49)
        call = self.transport.last_call
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], "https://api.apinex.bond/v1/chat/completions")
        self.assertEqual(call["payload"]["model"], "free/gpt-6-luna")
        self.assertEqual(call["headers"]["Authorization"], "Bearer sk-apx_teste_123")

    def test_chat_inclui_temperature_e_max_tokens(self):
        self.transport.responses.append((200, {}, json_body(completion())))
        self.provider.chat([{"role": "user", "content": "oi"}], temperature=0.3, max_tokens=50)
        payload = self.transport.last_call["payload"]
        self.assertEqual(payload["temperature"], 0.3)
        self.assertEqual(payload["max_tokens"], 50)

    def test_resposta_vazia_levanta_erro(self):
        self.transport.responses.append((200, {}, json_body({"choices": []})))
        with self.assertRaises(Exception):
            self.provider.chat([{"role": "user", "content": "oi"}])

    def test_modelo_pode_ser_trocado_em_execucao(self):
        self.transport.responses.append((200, {}, json_body(completion())))
        self.provider.model = "free/gemini-3.8-flash"
        self.provider.chat([{"role": "user", "content": "oi"}])
        self.assertEqual(self.transport.last_call["payload"]["model"], "free/gemini-3.8-flash")

    # -- erros ------------------------------------------------------------
    def test_401_vira_chave_invalida_com_dica(self):
        self.transport.responses.append((401, {}, json_body({"error": {"message": "Invalid key"}})))
        with self.assertRaises(InvalidAPIKey) as ctx:
            self.provider.chat([{"role": "user", "content": "oi"}])
        self.assertIn("apinex.bond", ctx.exception.hint)

    def test_402_vira_saldo_insuficiente(self):
        self.transport.responses.append((402, {}, json_body({"error": {"message": "no balance"}})))
        with self.assertRaises(InsufficientBalance) as ctx:
            self.provider.chat([{"role": "user", "content": "oi"}])
        self.assertIn("free/", ctx.exception.hint)

    def test_429_tenta_de_novo_e_da_certo(self):
        provider = APInexProvider({"max_retries": 2}, transport=self.transport)
        self.transport.responses.extend([
            (429, {"retry-after": "0"}, json_body({"error": {"message": "slow down"}})),
            (200, {}, json_body(completion("Depois do retry!"))),
        ])
        result = provider.chat([{"role": "user", "content": "oi"}])
        self.assertEqual(result.text, "Depois do retry!")
        self.assertEqual(len(self.transport.calls), 2)

    def test_429_sem_retries_levanta_rate_limited(self):
        self.transport.responses.append((429, {}, json_body({"error": {"message": "slow down"}})))
        with self.assertRaises(RateLimited):
            self.provider.chat([{"role": "user", "content": "oi"}])

    def test_503_tenta_de_novo(self):
        provider = APInexProvider({"max_retries": 1}, transport=self.transport)
        self.transport.responses.extend([
            (503, {}, b"<html>indisponivel</html>"),
            (200, {}, json_body(completion("Voltei!"))),
        ])
        self.assertEqual(provider.chat([{"role": "user", "content": "oi"}]).text, "Voltei!")

    # -- streaming --------------------------------------------------------
    def test_stream_le_pedacos_sse(self):
        chunks = [
            b'data: {"choices":[{"delta":{"content":"Oi"}}]}',
            b'',
            b'data: {"choices":[{"delta":{"content":" chat"}}]}',
            b'data: {"choices":[{"delta":{"reasoning_content":"pensando"}}]}',
            b'data: [DONE]',
        ]
        self.transport.responses.append((200, {}, iter(chunks)))
        parts = list(self.provider.chat_stream([{"role": "user", "content": "oi"}]))
        self.assertEqual("".join(parts), "Oi chat")
        self.assertTrue(self.transport.last_call["stream"])

    def test_parse_sse_ignora_linhas_quebradas(self):
        self.assertEqual(list(parse_sse_lines(["lixo", "", ": comentario", "data: 123"])), [])

    # -- ferramentas do APInex -------------------------------------------
    def test_saldo(self):
        self.transport.responses.append((200, {}, json_body({"balance_usd": 4.7312})))
        self.assertAlmostEqual(self.provider.balance_usd(), 4.7312, places=4)

    def test_lista_de_modelos_e_gratuitos(self):
        self.transport.responses.append((200, {}, json_body({"data": [
            {"id": "free/gpt-6-luna"}, {"id": "gpt-5.6-terra"}, {"id": "free/kimi-k3"}]})))
        self.assertEqual(self.provider.free_models(), ["free/gpt-6-luna", "free/kimi-k3"])

    def test_busca_web(self):
        self.transport.responses.append((200, {}, json_body({"results": [
            {"title": "Noticia", "url": "https://exemplo.com", "snippet": "resumo"}]})))
        results = self.provider.search("noticias de ia", count=3)
        self.assertEqual(results[0]["title"], "Noticia")
        call = self.transport.last_call
        self.assertEqual(call["url"], "https://api.apinex.bond/v1/tools/web/search")
        self.assertEqual(call["payload"], {"query": "noticias de ia", "count": 3})

    def test_busca_aceita_formatos_diferentes(self):
        self.transport.responses.append((200, {}, json_body({"data": {"items": [{"title": "a"}]}})))
        self.assertEqual(self.provider.search("x")[0]["title"], "a")

    # -- registro ---------------------------------------------------------
    def test_build_provider_escolhe_apinex(self):
        provider = build_provider({"provider": "apinex"}, transport=self.transport)
        self.assertIsInstance(provider, APInexProvider)

    def test_build_provider_aceita_apelido(self):
        provider = build_provider({"provider": "apx"})
        self.assertEqual(provider.name, "apinex")

    def test_build_provider_desconhecido_levanta_erro(self):
        with self.assertRaises(Exception):
            build_provider({"provider": "nao-existe"})

    def test_resolve_api_key_prioriza_config(self):
        key = resolve_api_key({"api_key": "sk-apx_direto", "api_key_env": "APINEX_API_KEY"},
                             "apinex", ("APINEX_API_KEY",))
        self.assertEqual(key, "sk-apx_direto")


if __name__ == "__main__":
    unittest.main()
