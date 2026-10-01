"""Painel web completo - controle pelo navegador.

Paginas:
    /            -> redireciona para /admin
    /admin       -> dashboard (status da IA, do chat, votacao, botoes)
    /chat        -> historico do que o robo falou
APIs:
    GET  /api/status      -> modo, tempo, IA, chat, dificuldade
    GET  /api/ai          -> estado do provedor de IA
    GET  /api/history     -> ultimas mensagens do robo
    POST /api/command     -> force_troll, force_chat, chaos_on, chaos_off, say, ai_ask
"""

from __future__ import annotations

import threading

from flask import Flask, jsonify, redirect, request

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI vs Streamer - Painel</title>
<style>
  :root { --bg:#0f1117; --card:#181b25; --line:#262b38; --txt:#e6e8ef;
          --dim:#8b93a7; --ok:#39d98a; --warn:#f0b429; --bad:#f2555a; --accent:#6c8cff; }
  * { box-sizing:border-box; }
  body { margin:0; padding:24px; background:var(--bg); color:var(--txt);
         font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
  h1 { font-size:20px; margin:0 0 4px; }
  .sub { color:var(--dim); font-size:13px; margin-bottom:20px; }
  .grid { display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }
  .card h2 { font-size:12px; text-transform:uppercase; letter-spacing:.08em;
             color:var(--dim); margin:0 0 10px; font-weight:600; }
  .big { font-size:22px; font-weight:600; }
  .row { display:flex; justify-content:space-between; gap:10px; padding:3px 0; font-size:14px; }
  .row span:first-child { color:var(--dim); }
  .pill { display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px;
          font-weight:600; border:1px solid transparent; }
  .ok   { background:rgba(57,217,138,.14); color:var(--ok);   border-color:rgba(57,217,138,.35); }
  .warn { background:rgba(240,180,41,.14); color:var(--warn); border-color:rgba(240,180,41,.35); }
  .bad  { background:rgba(242,85,90,.14);  color:var(--bad);  border-color:rgba(242,85,90,.35); }
  .buttons { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
  button { background:#222738; color:var(--txt); border:1px solid var(--line); border-radius:8px;
           padding:8px 12px; font-size:13px; cursor:pointer; }
  button:hover { border-color:var(--accent); }
  button.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
  textarea, input { width:100%; background:#12141c; color:var(--txt); border:1px solid var(--line);
                    border-radius:8px; padding:9px; font:inherit; resize:vertical; }
  .feed { max-height:260px; overflow:auto; font-size:13px; }
  .feed div { padding:4px 0; border-bottom:1px solid var(--line); }
  .feed b { color:var(--accent); }
  code { background:#12141c; padding:1px 5px; border-radius:5px; font-size:12px; }
</style>
</head>
<body>
  <h1>AI vs Streamer <span id="mode" class="pill ok">chat</span></h1>
  <div class="sub">Painel local do robo &middot; atualiza sozinho a cada 3s &middot;
    <a href="/chat" style="color:var(--accent)">chat da IA</a></div>

  <div class="grid">
    <div class="card">
      <h2>Votacao</h2>
      <div class="big" id="timer">--</div>
      <div class="row"><span>Modo atual</span><span id="mode2">-</span></div>
      <div class="row"><span>Dificuldade do troll</span><span id="difficulty">-</span></div>
      <div class="row"><span>Modo caos</span><span id="chaos">-</span></div>
      <div class="buttons">
        <button onclick="cmd('force_chat')">Forcar CHAT</button>
        <button onclick="cmd('force_troll')">Forcar TROLL</button>
        <button onclick="cmd('chaos_on')">Caos ON</button>
        <button onclick="cmd('chaos_off')">Caos OFF</button>
      </div>
    </div>

    <div class="card">
      <h2>IA</h2>
      <div class="big" id="provider">-</div>
      <div class="row"><span>Modelo</span><span id="model">-</span></div>
      <div class="row"><span>Endpoint</span><span id="endpoint">-</span></div>
      <div class="row"><span>Estado</span><span id="ai-state">-</span></div>
      <div class="row"><span>Reserva</span><span id="fallback">-</span></div>
      <div class="row"><span>Erros / respostas</span><span id="stats">-</span></div>
    </div>

    <div class="card">
      <h2>Chat (Twitch)</h2>
      <div class="big" id="chat-state">-</div>
      <div class="row"><span>Canal</span><span id="channel">-</span></div>
      <div class="row"><span>Mensagens enviadas</span><span id="sent">-</span></div>
      <div class="row"><span>Memorias</span><span id="memories">-</span></div>
    </div>

    <div class="card">
      <h2>Falar pelo painel</h2>
      <textarea id="say-text" rows="2" placeholder="mensagem para o robo falar no chat"></textarea>
      <div class="buttons">
        <button class="primary" onclick="sayIt()">Falar no chat</button>
      </div>
      <textarea id="ask-text" rows="2" placeholder="pergunte algo para a IA (nao vai pro chat)"
                style="margin-top:10px"></textarea>
      <div class="buttons">
        <button onclick="askIt()">Perguntar a IA</button>
      </div>
      <div id="answer" style="margin-top:10px;font-size:13px;color:var(--dim)"></div>
    </div>

    <div class="card" style="grid-column:1/-1">
      <h2>Ultimas mensagens do robo</h2>
      <div class="feed" id="feed"><em style="color:var(--dim)">carregando...</em></div>
    </div>
  </div>

<script>
const $ = (id) => document.getElementById(id);

function pill(el, ok, texto) {
  el.className = 'pill ' + (ok ? 'ok' : 'warn');
  el.textContent = texto;
}

async function refresh() {
  try {
    const d = await (await fetch('/api/status')).json();
    const ai = d.ai, chat = d.chat || {}, tw = chat.twitch || {};

    $('timer').textContent = d.time_left + 's';
    $('mode2').textContent = d.mode;
    $('difficulty').textContent = d.difficulty;
    $('chaos').textContent = d.chaos ? 'ligado' : 'desligado';
    pill($('mode'), d.mode !== 'troll', d.mode);

    $('provider').textContent = ai.provider + (ai.model ? ' / ' + ai.model : '');
    $('model').textContent = ai.model || '-';
    $('endpoint').textContent = ai.endpoint || '-';
    pill($('ai-state'), ai.available, ai.available ? 'ok' : 'sem chave');
    $('fallback').textContent = ai.fallback || '-';
    $('stats').textContent = ai.stats.errors + ' / ' + ai.stats.requests;
    $('memories').textContent = ai.memories;

    if (tw.simulated) pill($('chat-state'), true, 'simulado');
    else if (!tw.enabled) pill($('chat-state'), false, 'desligado');
    else if (chat.can_send) pill($('chat-state'), true, 'pode responder');
    else pill($('chat-state'), false, tw.reason || 'sem login');
    $('channel').textContent = tw.channel ? '#' + tw.channel : '-';
    $('sent').textContent = tw.sent ?? '-';
  } catch (e) { /* painel segue tentando */ }

  try {
    const h = await (await fetch('/api/history')).json();
    $('feed').innerHTML = h.entries.map(e =>
      `<div><b>${e.author}</b> <span style="color:var(--dim)">[${e.kind}]</span> ${escapeHtml(e.text)}</div>`
    ).join('') || '<em style="color:var(--dim)">nada ainda</em>';
  } catch (e) {}
}

function escapeHtml(t) {
  return String(t).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}

async function cmd(nome, extra) {
  const body = Object.assign({command: nome}, extra || {});
  const r = await (await fetch('/api/command', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  })).json();
  refresh();
  return r;
}

async function sayIt() {
  const texto = $('say-text').value.trim();
  if (!texto) return;
  await cmd('say', {text: texto});
  $('say-text').value = '';
}

async function askIt() {
  const texto = $('ask-text').value.trim();
  if (!texto) return;
  $('answer').textContent = 'pensando...';
  const r = await cmd('ai_ask', {text: texto});
  $('answer').textContent = r.answer ? 'IA: ' + r.answer : 'a IA nao respondeu (veja o console)';
}

refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>
"""


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
            return DASHBOARD_HTML

        @f.route("/chat")
        def chat():
            entries = self.app_ref.history.get_recent(50)
            html = ("<!DOCTYPE html><meta charset='utf-8'><title>Chat da IA</title>"
                    "<body style='background:#0f1117;color:#e6e8ef;font:15px system-ui;padding:24px'>"
                    "<h1>Chat da IA</h1><p><a href='/admin' style='color:#6c8cff'>voltar ao painel</a></p>")
            for entry in entries:
                html += (f"<p><b style='color:#6c8cff'>{entry['author']}</b> "
                         f"<span style='color:#8b93a7'>[{entry['kind']}]</span> {entry['text']}</p>")
            return html + "</body>"

        @f.route("/api/status")
        def status():
            return jsonify({
                "mode": self.app_ref.voting.get_mode(),
                "time_left": self.app_ref.voting.time_left(),
                "difficulty": self.app_ref.difficulty.get_level(),
                "chaos": self.config.get("chaos_mode", False),
                "chat": self.app_ref.chat.status(),
                "ai": self.app_ref.ai.status(),
            })

        @f.route("/api/ai")
        def ai_status():
            return jsonify(self.app_ref.ai.status())

        @f.route("/api/history")
        def history():
            return jsonify({"entries": self.app_ref.history.get_recent(30)})

        @f.route("/api/command", methods=["POST"])
        def command():
            data = request.get_json(silent=True) or {}
            cmd = str(data.get("command", ""))
            if cmd == "force_troll":
                self.app_ref.voting.force_mode("troll")
                return jsonify({"ok": True})
            if cmd == "force_chat":
                self.app_ref.voting.force_mode("chat")
                return jsonify({"ok": True})
            if cmd == "chaos_on":
                self.app_ref.voting.set_interval(self.config["chaos_interval"])
                self.config["chaos_mode"] = True
                return jsonify({"ok": True})
            if cmd == "chaos_off":
                self.app_ref.voting.set_interval(self.config["voting_interval"])
                self.config["chaos_mode"] = False
                return jsonify({"ok": True})
            if cmd == "say":
                text = str(data.get("text", "")).strip()
                if not text:
                    return jsonify({"ok": False, "error": "texto vazio"})
                self.app_ref.ai.speak(text)
                enviado = self.app_ref.chat.send_message(text)
                self.app_ref.history.add("PAINEL", text, "say")
                return jsonify({"ok": True, "said": text, "sent_to_chat": bool(enviado)})
            if cmd == "ai_ask":
                question = str(data.get("text", "")).strip()
                answer = self.app_ref.ai.ask(question, username="painel")
                if answer:
                    self.app_ref.history.add("PAINEL", question, "ask")
                    self.app_ref.history.add("AI", answer, "ask")
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
