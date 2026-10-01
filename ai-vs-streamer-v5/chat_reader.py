"""Leitura e envio de chat (Twitch IRC).

- `ChatReader` e a fachada usada pelo main.py: `read()` devolve [(usuario, mensagem)]
  e `send_message()` manda a mensagem do robo no chat.
- `TwitchChat` fala IRC com a Twitch via TLS (biblioteca padrao, sem dependencias),
  com reconexao automatica, resposta a PING e limite de envio.
- Sem token o robo entra em modo anonimo (so le, nao escreve) - util para testar.

YouTube ainda nao esta implementado (o stub antigo nao fazia nada).
"""

from __future__ import annotations

import os
import queue
import random
import socket
import ssl
import threading
import time

from providers import RateLimiter

TWITCH_HOST = "irc.chat.twitch.tv"
TWITCH_PORT = 6697


def parse_irc_line(line):
    """Traduz uma linha IRC da Twitch.

    Devolve:
        ("message", usuario, texto)  -> PRIVMSG normal
        ("ping", None, None)         -> precisa responder PONG
        ("notice", None, texto)      -> avisos do servidor (ex.: login falhou)
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

    if command == "PING":
        return ("ping", None, None)

    if command == "PRIVMSG":
        text = ""
        if " :" in rest:
            target, _, text = rest.partition(" :")
        username = tags.get("display-name") or tags.get("login") or prefix.split("!")[0]
        if not username or not text:
            return None
        return ("message", username, text.strip())

    if command in ("NOTICE", "USERNOTICE"):
        _, _, text = rest.partition(" :")
        return ("notice", None, text.strip() or "aviso do Twitch")

    return None


class TwitchChat:
    """Conexao IRC com a Twitch (TLS) rodando numa thread."""

    def __init__(self, config=None, logger=print, on_message=None):
        config = dict(config or {})
        self.logger = logger
        self.on_message = on_message
        self.channel = str(config.get("channel") or "").strip().lstrip("#").lower()
        self.nickname = str(config.get("nickname") or "").strip() or self.channel
        self.oauth = str(
            config.get("oauth")
            or os.environ.get(config.get("oauth_env") or "TWITCH_OAUTH", "")
            or ""
        ).strip()
        self.host = config.get("host", TWITCH_HOST)
        self.port = int(config.get("port", TWITCH_PORT))
        self.use_ssl = bool(config.get("use_ssl", True))
        self.queue = queue.Queue()
        self.messages_out = []
        self._socket = None
        self._thread = None
        self.running = False
        self.connected = False
        self.send_gate = RateLimiter(max_per_minute=int(config.get("send_per_minute", 18)),
                                     min_interval=float(config.get("send_interval", 1.5)))
        self.backlog = list(config.get("backlog") or [])
        self.last_error = None

    # -- estado ---------------------------------------------------------
    @property
    def anonymous(self):
        return not self.oauth

    def status(self):
        return {
            "enabled": self.running,
            "connected": self.connected,
            "channel": self.channel,
            "anonymous": self.anonymous,
            "last_error": str(self.last_error) if self.last_error else None,
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
        try:
            if self._socket:
                self._socket.close()
        except OSError:
            pass
        self.connected = False

    # -- conexao ---------------------------------------------------------
    def _open_socket(self):
        raw = socket.create_connection((self.host, self.port), timeout=30)
        if self.use_ssl:
            context = ssl.create_default_context()
            raw = context.wrap_socket(raw, server_hostname=self.host)
        raw.settimeout(None)
        return raw

    def _send_raw(self, text):
        if not self._socket:
            return False
        try:
            self._socket.sendall((text + "\r\n").encode("utf-8"))
            return True
        except OSError as error:
            self.last_error = error
            self.connected = False
            return False

    def _login(self):
        self._socket = self._open_socket()
        nickname = self.nickname
        if self.anonymous:
            nickname = f"justinfan{random.randint(10000, 99999)}"
            self.logger(f"[CHAT] Twitch em modo anonimo (so leitura) no canal #{self.channel}")
        else:
            token = self.oauth if self.oauth.startswith("oauth:") else f"oauth:{self.oauth}"
            self._send_raw(f"PASS {token}")
        self._send_raw(f"NICK {nickname}")
        self._send_raw("CAP REQ :twitch.tv/tags twitch.tv/commands")
        self._send_raw(f"JOIN #{self.channel}")
        self.connected = True
        self.logger(f"[CHAT] Twitch conectada em #{self.channel} como {nickname}")

    def _loop(self):
        backoff = 2
        while self.running:
            try:
                self._login()
                backoff = 2
                for message in self.backlog:
                    self.queue.put(message)
                self._read_forever()
            except Exception as error:
                self.last_error = error
                self.logger(f"[CHAT] erro na conexao Twitch: {error}")
            self.connected = False
            if not self.running:
                break
            self.logger(f"[CHAT] reconectando em {backoff}s...")
            time.sleep(backoff)
            backoff = min(60, backoff * 2)

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
        elif kind == "message":
            item = (username, text)
            self.queue.put(item)
            if self.on_message:
                self.on_message(*item)
        elif kind == "notice":
            self.logger(f"[CHAT] Twitch avisa: {text}")

    # -- envio -----------------------------------------------------------
    def send(self, text, force=False):
        text = (text or "").strip()
        if not text:
            return False
        if not self.connected or not self._socket:
            self.logger(f"[CHAT] (offline) {text}")
            return False
        if self.anonymous:
            self.logger("[CHAT] sem token: nao da para enviar mensagens no Twitch")
            return False
        if not force and not self.send_gate.allow():
            self.logger("[CHAT] limite de envio atingido; mensagem descartada")
            return False
        self.send_gate.register()
        for chunk in split_message(text, 480):
            self._send_raw(f"PRIVMSG #{self.channel} :{chunk}")
        self.messages_out.append(text)
        return True


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

    def status(self):
        return {
            "twitch": self.twitch.status() if self.twitch else {"enabled": False},
            "queued": self.queue.qsize(),
        }
