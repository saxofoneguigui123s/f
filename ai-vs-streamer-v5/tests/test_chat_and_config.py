"""Testes do leitor de chat (IRC), do config.json e dos comandos do main."""

from __future__ import annotations

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from chat_reader import ChatReader, parse_irc_line, split_message  # noqa: E402
from main import AIvsStreamer, load_config  # noqa: E402
from providers import provider_info  # noqa: E402


class IRCParserTests(unittest.TestCase):
    def test_privmsg_com_tags(self):
        line = ("@badges=subscriber/1;display-name=Ana;login=ana "
                ":ana!ana@ana.tmi.twitch.tv PRIVMSG #guigui123wa :oi robô, tudo bem?")
        kind, user, text = parse_irc_line(line)
        self.assertEqual(kind, "message")
        self.assertEqual(user, "Ana")
        self.assertEqual(text, "oi robô, tudo bem?")

    def test_privmsg_sem_tags(self):
        kind, user, text = parse_irc_line(":bob!bob@bob.tmi.twitch.tv PRIVMSG #canal :!troll")
        self.assertEqual((kind, user, text), ("message", "bob", "!troll"))

    def test_ping(self):
        self.assertEqual(parse_irc_line("PING :tmi.twitch.tv"), ("ping", None, None))

    def test_notice(self):
        kind, _, text = parse_irc_line(":tmi.twitch.tv NOTICE * :Login unsuccessful")
        self.assertEqual(kind, "notice")
        self.assertIn("Login", text)

    def test_linha_irrelevante(self):
        self.assertIsNone(parse_irc_line(":ana!ana@ana.tmi.twitch.tv JOIN #canal"))

    def test_split_de_mensagem_longa(self):
        chunks = split_message("palavra " * 200, limit=100)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 100 for chunk in chunks))


class ChatReaderTests(unittest.TestCase):
    def test_le_mensagens_da_fila(self):
        reader = ChatReader({"twitch": {"enabled": False}}, logger=lambda *a: None)
        reader.feed("ana", "oi")
        reader.feed("bob", "!troll")
        self.assertEqual(reader.read(), [("ana", "oi"), ("bob", "!troll")])
        self.assertEqual(reader.read(), [])

    def test_sem_twitch_so_imprime(self):
        reader = ChatReader({"twitch": {"enabled": False}}, logger=lambda *a: None)
        self.assertTrue(reader.send_message("teste"))
        self.assertEqual(reader.last_sent, ["teste"])
        self.assertFalse(reader.status()["twitch"]["enabled"])


class ConfigTests(unittest.TestCase):
    def test_config_json_valido(self):
        config = load_config(os.path.join(BASE_DIR, "config.json"))
        self.assertEqual(config["provider"], "apinex")
        self.assertEqual(config["providers"]["apinex"]["base_url"], "https://api.apinex.bond/v1")
        self.assertEqual(config["api_key_env"], "APINEX_API_KEY")
        self.assertIn("ai", config)

    def test_token_do_twitch_nao_esta_no_config(self):
        """O token antigo ficou publico no GitHub: deve vir do ambiente/.env."""
        config = load_config(os.path.join(BASE_DIR, "config.json"))
        self.assertEqual(config["twitch"]["oauth"], "")
        self.assertEqual(config["twitch"]["oauth_env"], "TWITCH_OAUTH")

    def test_info_do_provedor_apinex(self):
        config = load_config(os.path.join(BASE_DIR, "config.json"))
        info = provider_info(config, "apinex")
        self.assertEqual(info["name"], "apinex")
        self.assertEqual(info["model"], "free/gpt-6-luna")
        self.assertIn("APINEX_API_KEY", info["env"])


