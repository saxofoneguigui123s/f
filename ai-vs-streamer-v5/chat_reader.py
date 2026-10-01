"""Leitura e envio de chat (Twitch IRC).

- `ChatReader` e a fachada usada pelo main.py: `read()` devolve [(usuario, mensagem)]
  e `send_message()` manda a mensagem do robo no chat.
- `TwitchChat` fala IRC com a Twitch via TLS (biblioteca padrao, sem dependencias).
  * espera o "001 Welcome" antes de dizer que conectou (nao mente mais no log);
  * se o token estiver invalido, avisa alto e cai para modo anonimo (so leitura);
  * sem token, conecta anonimo: LE o chat mas NAO consegue responder;
  * reconecta sozinho, responde PING e trata RECONNECT.

YouTube ainda nao esta implementado.
"""

from __future__ import annotations

import os
import queue
import random
import socket
import ssl
import threading
import time

from providers import RateLimiter, resolve_secret

TWITCH_HOST = "irc.chat.twitch.tv"
TWITCH_PORT = 6697

TOKEN_HELP = (
    "Para o robo FALAR no chat voce precisa de um token de chat da Twitch:\n"
    "  1) abra https://twitchtokengenerator.com e escolha 'Bot Chat Token'\n"
    "  2) marque os escopos chat:read e chat:edit\n"
    "  3) copie o token e coloque em ai-vs-streamer-v5/.env ->  TWITCH_OAUTH=<token>\n"
    "     (pode ser com ou sem o prefixo 'oauth:')\n"
    "  4) rode: python main.py --check   (ele testa o login e manda um 'ola' de teste)"
)


class TwitchAuthError(RuntimeError):
    """Token invalido/expirado ou login recusado pela Twitch."""

    def __init__(self, message, hint=TOKEN_HELP):
        super().__init__(message)
        self.hint = hint


def resolve_oauth(config):
    """Le o token do Twitch: config -> "env:VARIAVEL" -> campo oauth_env -> ambiente.

    Assim da para escrever no config.json tanto o token direto quanto
    "oauth": "env:TWITCH_OAUTH" (recomendado, mantem o segredo fora do Git).
    """
    config = dict(config or {})
    raw = resolve_secret(str(config.get("oauth") or "").strip())
    if not raw:
        env_name = str(config.get("oauth_env") or "TWITCH_OAUTH").strip()
        raw = resolve_secret(f"env:{env_name}") or os.environ.get(env_name, "")
    return str(raw or "").strip()


def parse_irc_line(line):
    """Traduz uma linha IRC da Twitch.

    Devolve:
        ("message", usuario, texto)  -> PRIVMSG normal
        ("ping", None, None)         -> precisa responder PONG
        ("notice", None, texto)      -> avisos do servidor (ex.: login falhou)
        ("welcome", None, nick)      -> 001: login aceito
        ("reconnect", None, None)    -> servidor pediu reconexao
        None                         -> linha irrelevante
    """
    line = (line or "").strip()
    if not line:
        return None

    tags = {}
    if line.startswith("@"):
        raw_tags, _, line = line.partition(" ")
        for pair in raw_tags[1:].split(";"):
            key, _, value = pair.partition("=")
            tags[key] = value

    prefix = ""
    if line.startswith(":"):
        prefix, _, line = line[1:].partition(" ")
    command, _, rest = line.partition(" ")
    command = command.upper()

    if command == "PING":
        return ("ping", None, None)

    if command == "RECONNECT":
        return ("reconnect", None, None)

    if command == "001":
        nick = rest.split()[0] if rest else ""
        return ("welcome", None, nick)

    if command == "PRIVMSG":
        text = ""
        if " :" in rest:
            _, _, text = rest.partition(" :")
        username = tags.get("display-name") or tags.get("login") or prefix.split("!")[0]
        if not username or not text:
            return None
        return ("message", username, text.strip())

    if command in ("NOTICE", "USERNOTICE"):
        _, _, text = rest.partition(" :")
        text = text.strip() or "aviso do Twitch"
        msg_id = tags.get("msg-id", "")
        if msg_id:
            text = f"{text} [{msg_id}]"
        return ("notice", None, text)

    return None


def looks_like_auth_failure(text):
    """Reconhece as mensagens de token ruim da Twitch."""
    text = (text or "").lower()
    markers = ("login authentication failed", "login unsuccessful", "error logging in",
               "improperly formatted auth", "invalid oauth", "authentication failed")
    return any(marker in text for marker in markers)


