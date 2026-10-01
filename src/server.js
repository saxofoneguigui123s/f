/**
 * server.js — HTTP + WebSocket.
 *
 *   /                 → PAINEL do streamer (controles + IA + system prompt)
 *   /overlay.html     → OVERLAY para o OBS (1920x1080, fundo transparente)
 *   /robo.html        → ROSTO do robô (avatar que fala), também pro OBS
 *   /answer           → site de respostas "IA responde" (link compartilhável)
 *   /api/...          → API REST + WebSocket em /ws
 *
 * Todo o estado sai por WebSocket: painel e overlay atualizam sozinhos.
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { WebSocketServer } from 'ws';
import { PUBLIC_DIR, config, redactedConfig } from './config.js';
import { log, recentLogs } from './log.js';
import { state, bus, snapshot } from './state.js';
import { chatlog } from './game/chatlog.js';
import * as round from './game/round.js';
import { voting } from './game/voting.js';
import { promptStore } from './prompt-store.js';
import { aiStatus, testAi, listModels, PRESETS } from './ai/llm.js';
import { hub } from './chat/source.js';
import { answerQuestion } from './ai/answer.js';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.webmanifest': 'application/manifest+json',
  '.txt': 'text/plain; charset=utf-8',
  '.woff2': 'font/woff2',
};

export function createServer() {
  const server = http.createServer(handleRequest);
  const wss = new WebSocketServer({ server, path: '/ws' });

  wss.on('connection', (ws) => {
    ws.send(JSON.stringify({ type: 'hello', state: snapshot(), logs: recentLogs(60), prompt: promptStore.get(), ai: aiStatus() }));
    ws.on('message', (buf) => {
      try {
        const msg = JSON.parse(buf.toString());
        if (msg.type === 'ping') ws.send(JSON.stringify({ type: 'pong', t: Date.now() }));
        if (msg.type === 'speak') round.talkNow(msg.mode || state.mode, 'painel');
        if (msg.type === 'mark-speaking') ws.send(JSON.stringify({ type: 'noop' }));
      } catch {
        /* ignore */
      }
    });
  });

  const broadcast = (payload) => {
    const data = JSON.stringify(payload);
    for (const client of wss.clients) {
      if (client.readyState === 1) {
        try {
          client.send(data);
        } catch {
          /* ignore */
        }
      }
    }
  };

  bus.on('event', (evt) => {
    broadcast({ type: 'event', event: evt });
    if (['vote-result', 'mode-change', 'level-up', 'phase-start', 'round-start', 'round-stop'].includes(evt.type)) {
      broadcast({ type: 'state', state: snapshot() });
    }
  });

  // snapshot periódico (1x por segundo) para painel e overlay
  const stateTimer = setInterval(() => {
    if (wss.clients.size) broadcast({ type: 'state', state: snapshot() });
  }, 1000);
  stateTimer.unref?.();

  server.on('listening', () => {
    const addr = server.address();
    const port = addr.port;
    const host = addr.address || '0.0.0.0';
    log('painel', `rodando em http://localhost:${port}  (escutando em ${host})`);
    log('painel', `painel: /  |  overlay OBS: /overlay.html  |  rosto: /robo.html`);
  });

  return server;
}

/* ------------------------------------------------------------------ */
/* Roteador                                                            */
/* ------------------------------------------------------------------ */
async function handleRequest(req, res) {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = decodeURIComponent(url.pathname);

  if (pathname.startsWith('/api/')) {
    try {
      await handleApi(req, res, url, pathname);
    } catch (err) {
      log('erro', `api ${pathname}: ${err.message}`);
      json(res, 500, { ok: false, error: err.message });
    }
    return;
  }

  serveStatic(res, pathname);
}