class CommandTests(unittest.TestCase):
    """Testa os comandos do robo com um provedor de mentira (sem rede)."""

    def setUp(self):
        from tests.helpers import FakeProvider

        config = load_config(os.path.join(BASE_DIR, "config.json"))
        config["provider"] = "offline"
        config["twitch"]["enabled"] = False
        config["tts"]["enabled"] = False
        config["voice"]["enabled"] = False
        memory_file = os.path.join(BASE_DIR, "data", "memories_test.json")
        if os.path.exists(memory_file):  # cada teste comeca com a memoria limpa
            os.remove(memory_file)
        config["ai"]["memory_file"] = memory_file
        self.app = AIvsStreamer(config, simulate=True, use_web=False, logger=lambda *a: None)
        self.app.ai.provider = FakeProvider("Oi! Tudo certo.")
        self.app.chat.send_message = lambda message: self.app.chat.last_sent.append(message) or True

    def test_comando_help(self):
        answer = self.app.handle_command("ana", "!help")
        self.assertIn("!pergunta", answer)

    def test_comando_lembra_e_memoria(self):
        self.app.handle_command("ana", "!lembra o streamer ama pizza")
        self.assertIn("pizza", self.app.handle_command("bob", "!memoria"))

    def test_comando_esquece(self):
        self.app.handle_command("ana", "!lembra segredo do streamer")
        self.app.handle_command("ana", "!esquece segredo")
        self.assertIn("nenhuma", self.app.handle_command("bob", "!memoria").lower())

    def test_comando_ai(self):
        answer = self.app.handle_command("ana", "!ai")
        self.assertIn("IA:", answer)

    def test_comando_modelo(self):
        self.assertIn("Modelo atual", self.app.handle_command("ana", "!modelo"))
        self.assertIn("free/kimi-k3", self.app.handle_command("ana", "!modelo free/kimi-k3"))

    def test_comando_de_provedor(self):
        answer = self.app.handle_command("ana", "!provedor offline")
        self.assertIn("offline", answer)

    def test_comando_pergunta_responde(self):
        answer = self.app.handle_command("ana", "!pergunta qual o melhor jogo?")
        self.assertIn("Oi! Tudo certo.", answer)

    def test_mensagem_do_chat_gera_resposta_da_ia(self):
        self.app.handle_message("ana", "ei robô, bom dia")
        self.assertTrue(any("Oi! Tudo certo." in msg for msg in self.app.chat.last_sent))

    def test_comando_nao_gera_resposta_extra_da_ia(self):
        self.app.chat.last_sent.clear()
        self.app.handle_message("ana", "!ranking")
        self.assertEqual(len(self.app.chat.last_sent), 1)
        self.assertIn("Ninguem trollou ainda", self.app.chat.last_sent[0])

    def test_voto_conta_xp(self):
        self.app.handle_message("ana", "!troll")
        self.assertEqual(self.app.voting.votes["troll"], 1)
        self.assertGreater(self.app.levels.get_xp("ana"), 0)


class WebPanelTests(unittest.TestCase):
    """O painel web precisa subir e mostrar o estado da IA."""

    def setUp(self):
        from tests.helpers import FakeProvider
        from web_panel import WebPanel

        config = load_config(os.path.join(BASE_DIR, "config.json"))
        config["provider"] = "offline"
        config["twitch"]["enabled"] = False
        config["tts"]["enabled"] = False
        config["voice"]["enabled"] = False
        config["ai"]["memory_file"] = os.path.join(BASE_DIR, "data", "memories_test_web.json")
        self.app = AIvsStreamer(config, simulate=True, use_web=False, logger=lambda *a: None)
        self.app.chat.logger = lambda *a: None
        self.app.ai.provider = FakeProvider("Fala, chat!")
        self.panel = WebPanel(self.app, config)
        self.client = self.panel.flask.test_client()

    def test_api_ai_mostra_provedor(self):
        data = self.client.get("/api/ai").get_json()
        self.assertEqual(data["provider"], "fake")
        self.assertTrue(data["available"])

    def test_api_status_traz_ia_e_chat(self):
        data = self.client.get("/api/status").get_json()
        self.assertIn("ai", data)
        self.assertIn("chat", data)

    def test_comando_say(self):
        response = self.client.post("/api/command", json={"command": "say", "text": "ola"}).get_json()
        self.assertTrue(response["ok"])

    def test_comando_ai_ask(self):
        response = self.client.post("/api/command", json={"command": "ai_ask",
                                                          "text": "qual o placar?"}).get_json()
        self.assertEqual(response["answer"], "Fala, chat!")

    def test_comando_desconhecido(self):
        response = self.client.post("/api/command", json={"command": "xyz"}).get_json()
        self.assertFalse(response["ok"])

    def test_admin_mostra_o_provedor(self):
        html = self.client.get("/admin").get_data(as_text=True)
        self.assertIn("IA:", html)


if __name__ == "__main__":
    unittest.main()
