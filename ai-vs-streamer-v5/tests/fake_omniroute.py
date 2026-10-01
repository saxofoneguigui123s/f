"""Servidor HTTP de mentira que imita o OmniRoute local (http://localhost:20128/v1).

Serve para testar o robo com o provedor omnirouter sem instalar o gateway:

    python tests/fake_omniroute.py 20128
    # config.json -> "provider": "omnirouter"
    #                "providers": {"omnirouter": {"base_url": "http://localhost:20128/v1"}}

Ele responde /models (com a rota gratuita oc/deepseek-v4-flash-free), /balance
e /chat/completions no formato da OpenAI.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# catalogo que o gateway falso anuncia (imita as rotas do OmniRoute)
CATALOG = (
    "oc/deepseek-v4-flash-free",
    "oc/big-pickle",
    "auto",
    "auto/cheap",
    "cc/claude-opus-4-6",
    "gg/gemini-2.5-pro",
    "if/kimi-k2-thinking",
)


class FakeOmniRoute:
    """Gateway minimo compativel com a API da OpenAI."""

    def __init__(self, port=20128, require_key=False, catalog=CATALOG, balance=1_000_000):
        self.require_key = require_key
        self.catalog = tuple(catalog)
        self.balance = balance
        self.requests = []
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
                if not outer.require_key:
                    return True
                return "Bearer" in self.headers.get("Authorization", "")

            def do_GET(self):
                outer.requests.append(("GET", self.path, None))
                if not self._authorized():
                    self._send({"error": {"message": "API key required",
                                          "type": "authentication_error"}}, 401)
                    return
                if self.path.endswith("/models"):
                    self._send({"object": "list",
                                "data": [{"id": mid, "object": "model"} for mid in outer.catalog]})
                elif self.path.endswith("/balance"):
                    self._send({"balance_usd": outer.balance})
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
                    self._send({"error": {"message": "API key required",
                                          "type": "authentication_error"}}, 401)
                    return

                if self.path.endswith("/chat/completions"):
                    modelo = payload.get("model", "auto")
                    user = ""
                    for message in payload.get("messages") or []:
                        if message.get("role") == "user":
                            user = str(message.get("content") or "")
                    if modelo not in outer.catalog:
                        self._send({"error": {
                            "message": f"model '{modelo}' nao existe no catalogo",
                            "type": "invalid_request_error"}}, 400)
                        return
                    self._send({
                        "id": "chatcmpl-fake-omni",
                        "object": "chat.completion",
                        "model": modelo,
                        "choices": [{
                            "index": 0, "finish_reason": "stop",
                            "message": {"role": "assistant",
                                        "content": f"(omniroute/{modelo}) recebi: {user[:50]}"},
                        }],
                        "usage": {"prompt_tokens": 24, "completion_tokens": 10, "total_tokens": 34},
                    })
                else:
                    self._send({"error": {"message": "not found"}}, 404)

        class Server(ThreadingHTTPServer):
            allow_reuse_address = True
            daemon_threads = True

        self._server = Server(("127.0.0.1", port), Handler)
        self.port = self._server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}/v1"

    def start(self):
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        try:
            self._server.shutdown()
            self._server.server_close()
        except Exception:
            pass


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 20128
    servidor = FakeOmniRoute(port=porta).start()
    print(f"OmniRoute falso rodando em {servidor.base_url}")
    print(f"Catalogo: {', '.join(servidor.catalog)}")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        servidor.stop()
