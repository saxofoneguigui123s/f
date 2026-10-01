"""Testes do provedor OmniRouter/OmniRoute (sem internet)."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers import OmniRouterProvider, build_provider, normalize_name  # noqa: E402
from providers.omnirouter import is_loopback  # noqa: E402
from tests.helpers import FakeTransport, completion, json_body  # noqa: E402

LOCAL = "http://localhost:20128/v1"


def build(responses=None, config=None, **overrides):
    """Cria o provedor com transporte falso (a deteccao usa o mesmo transporte)."""
    transport = FakeTransport(list(responses or []))
    cfg = {"auto_detect": False, "max_retries": 0}
    cfg.update(config or {})
    provider = OmniRouterProvider(cfg, transport=transport, **overrides)
    provider.transport = transport  # conveniencia nos testes
    return provider, transport


class RegistryTests(unittest.TestCase):
    def test_esta_no_registro(self):
        from providers import PROVIDER_NAMES

        self.assertIn("omnirouter", PROVIDER_NAMES)

    def test_aceita_apelidos(self):
        for apelido in ("omniroute", "omni", "omni-router", "omnirouter.li",
                        "omnirouter.cc", "OMNIROUTER", "OMNIROUTE"):
            self.assertEqual(normalize_name(apelido), "omnirouter", apelido)

    def test_build_provider_cria_omnirouter(self):
        provider = build_provider({"provider": "omnirouter",
                                   "providers": {"omnirouter": {"auto_detect": False}}})
        self.assertIsInstance(provider, OmniRouterProvider)

    def test_auto_continua_sendo_uma_opcao(self):
        """O gateway ainda aceita "auto"; o padrao agora e a rota gratuita."""
        provider = build_provider({"provider": "omnirouter",
                                   "providers": {"omnirouter": {"auto_detect": False,
                                                                "model": "auto"}}})
        self.assertEqual(provider.model, "auto")
        self.assertIn("auto", OmniRouterProvider.default_models)

    def test_mesmo_provedor_atende_gateway_local_e_saas(self):
        """Os tres servicos falam OpenAI: muda so a base_url."""
        local = OmniRouterProvider({"base_url": LOCAL, "auto_detect": False})
        nuvem_li = OmniRouterProvider({"base_url": "https://omnirouter.li/v1",
                                       "auto_detect": False})
        nuvem_cc = OmniRouterProvider({"base_url": "https://omnirouter-api.cc/v1",
                                       "auto_detect": False})
        self.assertTrue(local.is_local)
        self.assertFalse(nuvem_li.is_local)
        self.assertFalse(nuvem_cc.is_local)


class DetectionTests(unittest.TestCase):
    """Sem base_url, o robo procura o gateway local primeiro."""

    def setUp(self):
        self.salvo = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.salvo)

    def test_detecta_o_gateway_local(self):
        provider, transport = build(
            responses=[(200, {}, json_body({"data": [{"id": "auto"}]}))],
            config={"auto_detect": True, "base_url": ""},
        )
        self.assertEqual(provider.base_url, LOCAL)
        self.assertEqual(provider.detected, LOCAL)
        self.assertIn("/models", transport.last_call["url"])

    def test_401_ainda_conta_como_gateway_encontrado(self):
        """Gateway com REQUIRE_API_KEY=true responde 401 - esta no ar do mesmo jeito."""
        provider, _ = build(
            responses=[(401, {}, json_body({"error": {"message": "chave obrigatoria"}}))],
            config={"auto_detect": True, "base_url": ""},
        )
        self.assertEqual(provider.base_url, LOCAL)

    def test_cai_para_a_nuvem_quando_nao_ha_gateway_local(self):
        def recusar_local(*args, **kwargs):
            raise ConnectionError("nada escutando em localhost:20128")

        transport = FakeTransport([
            (200, {}, json_body({"data": [{"id": "auto"}]})),
        ])
        original = transport.__call__

        def transporte(method, url, payload, headers, timeout, stream=False):
            if "20128" in url:
                raise ConnectionError("recusado")
            return original(method, url, payload, headers, timeout, stream)

        provider = OmniRouterProvider(
            {"auto_detect": True, "base_url": "", "probe_timeout": 0.01},
            transport=transporte,
        )
        self.assertEqual(provider.base_url, "https://omnirouter.li/v1")
        self.assertTrue(recusar_local)

    def test_deteccao_pode_ser_desligada(self):
        provider, transport = build(config={"auto_detect": False, "base_url": ""})
        self.assertEqual(provider.base_url, LOCAL)      # padrao, sem sondar ninguem
        self.assertEqual(transport.calls, [])

    def test_base_url_explicita_nao_e_sobrescrita(self):
        provider, transport = build(
            config={"auto_detect": True, "base_url": "https://meu-gateway.exemplo/v1"})
        self.assertEqual(provider.base_url, "https://meu-gateway.exemplo/v1")
        self.assertEqual(transport.calls, [])           # nem tenta detectar

    def test_lista_de_candidatos_personalizada(self):
        provider, _ = build(
            responses=[(200, {}, json_body({"data": []}))],
            config={"auto_detect": True, "base_url": "",
                    "candidates": [["meu gateway", "http://127.0.0.1:9999/v1"]]},
        )
        self.assertEqual(provider.base_url, "http://127.0.0.1:9999/v1")

    def test_is_loopback(self):
        self.assertTrue(is_loopback("http://localhost:20128/v1"))
        self.assertTrue(is_loopback("http://127.0.0.1:20128/v1"))
        self.assertTrue(is_loopback("http://192.168.0.10:20128/v1"))
        self.assertFalse(is_loopback("https://omnirouter.li/v1"))


class KeyTests(unittest.TestCase):
    def setUp(self):
        self.salvo = dict(os.environ)
        for nome in ("OMNIROUTER_API_KEY", "OMNI_API_KEY", "OMNIROUTE_API_KEY", "OMNI_KEY"):
            os.environ.pop(nome, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.salvo)

    def test_gateway_local_funciona_sem_chave(self):
        provider = OmniRouterProvider({"base_url": LOCAL, "auto_detect": False})
        self.assertTrue(provider.available())
        self.assertFalse(provider.api_key)
        self.assertIn("Bearer omniroute-local", provider._headers()["Authorization"])

    def test_servico_na_nuvem_exige_chave(self):
        provider = OmniRouterProvider({"base_url": "https://omnirouter.li/v1",
                                       "auto_detect": False})
        self.assertFalse(provider.available())
        mensagem = provider.missing_key_message()
        self.assertIn("OMNIROUTER_API_KEY", mensagem)
        self.assertIn("omniroute", mensagem)

    def test_chave_pode_vir_de_qualquer_uma_das_variaveis(self):
        for nome in ("OMNIROUTER_API_KEY", "OMNI_API_KEY", "OMNIROUTE_API_KEY", "OMNI_KEY"):
            os.environ.clear()
            os.environ.update(self.salvo)
            os.environ[nome] = f"sk-{nome.lower()}"
            provider = OmniRouterProvider({"base_url": "https://omnirouter.li/v1",
                                           "auto_detect": False})
            self.assertTrue(provider.available(), nome)
            self.assertEqual(provider.api_key, f"sk-{nome.lower()}")

    def test_chave_do_config_tem_prioridade(self):
        os.environ["OMNIROUTER_API_KEY"] = "sk-do-ambiente"
        provider = OmniRouterProvider({"api_key": "sk-do-config", "auto_detect": False})
        self.assertEqual(provider.api_key, "sk-do-config")

    def test_keyless_pode_ser_desligado(self):
        provider = OmniRouterProvider({"base_url": LOCAL, "auto_detect": False,
                                       "allow_keyless": False})
        self.assertFalse(provider.available())


class ChatTests(unittest.TestCase):
    def setUp(self):
        os.environ["OMNIROUTER_API_KEY"] = "sk-omnirouter-teste"
        self.provider, self.transport = build(config={"base_url": LOCAL})

    def tearDown(self):
        os.environ.pop("OMNIROUTER_API_KEY", None)

    def test_chat_usa_base_url_e_o_modelo_configurado(self):
        self.transport.responses.append((200, {}, json_body(completion("Oi, chat!", model="auto"))))
        result = self.provider.chat([{"role": "user", "content": "oi"}])
        self.assertEqual(result.text, "Oi, chat!")
        call = self.transport.last_call
        self.assertEqual(call["url"], "http://localhost:20128/v1/chat/completions")
        self.assertEqual(call["payload"]["model"], "oc/deepseek-v4-flash-free")
        self.assertEqual(call["headers"]["Authorization"], "Bearer sk-omnirouter-teste")

    def test_modelo_de_rota_especifica(self):
        self.transport.responses.append((200, {}, json_body(completion())))
        self.provider.model = "if/kimi-k2-thinking"
        self.provider.chat([{"role": "user", "content": "oi"}])
        self.assertEqual(self.transport.last_call["payload"]["model"], "if/kimi-k2-thinking")

    def test_lista_de_modelos_do_gateway(self):
        self.transport.responses.append((200, {}, json_body({"data": [
            {"id": "auto"}, {"id": "cc/claude-opus-4-6"}, {"id": "if/kimi-k2-thinking"}]})))
        modelos = self.provider.list_models()
        self.assertIn("cc/claude-opus-4-6", modelos)

    def test_erro_401_traz_dica_do_painel(self):
        from providers import InvalidAPIKey

        self.transport.responses.append((401, {}, json_body({"error": {"message": "invalid key"}})))
        with self.assertRaises(InvalidAPIKey) as ctx:
            self.provider.chat([{"role": "user", "content": "oi"}])
        self.assertIn("20128", ctx.exception.hint)

    def test_429_espera_e_tenta_de_novo(self):
        self.provider.max_retries = 2
        self.provider.client.max_retries = 2
        self.transport.responses.extend([
            (429, {"retry-after": "0"}, json_body({"error": {"message": "slow down"}})),
            (200, {}, json_body(completion("Depois do retry"))),
        ])
        self.assertEqual(self.provider.chat([{"role": "user", "content": "oi"}]).text,
                         "Depois do retry")

    def test_gateway_local_fora_do_ar_da_erro_amigavel(self):
        def sem_conexao(*args, **kwargs):
            raise ConnectionError("connection refused")

        provider = OmniRouterProvider({"base_url": LOCAL, "auto_detect": False,
                                       "max_retries": 0, "api_key": "x"},
                                      transport=sem_conexao)
        with self.assertRaises(Exception) as ctx:
            provider.chat([{"role": "user", "content": "oi"}])
        self.assertIn("omnirouter", str(ctx.exception).lower())

    def test_status_mostra_detalhes(self):
        status = self.provider.status()
        self.assertEqual(status["provider"], "omnirouter")
        self.assertEqual(status["base_url"], LOCAL)
        self.assertTrue(status["local"])
        self.assertFalse(status["keyless"])
        self.assertIn("localhost:20128", self.provider.explain())


class EngineIntegrationTests(unittest.TestCase):
    """O motor de IA precisa conseguir usar o OmniRouter como qualquer provedor."""

    def test_ai_engine_com_omnirouter(self):
        import tempfile

        from ai_engine import AIEngine

        os.environ["OMNIROUTER_API_KEY"] = "sk-teste"
        try:
            provider, transport = build(config={"base_url": LOCAL})
            engine = AIEngine(
                {"provider": "offline", "ai": {"memory_file":
                                               os.path.join(tempfile.mkdtemp(), "m.json")}},
                provider=provider, logger=lambda *a: None,
            )
            transport.responses.append((200, {}, json_body(completion("Olá, chat!"))))
            self.assertEqual(engine.reply("ana", "oi robô"), "Olá, chat!")
            self.assertEqual(engine.status()["provider"], "omnirouter")
        finally:
            os.environ.pop("OMNIROUTER_API_KEY", None)

    def test_trocar_para_omnirouter_em_execucao(self):
        import tempfile

        from ai_engine import AIEngine

        engine = AIEngine(
            {"provider": "offline", "ai": {"memory_file":
                                           os.path.join(tempfile.mkdtemp(), "m.json")}},
            logger=lambda *a: None,
        )
        self.assertEqual(engine.set_provider("omniroute"), "omnirouter")
        self.assertEqual(engine.status()["provider"], "omnirouter")


if __name__ == "__main__":
    unittest.main()


class TrocandoDeProvedorTests(unittest.TestCase):
    """Trocar "provider" no config nao pode herdar modelo/chave do anterior."""

    def test_bloco_do_provedor_vence_o_atalho_do_topo(self):
        from providers import provider_config

        config = {
            "provider": "omnirouter",
            "model": "free/gpt-6-luna",            # atalho que era do APInex
            "api_key_env": "APINEX_API_KEY",
            "providers": {"omnirouter": {"model": "auto",
                                         "api_key_env": "OMNIROUTER_API_KEY",
                                         "base_url": LOCAL}},
        }
        bloco = provider_config(config, "omnirouter")
        self.assertEqual(bloco["model"], "auto")
        self.assertEqual(bloco["api_key_env"], "OMNIROUTER_API_KEY")
        self.assertEqual(bloco["base_url"], LOCAL)

    def test_sem_bloco_o_atalho_do_topo_ainda_vale(self):
        from providers import provider_config

        config = {"provider": "apinex", "model": "meu/modelo", "providers": {}}
        self.assertEqual(provider_config(config, "apinex")["model"], "meu/modelo")

    def test_config_real_nao_contamina_o_omnirouter(self):
        import json
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parent.parent
        config = json.loads((raiz / "config.json").read_text(encoding="utf-8"))
        config["provider"] = "omnirouter"
        provider = build_provider(config)
        self.assertEqual(provider.model, "oc/deepseek-v4-flash-free")
        self.assertIn("OMNIROUTER_API_KEY", provider.default_env)


class StatusTests(unittest.TestCase):
    def test_status_inclui_o_endpoint(self):
        provider, _ = build(config={"base_url": LOCAL})
        engine_status = provider.status()
        self.assertEqual(engine_status["base_url"], LOCAL)

    def test_ai_engine_expoe_o_endpoint(self):
        import tempfile

        from ai_engine import AIEngine

        provider, _ = build(config={"base_url": LOCAL})
        engine = AIEngine({"provider": "offline", "ai": {"memory_file":
                           os.path.join(tempfile.mkdtemp(), "m.json")}},
                          provider=provider, logger=lambda *a: None)
        self.assertEqual(engine.status()["endpoint"], LOCAL)


class ModeloTests(unittest.TestCase):
    """O modelo padrao do OmniRouter e a rota gratuita oc/deepseek-v4-flash-free."""

    def test_modelo_padrao_e_a_rota_gratuita(self):
        self.assertEqual(OmniRouterProvider.default_model, "oc/deepseek-v4-flash-free")
        provider = OmniRouterProvider({"auto_detect": False, "base_url": LOCAL})
        self.assertEqual(provider.model, "oc/deepseek-v4-flash-free")

    def test_config_do_projeto_usa_esse_modelo(self):
        import json
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parent.parent
        config = json.loads((raiz / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["providers"]["omnirouter"]["model"],
                         "oc/deepseek-v4-flash-free")

    def test_pedido_leva_o_id_do_modelo_para_o_gateway(self):
        provider, transport = build(config={"base_url": LOCAL})
        transport.responses.append((200, {}, json_body(completion())))
        provider.chat([{"role": "user", "content": "oi"}])
        self.assertEqual(transport.last_call["payload"]["model"], "oc/deepseek-v4-flash-free")

    def test_aceita_rota_oc_na_lista_de_modelos(self):
        provider, transport = build(config={"base_url": LOCAL})
        transport.responses.append((200, {}, json_body({"data": [
            {"id": "oc/deepseek-v4-flash-free"}, {"id": "auto"}]})))
        self.assertIn("oc/deepseek-v4-flash-free", provider.list_models())


class ValidateModelTests(unittest.TestCase):
    """Validacao contra o catalogo do gateway (o que o --check mostra)."""

    def test_modelo_existe_no_catalogo(self):
        provider, transport = build(config={"base_url": LOCAL})
        transport.responses.append((200, {}, json_body({"data": [
            {"id": "oc/deepseek-v4-flash-free"}, {"id": "auto"}]})))
        resultado = provider.validate_model()
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["catalog_size"], 2)

    def test_modelo_com_erro_de_digitacao_sugere_parecidos(self):
        provider, transport = build(config={"base_url": LOCAL, "model": ""})
        transport.responses.append((200, {}, json_body({"data": [
            {"id": "oc/deepseek-v4-flash-free"}, {"id": "oc/big-pickle"}, {"id": "auto"}]})))
        resultado = provider.validate_model("oc/deepseek-v4-flash")
        self.assertFalse(resultado["ok"])
        self.assertIn("oc/deepseek-v4-flash-free", resultado["suggestions"])
        self.assertIn("oc/big-pickle", resultado["examples"])

    def test_modelo_desconhecido_mostra_exemplos_gratuitos(self):
        provider, transport = build(config={"base_url": LOCAL, "model": ""})
        transport.responses.append((200, {}, json_body({"data": [
            {"id": "oc/deepseek-v4-flash-free"}, {"id": "zz/coisa"}]})))
        resultado = provider.validate_model("modelo/inexistente")
        self.assertFalse(resultado["ok"])
        self.assertTrue(resultado["examples"])
        self.assertTrue(all(e.startswith("oc/") for e in resultado["examples"]))

    def test_gateway_sem_catalogo_nao_afirma_nem_nega(self):
        provider, transport = build(config={"base_url": LOCAL})
        transport.responses.append((500, {}, json_body({"error": {"message": "sem catalogo"}})))
        self.assertIsNone(provider.validate_model()["ok"])

    def test_check_do_projeto_avisa_quando_o_modelo_nao_existe(self):
        """--check precisa apontar o problema e sugerir o id certo."""
        import json
        import pathlib

        from tests.fake_omniroute import CATALOG

        self.assertIn("oc/deepseek-v4-flash-free", CATALOG)
        raiz = pathlib.Path(__file__).resolve().parent.parent
        config = json.loads((raiz / "config.json").read_text(encoding="utf-8"))
        prove = config["providers"]["omnirouter"]["model"]
        self.assertEqual(prove, "oc/deepseek-v4-flash-free")
