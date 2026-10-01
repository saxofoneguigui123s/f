"""Testes do motor de IA: prompt, memoria, limites e plano B."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine import AIEngine  # noqa: E402
from providers import OfflineProvider  # noqa: E402
from tests.helpers import FakeProvider, FailingProvider  # noqa: E402


def build_engine(provider=None, **ai_overrides):
    ai_config = {
        "history_turns": 4,
        "reply_enabled": True,
        "reply_mode": "mentions",
        "bot_names": ["robô", "robo", "bot", "ia"],
        "reply_cooldown": 0,
        "responses_per_minute": 0,
        "max_reply_chars": 60,
        "memory_file": os.path.join(tempfile.mkdtemp(), "memories.json"),
    }
    ai_config.update(ai_overrides)
    config = {"provider": "offline", "ai": ai_config}
    return AIEngine(config, provider=provider or FakeProvider(), logger=lambda *a: None)


class AIEngineTests(unittest.TestCase):
    def test_responde_e_guarda_historico(self):
        provider = FakeProvider("Boa noite, chat!")
        engine = build_engine(provider)
        answer = engine.reply("ana", "oi robô")
        self.assertEqual(answer, "Boa noite, chat!")
        self.assertEqual(len(engine.messages), 2)  # user + assistant
        self.assertEqual(len(provider.received), 1)

    def test_prompt_leva_modo_e_memorias(self):
        provider = FakeProvider()
        engine = build_engine(provider)
        engine.remember("o streamer odeia lag", source="chat")
        engine.on_mode_change("troll")
        engine.reply("ana", "oi robô")

        sent = provider.received[-1]
        system = sent[0]["content"]
        self.assertEqual(sent[0]["role"], "system")
        self.assertIn("MODO ATUAL: TROLL", system)
        self.assertIn("o streamer odeia lag", system)

    def test_modo_chat_no_prompt(self):
        provider = FakeProvider()
        engine = build_engine(provider)
        engine.reply("ana", "oi robô")
        self.assertIn("MODO ATUAL: CHAT", provider.received[-1][0]["content"])

    def test_mensagem_do_usuario_vai_com_o_nome(self):
        provider = FakeProvider()
        engine = build_engine(provider)
        engine.reply("ana", "oi robô")
        self.assertEqual(provider.received[-1][-1]["content"], "@ana: oi robô")

    def test_portao_de_mencao(self):
        engine = build_engine()
        self.assertFalse(engine.should_reply("ana", "bom dia a todos"))
        self.assertTrue(engine.should_reply("ana", "ei robô, tudo bem?"))
        self.assertTrue(engine.should_reply("ana", "BOT?"))

    def test_nao_responde_quando_o_nome_aparece_dentro_de_outra_palavra(self):
        """Bug antigo: "ia" dentro de "dia"/"familia" fazia o robo responder tudo."""
        engine = build_engine()
        for frase in ("bom dia pessoal", "minha familia chegou", "a economia ta ruim",
                      "ele jogaria melhor", "olha o dibre"):
            self.assertFalse(engine.should_reply("ana", frase), frase)

    def test_responde_quando_o_nome_e_palavra_inteira(self):
        engine = build_engine()
        for frase in ("robô, ajuda aqui", "ei robo", "fala BOT", "ia, responde",
                      "Robô!", "bot?"):
            self.assertTrue(engine.should_reply("ana", frase), frase)

    def test_portao_ignora_comandos(self):
        engine = build_engine()
        self.assertFalse(engine.should_reply("ana", "!ranking"))

    def test_portao_modo_all(self):
        engine = build_engine(reply_mode="all")
        self.assertTrue(engine.should_reply("ana", "qualquer coisa"))

    def test_portao_desligado(self):
        engine = build_engine(reply_enabled=False)
        self.assertFalse(engine.should_reply("ana", "oi robô"))
        self.assertEqual(engine.reply("ana", "oi robô"), "")

    def test_intervalo_minimo_entre_respostas(self):
        engine = build_engine(reply_cooldown=60)
        self.assertTrue(engine.should_reply("ana", "oi robô"))
        engine.reply("ana", "oi robô")
        self.assertFalse(engine.should_reply("ana", "fala robô"))

    def test_limite_por_minuto(self):
        engine = build_engine(responses_per_minute=2)
        self.assertTrue(engine.should_reply("ana", "oi robô"))
        engine.reply("ana", "oi robô")
        self.assertTrue(engine.should_reply("ana", "oi robô denovo"))
        engine.reply("ana", "oi robô denovo")
        self.assertFalse(engine.should_reply("ana", "oi robô terceira vez"))

    def test_ask_respeita_limite(self):
        engine = build_engine(responses_per_minute=1)
        self.assertTrue(engine.ask("tudo bem?", username="ana"))
        limited = engine.ask("e agora?", username="ana")
        self.assertIn("limite", limited.lower())

    def test_ask_ignora_a_espera_entre_respostas_automaticas(self):
        engine = build_engine(reply_cooldown=600, responses_per_minute=0)
        self.assertTrue(engine.should_reply("ana", "oi robô"))
        engine.reply("ana", "oi robô")
        self.assertEqual(engine.ask("e ai?", username="ana"), "Resposta de teste, chat!")

    def test_corta_respostas_longas(self):
        engine = build_engine(FakeProvider("palavra " * 60), max_reply_chars=40)
        answer = engine.reply("ana", "oi robô")
        self.assertLessEqual(len(answer), 43)
        self.assertTrue(answer.endswith("..."))

    def test_remove_markdown(self):
        engine = build_engine(FakeProvider("**Negrito** e `codigo` no chat"))
        self.assertEqual(engine.reply("ana", "oi robô"), "Negrito e codigo no chat")

    def test_memorias_persistem_em_arquivo(self):
        path = os.path.join(tempfile.mkdtemp(), "memories.json")
        engine = build_engine(memory_file=path)
        engine.remember("o chat ama gatos", source="ana")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as handle:
            self.assertIn("o chat ama gatos", json.load(handle)[0])

        engine2 = build_engine(memory_file=path)
        self.assertEqual(len(engine2.get_memories()), 1)

    def test_esquecer_memoria(self):
        engine = build_engine()
        engine.remember("o streamer tem medo de palhaço")
        engine.remember("o chat gosta de pizza")
        self.assertEqual(engine.forget("palhaço"), 1)
        self.assertEqual(len(engine.get_memories()), 1)

    def test_plano_b_offline_quando_o_provedor_falha(self):
        engine = build_engine(FailingProvider())
        engine.fallback = OfflineProvider()
        answer = engine.reply("ana", "oi robô")
        self.assertTrue(answer)
        self.assertEqual(engine.stats["fallbacks"], 1)
        self.assertIsNotNone(engine.last_error)

    def test_elogio_do_streamer(self):
        engine = build_engine(FakeProvider("Jogou demais!"))
        self.assertEqual(engine.get_praise(), "Jogou demais!")

    def test_status_do_motor(self):
        engine = build_engine()
        status = engine.status()
        self.assertEqual(status["provider"], "fake")
        self.assertEqual(status["fallback"], "offline")
        self.assertIn("stats", status)

    def test_troca_de_modelo(self):
        engine = build_engine()
        engine.set_model("free/gemini-3.8-flash")
        self.assertEqual(engine.status()["model"], "free/gemini-3.8-flash")

    def test_troca_de_provedor_desconhecido(self):
        engine = build_engine()
        self.assertIsNone(engine.set_provider("nao-existe"))

    def test_sem_busca_quando_provedor_nao_suporta(self):
        engine = build_engine()
        self.assertFalse(engine.can_search())
        self.assertIsNone(engine.search("qualquer coisa"))


if __name__ == "__main__":
    unittest.main()