async function handleApi(req, res, url, pathname) {
  const method = req.method || 'GET';

  /* ---------- estado ---------- */
  if (pathname === '/api/state') {
    return json(res, 200, { ok: true, state: snapshot(), ai: aiStatus(), logs: recentLogs(80) });
  }

  /* ---------- configuração ---------- */
  if (pathname === '/api/config') {
    if (method === 'GET') return json(res, 200, { ok: true, config: redactedConfig() });
    if (method === 'POST') {
      const body = await readJsonBody(req);
      const clean = stripMasked(body);
      config.patch(clean);
      log('painel', `configuração atualizada (${Object.keys(flattenShallow(clean)).length} campos)`);
      bus.emit('event', { type: 'config-change' });
      return json(res, 200, { ok: true, config: redactedConfig() });
    }
  }
  if (pathname === '/api/config/reset' && method === 'POST') {
    config.reset();
    return json(res, 200, { ok: true, config: redactedConfig() });
  }

  /* ---------- system prompt ---------- */
  if (pathname === '/api/prompt') {
    if (method === 'GET') {
      return json(res, 200, {
        ok: true,
        prompt: promptStore.get(),
        custom: promptStore.isCustom(),
        base: promptStore.base,
        modeChat: promptStore.getModeBlock('chat'),
        modeStreamer: promptStore.getModeBlock('streamer'),
        history: promptStore.history(),
        preview: promptStore.render({
          mode: state.mode,
          chat_digest: chatlog.digestText(150, 40),
          chat_recent: chatlog.last(15).map((m) => `${m.display}: ${m.text}`).join('\n') || '(vazio)',
          time_left: `${Math.floor(state.phase.secondsLeft / 60)}m${String(state.phase.secondsLeft % 60).padStart(2, '0')}s`,
        }),
      });
    }
    if (method === 'POST') {
      const body = await readJsonBody(req);
      if (body.action === 'reset') promptStore.reset();
      else if (body.action === 'mode' && body.mode) promptStore.patchModePrompt(body.mode, body.text);
      else promptStore.set(body.prompt);
      return json(res, 200, { ok: true, custom: promptStore.isCustom() });
    }
  }

  /* ---------- IA ---------- */
  if (pathname === '/api/ai/providers') {
    return json(res, 200, {
      ok: true,
      providers: Object.entries(PRESETS).map(([id, p]) => ({ id, label: p.label, baseUrl: p.baseUrl, model: p.model, needsKey: p.needsKey })),
      current: aiStatus(),
    });
  }
  if (pathname === '/api/ai/test' && method === 'POST') {
    const result = await testAi();
    log('ia', `teste: ${result.ok ? 'OK' : 'FALHOU'} (${result.provider}) ${result.message}`);
    return json(res, 200, result);
  }
  if (pathname === '/api/ai/models') {
    return json(res, 200, { ok: true, models: await listModels() });
  }
  if (pathname === '/api/ai/ask' && method === 'POST') {
    const body = await readJsonBody(req);
    const answer = await answerQuestion(body.q || body.question || '', { user: body.user || 'streamer/web' });
    return json(res, 200, { ok: true, ...answer });
  }

  /* ---------- chat ---------- */
  if (pathname === '/api/chat/say' && method === 'POST') {
    const body = await readJsonBody(req);
    const text = String(body.text || '').slice(0, 400);
    const sent = hub.sayTwitch(text);
    return json(res, 200, { ok: true, sent });
  }
  if (pathname === '/api/chat/history') {
    return json(res, 200, { ok: true, messages: chatlog.last(Number(url.searchParams.get('limit') || 60)), stats: chatlog.stats(180), topics: chatlog.topics(10) });
  }
  if (pathname === '/api/chat/simulate' && method === 'POST') {
    const body = await readJsonBody(req);
    const msg = hub.ingest({
      platform: 'sim',
      user: String(body.user || 'teste'),
      display: String(body.display || body.user || 'teste'),
      text: String(body.text || ''),
      isMod: Boolean(body.isMod),
      isSub: Boolean(body.isSub),
      isVip: Boolean(body.isVip),
      bits: Number(body.bits || 0),
    });
    return json(res, 200, { ok: true, message: msg });
  }

  /* ---------- controles do streamer ---------- */
  if (pathname === '/api/control' && method === 'POST') {
    const body = await readJsonBody(req);
    const action = String(body.action || '');
    let result = { ok: true, action };
    switch (action) {
      case 'start':
        round.startRound();
        break;
      case 'stop':
        round.stopRound();
        break;
      case 'pause':
        result.paused = round.pause(true);
        break;
      case 'resume':
        result.paused = round.pause(false);
        break;
      case 'mode':
        result.mode = round.forceMode(body.mode || 'streamer');
        break;
      case 'next-level':
        round.markLevelDone({ display: 'painel' });
        break;
      case 'vote-open':
        round.forceVoteOpen(Number(body.seconds || 60));
        break;
      case 'vote-close':
        voting.forceClose();
        break;
      case 'skip-to-vote':
        round.skipToVote(Number(body.seconds || 15));
        break;
      case 'talk':
        result.line = await round.talkNow(body.mode || state.mode, 'painel');
        break;
      case 'mute':
        result.silenceUntil = round.muteFor(Number(body.seconds || 45), 'painel');
        break;
      case 'reset-level':
        state.level = 1;
        break;
      default:
        result = { ok: false, error: `ação desconhecida: ${action}` };
    }
    return json(res, 200, result);
  }

  /* ---------- votos manuais (para testar) ---------- */
  if (pathname === '/api/vote' && method === 'POST') {
    const body = await readJsonBody(req);
    const res2 = voting.cast(
      { platform: 'painel', user: body.user || `painel-${Date.now()}`, display: body.user || 'Painel', isMod: true },
      body.mode,
      { engine: 'painel' },
    );
    return json(res, 200, { ok: res2.ok, ...res2, tally: voting.tally });
  }

  /* ---------- logs ---------- */
  if (pathname === '/api/logs') {
    return json(res, 200, { ok: true, logs: recentLogs(Number(url.searchParams.get('limit') || 200)) });
  }

  /* ---------- site "IA responde" (funciona local e na Vercel) ---------- */
  if (pathname === '/api/answer') {
    const q = url.searchParams.get('q') || url.searchParams.get('pergunta') || '';
    const answer = await answerQuestion(q, { user: url.searchParams.get('de') || 'anônimo' });
    if (url.searchParams.get('format') === 'json') return json(res, 200, { ok: true, ...answer });
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(answer.text);
    return;
  }

  return json(res, 404, { ok: false, error: 'rota não encontrada' });
}

