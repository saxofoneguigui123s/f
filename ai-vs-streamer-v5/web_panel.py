"""Painel web completo - controle pelo navegador."""

import threading
from flask import Flask, jsonify, redirect, request

class WebPanel:
    def __init__(self, app, config):
        self.app_ref = app
        self.config = config
        self.flask = Flask(__name__)
        self._setup_routes()

    def _setup_routes(self):
        f = self.flask

        @f.route("/")
        def home():
            return redirect("/admin")

        @f.route("/admin")
        def admin():
            info = self.app_ref.ai.status()
            return (
                "<h1>Painel Admin</h1>"
                f"<p>Modo: {self.app_ref.voting.get_mode()}</p>"
                f"<p>IA: {info['provider']} / {info['model']} "
                f"({'ok' if info['available'] else 'sem chave'})</p>"
                f"<p>Reserva: {info['fallback']} | memorias: {info['memories']} | "
                f"erros: {info['stats']['errors']}</p>"
                "<p><a href='/chat'>Chat da IA</a> | <a href='/api/status'>/api/status</a> | "
                "<a href='/api/ai'>/api/ai</a></p>"
            )

        @f.route("/chat")
        def chat():
            entries = self.app_ref.history.get_recent(50)
            html = "<h1>Chat da IA</h1>"
            for e in entries:
                html += f"<p><b>{e['author']}</b> [{e['kind']}]: {e['text']}</p>"
            return html

        @f.route("/api/status")
        def status():
            return jsonify({
                "mode": self.app_ref.voting.get_mode(),
                "time_left": self.app_ref.voting.time_left(),
                "difficulty": self.app_ref.difficulty.get_level(),
                "chaos": self.config.get("chaos_mode", False),
                "chat": self.app_ref.chat.status(),
                "ai": self.app_ref.ai.status()
            })

        @f.route("/api/ai")
        def ai_status():
            return jsonify(self.app_ref.ai.status())

        @f.route("/api/command", methods=["POST"])
        def command():
            data = request.get_json()
            cmd = data.get("command", "")
            if cmd == "force_troll":
                self.app_ref.voting.force_mode("troll")
                return jsonify({"ok": True})
            if cmd == "force_chat":
                self.app_ref.voting.force_mode("chat")
                return jsonify({"ok": True})
            if cmd == "chaos_on":
                self.app_ref.voting.set_interval(self.config["chaos_interval"])
                return jsonify({"ok": True})
            if cmd == "chaos_off":
                self.app_ref.voting.set_interval(self.config["voting_interval"])
                return jsonify({"ok": True})
            if cmd == "say":
                text = str(data.get("text", "")).strip()
                self.app_ref.ai.speak(text)
                self.app_ref.chat.send_message(text)
                return jsonify({"ok": True, "said": text})
            if cmd == "ai_ask":
                question = str(data.get("text", "")).strip()
                answer = self.app_ref.ai.ask(question, username="painel")
                return jsonify({"ok": bool(answer), "answer": answer,
                                "provider": self.app_ref.ai.status()["provider"]})
            return jsonify({"ok": False, "error": "comando desconhecido"})

    def start(self):
        import os

        web = self.config.get("web", {})
        # variaveis de ambiente permitem sobrescrever sem editar o config
        host = os.environ.get("WEB_HOST") or web.get("host", "localhost")
        port = int(os.environ.get("WEB_PORT") or web.get("port", 8080))
        threading.Thread(
            target=self.flask.run,
            kwargs={"host": host, "port": port, "debug": False, "threaded": True,
                    "use_reloader": False},
            daemon=True,
        ).start()
        print(f"Painel web: http://{host}:{port}/admin")
