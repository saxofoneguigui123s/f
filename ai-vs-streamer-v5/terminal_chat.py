"""Chat de terminal - testa o robo (e o provedor de IA) sem Twitch.

Rode `python main.py --simulate` e digite no terminal como se fosse o chat:
    voce> oi robo
    [AI] Oi! Pronto pra atrapalhar ou pra ajudar?
"""

from __future__ import annotations

import queue
import sys
import threading
import time


class TerminalChat:
    """Mesma interface do ChatReader, mas lendo do teclado."""

    def __init__(self, nickname="voce", logger=print):
        self.nickname = nickname
        self.logger = logger
        self.queue = queue.Queue()
        self.last_sent = []
        self.running = False
        self.stdin_closed = False
        self._thread = None

    def start(self):
        if self.running:
            return self
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="terminal-chat")
        self._thread.start()
        self.logger("[SIM] Chat simulado. Digite uma mensagem e aperte Enter (Ctrl+C para sair).")
        self.logger("[SIM] Dica: digite '!help' para ver os comandos do robo.")
        return self

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running:
            try:
                line = input()
            except KeyboardInterrupt:
                self.running = False
                break
            except EOFError:
                # sem terminal (ex.: rodando em segundo plano): segue servindo o painel web
                if not self.stdin_closed:
                    self.stdin_closed = True
                    self.logger("[SIM] sem entrada no terminal; use o painel web ou reinicie interativo.")
                time.sleep(0.5)
                continue
            line = (line or "").strip()
            if not line:
                continue
            if ":" in line and len(line.split(":", 1)[0].split()) == 1:
                user, text = line.split(":", 1)
                self.queue.put((user.strip() or self.nickname, text.strip()))
            else:
                self.queue.put((self.nickname, line))

    def read(self):
        messages = []
        while True:
            try:
                messages.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return messages

    def feed(self, username, message):
        self.queue.put((username, message))

    def send_message(self, message):
        self.last_sent.append(message)
        self.last_sent = self.last_sent[-50:]
        sys.stdout.write(f"[BOT] {message}\n")
        sys.stdout.flush()
        return True

    def status(self):
        return {
            "twitch": {"enabled": False, "simulated": True},
            "can_send": True,   # no terminal o robo sempre "fala"
            "queued": self.queue.qsize(),
        }
