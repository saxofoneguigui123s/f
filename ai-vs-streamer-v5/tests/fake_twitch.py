"""Servidor IRC de mentira que imita a Twitch, para testar o chat sem internet."""

from __future__ import annotations

import socketserver
import threading
import time

VALID_TOKEN = "oauth:token_valido"


class FakeTwitchServer:
    """Aceita conexoes, valida o token e guarda o que o robo mandou."""

    def __init__(self, port=0, valid_token=VALID_TOKEN, fail_login=False, silent=False):
        self.valid_token = valid_token
        self.fail_login = fail_login
        self.silent = silent          # se True, nunca manda o 001 (login travado)
        self.received = []
        self.connections = 0
        self._handle = None
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                outer.connections += 1
                outer._handle = self
                nick, token = "?", ""
                while True:
                    line = self.rfile.readline()
                    if not line:
                        return
                    text = line.decode("utf-8", "replace").strip()
                    outer.received.append(text)
                    if text.startswith("PASS "):
                        token = text[5:].strip()
                    elif text.startswith("NICK "):
                        nick = text[5:].strip()
                        if outer.fail_login or (token and token != outer.valid_token):
                            self.wfile.write(
                                b":tmi.twitch.tv NOTICE * :Login authentication failed\r\n")
                            self.wfile.flush()
                            time.sleep(0.2)
                            return
                        if not outer.silent:
                            self.wfile.write(
                                f":tmi.twitch.tv 001 {nick} :Welcome, GLHF!\r\n".encode())
                            self.wfile.flush()
                        break
                while True:
                    line = self.rfile.readline()
                    if not line:
                        return
                    text = line.decode("utf-8", "replace").strip()
                    outer.received.append(text)
                    if text.startswith("PING"):
                        self.wfile.write(b"PONG :tmi.twitch.tv\r\n")
                        self.wfile.flush()

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True     # sem isso o server_close() trava

        self._server = Server(("127.0.0.1", port), Handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    # -- utilidades -----------------------------------------------------
    def wait_for_connection(self, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._handle is not None:
                return True
            time.sleep(0.02)
        return False

    def say(self, user, text, display=None):
        """Manda uma mensagem como se fosse alguem do chat."""
        handle = self._handle
        if not handle:
            return False
        display = display or user.capitalize()
        line = (f"@badges=;display-name={display};login={user} "
                f":{user}!{user}@{user}.tmi.twitch.tv PRIVMSG #canal :{text}\r\n")
        handle.wfile.write(line.encode())
        handle.wfile.flush()
        return True

    def ping(self):
        if self._handle:
            self._handle.wfile.write(b"PING :tmi.twitch.tv\r\n")
            self._handle.wfile.flush()

    def sent_messages(self):
        """PRIVMSG que o robo enviou."""
        out = []
        for line in list(self.received):
            if "PRIVMSG #canal :" in line:
                out.append(line.split("PRIVMSG #canal :", 1)[1])
        return out

    def stop(self):
        try:
            self._server.shutdown()
            self._server.server_close()
        except Exception:
            pass


def twitch_config(port, **overrides):
    config = {
        "enabled": True,
        "channel": "canal",
        "host": "127.0.0.1",
        "port": port,
        "use_ssl": False,
        "oauth": VALID_TOKEN,
        "oauth_env": "TWITCH_OAUTH_TESTE_QUE_NAO_EXISTE",
        "login_timeout": 3,
        "send_interval": 0,
        "send_per_minute": 0,
    }
    config.update(overrides)
    return config
