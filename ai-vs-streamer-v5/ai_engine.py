"""Motor de IA - conversa com o provedor escolhido (APInex por padrao).

Responsabilidades:
- montar o prompt (personalidade + modo CHAT/TROLL + memorias + historico);
- chamar o provedor configurado (APInex/OpenAI/Gemini/Claude/offline);
- limitar a frequencia das respostas (o plano gratuito do APInex tem ~5 RPM);
- cair para o provedor reserva / frases prontas se algo falhar;
- guardar memorias do stream ("!lembra ...") entre reinicios.

Para trocar de provedor basta mexer em config.json:
    "provider": "apinex"  ->  "openai" | "gemini" | "anthropic" | "offline"
"""

from __future__ import annotations

import json
import os
import re
import unicodedata

from providers import (
    PROVIDER_NAMES,
    ProviderError,
    RateLimiter,
    build_provider,
    load_env,
    normalize_name,
)

DEFAULT_SYSTEM_PROMPT = (
    "Voce e o robo do stream, o 'AI vs Streamer'. Voce tem duas personalidades:\n"
    "- Modo CHAT: conversa com o chat, responde perguntas, faz piadas, e simpatico.\n"
    "- Modo TROLL: atrapalha o streamer, da dicas erradas, inventa comandos falsos, distrai.\n"
    "Regras:\n"
    "- Responda sempre em portugues brasileiro.\n"
    "- Seja engraçado e carismatico, sem ofender ninguem de verdade.\n"
    "- Respostas CURTAS: no maximo 2 frases, porque vao virar fala (TTS) no stream.\n"
    "- Nunca use markdown, listas ou emojis: e texto falado.\n"
)

MODE_LINES = {
    "chat": "Voltamos ao modo chat! Podem perguntar, eu estou inspirado.",
    "troll": "MODO TROLL ATIVADO! Streamer, eu nao vou ajudar nem um pouquinho.",
}


def _strip_accents(text):
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _mention_pattern(names):
    """Monta o regex que acha o robo sendo citado como PALAVRA INTEIRA.

    Sem isso, "ia" casaria dentro de "dia", "familia", "economia"... e o robo
    responderia qualquer conversa fiada do chat.
    """
    limpos = []
    for name in names or ():
        nome = _strip_accents(str(name).lower()).strip()
        if nome and nome not in limpos:
            limpos.append(nome)
    if not limpos:
        return None
    alternativas = "|".join(re.escape(nome) for nome in limpos)
    return re.compile(rf"(?<![a-z0-9])(?:{alternativas})(?![a-z0-9])")


def is_mentioned(message, names):
    """True se a mensagem chama o robo pelo nome (palavra inteira, sem acento)."""
    pattern = _mention_pattern(names)
    if pattern is None:
        return False
    return bool(pattern.search(_strip_accents(str(message or "").lower())))


