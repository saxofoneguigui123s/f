"""Servidor HTTP de mentira que imita a API do APInex.

Serve para dois usos:
  1) testes (sem internet e sem gastar saldo);
  2) dry run de verdade: suba este servidor e aponte o config para ele, assim
     voce ve o robo inteiro funcionando antes de colocar sua key real.

Rodar na mao:
    python tests/fake_apinex.py 8099
e no config.json:
    "providers": {"apinex": {"base_url": "http://127.0.0.1:8099/v1"}},
    "api_key": "sk-apx_teste"
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VALID_KEY_HINT = "sk-apx_teste"      # qualquer key que contenha isso e aceita
BALANCE_USD = 3.50


class FakeAPInex:
    """Servidor compativel com /chat/completions, /models, /balance e /tools/web/search."""

    def __init__(self, port=8099, required_key=VALID_KEY_HINT, balance=BALANCE_USD):
        self.required_key = required_key
        self.balance = balance
        self.requests = []
        self.prompts = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _send(self, payload, status=200):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _authorized(self):
                auth = self.headers.get("Authorization", "") + self.headers.get("x-api-key", "")
                return outer.required_key in auth

            def do_GET(self):
                outer.requests.append(("GET", self.path, None))
                if not self._authorized():
                    self._send({"error": {"message": "Missing API key",
                                          "type": "authentication_error"}}, 401)
                    return
                if self.path.endswith("/balance"):
                    self._send({"balance_usd": outer.balance, "reserved_usd": 0.0})
                elif self.path.endswith("/models"):
                    self._send({"data": [{"id": "free/gpt-6-luna"}, {"id": "gpt-5.6-terra"},
                                         {"id": "free/gemini-3.8-flash"}, {"id": "free/kimi-k3"}]})
                else:
                    self._send({"error": {"message": "not found"}}, 404)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    payload = json.loads(raw or b"{}")
                except ValueError:
                    payload = {}
                outer.requests.append(("POST", self.path, payload))

                if not self._authorized():
                    self._send({"error": {"message": "Missing API key",
                                          "type": "authentication_error"}}, 401)
                    return

                if self.path.endswith("/chat/completions"):
                    messages = payload.get("messages") or []
                    user = ""
                    for message in messages:
                        if message.get("role") == "user":
                            user = str(message.get("content") or "")
                    outer.prompts.append(messages)
                    self._send({
                        "id": "chatcmpl-fake",
                        "object": "chat.completion",
                        "model": payload.get("model", "fake"),
                        "choices": [{
                            "index": 0, "finish_reason": "stop",
                            "message": {"role": "assistant",
                                        "content": f"(fake) recebi: {user[:60]}"},
                        }],
                        "usage": {"prompt_tokens": 31, "completion_tokens": 9, "total_tokens": 40},
                    })
                elif self.path.endswith("/tools/web/search"):
                    self._send({"results": [
                        {"title": "Noticia de teste", "url": "https://exemplo.com", "snippet": "s"}]})
                else:
                    self._send({"error": {"message": "not found"}}, 404)

        class Server(ThreadingHTTPServer):
            allow_reuse_address = True
            daemon_threads = True

        self._server = Server(("127.0.0.1", port), Handler)
        self.port = self._server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        try:
            self._server.shutdown()
            self._server.server_close()
        except Exception:
            pass


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    servidor = FakeAPInex(port=porta).start()
    print(f"APInex falso rodando em {servidor.base_url}")
    print('Use "api_key": "sk-apx_teste" no config.json para testar.')
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        servidor.stop()
