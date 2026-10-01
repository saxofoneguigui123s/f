"""Testes do 'conecta mas nao responde': login, modo anonimo e envio de mensagens.

Usa um servidor IRC de mentira (tests/fake_twitch.py) - nada de internet.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from chat_reader import ChatReader, TwitchChat, looks_like_auth_failure  # noqa: E402
from tests.fake_twitch import FakeTwitchServer, twitch_config  # noqa: E402


def wait_for(predicate, timeout=5.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class TokenValidationTests(unittest.TestCase):
    def test_reconhece_mensagens_de_token_recusado(self):
        self.assertTrue(looks_like_auth_failure("Login authentication failed"))
        self.assertTrue(looks_like_auth_failure("Error logging in"))
        self.assertFalse(looks_like_auth_failure("Bem-vindo ao canal"))

    def test_token_vem_do_ambiente_quando_nao_esta_no_config(self):
        os.environ["TWITCH_OAUTH_TESTE"] = "oauth:do_ambiente"
        try:
            client = TwitchChat({"channel": "canal", "oauth": "", "oauth_env": "TWITCH_OAUTH_TESTE"},
                                logger=lambda *a: None)
            self.assertEqual(client.oauth, "oauth:do_ambiente")
            self.assertFalse(client.anonymous)
        finally:
            os.environ.pop("TWITCH_OAUTH_TESTE", None)

    def test_sem_token_vira_modo_anonimo(self):
        client = TwitchChat({"channel": "canal", "oauth": "", "oauth_env": "VAR_QUE_NAO_EXISTE"},
                            logger=lambda *a: None)
        self.assertTrue(client.anonymous)
        self.assertFalse(client.can_send)


class LoginTests(unittest.TestCase):
    """O bug principal: o robo dizia 'conectada' antes de autenticar de verdade."""

    def setUp(self):
        self.servers = []

    def tearDown(self):
        for server in self.servers:
            server.stop()

    def start_server(self, **kwargs):
        server = FakeTwitchServer(**kwargs)
        self.servers.append(server)
        return server

    def test_token_valido_loga_e_consegue_enviar(self):
        server = self.start_server()
        client = TwitchChat(twitch_config(server.port), logger=lambda *a: None)
        logs = []
        client.logger = logs.append
        client.start()
        self.assertTrue(wait_for(lambda: client.can_send), "nao logou")
        self.assertTrue(client.send("ola chat"))
        self.assertTrue(wait_for(lambda: server.sent_messages() == ["ola chat"]))
        self.assertTrue(client.status()["can_send"])
        client.stop()

    def test_token_invalido_nao_finge_que_conectou(self):
        server = self.start_server()
        client = TwitchChat(twitch_config(server.port, oauth="oauth:token_velho_do_github"),
                            logger=lambda *a: None)
        client.start()
        self.assertTrue(wait_for(lambda: client.auth_failed), "nao detectou o token ruim")
        self.assertFalse(client.logged_in)
        self.assertFalse(client.can_send)
        status = client.status()
        self.assertIn("recusado", status["reason"])
        client.stop()

    def test_token_invalido_avisa_e_cai_para_anonimo(self):
        server = self.start_server()
        logs = []
        client = TwitchChat(twitch_config(server.port, oauth="oauth:ruim"), logger=logs.append)
        client.start()
        self.assertTrue(wait_for(lambda: client.auth_failed))
        self.assertTrue(wait_for(lambda: client.anonymous), "nao caiu para anonimo")
        texto = "\n".join(logs)
        self.assertIn("TOKEN DO TWITCH RECUSADO", texto)
        self.assertIn("twitchtokengenerator.com", texto)   # diz como resolver
        client.stop()

    def test_timeout_de_login_nao_trava_para_sempre(self):
        server = self.start_server(silent=True)     # servidor nunca manda o 001
        client = TwitchChat(twitch_config(server.port, login_timeout=1), logger=lambda *a: None)
        started = time.time()
        try:
            ok, message = client.test_login()
            self.assertFalse(ok)
            self.assertIn("tempo esgotado", message)
            self.assertLess(time.time() - started, 5)
        finally:
            client.stop()

    def test_test_login_com_token_valido(self):
        server = self.start_server()
        client = TwitchChat(twitch_config(server.port), logger=lambda *a: None)
        try:
            ok, message = client.test_login()
            self.assertTrue(ok, message)
            self.assertIn("canal", message)
            self.assertTrue(client.can_send)  # conexao fica aberta para o --say
        finally:
            client.stop()

    def test_test_login_sem_token_explica_o_problema(self):
        server = self.start_server()
        client = TwitchChat(twitch_config(server.port, oauth=""), logger=lambda *a: None)
        try:
            ok, message = client.test_login()
            self.assertFalse(ok)
            self.assertIn("anonimo", message)
        finally:
            client.stop()

    def test_linha_de_comando_nao_e_tratada_como_mensagem(self):
        server = self.start_server()
        client = TwitchChat(twitch_config(server.port), logger=lambda *a: None)
        client.start()
        self.assertTrue(wait_for(lambda: client.can_send))
        server.say("ana", "oi robo")
        self.assertTrue(wait_for(lambda: not client.queue.empty()))
        self.assertEqual(client.queue.get(), ("Ana", "oi robo"))
        client.stop()


class SemTokenTests(unittest.TestCase):
    """Referencia do 'conecta mas nao funciona': anonimo le mas nao escreve."""

    def setUp(self):
        self.server = FakeTwitchServer()
        self.logs = []
        self.client = TwitchChat(twitch_config(self.server.port, oauth=""), logger=self.logs.append)

    def tearDown(self):
        self.client.stop()
        self.server.stop()

    def test_anonimo_le_o_chat(self):
        self.client.start()
        self.assertTrue(wait_for(lambda: self.client.connected))
        self.assertTrue(self.client.anonymous)
        self.server.say("ana", "oi gente")
        self.assertTrue(wait_for(lambda: not self.client.queue.empty()))

    def test_anonimo_nao_consegue_enviar_e_explica(self):
        self.client.start()
        self.assertTrue(wait_for(lambda: self.client.connected))
        self.assertFalse(self.client.send("oi chat"))
        texto = "\n".join(self.logs)
        self.assertIn("NAO ENVIEI", texto)
        self.assertIn("sem token", texto)
        self.assertIn("twitchtokengenerator.com", texto)

    def test_aviso_de_anonimo_aparece_na_conexao(self):
        self.client.start()
        self.assertTrue(wait_for(lambda: self.client.connected))
        texto = "\n".join(self.logs)
        self.assertIn("SEM TOKEN", texto)
        self.assertIn("NAO consegue ESCREVER", texto)


class StopTests(unittest.TestCase):
    """O stop() tinha que destravar o recv (antes ficava pendurado)."""

    def test_stop_nao_fica_pendurado(self):
        server = FakeTwitchServer()
        client = TwitchChat(twitch_config(server.port), logger=lambda *a: None)
        client.start()
        self.assertTrue(wait_for(lambda: client.connected))
        done = threading.Event()

        def parar():
            client.stop()
            done.set()

        threading.Thread(target=parar, daemon=True).start()
        self.assertTrue(done.wait(3), "stop() travou")
        server.stop()


class ChatReaderTests2(unittest.TestCase):
    """A fachada usada pelo main.py precisa refletir o estado real."""

    def setUp(self):
        self.server = FakeTwitchServer()

    def tearDown(self):
        self.server.stop()

    def test_status_mostra_que_nao_pode_responder(self):
        reader = ChatReader({"twitch": twitch_config(self.server.port, oauth="")},
                            logger=lambda *a: None)
        reader.start()
        self.assertTrue(wait_for(lambda: reader.twitch.connected))
        status = reader.status()
        self.assertTrue(status["twitch"]["anonymous"])
        self.assertFalse(status["can_send"])
        reader.stop()

    def test_status_mostra_que_pode_responder(self):
        reader = ChatReader({"twitch": twitch_config(self.server.port)}, logger=lambda *a: None)
        reader.start()
        self.assertTrue(wait_for(lambda: reader.can_send))
        self.assertTrue(reader.status()["can_send"])
        self.assertTrue(reader.send_message("teste"))
        reader.stop()


if __name__ == "__main__":
    unittest.main()