class TwitchChat:
    """Conexao IRC com a Twitch (TLS) rodando numa thread."""

    def __init__(self, config=None, logger=print, on_message=None):
        config = dict(config or {})
        self.logger = logger
        self.on_message = on_message
        self.channel = str(config.get("channel") or "").strip().lstrip("#").lower()
        self.nickname = str(config.get("nickname") or "").strip() or self.channel
        self.oauth = resolve_oauth(config)
        self.oauth_env = str(config.get("oauth_env") or "TWITCH_OAUTH")
        self.host = config.get("host", TWITCH_HOST)
        self.port = int(config.get("port", TWITCH_PORT))
        self.use_ssl = bool(config.get("use_ssl", True))
        self.login_timeout = float(config.get("login_timeout", 12))
        # se o token for recusado, continua lendo o chat em modo anonimo
        self.allow_anonymous_fallback = bool(config.get("anonymous_fallback", True))
        self.queue = queue.Queue()
        self.messages_out = []
        self._socket = None
        self._thread = None
        self.running = False
        self.connected = False
        self.logged_in = False
        self.auth_failed = False
        self.auth_error = ""
        self.last_error = None
        self._last_send_warning = 0.0
        self.send_gate = RateLimiter(max_per_minute=int(config.get("send_per_minute", 18)),
                                     min_interval=float(config.get("send_interval", 1.5)))
        self.backlog = list(config.get("backlog") or [])

    # -- estado ---------------------------------------------------------
    @property
    def anonymous(self):
        return not self.oauth

    @property
    def can_send(self):
        """So da para escrever no chat com login de verdade (token valido)."""
        return bool(self.logged_in and not self.anonymous and self.connected)

    def status(self):
        reason = ""
        if self.auth_failed:
            # o motivo importa mais que o sintoma: a Twitch recusou o token
            reason = f"token recusado pela Twitch: {self.auth_error}"
            if self.anonymous:
                reason += " (cai para modo anonimo: so leitura)"
        elif not self.oauth:
            reason = "sem token: modo anonimo (so leitura)"
        elif not self.connected:
            reason = "desconectado (tentando reconectar)"
        return {
            "enabled": self.running,
            "connected": self.connected,
            "logged_in": self.logged_in,
            "can_send": self.can_send,
            "channel": self.channel,
            "nickname": "" if self.anonymous else self.nickname,
            "anonymous": self.anonymous,
            "auth_failed": self.auth_failed,
            "reason": reason,
            "last_error": str(self.last_error) if self.last_error else None,
            "sent": len(self.messages_out),
        }

    # -- ciclo de vida ---------------------------------------------------
    def start(self):
        if self.running:
            return self
        if not self.channel:
            self.logger("[CHAT] Twitch desligada: configure twitch.channel no config.json")
            return None
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="twitch-chat")
        self._thread.start()
        return self

    def stop(self):
        self.running = False
        self._close_socket()
        self.connected = False
        self.logged_in = False

    def _close_socket(self):
        sock, self._socket = self._socket, None
        if not sock:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)  # sem isso o recv() fica travado
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    # -- conexao ---------------------------------------------------------
    def _open_socket(self):
        raw = socket.create_connection((self.host, self.port), timeout=self.login_timeout)
        if self.use_ssl:
            context = ssl.create_default_context()
            raw = context.wrap_socket(raw, server_hostname=self.host)
        return raw

    def _send_raw(self, text):
        sock = self._socket
        if not sock:
            return False
        try:
            sock.sendall((text + "\r\n").encode("utf-8"))
            return True
        except OSError as error:
            self.last_error = error
            self.connected = False
            return False

    def _nickname_to_use(self):
        if self.anonymous:
            return f"justinfan{random.randint(10000, 99999)}"
        return self.nickname

    def _login(self):
        """Conecta e espera o 001 (login aceito). Levanta TwitchAuthError se recusado."""
        self._socket = self._open_socket()
        nickname = self._nickname_to_use()

        if not self.anonymous:
            token = self.oauth if self.oauth.startswith("oauth:") else f"oauth:{self.oauth}"
            self._send_raw(f"PASS {token}")
        self._send_raw(f"NICK {nickname}")
        self._send_raw("CAP REQ :twitch.tv/tags twitch.tv/commands")

        welcome = self._wait_for_welcome(timeout=self.login_timeout)
        self.logged_in = True
        self.auth_failed = False
        self.auth_error = ""
        self.connected = True
        self._send_raw(f"JOIN #{self.channel}")

        if self.anonymous:
            self.logger(f"[CHAT] Twitch conectada em #{self.channel} como {nickname} (anonimo)")
            self._warn_anonymous()
        else:
            self.logger(f"[CHAT] Twitch conectada em #{self.channel} como {welcome or nickname}")

    def _wait_for_welcome(self, timeout=None):
        """Le linhas ate receber 001 (login ok) ou uma falha de login."""
        timeout = float(timeout or self.login_timeout)
        deadline = time.monotonic() + timeout
        buffer = b""
        self._socket.settimeout(max(0.5, timeout))
        try:
            while time.monotonic() < deadline:
                try:
                    data = self._socket.recv(4096)
                except socket.timeout:
                    break
                if not data:
                    raise TwitchAuthError(
                        "a Twitch fechou a conexao antes do login (token invalido ou expirado?)")
                buffer += data
                while b"\r\n" in buffer:
                    raw, _, buffer = buffer.partition(b"\r\n")
                    parsed = parse_irc_line(raw.decode("utf-8", "replace"))
                    if not parsed:
                        continue
                    kind, _, detail = parsed
                    if kind == "welcome":
                        return detail
                    if kind == "ping":
                        self._send_raw("PONG :tmi.twitch.tv")
                    if kind == "notice" and looks_like_auth_failure(detail):
                        raise TwitchAuthError(f"a Twitch recusou o login: {detail}")
        finally:
            if self._socket:
                self._socket.settimeout(None)
        raise TwitchAuthError("a Twitch nao confirmou o login (tempo esgotado)")

    def test_login(self, timeout=None):
        """Testa token + canal. Devolve (ok, mensagem).

        Quando da certo, a conexao FICA ABERTA (com `can_send` verdadeiro) para o
        chamador poder mandar uma mensagem de teste. Feche com `stop()` no final.
        """
        if not self.channel:
            return False, "twitch.channel nao esta configurado"
        if self.anonymous:
            return False, ("sem token configurado - o robo conecta em modo anonimo "
                           "e NAO consegue responder no chat")
        try:
            self._socket = self._open_socket()
            token = self.oauth if self.oauth.startswith("oauth:") else f"oauth:{self.oauth}"
            self._send_raw(f"PASS {token}")
            self._send_raw(f"NICK {self.nickname}")
            self._send_raw("CAP REQ :twitch.tv/tags twitch.tv/commands")
            nick = self._wait_for_welcome(timeout=timeout or self.login_timeout)
            self.connected = True
            self.logged_in = True
            self.auth_failed = False
            self._send_raw(f"JOIN #{self.channel}")
            return True, f"token valido, logado como {nick or self.nickname}"
        except TwitchAuthError as error:
            self._close_socket()
            return False, str(error)
        except Exception as error:  # rede/DNS/TLS
            self._close_socket()
            return False, f"nao consegui conectar em {self.host}:{self.port} ({error})"

    # -- loop --------------------------------------------------------------
    def _loop(self):
        backoff = 2
        while self.running:
            try:
                self._login()
                backoff = 2
                for message in self.backlog:
                    self.queue.put(message)
                self._read_forever()
            except TwitchAuthError as error:
                self.last_error = error
                self.auth_failed = True
                self.auth_error = str(error)
                self.connected = False
                self.logged_in = False
                self._report_auth_failure(error)
            except Exception as error:
                if self.running:
                    self.last_error = error
                    self.logger(f"[CHAT] erro na conexao Twitch: {error}")
            self.connected = False
            self.logged_in = False
            if not self.running:
                break
            self.logger(f"[CHAT] reconectando em {backoff}s...")
            time.sleep(backoff)
            backoff = min(60, backoff * 2)

    def _report_auth_failure(self, error):
        """Avisa o usuario e, se possivel, segue lendo o chat em modo anonimo."""
        self.logger("=" * 68)
        self.logger(f"[CHAT] !!! TOKEN DO TWITCH RECUSADO: {error}")
        if self.allow_anonymous_fallback:
            self.oauth = ""
            self.logger("[CHAT] !!! Vou seguir em MODO ANONIMO: leio o chat, "
                        "mas o robo NAO consegue responder.")
        self.logger("=" * 68)
        for line in TOKEN_HELP.splitlines():
            self.logger(f"[CHAT] {line}")
        self.logger("=" * 68)

    def _warn_anonymous(self):
        self.logger("=" * 68)
        self.logger("[CHAT] !!! SEM TOKEN: modo anonimo (so leitura).")
        self.logger("[CHAT] !!! O robo vai LER o chat, mas NAO consegue ESCREVER nele.")
        for line in TOKEN_HELP.splitlines():
            self.logger(f"[CHAT] {line}")
        self.logger("=" * 68)

    def _read_forever(self):
        buffer = b""
        while self.running:
            data = self._socket.recv(4096)
            if not data:
                raise ConnectionError("conexao encerrada pelo Twitch")
            buffer += data
            while b"\r\n" in buffer:
                raw, _, buffer = buffer.partition(b"\r\n")
                self._handle_line(raw.decode("utf-8", "replace"))

    def _handle_line(self, line):
        parsed = parse_irc_line(line)
        if not parsed:
            return
        kind, username, text = parsed
        if kind == "ping":
            self._send_raw("PONG :tmi.twitch.tv")
        elif kind == "reconnect":
            self.logger("[CHAT] a Twitch pediu reconexao")
            self._close_socket()
        elif kind == "message":
            self.queue.put((username, text))
            if self.on_message:
                self.on_message(username, text)
        elif kind == "notice":
            self.logger(f"[CHAT] Twitch avisa: {text}")
            if looks_like_auth_failure(text):
                self._close_socket()

    # -- envio -----------------------------------------------------------
    def send(self, text, force=False):
        text = (text or "").strip()
        if not text:
            return False
        if not self.can_send:
            self._warn_cannot_send(text)
            return False
        if not force and not self.send_gate.allow():
            self.logger("[CHAT] limite de envio atingido; mensagem descartada")
            return False
        self.send_gate.register()
        for chunk in split_message(text, 480):
            self._send_raw(f"PRIVMSG #{self.channel} :{chunk}")
        self.messages_out.append(text)
        self.messages_out = self.messages_out[-50:]
        return True

    def _warn_cannot_send(self, text):
        """Explica (no maximo 1x por minuto) por que a mensagem nao foi enviada."""
        now = time.monotonic()
        if now - self._last_send_warning < 60:
            return
        self._last_send_warning = now
        if self.anonymous:
            self.logger(f"[CHAT] NAO ENVIEI \"{text[:60]}\": estou sem token (modo anonimo).")
            self.logger("[CHAT] " + TOKEN_HELP.splitlines()[0])
        elif self.auth_failed:
            self.logger(f"[CHAT] NAO ENVIEI \"{text[:60]}\": token recusado ({self.auth_error}).")
        elif not self.connected:
            self.logger(f"[CHAT] NAO ENVIEI \"{text[:60]}\": Twitch desconectada, tentando reconectar...")
        else:
            self.logger(f"[CHAT] NAO ENVIEI \"{text[:60]}\": login ainda nao confirmado.")


