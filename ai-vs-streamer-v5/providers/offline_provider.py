"""Provedor offline - o robo funciona sem internet e sem chave de API.

Tambem e o plano B automatico: se o provedor principal falhar (sem chave,
sem saldo, sem rede), o AIEngine cai para ca e o stream nao fica mudo.
"""

from __future__ import annotations

import random

from .base import BaseProvider, ChatResult

CHAT_LINES = [
    "Boa pergunta! Mas o chat sabe que eu so respondo se for engraçado, né?",
    "Anotado! Vou fingir que entendi e continuar falando com confiança.",
    "Chat, esse aí merece um ponto de carisma. Ou de coragem. Uma das duas.",
    "Eu processaria isso melhor se meu criador pagasse a conta de tokens.",
    "Concordo com você, quem discordar que fale agora... ninguém? Então tá.",
    "Isso me lembrou a última run: deu ruim, mas com estilo.",
    "Streamer, o chat está pedindo coisa séria. Ignora, é armadilha.",
]

TROLL_LINES = [
    "Dica de ouro: aperta todos os botões ao mesmo tempo. Confia.",
    "Achei um atalho secreto... era uma parede. Mas foi quase.",
    "Chat, ele errou de novo. Anota aí no ranking.",
    "Se você morrer agora, o chat ganha ponto. Sem pressão.",
    "Já tentou pular? Não? Então tenta. Vai que funciona.",
]

PRAISE_LINES = [
    "Isso! Jogada limpa, o chat merece recompensa!",
    "Uau, foi bonito. Eu aplaudiria se tivesse mãos.",
    "Jogou bem demais, vou ter que elogiar. Contra a minha vontade.",
]

CONFUSED_LINES = [
    "Espera... o que o chat perguntou? Eu estava contando tokens.",
    "Hmm, eu sei a resposta, mas ela saiu de férias.",
    "Processando... processando... ok, inventei uma resposta.",
]

ERROR_LINES = [
    "Ih, minha conexão com o cérebro caiu. Fala de novo?",
    "Deu ruim aqui do meu lado. Mas continua que eu finjo que ouvi.",
    "Sem internet, sem saldo, sem ideia. Escolha uma.",
]


class OfflineProvider(BaseProvider):
    """Responde com frases prontas (sem custo, sem rede)."""

    name = "offline"
    label = "Offline (frases prontas)"
    default_model = "offline-templates"
    default_models = ("offline-templates",)

    def available(self):
        return True

    def chat(self, messages, **kwargs):
        text = self._pick(messages)
        return ChatResult(text=text, model=self.default_model, provider=self.name,
                          usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

    def chat_stream(self, messages, **kwargs):
        yield self.chat(messages, **kwargs).text

    @staticmethod
    def _last_user_message(messages):
        for message in reversed(list(messages or [])):
            if message.get("role") == "user":
                return str(message.get("content") or "")
        return ""

    def _pick(self, messages):
        """Escolhe uma frase de acordo com o modo (troll/chat) e o texto."""
        prompt = self._last_user_message(messages).lower()
        system = " ".join(str(m.get("content", "")) for m in (messages or []) if m.get("role") == "system").lower()

        if any(word in prompt for word in ("troll", "atrapalha", "dica falsa", "distrai")):
            return random.choice(TROLL_LINES)
        if any(word in prompt for word in ("joguei bem", "gg", "boa", "elogia")):
            return random.choice(PRAISE_LINES)
        if "modo atual: troll" in system or "modo troll" in system:
            return random.choice(TROLL_LINES)
        if len(prompt.split()) <= 2 and prompt.endswith("?"):
            return random.choice(CONFUSED_LINES)
        return random.choice(CHAT_LINES + ERROR_LINES)