/* ------------------------------------------------------------------ */
/* Estáticos                                                           */
/* ------------------------------------------------------------------ */
function serveStatic(res, pathname) {
  let rel = pathname === '/' ? '/index.html' : pathname;
  if (rel.startsWith('/answer')) rel = '/answer/index.html';
  const file = path.join(PUBLIC_DIR, path.normalize(rel).replace(/^([/\\])+/, ''));
  if (!file.startsWith(PUBLIC_DIR)) return notFound(res);
  fs.stat(file, (err, stat) => {
    if (err || !stat.isFile()) return notFound(res);
    const ext = path.extname(file).toLowerCase();
    res.writeHead(200, {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Cache-Control': ext === '.html' ? 'no-cache' : 'public, max-age=60',
      'Access-Control-Allow-Origin': '*',
    });
    fs.createReadStream(file).pipe(res);
  });
}

function notFound(res) {
  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end('404 — não encontrado');
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */
function json(res, code, data) {
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  });
  res.end(JSON.stringify(data));
}

function readJsonBody(req) {
  return new Promise((resolve) => {
    if (req.method === 'OPTIONS') return resolve({});
    let raw = '';
    req.on('data', (c) => {
      raw += c;
      if (raw.length > 1_000_000) req.destroy();
    });
    req.on('end', () => {
      if (!raw) return resolve({});
      try {
        resolve(JSON.parse(raw));
      } catch {
        resolve({});
      }
    });
    req.on('error', () => resolve({}));
  });
}

/** Não deixa o painel sobrescrever segredos com a versão mascarada (abc…1234) */
function stripMasked(obj) {
  if (Array.isArray(obj)) return obj.map(stripMasked);
  if (obj && typeof obj === 'object') {
    const out = {};
    for (const [k, v] of Object.entries(obj)) out[k] = stripMasked(v);
    return out;
  }
  if (typeof obj === 'string' && /^.{0,8}…/.test(obj)) return undefined;
  return obj;
}

function flattenShallow(obj, prefix = '', out = {}) {
  for (const [k, v] of Object.entries(obj || {})) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) flattenShallow(v, key, out);
    else out[key] = v;
  }
  return out;
}