def split_message(text, limit=480):
    """Quebra mensagens longas em pedacos (limite do Twitch ~500 caracteres)."""
    text = (text or "").strip()
    if len(text) <= limit:
        return [text] if text else []
    chunks, current = [], ""
    for word in text.split():
        if len(current) + len(word) + 1 > limit:
            chunks.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        chunks.append(current)
    return chunks


class ChatReader:
    """Fachada de chat do robo (Twitch + fila local)."""

    def __init__(self, config=None, logger=print):
        self.config = config or {}
        self.logger = logger
        self.queue = queue.Queue()
        twitch_config = dict(self.config.get("twitch") or {})
        self.twitch_config = twitch_config
        self.twitch = None
        self.last_sent = []
        if twitch_config.get("enabled"):
            self.twitch = TwitchChat(twitch_config, logger=logger, on_message=self._enqueue)

    def _enqueue(self, username, message):
        self.queue.put((username, message))

    def start(self):
        if self.twitch:
            self.twitch.start()
        return self

    def stop(self):
        if self.twitch:
            self.twitch.stop()

    def read(self):
        """Drena a fila e devolve as mensagens novas."""
        messages = []
        while True:
            try:
                messages.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return messages

    def feed(self, username, message):
        """Injeta uma mensagem manualmente (usado pelos testes/simulador)."""
        self._enqueue(username, message)

    def send_message(self, message):
        self.last_sent.append(message)
        self.last_sent = self.last_sent[-50:]
        if self.twitch:
            return self.twitch.send(message)
        self.logger(f"[CHAT] {message}")
        return True

    @property
    def can_send(self):
        return self.twitch.can_send if self.twitch else True

    def status(self):
        return {
            "twitch": self.twitch.status() if self.twitch else {"enabled": False},
            "can_send": self.can_send,
            "queued": self.queue.qsize(),
        }
