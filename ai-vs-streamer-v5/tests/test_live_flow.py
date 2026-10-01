"""Testes do fluxo ao vivo: boas-vindas no chat, !ping e logs de decisao.

Estes cobrem o caso "o --check passa, mas eu nao vejo o robo respondendo":
o console precisa mostrar o que esta acontecendo, e o robo precisa provar
que escreve no chat.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from main import AIvsStreamer, load_config  # noqa: E402
from tests.fake_twitch import FakeTwitchServer, twitch_config  # noqa: E402
from tests.helpers import FakeProvider  # noqa: E402


def wait_for(predicate, timeout=6.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def build_app(config, logger=print):
    """App real (com ChatReader/TwitchChat), so que apontando para o Twitch falso."""
    config = dict(config)
    config["tts"] = dict(config.get("tts") or {}, enabled=False)
    config["voice"] = dict(config.get("voice") or {}, enabled=False)
    return AIvsStreamer(config, simulate=False, use_web=False, logger=logger)


class LiveFlowTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeTwitchServer()
        self.logs = []
        config = load_config(os.path.join(BASE_DIR, "config.json"))
        config["provider"] = "offline"
        config["twitch"] = twitch_config(self.server.port)
        config["twitch"]["startup_message"] = "Robo online! Digite !help."
        config["ai"]["log_chat"] = True
        config["ai"]["reply_cooldown"] = 0        # testes nao podem esbarrar no limite
        config["ai"]["responses_per_minute"] = 0
        config["ai"]["memory_file"] = os.path.join(BASE_DIR, "data", "mem_live.json")
        self.config = config

    def tearDown(self):
        self.server.stop()

    def log(self, message):
        self.logs.append(str(message))

    def texto(self):
        return "\n".join(self.logs)

    def test_manda_boas_vindas_quando_conecta(self):
        app = build_app(self.config, self.log)
        app.ai.provider = FakeProvider("oi!")
        thread = threading.Thread(target=app.run, daemon=True)
        thread.start()
        try:
            self.assertTrue(wait_for(lambda: "Robo online! Digite !help."
                                     in self.server.sent_messages()),
                            f"boas-vindas nao chegaram: {self.server.sent_messages()}")
        finally:
            app.stop()

    def test_loga_mensagem_recebida_e_a_decisao(self):
        app = build_app(self.config, self.log)
        app.ai.provider = FakeProvider("Fala, chat!")
        thread = threading.Thread(target=app.run, daemon=True)
        thread.start()
        try:
            self.assertTrue(wait_for(lambda: app.chat.can_send))
            self.server.say("ana", "ei robô, ta funcionando?")
            self.assertTrue(wait_for(lambda: any("Fala, chat!" in m
                                                 for m in self.server.sent_messages())))
        finally:
            app.stop()
        texto = self.texto()
        self.assertIn("[chat] ana: ei robô, ta funcionando?", texto.lower())
        self.assertIn("[ia] respondi para ana", texto.lower())

    def test_console_explica_quando_nao_responde_por_falta_de_mencao(self):
        app = build_app(self.config, self.log)
        app.ai.provider = FakeProvider("nao deveria aparecer")
        thread = threading.Thread(target=app.run, daemon=True)
        thread.start()
        try:
            self.assertTrue(wait_for(lambda: app.chat.can_send))
            self.server.say("ana", "bom dia pessoal, bora jogar")
            time.sleep(0.6)
        finally:
            app.stop()
        texto = self.texto()
        self.assertIn("[chat] ana: bom dia pessoal, bora jogar", texto.lower())
        self.assertIn("nao citaram o robo", texto)
        self.assertNotIn("nao deveria aparecer", " ".join(self.server.sent_messages()))

    def test_avisa_quando_o_provedor_nao_devolve_texto(self):
        app = build_app(self.config, self.log)

        class ProviderMudo(FakeProvider):
            def chat(self, messages, **kwargs):
                from providers.base import ChatResult

                return ChatResult(text="   ", model="vazio", provider="mudo")

        app.ai.provider = ProviderMudo()
        app.ai.fallback = ProviderMudo()   # nem o plano B devolve texto
        resposta = app.ai.reply("ana", "ei robô")
        self.assertEqual(resposta, "")
        app.handle_message("ana", "ei robô")
        self.assertIn("mas nao saiu texto", self.texto())

    def test_comando_ping_responde_com_estado(self):
        app = build_app(self.config, self.log)
        app.chat.send_message = lambda msg: self.logs.append(f"[ENVIADO] {msg}") or True
        resposta = app.handle_command("ana", "!ping")
        self.assertIn("estou vivo", resposta)
        self.assertIn("provedor=", resposta)

    def test_ping_funciona_mesmo_sem_chave_de_ia(self):
        """!ping e comando de codigo: nao depende do provedor."""
        app = build_app(self.config, self.log)
        app.ai.provider = FakeProvider()          # provedor responde qualquer coisa
        app.chat.send_message = lambda msg: True
        self.assertIn("estou vivo", app.handle_command("ana", "!bot"))
        self.assertIn("estou vivo", app.handle_command("ana", "!status"))


if __name__ == "__main__":
    unittest.main()
