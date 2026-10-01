"""Testes do diagnostico (--check) e das explicacoes que o robo da no console."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from ai_engine import AIEngine  # noqa: E402
from main import check_twitch  # noqa: E402
from providers import OfflineProvider  # noqa: E402
from tests.fake_twitch import FakeTwitchServer, twitch_config  # noqa: E402
from tests.helpers import FakeProvider  # noqa: E402


def build_engine(provider=None, **ai_overrides):
    ai_config = {
        "reply_mode": "mentions", "reply_cooldown": 0, "responses_per_minute": 0,
        "bot_names": ["robô", "robo", "bot", "ia"], "memory_file":
            os.path.join(tempfile.mkdtemp(), "mem.json"),
    }
    ai_config.update(ai_overrides)
    return AIEngine({"provider": "offline", "ai": ai_config},
                    provider=provider or FakeProvider(), logger=lambda *a: None)


class ExplainSkipTests(unittest.TestCase):
    """O robo ficar quieto precisa ter um motivo visivel no console."""

    def test_explica_que_faltou_mencao(self):
        engine = build_engine()
        motivo = engine.explain_skip("ana", "bom dia pessoal")
        self.assertIn("nao citaram o robo", motivo)
        self.assertIn("!pergunta", motivo)

    def test_explica_limite_de_respostas(self):
        engine = build_engine(reply_cooldown=600)
        engine.reply("ana", "oi robô")
        motivo = engine.explain_skip("ana", "fala robô")
        self.assertIn("limite de respostas", motivo)

    def test_explica_respostas_desligadas(self):
        engine = build_engine(reply_enabled=False)
        self.assertIn("desligadas", engine.explain_skip("ana", "oi robô"))

    def test_nao_explica_quando_deveria_responder(self):
        engine = build_engine()
        self.assertEqual(engine.explain_skip("ana", "ei robô"), "")
        self.assertEqual(engine.explain_skip("ana", "!ranking"), "")


class OfflineProviderModeTests(unittest.TestCase):
    """Frase pronta precisa combinar com o modo (antes era sempre troll)."""

    def test_modo_chat_nao_responde_com_frase_de_troll(self):
        provider = OfflineProvider()
        system = ("Voce e o robo do stream.\n- Modo TROLL: atrapalha o streamer.\n"
                  "MODO ATUAL: CHAT.")
        for _ in range(12):
            text = provider.chat([{"role": "system", "content": system},
                                  {"role": "user", "content": "@ana: oi"}]).text
            self.assertNotIn("Dica de ouro", text)

    def test_modo_troll_responde_com_frase_de_troll(self):
        provider = OfflineProvider()
        system = "Regras...\nMODO ATUAL: TROLL."
        respostas = {provider.chat([{"role": "system", "content": system},
                                    {"role": "user", "content": "@ana: oi"}]).text
                     for _ in range(20)}
        self.assertTrue(respostas & set(provider_troll_lines()))


def provider_troll_lines():
    from providers.offline_provider import TROLL_LINES

    return TROLL_LINES


class CheckTwitchTests(unittest.TestCase):
    """O 'python main.py --check' agora diz se o robô consegue mesmo responder."""

    def setUp(self):
        self.server = FakeTwitchServer()
        self.logs = []

    def tearDown(self):
        self.server.stop()

    def log(self, message):
        self.logs.append(str(message))

    def texto(self):
        return "\n".join(self.logs)

    def test_sem_token_avisa_que_nao_responde(self):
        ok = check_twitch({"twitch": twitch_config(self.server.port, oauth="")}, self.log)
        self.assertFalse(ok)
        self.assertIn("MODO ANONIMO", self.texto())
        self.assertIn("twitchtokengenerator.com", self.texto())

    def test_token_invalido_reprova(self):
        ok = check_twitch({"twitch": twitch_config(self.server.port, oauth="oauth:ruim")}, self.log)
        self.assertFalse(ok)
        self.assertIn("FALHA", self.texto())

    def test_token_valido_passa_e_manda_mensagem_de_teste(self):
        ok = check_twitch({"twitch": twitch_config(self.server.port)}, self.log,
                          say="ola chat, teste do robo")
        self.assertTrue(ok, self.texto())
        self.assertIn("token valido", self.texto())
        self.assertEqual(self.server.sent_messages(), ["ola chat, teste do robo"])

    def test_canal_nao_configurado_reprova(self):
        ok = check_twitch({"twitch": twitch_config(self.server.port, channel="")}, self.log)
        self.assertFalse(ok)
        self.assertIn("twitch.channel", self.texto())

    def test_twitch_desligada_nao_e_erro(self):
        ok = check_twitch({"twitch": {"enabled": False}}, self.log)
        self.assertTrue(ok)
        self.assertIn("desligada", self.texto().lower())


if __name__ == "__main__":
    unittest.main()
