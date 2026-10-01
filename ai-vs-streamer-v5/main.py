"""AI vs Streamer - v5

Robo de stream (Twitch) que conversa com o chat usando IA e, quando o chat
manda, entra em modo TROLL para atrapalhar o streamer de forma engraçada.

O provedor de IA padrao e o APInex (https://apinex.bond):
    config.json -> "provider": "apinex", "api_key_env": "APINEX_API_KEY"

Como rodar:
    python main.py --check      # valida config, provedor, chave e saldo
    python main.py --simulate   # testa no terminal, sem Twitch
    python main.py              # roda de verdade (Twitch + painel web)
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time

DEFAULT_CONFIG_FILE = "config.json"


def load_config(path=DEFAULT_CONFIG_FILE):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


from chat_reader import TOKEN_HELP, ChatReader, TwitchChat  # noqa: E402
from terminal_chat import TerminalChat                  # noqa: E402
from voting import VotingSystem                          # noqa: E402
from ai_engine import AIEngine                           # noqa: E402
from troll_logic import TrollLogic                       # noqa: E402
from emoji_voting import EmojiVoting                     # noqa: E402
from ranking import RankingSystem                        # noqa: E402
from difficulty import DifficultyManager                 # noqa: E402
from achievements import AchievementSystem               # noqa: E402
from chat_levels import ChatLevels                       # noqa: E402
from mini_games import MiniGames                         # noqa: E402
from web_panel import WebPanel                           # noqa: E402
from chat_history import ChatHistory                      # noqa: E402
from voice_commands import VoiceCommands                 # noqa: E402
from tts_engine import TTSEngine                         # noqa: E402
from sound_effects import SoundEffects                   # noqa: E402
from offline_mode import OfflineMode                     # noqa: E402
from streamer_bot import StreamerBotBridge               # noqa: E402
from providers import (  # noqa: E402
    PROVIDER_NAMES,
    build_provider,
    env_sources,
    load_env,
    mask_secret,
    provider_info,
)

HELP_TEXT = (
    "Comandos: !modo !tempo !memoria !esquece <coisa> !lembra <coisa> !ranking !badges "
    "!xp !level [1-10] !caos !calma !gg !pergunta <texto> !busca <texto> !saldo "
    "!modelo [id] !provedor [nome] !ai !help"
)


class AIvsStreamer:
    def __init__(self, config, simulate=False, use_web=True, logger=print):
        self.config = config
        self.logger = logger
        self.simulate = simulate
        self.use_web = use_web

        load_env()

        # ordem importa: o TTS precisa existir antes do motor de IA falar
        self.tts = TTSEngine(config)
        self.history = ChatHistory()
        self.ai = AIEngine(config, logger=logger)
        self.ai.set_speaker(self.tts.speak)

        self.chat = TerminalChat(logger=logger) if simulate else ChatReader(config, logger=logger)
        self.voting = VotingSystem(config)
        self.troll = TrollLogic(config)
        self.emoji = EmojiVoting(config)
        self.ranking = RankingSystem()
        self.difficulty = DifficultyManager()
        self.achievements = AchievementSystem()
        self.levels = ChatLevels()
        self.mini_games = MiniGames()
        self.sounds = SoundEffects(config)
        self.voice = VoiceCommands(config, self.ai, self.troll)
        self.bot_bridge = StreamerBotBridge()
        self.offline = OfflineMode(self.ai, self.chat)
        self.web = WebPanel(self, config) if use_web else None
        self.running = True

    # ------------------------------------------------------------------
    # comandos do chat
    # ------------------------------------------------------------------
    def handle_command(self, username, message):
        msg = (message or "").strip()
        low = msg.lower()
        mention = f"@{username} "

        if low == "!help" or low == "!ajuda":
            return mention + HELP_TEXT
        if low in ("!ping", "!bot", "!status"):
            info = self.ai.status()
            chat = self.chat.status().get("twitch") or {}
            onde = "chat" if chat.get("can_send") else (chat.get("reason") or "sem chat")
            return (f"@{username} estou vivo! provedor={info['provider']} "
                    f"modelo={info['model']} modo={info['mode']} | escrevendo: {onde}")
        if low == "!modo":
            mode = self.voting.get_mode()
            return f"@{username} Modo atual: {'CHAT' if mode == 'chat' else 'TROLL'}"
        if low == "!tempo":
            return f"@{username} Proxima votacao em {self.voting.time_left()}s"
        if low == "!memoria":
            mems = self.ai.get_memories()
            return f"@{username} Memorias: {', '.join(mems) if mems else 'nenhuma'}"
        if low.startswith("!lembra") or low.startswith("!anota"):
            thing = msg.split(" ", 1)[1].strip() if " " in msg else ""
            if not thing:
                return f"@{username} Uso: !lembra <coisa que eu devo guardar>"
            self.ai.remember(thing, source=username)
            return f"@{username} Guardei: {thing}"
        if low.startswith("!esquece"):
            thing = msg.replace("!", "").split(" ", 1)
            thing = thing[1].strip() if len(thing) > 1 else ""
            removed = self.ai.forget(thing)
            return f"@{username} Esqueci {removed} memoria(s) sobre '{thing}'"
        if low == "!ranking":
            return self.ranking.get_top()
        if low == "!badges":
            return self.achievements.get_user_badges(username)
        if low == "!caos":
            self.voting.set_interval(self.config["chaos_interval"])
            self.config["chaos_mode"] = True
            self.sounds.play("chaos")
            return "MODO CAOS ATIVADO! Votacao a cada 60s!"
        if low == "!calma":
            self.voting.set_interval(self.config["voting_interval"])
            self.config["chaos_mode"] = False
            return f"Voltamos ao normal. Votacao a cada {self.config['voting_interval']}s."
        if low == "!gg":
            praise = self.reward_streamer()
            return f"@{username} {praise}"
        if low == "!level":
            return self.difficulty.get_info()
        if low.startswith("!level "):
            try:
                level = int(msg.split()[1])
                self.difficulty.set_level(level)
                return f"Dificuldade do troll: nivel {self.difficulty.get_level()}"
            except ValueError:
                return "Uso: !level <1-10>"
        if low == "!xp":
            return (f"@{username} Nivel {self.levels.get_level(username)} | "
                    f"XP: {self.levels.get_xp(username)}")
        if low == "!ai":
            status = self.ai.status()
            return (f"IA: {status['provider']} / {status['model']} | modo {status['mode']} | "
                    f"memorias {status['memories']} | erros {status['stats']['errors']}")
        if low == "!saldo":
            if not hasattr(self.ai.provider, "balance_usd"):
                return f"@{username} O provedor '{getattr(self.ai.provider, 'name', '?')}' nao tem saldo para consultar."
            value = self.ai.balance()
            if value is None:
                return f"@{username} Nao consegui consultar o saldo agora (veja o console)."
            return f"@{username} Saldo APInex: US$ {value:.4f}"
        if low.startswith("!modelo"):
            new_model = msg.split(" ", 1)[1].strip() if " " in msg else ""
            if not new_model:
                return f"@{username} Modelo atual: {getattr(self.ai.provider, 'model', '?')}"
            self.ai.set_model(new_model)
            return f"@{username} Modelo trocado para {new_model}"
        if low.startswith("!provedor"):
            name = msg.split(" ", 1)[1].strip() if " " in msg else ""
            if not name:
                return f"@{username} Provedor atual: {getattr(self.ai.provider, 'name', '?')} (opcoes: {', '.join(PROVIDER_NAMES)})"
            changed = self.ai.set_provider(name)
            if not changed:
                return f"@{username} Nao conheco o provedor '{name}'. Opcoes: {', '.join(PROVIDER_NAMES)}"
            return f"@{username} Agora eu uso o provedor {changed}"
        if low.startswith("!pergunta"):
            question = msg.split(" ", 1)[1].strip() if " " in msg else ""
            if not question:
                return f"@{username} Uso: !pergunta <sua pergunta>"
            answer = self.ai.ask(question, username=username)
            if answer:
                self.history.add("AI", answer, "pergunta")
            return f"@{username} {answer}" if answer else f"@{username} Nao consegui pensar agora, tenta de novo."
        if low.startswith("!busca"):
            query = msg.split(" ", 1)[1].strip() if " " in msg else ""
            if not query:
                return f"@{username} Uso: !busca <assunto>"
            results = self.ai.search(query)
            if results is None:
                if self.ai.can_search():
                    return f"@{username} Nao consegui buscar agora (limite de requisicoes). Tenta em instantes."
                return f"@{username} Meu provedor atual nao tem busca web."
            if not results:
                return f"@{username} Nao achei nada sobre '{query}'."
            top = results[:3]
            parts = []
            for item in top:
                title = item.get("title") or item.get("name") or "resultado"
                url = item.get("url") or item.get("link") or ""
                parts.append(f"{title}{' - ' + url if url else ''}")
            return f"@{username} " + " | ".join(parts)
        return None

    def reward_streamer(self):
        praise = self.ai.get_praise()
        self.ai.speak(praise)
        self.history.add("AI", praise, "reward")
        self.sounds.play("reward")
        return praise

    # ------------------------------------------------------------------
    # loop principal
    # ------------------------------------------------------------------
    def handle_message(self, user, msg):
        """Processa uma mensagem do chat: comando, voto, XP e resposta da IA."""
        if self.config.get("ai", {}).get("log_chat", True):
            self.logger(f"[CHAT] {user}: {msg}")

        cmd = self.handle_command(user, msg)
        if cmd:
            self.chat.send_message(cmd)
            self.history.add("BOT", cmd, "command")
            return

        vote = self.emoji.process(user, msg)
        if vote:
            self.voting.add_vote(user, vote)
            self.levels.add_xp(user, 5)
        elif "!chat" in msg.lower():
            self.voting.add_vote(user, "chat")
        elif "!troll" in msg.lower():
            self.voting.add_vote(user, "troll")

        if self.ai.should_reply(user, msg):
            answer = self.ai.reply(user, msg)
            if answer:
                self.ai.speak(answer)
                self.chat.send_message(f"@{user} {answer}")
                self.history.add("AI", answer, "reply")
                self.logger(f"[IA] respondi para {user}")
            else:
                status = self.ai.status()
                self.logger(f"[IA] tentei responder {user} mas nao saiu texto "
                            f"(provedor {status['provider']} falhou - veja os erros acima)")
        else:
            self._explain_skip(user, msg)

    def _explain_skip(self, user, msg):
        """Mostra no console por que o robo ficou quieto (so nas primeiras vezes)."""
        reason = self.ai.explain_skip(user, msg)
        if not reason:
            return
        self.skipped = getattr(self, "skipped", 0) + 1
        if self.skipped <= 5:
            self.logger(f'[IA] nao respondi "{msg[:50]}" -> {reason}')
        elif self.skipped == 6:
            self.logger("[IA] (nao vou repetir esse aviso; veja ai.reply_mode no config.json)")

    def start(self):
        self.logger("AI vs Streamer v5 rodando!")
        info = self.ai.status()
        self.logger(f"IA: provedor={info['provider']} modelo={info['model']} "
                    f"disponivel={info['available']} reserva={info['fallback']}")
        if not info["available"]:
            self.logger("[AI] provedor principal sem chave: rodando com frases prontas. "
                        "Rode 'python main.py --check' para configurar.")
        self.chat.start()
        self._warn_chat()
        self._announce_startup()
        if self.use_web:
            self.web.start()
        if self.config.get("streamer_offline_mode"):
            self.offline.start()
        try:
            self.voice.start()
        except Exception as error:
            self.logger(f"[VOZ] desligada: {error}")

    def _announce_startup(self):
        """Manda a mensagem de boas-vindas no chat (prova que o robo consegue escrever)."""
        texto = str((self.config.get("twitch") or {}).get("startup_message") or "").strip()
        if not texto:
            return

        def worker():
            deadline = time.time() + 20
            while time.time() < deadline and self.running:
                if getattr(self.chat, "can_send", True):
                    if self.chat.send_message(texto):
                        self.history.add("BOT", texto, "startup")
                    return
                time.sleep(0.5)
            self.logger("[CHAT] nao consegui mandar a mensagem de boas-vindas "
                        "(o chat nao esta pronto para escrever)")

        threading.Thread(target=worker, daemon=True, name="startup-message").start()

    def _warn_chat(self):
        """Avisa na largada quando o robo conecta mas nao vai conseguir responder."""
        status = self.chat.status()
        twitch = status.get("twitch") or {}
        if not twitch.get("enabled"):
            return
        if "simulated" in twitch:
            return
        if not twitch.get("anonymous") and not twitch.get("auth_failed"):
            return
        if twitch.get("anonymous"):
            self.logger("[CHAT] ATENCAO: sem token do Twitch -> o robo LE o chat mas NAO responde.")
        else:
            self.logger("[CHAT] ATENCAO: token do Twitch recusado -> rodando so leitura.")
        self.logger("[CHAT] Resolva com: python main.py --check   (ele testa o token e explica)")

    def run(self):
        self.start()
        try:
            while self.running:
                try:
                    for user, msg in self.chat.read():
                        self.handle_message(user, msg)

                    if self.voting.check_finished():
                        self.on_mode_finished()

                    self.offline.tick()
                    if self.simulate and not getattr(self.chat, "running", True):
                        self.running = False
                        break
                    time.sleep(0.5)
                except KeyboardInterrupt:
                    self.running = False
                except Exception as error:
                    self.logger(f"Erro: {error}")
                    time.sleep(1)
        finally:
            self.stop()
        return 0

    def on_mode_finished(self):
        mode = self.voting.get_mode()
        self.sounds.play(mode)
        self.ai.on_mode_change(mode)
        self.history.add("SISTEMA", f"Modo mudou para {mode}", "mode")
        if mode == "troll":
            self.ranking.add_troll_point(self.voting.get_last_troll_voters())
            new_badges = self.check_badges()
            for badge in new_badges:
                self.chat.send_message(f"Conquista desbloqueada: {badge}!")
            self.difficulty.increase_progress()
            troll_line = self.mini_games.execute()
            self.ai.speak(troll_line)
            self.chat.send_message(troll_line)
            self.history.add("TROLL", troll_line, "troll")

    def check_badges(self):
        """Da badges para quem trollou o suficiente (integracao com o ranking)."""
        badges = []
        try:
            from achievements import check_badges as check
            for user, points in getattr(self.ranking, "_load")().items():
                for badge in check(user, points):
                    badges.append(f"{user} -> {badge}")
                    self.history.add("SISTEMA", f"{user} ganhou {badge}", "badge")
        except Exception as error:
            self.logger(f"[BADGES] {error}")
        return badges

    def stop(self):
        self.running = False
        try:
            self.chat.stop()
        except Exception:
            pass


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def describe_env(config, logger=print):
    """Mostra onde o robo procurou as chaves e se achou (sem revelar os segredos)."""
    import os

    logger("== Arquivos e chaves ==")
    logger(f"Pasta: {os.path.abspath('.')}")
    report = load_env(logger=None)

    if report["found"]:
        logger(f"  .env ........... encontrado em {report['path']}")
        logger(f"  chaves no .env . {', '.join(report['keys']) or '(nenhuma)'}")
        logger(f"  python-dotenv .. {'instalado' if report['dotenv'] else 'nao instalado (leitor interno)'}")
    else:
        logger("  .env ........... NAO ENCONTRADO")

    for warning in report["warnings"]:
        logger(f"  AVISO: {warning}")

    # de onde cada chave veio de verdade (config.json, .env ou ambiente)
    provider = config.get("provider", "apinex")
    info = provider_info(config, provider)
    logger("  chaves (com o miolo escondido):")
    _report_key(info["env"], f"IA {provider}", logger, report, config.get("api_key"))

    twitch_env = str((config.get("twitch") or {}).get("oauth_env") or "TWITCH_OAUTH")
    twitch_token = (config.get("twitch") or {}).get("oauth") or ""
    if str(twitch_token).startswith("env:"):
        twitch_env = str(twitch_token)[4:]
        twitch_token = ""
    _report_key([twitch_env], "chat do Twitch", logger, report,
                twitch_token if str(twitch_token) and not str(twitch_token).startswith("env:") else None,
                extra="(o robo conecta so leitura sem ele)")

    if not report["found"]:
        logger("  Dica: copie .env.example para .env e cole as chaves la.")
    return report


def _report_key(names, label, logger, report, config_value=None, extra=""):
    """Imprime o estado das variaveis de uma chave, sem repetir apelidos vazios."""
    import os

    names = list(names)
    defined = [(name, os.environ.get(name, "")) for name in names if os.environ.get(name)]
    if defined:
        name, value = defined[0]
        origem = report["sources"].get(name) or env_sources().get(name) or "ambiente"
        logger(f"    {name:<16} definida ({mask_secret(value)}) via {origem}")
    elif config_value:
        logger(f"    {names[0]:<16} definida no config.json (api_key/oauth) - ok")
    else:
        opcoes = " ou ".join(names)
        logger(f"    {opcoes:<16} NAO DEFINIDA  <-- sem isso o robo nao usa {label} {extra}")


def check_ai(config, logger=print):
    """Testa o provedor de IA: chave, uma chamada de verdade, saldo e modelos."""
    ok = True
    logger("== IA (o cerebro) ==")
    current = config.get("provider", "apinex")
    logger(f"Provedor principal: {current} | reserva: {config.get('fallback_provider', 'offline')}")
    logger(f"Modelo: {config.get('model') or '(padrao do provedor)'} | "
           f"api_key_env: {config.get('api_key_env') or '(nenhum)'}")

    logger("\nProvedores disponiveis:")
    for name in PROVIDER_NAMES:
        info = provider_info(config, name)
        mark = "x" if info["has_key"] else " "
        logger(f"  [{mark}] {name:<10} modelo={info['model']:<26} env={', '.join(info['env']) or '-'}")

    logger("")
    provider = build_provider(config, current)
    if not provider.available():
        logger("[FALHA] " + provider.missing_key_message())
        logger("Dica: sem chave o robo responde com frases prontas (provedor offline).")
        fallback = config.get("fallback_provider", "offline")
        logger(f"(o plano B configurado e '{fallback}', entao o chat nao fica mudo)")
        return False

    logger(f"Chamando {provider.name}/{getattr(provider, 'model', '?')}...")
    try:
        result = provider.chat([{"role": "user", "content": "Responda apenas: ok"}])
        logger(f"  resposta: {result.text!r}")
        logger(f"  usage: {result.usage or 'nao informado'}")
    except Exception as error:
        ok = False
        logger(f"  [FALHA] {error}")
        hint = getattr(error, "hint", "")
        if hint:
            logger(f"  dica: {hint}")

    if hasattr(provider, "balance_usd"):
        balance = provider.balance_usd()
        logger(f"Saldo APInex: {'US$ %.4f' % balance if balance is not None else 'nao disponivel'}")

    if hasattr(provider, "models"):
        free = provider.free_models() if ok else []
        if free:
            logger(f"Modelos gratuitos: {', '.join(free[:8])}...")
    return ok


def run_check(config, logger=print, say=None):
    """Roda o diagnostico completo: IA + Twitch, e explica o que impede de funcionar."""
    logger("== AI vs Streamer - check de configuracao ==")
    describe_env(config, logger)
    logger("")
    ok = check_ai(config, logger)

    logger("\n== Twitch (o chat) ==")
    twitch_ok = check_twitch(config, logger, say=say)

    logger("")
    logger("Resumo:")
    logger(f"  IA .....: {'OK' if ok else 'COM PROBLEMA'}")
    logger(f"  Twitch .: {'OK' if twitch_ok else 'COM PROBLEMA'}")
    if not twitch_ok:
        logger("  -> Sem o Twitch OK o robo pode CONECTAR e mesmo assim NAO responder no chat.")
    return 0 if (ok and twitch_ok) else 1


def check_twitch(config, logger=print, say=None):
    """Testa token/canal e (opcional) manda uma mensagem de teste. True = pode responder."""
    twitch = dict(config.get("twitch") or {})
    if not twitch.get("enabled"):
        logger("Twitch desligada no config.json (twitch.enabled = false).")
        return True

    channel = str(twitch.get("channel") or "").strip()
    if not channel or channel.lower() == "seu_canal":
        logger("[FALHA] twitch.channel nao foi configurado - nao da para entrar em nenhum chat.")
        return False

    client = TwitchChat(twitch, logger=logger)
    logger(f"Canal: #{client.channel} | nick: {client.nickname} | "
           f"token: {'sim' if not client.anonymous else 'NAO'}")

    if client.anonymous:
        logger("[FALHA] Sem token do Twitch: o robo conecta em MODO ANONIMO, le o chat, "
               "mas NAO consegue responder.")
        for line in TOKEN_HELP.splitlines():
            logger("  " + line)
        if client.allow_anonymous_fallback:
            logger("(para testar so a leitura, rode: python main.py --simulate)")
        return False

    logger("Testando login no Twitch...")
    started = time.time()
    ok, message = client.test_login()
    logger(f"  [{ok and 'OK' or 'FALHA'}] {message} ({time.time() - started:.1f}s)")

    try:
        if ok and say:
            logger(f"Enviando mensagem de teste: {say!r}")
            time.sleep(0.5)  # deixa o JOIN chegar na Twitch
            sent = client.send(say, force=True)
            time.sleep(0.5)
            if sent:
                logger("  [OK] mensagem enviada - olhe o seu chat da Twitch!")
            else:
                logger("  [FALHA] a Twitch nao aceitou a mensagem (veja os avisos acima)")
            ok = ok and bool(sent)
        elif ok:
            logger('Dica: use --say "ola chat" para eu mandar uma mensagem de teste no chat.')
    finally:
        client.stop()

    if not ok:
        logger("Confira o token (precisa dos escopos chat:read e chat:edit) e se o canal existe.")
    return bool(ok)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="AI vs Streamer v5 - robo de chat com IA (APInex)")
    parser.add_argument("--config", default=DEFAULT_CONFIG_FILE, help="arquivo de configuracao")
    parser.add_argument("--check", action="store_true", help="valida config/provedor/chave e sai")
    parser.add_argument("--simulate", action="store_true", help="roda no terminal, sem Twitch")
    parser.add_argument("--no-web", action="store_true", help="nao sobe o painel web")
    parser.add_argument("--say", metavar="TEXTO",
                        help="com --check, manda uma mensagem de teste no chat do Twitch")
    return parser.parse_args(argv)


def resolve_config_path(path):
    """Aceita rodar de outra pasta: procura o config.json tambem ao lado do script."""
    import os

    if os.path.isfile(path):
        return path
    if path == DEFAULT_CONFIG_FILE:
        candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
        if os.path.isfile(candidate):
            return candidate
    return path


def main(argv=None):
    import os

    args = parse_args(argv)
    args.config = resolve_config_path(args.config)

    # o .env precisa entrar antes de qualquer coisa (inclusive no --check)
    env_report = load_env(os.path.join(os.path.dirname(os.path.abspath(args.config)), ".env"))
    if not args.check:
        for warning in env_report["warnings"]:
            print(f"[ENV] {warning}")

    try:
        config = load_config(args.config)
    except (OSError, ValueError) as error:
        print(f"Nao consegui ler {args.config}: {error}")
        return 1

    if args.check:
        return run_check(config, say=args.say)

    app = AIvsStreamer(config, simulate=args.simulate, use_web=not args.no_web)
    try:
        return app.run()
    except KeyboardInterrupt:
        app.stop()
        return 0


if __name__ == "__main__":
    sys.exit(main())