class AIEngine:
    """Fachada de IA do robo: prompt + provedor + memoria + limite de uso."""

    def __init__(self, config, provider=None, logger=print):
        self.config = config or {}
        self.logger = logger
        ai_config = dict(self.config.get("ai") or {})
        self.ai_config = ai_config

        # prompt / comportamento
        self.prompt_file = ai_config.get("system_prompt_file", "prompts/default.txt")
        self.system_prompt = self._load_prompt(self.prompt_file)
        self.history_turns = int(ai_config.get("history_turns", 8))
        self.max_reply_chars = int(ai_config.get("max_reply_chars", 260))
        self.reply_enabled = bool(ai_config.get("reply_enabled", True))
        self.reply_mode = str(ai_config.get("reply_mode", "mentions")).lower()
        self.bot_names = [str(n).lower() for n in (ai_config.get("bot_names") or ["robô", "robo", "bot", "ia"])]
        self.memories = self._load_memories(ai_config.get("memory_file", "data/memories.json"))

        self.mode = "chat"
        self.messages = []           # historico rolante [(role, content)]
        self.speaker = None          # callback de TTS (definido pelo main)
        self.last_error = None
        self.stats = {"requests": 0, "errors": 0, "fallbacks": 0}

        # limita respostas automaticas (APInex gratuito: ~5 RPM por IP)
        self.reply_gate = RateLimiter(
            max_per_minute=int(ai_config.get("responses_per_minute", 4) or 0),
            min_interval=float(ai_config.get("reply_cooldown", 5) or 0),
        )

        # provedores
        load_env()
        self.provider = provider or self._build("provider", "apinex")
        self.fallback = self._build("fallback_provider", "offline")

    # ------------------------------------------------------------------
    # inicializacao
    # ------------------------------------------------------------------
    def _load_prompt(self, path):
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read().strip()
            return text or DEFAULT_SYSTEM_PROMPT
        except OSError:
            return DEFAULT_SYSTEM_PROMPT

    def _load_memories(self, path):
        self.memory_file = path
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                return [str(item) for item in data if str(item).strip()]
        except (OSError, ValueError):
            pass
        return []

    def _save_memories(self):
        try:
            os.makedirs(os.path.dirname(self.memory_file) or ".", exist_ok=True)
            with open(self.memory_file, "w", encoding="utf-8") as handle:
                json.dump(self.memories, handle, ensure_ascii=False, indent=2)
        except OSError as error:
            self.logger(f"[AI] nao deu para salvar memorias: {error}")

    def _build(self, key, default_name):
        name = normalize_name(self.config.get(key) or default_name)
        try:
            return build_provider(self.config, name, logger=self.logger)
        except Exception as error:  # provedor invalido/ausente -> offline
            self.logger(f"[AI] provedor '{name}' indisponivel ({error}); usando offline")
            return build_provider(self.config, "offline")

    # ------------------------------------------------------------------
    # fala / TTS
    # ------------------------------------------------------------------
    def set_speaker(self, callback):
        """Define a funcao que fala de verdade (TTSEngine.speak)."""
        self.speaker = callback

    def speak(self, text, use_tts=True):
        text = (text or "").strip()
        if not text:
            return ""
        self.logger(f"[AI] {text}")
        if use_tts and self.speaker:
            try:
                self.speaker(text)
            except Exception as error:
                self.logger(f"[AI] falha no TTS: {error}")
        return text

    # ------------------------------------------------------------------
    # modo / memoria
    # ------------------------------------------------------------------
    def on_mode_change(self, mode):
        self.mode = "troll" if str(mode).lower().startswith("troll") else "chat"
        self.messages.append({"role": "system", "content": f"[SISTEMA] Modo mudou para {self.mode.upper()}."})
        self._trim_history()
        line = MODE_LINES.get(self.mode, "")
        if line:
            self.speak(line)
        return line

    def remember(self, thing, source="chat"):
        thing = (thing or "").strip()
        if not thing:
            return None
        entry = f"{thing} (fonte: {source})"
        self.memories.append(entry)
        self.memories = self.memories[-50:]
        self._save_memories()
        return entry

    def forget(self, thing):
        # compara sem acento dos dois lados ("palhaço" acha "palhaco")
        thing = _strip_accents((thing or "").strip().lower())
        if not thing:
            return 0
        before = len(self.memories)
        self.memories = [m for m in self.memories if thing not in _strip_accents(m).lower()]
        self._save_memories()
        return before - len(self.memories)

    def get_memories(self):
        return list(self.memories)

    def clear_memories(self):
        self.memories = []
        self._save_memories()

    # ------------------------------------------------------------------
    # prompt
    # ------------------------------------------------------------------
    def build_messages(self, username=None, message=None):
        """Monta [system, ...historico, user] para enviar ao provedor."""
        context = [self.system_prompt]
        context.append(f"MODO ATUAL: {self.mode.upper()}.")
        if self.memories:
            context.append("MEMORIAS DO STREAM:\n- " + "\n- ".join(self.memories[-10:]))
        if self.mode == "troll":
            context.append("Neste modo, atrapalhe o streamer com humor (sem ofensa real).")
        else:
            context.append("Neste modo, ajude e converse com o chat de forma leve.")

        messages = [{"role": "system", "content": "\n\n".join(context)}]
        messages.extend(self.messages[-self.history_turns * 2:])
        if message:
            prefix = f"@{username}: " if username else ""
            messages.append({"role": "user", "content": f"{prefix}{message}".strip()})
        return messages

    def _trim_history(self):
        limit = max(2, self.history_turns * 2)
        if len(self.messages) > limit:
            self.messages = self.messages[-limit:]

    def _remember_turn(self, username, message, answer):
        self.messages.append({"role": "user", "content": f"@{username}: {message}" if username else message})
        self.messages.append({"role": "assistant", "content": answer})
        self._trim_history()

    # ------------------------------------------------------------------
    # respostas
    # ------------------------------------------------------------------
    def _call(self, messages, **kwargs):
        """Chama o provedor principal; se falhar, tenta o reserva. Nunca levanta."""
        try:
            self.stats["requests"] += 1
            result = self.provider.chat(messages, **kwargs)
            if result is None or not (result.text or "").strip():
                raise ProviderError("resposta vazia do provedor", provider=getattr(self.provider, "name", "?"))
            self.last_error = None
            return result.text.strip(), getattr(self.provider, "name", "")
        except Exception as error:
            self.stats["errors"] += 1
            self.last_error = error
            self.logger(f"[AI] erro no provedor '{getattr(self.provider, 'name', '?')}': {error}")
            hint = getattr(error, "hint", "")
            if hint:
                self.logger(f"[AI] dica: {hint}")
            if self.fallback is not None and self.fallback is not self.provider:
                self.stats["fallbacks"] += 1
                try:
                    result = self.fallback.chat(messages, **kwargs)
                    return result.text.strip(), getattr(self.fallback, "name", "offline")
                except Exception as fallback_error:
                    self.logger(f"[AI] reserva tambem falhou: {fallback_error}")
        return "", ""

    def _shorten(self, text):
        text = re.sub(r"\s+", " ", (text or "").replace("\n", " ")).strip()
        text = re.sub(r"[*_`#>]+", "", text).strip()
        if len(text) <= self.max_reply_chars:
            return text
        cut = text[: self.max_reply_chars]
        if " " in cut:
            cut = cut[: cut.rfind(" ")]
        return cut.rstrip(" ,;:") + "..."

    def should_reply(self, username, message):
        """Decide se o robo responde uma mensagem automaticamente (economiza cota)."""
        if not self.reply_enabled:
            return False
        message = (message or "").strip()
        if not message or message.startswith("!"):
            return False

        if self.reply_mode in ("mentions", "mention", "mencao", "menções"):
            if not is_mentioned(message, self.bot_names):
                return False
        elif self.reply_mode in ("questions", "perguntas"):
            if "?" not in message:
                return False
        elif self.reply_mode in ("off", "none", "nunca"):
            return False
        # qualquer outro valor ("all"/"tudo") responde tudo

        if not self.reply_gate.allow():
            return False
        return True

    def reply(self, username, message):
        """Resposta automatica para o chat (respeita o portao de frequencia)."""
        if not self.should_reply(username, message):
            return ""
        return self._answer(username, message)

    def explain_skip(self, username, message):
        """Diz (em portugues) por que o robo NAO respondeu uma mensagem.

        Serve para o console/README: sem isso o usuario ve o robo conectado e
        calado, sem saber se e limite, mencao ou configuracao.
        """
        message = (message or "").strip()
        if not message or message.startswith("!"):
            return ""
        if not self.reply_enabled:
            return "respostas automaticas desligadas (ai.reply_enabled = false)"
        if self.reply_mode in ("off", "none", "nunca"):
            return "ai.reply_mode esta em 'off'"
        if self.reply_mode in ("mentions", "mention", "mencao", "menções"):
            if not is_mentioned(message, self.bot_names):
                nomes = ", ".join(self.bot_names)
                return (f"nao citaram o robo (modo 'mentions'). Chame por {nomes} "
                        f"como palavra separada (ex: \"ei robô\"), ou use !pergunta, "
                        f"ou mude ai.reply_mode para \"all\"")
        elif self.reply_mode in ("questions", "perguntas") and "?" not in message:
            return "ai.reply_mode = 'questions' e a mensagem nao era pergunta"
        if not self.reply_gate.allow():
            return (f"limite de respostas atingido (ai.responses_per_minute="
                    f"{self.reply_gate.max_per_minute}, ai.reply_cooldown="
                    f"{self.reply_gate.min_interval:g}s)")
        return ""

    def ask(self, question, username="chat"):
        """Pergunta direta (comando !pergunta).

        Ignora a espera minima entre respostas automaticas (e um pedido explicito),
        mas continua respeitando o limite por minuto do provedor.
        """
        if not question:
            return ""
        if not self.reply_gate.allow_rpm():
            wait = self.reply_gate.wait_time()
            return f"Calma ai! Meu limite de respostas por minuto estourou. Tenta de novo em {wait:.0f}s."
        return self._answer(username, question)

    def _answer(self, username, message):
        self.reply_gate.register()
        messages = self.build_messages(username=username, message=message)
        text, provider_name = self._call(messages)
        if not text:
            return ""
        text = self._shorten(text)
        self._remember_turn(username, message, text)
        return text

    def get_praise(self):
        """Elogio do streamer (comando !gg)."""
        messages = self.build_messages(
            username="sistema",
            message="O streamer acabou de mandar bem no jogo. Elogie de forma epica e sugira recompensa pro chat.",
        )
        text, _ = self._call(messages)
        return self._shorten(text) or "Voce jogou muito bem! O chat merece recompensa!"

    # ------------------------------------------------------------------
    # extras
    # ------------------------------------------------------------------
    def can_search(self):
        return bool(getattr(self.provider, "supports_search", False))

    def search(self, query, count=4):
        """Busca web pelo provedor (APInex: /tools/web/search)."""
        if not self.can_search():
            return None
        if not self.reply_gate.allow_rpm():
            self.last_error = "limite de requisicoes por minuto atingido"
            return None
        try:
            self.stats["requests"] += 1
            self.reply_gate.register()
            return self.provider.search(query, count=count)
        except Exception as error:
            self.last_error = error
            self.stats["errors"] += 1
            self.logger(f"[AI] busca falhou: {error}")
            return None

    def set_model(self, model):
        model = (model or "").strip()
        if not model:
            return None
        old = getattr(self.provider, "model", "")
        try:
            self.provider.model = model
        except Exception:
            return None
        self.logger(f"[AI] modelo trocado: {old} -> {model}")
        return model

    def set_provider(self, name):
        """Troca o provedor em tempo de execucao (comando !provedor)."""
        name = normalize_name(name)
        if name not in PROVIDER_NAMES:
            return None
        try:
            new_provider = build_provider(self.config, name, logger=self.logger)
        except Exception as error:
            self.logger(f"[AI] nao deu para trocar para '{name}': {error}")
            return None
        self.provider = new_provider
        return name

    def balance(self):
        """Saldo do provedor (so APInex tem)."""
        if hasattr(self.provider, "balance_usd"):
            try:
                return self.provider.balance_usd()
            except Exception:
                return None
        return None

    def status(self):
        provider_name = getattr(self.provider, "name", "?")
        return {
            "provider": provider_name,
            "model": getattr(self.provider, "model", ""),
            "available": self.provider.available() if self.provider else False,
            "fallback": getattr(self.fallback, "name", ""),
            "mode": self.mode,
            "memories": len(self.memories),
            "history": len(self.messages),
            "reply_mode": self.reply_mode,
            "stats": dict(self.stats),
            "last_error": str(self.last_error) if self.last_error else None,
        }

    def available(self):
        return bool(self.provider and self.provider.available())
