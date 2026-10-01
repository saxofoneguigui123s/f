/* AI VS STREAMER — painel do streamer (vanilla JS, sem build) */
'use strict';

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

let SNAPSHOT = null;
let CONFIG = null;
let AI = { provider: 'auto', label: '', online: false };
const speechHistory = [];
const voteHistory = [];

/* ------------------------------------------------------------------ */
/* WebSocket                                                          */
/* ------------------------------------------------------------------ */
let ws = null;
let retry = 0;

function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws`);
  ws.onopen = () => {
    retry = 0;
    setPill('#pillChat', 'ok');
  };
  ws.onclose = () => {
    toast('Conexão com o servidor caiu — tentando reconectar…', 'err');
    setTimeout(connect, Math.min(8000, 500 * ++retry));
  };
  ws.onerror = () => ws.close();
  ws.onmessage = (evt) => {
    let data;
    try { data = JSON.parse(evt.data); } catch { return; }
    if (data.type === 'state' || data.type === 'hello') {
      if (data.state) { SNAPSHOT = data.state; render(); }
      if (data.type === 'hello') {
        if (data.logs) data.logs.forEach(addLog);
        if (data.prompt !== undefined) { $('#promptBox').value = data.prompt; }
        if (data.ai) AI = data.ai;
        loadPromptMeta();
        loadConfig();
      }
    }
    if (data.type === 'event') handleEvent(data.event);
  };
}

/* ------------------------------------------------------------------ */
/* Eventos em tempo real                                              */
/* ------------------------------------------------------------------ */
function handleEvent(e) {
  switch (e.type) {
    case 'chat-message':
      addFeed(e.message);
      break;
    case 'speak':
      setSpeech(e);
      if ($('#cVoiceBrowser')?.checked) speakInBrowser(e);
      break;
    case 'vote':
      voteHistory.unshift(`${new Date(e.t).toLocaleTimeString('pt-BR')} · ${e.user} → ${e.mode.toUpperCase()} (peso ${e.weight}${e.engine === 'ia' ? ' · via IA' : ''})`);
      renderVoteLog();
      break;
    case 'vote-open':
      toast(`🗳️ Votação aberta por ${e.seconds}s!`, 'ok');
      break;
    case 'vote-result': {
      const r = e.result;
      toast(`Resultado: chat ${r.tally.chat} × ${r.tally.streamer} streamer → ${r.winner === 'chat' ? 'falar com o CHAT' : 'atrapalhar o STREAMER'}`, 'ok');
      renderLastResult(r);
      break;
    }
    case 'mode-change':
      toast(`Modo agora: ${e.mode === 'chat' ? '💬 falar com o chat' : '😈 atrapalhar o streamer'}`, 'ok');
      break;
    case 'level-up':
      toast(`Fase ${e.level} começando!`, 'ok');
      break;
    case 'robot-muted':
      toast(`🔇 Robô calado por ${e.seconds}s (${e.by})`, 'err');
      break;
    case 'chat-connection':
      toast(e.connected ? `Chat conectado: ${e.platform} ${e.channel || ''}` : `Chat desconectado: ${e.platform}`, e.connected ? 'ok' : 'err');
      break;
    case 'chat-error':
      toast(`Erro no chat (${e.platform}): ${e.message}`, 'err');
      break;
    case 'config-change':
      loadConfig();
      break;
    case 'ai-reply':
      addLog({ t: e.t, tag: 'ia', text: `respondeu para ${e.to}: ${e.text}` });
      break;
    default:
      break;
  }
}

/* ------------------------------------------------------------------ */
/* Render do estado                                                   */
/* ------------------------------------------------------------------ */
function render() {
  const s = SNAPSHOT;
  if (!s) return;
  const phase = s.phase;
  const isVote = phase.kind === 'vote';
  const idle = !s.running || phase.kind === 'idle';

  // timer
  const left = idle ? 0 : phase.secondsLeft;
  $('#timer').textContent = fmt(left);
  $('#timer').className = `timer${isVote ? ' vote' : ''}`;

  const total = Number(s.config.phaseSeconds || 600);
  const pct = idle ? 0 : Math.max(0, Math.min(100, 100 - (left / total) * 100));
  $('#phaseProgress').style.width = `${pct}%`;

  $('#phaseKind').textContent = idle ? 'parado' : isVote ? 'votação' : `fase ${s.level}`;
  $('#phaseKind').className = `badge ${idle ? 'idle' : isVote ? 'vote' : 'chat'}`;

  const modeBadge = $('#modeBadge');
  modeBadge.textContent = `modo: ${s.mode === 'chat' ? 'falar com o chat' : 'atrapalhar o streamer'}`;
  modeBadge.className = `badge ${s.mode === 'chat' ? 'chat' : 'streamer'}`;
  $('#levelText').textContent = `Fase ${s.level} do jogo · ${s.stats?.phasesCompleted || 0} fases concluídas`;
  $('#setupPhase').textContent = s.config.phaseSeconds;

  // votação
  const tally = s.vote.tally || { chat: 0, streamer: 0 };
  const vtotal = Math.max(1, tally.chat + tally.streamer);
  $('#fillChat').style.width = `${(tally.chat / vtotal) * 100}%`;
  $('#fillStreamer').style.width = `${(tally.streamer / vtotal) * 100}%`;
  $('#numChat').textContent = tally.chat;
  $('#numStreamer').textContent = tally.streamer;
  $('#voteBadge').textContent = s.vote.open ? `aberta · ${s.vote.secondsLeft}s` : 'fechada';
  $('#voteBadge').className = `badge ${s.vote.open ? 'vote' : 'idle'}`;
  $('#voteInfo').innerHTML = s.vote.open
    ? `Votos válidos: <b>${s.vote.total}</b> · faltam <b>${s.vote.secondsLeft}s</b> · mínimos para mudar: ${s.config.minVotesToChange}`
    : `A votação abre nos últimos ${s.config.voteWindowSeconds}s de cada fase. !1 = falar com o chat · !2 = atrapalhar o streamer.`;

  // robô
  $('#kLast').textContent = s.robot.lastLine || '—';
  $('#kLines').textContent = s.robot.linesTotal;
  $('#kQueue').textContent = s.robot.queue;
  $('#kSilence').textContent = s.silenceUntil > Date.now() ? new Date(s.silenceUntil).toLocaleTimeString('pt-BR') : '—';

  // chat
  $('#chatRate').innerHTML = `<b>${Math.round(s.chat.hype || 0)}</b> msg/min`;
  $('#kRead').textContent = s.stats.chatMessagesRead;
  $('#pillChat').innerHTML = `<i class="led"></i><b>Chat</b> <span>${s.chat.connected ? (s.chat.channel || 'conectado') : 'desconectado'}</span>`;
  $('#pillChat').className = `pill ${s.chat.connected ? 'on' : 'off'}`;

  const aiInfo = s.config?.ai || {};
  $('#pillAI').innerHTML = `<i class="led"></i><b>IA</b> <span>${s.ai.brain === 'llm' ? (s.ai.model || s.ai.provider) : 'cérebro local'}</span>`;
  $('#pillAI').className = `pill ${s.ai.brain === 'llm' ? 'ai' : ''}`;
  $('#pillMode').innerHTML = `<b>Modo</b> <span>${s.mode === 'chat' ? 'CHAT 💬' : 'STREAMER 😈'}</span>`;
  $('#pillLevel').innerHTML = `<b>Fase</b> <span>${s.level}</span>`;

  $('#btnPause').textContent = s.paused ? '▶ Retomar robô' : '⏸ Pausar robô';
  void aiInfo;
}

function renderVoteLog() {
  const el = $('#voteLog');
  el.innerHTML = voteHistory.slice(0, 40).map((v) => `<div>${escapeHtml(v)}</div>`).join('');
}

function renderLastResult(r) {
  $('#lastResult').innerHTML = `
    <span class="k">Vencedor</span><span>${r.winner === 'chat' ? '💬 falar com o chat' : '😈 atrapalhar o streamer'}</span>
    <span class="k">Placar</span><span>chat ${r.tally.chat} × ${r.tally.streamer} streamer (${r.pct.chat}% / ${r.pct.streamer}%)</span>
    <span class="k">Votos</span><span>${r.total} de ${r.voters} pessoas</span>
    <span class="k">Motivo</span><span>${r.reason}${r.changed ? ' · modo trocado' : ' · modo mantido'}</span>
    <span class="k">Quando</span><span>${new Date(r.at).toLocaleString('pt-BR')}</span>`;
}

function setSpeech(e) {
  speechHistory.unshift({ t: e.t, text: e.text, mode: e.mode, engine: e.engine });
  $('#speechWho').textContent = `${SNAPSHOT?.robot?.name || 'ROBÔ'} · ${e.mode === 'chat' ? 'falando com o chat' : 'atrapalhando o streamer'} · ${e.engine === 'llm' ? 'gerado pela IA' : 'cérebro local'}`;
  const el = $('#speechHistory');
  if (el) el.innerHTML = speechHistory.slice(0, 30).map((s) => `<div>${new Date(s.t).toLocaleTimeString('pt-BR')} · ${escapeHtml(s.text)}</div>`).join('');
  const card = document.querySelector('#speechCard .line');
  if (card) {
    card.textContent = e.text;
    $('#speechCard')?.classList.add('speaking');
    setTimeout(() => $('#speechCard')?.classList.remove('speaking'), 4000);
  }
}

/* Voz no navegador (o áudio vira fonte de áudio do OBS) */
let voiceEnabled = true;
function speakInBrowser({ text, voice }) {
  if (!('speechSynthesis' in window) || !voiceEnabled) return;
  try {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'pt-BR';
    u.rate = voice?.rate ?? 1.05;
    u.pitch = voice?.pitch ?? 0.8;
    u.volume = voice?.volume ?? 1;
    const voices = speechSynthesis.getVoices();
    const pt = voices.find((v) => /pt[-_]BR/i.test(v.lang)) || voices.find((v) => /^pt/i.test(v.lang));
    if (pt) u.voice = pt;
    speechSynthesis.speak(u);
  } catch { /* ignore */ }
}

function addFeed(m) {
  const feed = $('#feed');
  const div = document.createElement('div');
  div.className = `msg ${m.platform === 'twitch' ? 'tw' : m.platform === 'sim' ? 'sim' : ''}`;
  const badges = [
    m.isBroadcaster ? '<span class="tag mod">streamer</span>' : '',
    m.isMod ? '<span class="tag mod">mod</span>' : '',
    m.isSub ? '<span class="tag sub">sub</span>' : '',
    m.bits ? `<span class="tag sub">${m.bits} bits</span>` : '',
  ].join('');
  div.innerHTML = `<b>${escapeHtml(m.display || m.user)}</b>${badges}: ${escapeHtml(m.text)}`;
  feed.appendChild(div);
  while (feed.children.length > 120) feed.removeChild(feed.firstChild);
  if (feed.scrollHeight - feed.scrollTop - feed.clientHeight < 160) feed.scrollTop = feed.scrollHeight;
}

function addLog(entry) {
  const logs = $('#logs');
  const div = document.createElement('div');
  div.innerHTML = `<span class="t">${new Date(entry.t).toLocaleTimeString('pt-BR')}</span><span class="tag ${entry.tag}">${entry.tag}</span><span>${escapeHtml(entry.text)}</span>`;
  logs.appendChild(div);
  while (logs.children.length > 600) logs.removeChild(logs.firstChild);
  logs.scrollTop = logs.scrollHeight;
}

/* ------------------------------------------------------------------ */
/* Ações (API)                                                        */
/* ------------------------------------------------------------------ */
async function api(path, body) {
  const res = await fetch(path, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

async function control(action, extra = {}) {
  const out = await api('/api/control', { action, ...extra });
  if (!out.ok) toast(`Falhou: ${out.error || action}`, 'err');
  return out;
}

function bindControls() {
  $('#btnStart').onclick = async () => { await control('start'); toast('Rodada iniciada', 'ok'); };
  $('#btnStop').onclick = async () => { await control('stop'); toast('Rodada parada', 'err'); };
  $('#btnPause').onclick = async () => {
    const paused = SNAPSHOT?.paused;
    await control(paused ? 'resume' : 'pause');
  };
  $('#btnTalk').onclick = async () => { const r = await control('talk'); if (r.line) toast(`» ${r.line}`, 'ok'); };
  $('#btnNextLevel').onclick = () => control('next-level');
  $('#btnSkipVote').onclick = () => { control('skip-to-vote', { seconds: 20 }); toast('Votação em 20s', 'ok'); };
  $('#btnMute').onclick = () => control('mute', { seconds: 45 });
  $('#btnVoteOpen').onclick = () => { control('vote-open', { seconds: 60 }); toast('Votação aberta por 60s', 'ok'); };
  $('#btnVoteClose').onclick = () => control('vote-close');
  $$('[data-force]').forEach((b) => (b.onclick = () => control('mode', { mode: b.dataset.force })));
  $$('[data-testvote]').forEach((b) => (b.onclick = () => api('/api/vote', { mode: b.dataset.testvote, user: `painel${Math.floor(Math.random() * 99)}` })));

  $('#btnSay').onclick = async () => {
    const text = $('#sayInput').value.trim();
    if (!text) return;
    const out = await api('/api/chat/say', { text });
    toast(out.sent ? 'Enviado para a Twitch' : 'Sem token da Twitch — não enviado', out.sent ? 'ok' : 'err');
    $('#sayInput').value = '';
  };

  $('#btnSim').onclick = async () => {
    const text = $('#simInput').value.trim();
    if (!text) return;
    await api('/api/chat/simulate', { user: $('#simUser').value.trim() || 'tester', text });
    $('#simInput').value = '';
  };
  $('#simInput').onkeydown = (e) => { if (e.key === 'Enter') $('#btnSim').click(); };

  $('#btnClearLogs').onclick = () => { $('#logs').innerHTML = ''; };

  $('#voiceToggle').onchange = (e) => {
    voiceEnabled = e.target.checked;
    if (!voiceEnabled && 'speechSynthesis' in window) speechSynthesis.cancel();
  };

  $$('.tabs button').forEach((b) => {
    b.onclick = () => {
      $$('.tabs button').forEach((x) => x.classList.remove('active'));
      $$('.tabpane').forEach((x) => x.classList.remove('active'));
      b.classList.add('active');
      $(`#tab-${b.dataset.tab}`).classList.add('active');
      if (b.dataset.tab === 'prompt') loadPromptMeta();
      if (b.dataset.tab === 'config') loadConfig();
      if (b.dataset.tab === 'ia') loadProviders();
    };
  });
}

/* ------------------------------------------------------------------ */
/* Config                                                            */
/* ------------------------------------------------------------------ */
async function loadConfig() {
  const out = await api('/api/config');
  CONFIG = out.config;
  const c = CONFIG;
  $('#cfgRobotName').value = c.robot.name;
  $('#cfgStreamerName').value = c.streamer.name;
  $('#cfgGame').value = c.streamer.game || '';
  $('#cfgContext').value = c.streamer.context || '';
  $('#cfgPhase').value = c.round.phaseSeconds;
  $('#cfgVoteWindow').value = c.round.voteWindowSeconds;
  $('#cfgStartMode').value = c.round.startMode;
  $('#cfgMinVotes').value = c.round.minVotesToChange;
  $('#cfgTwitch').value = c.chat.twitch.channel || '';
  $('#cfgTwitchUser').value = c.chat.twitch.username || '';
  $('#cfgTwitchToken').value = c.chat.twitch.oauthToken || '';
  $('#cfgYoutube').value = c.chat.youtube.videoId || '';
  $('#cfgSim').checked = !!c.chat.simulator.enabled;

  const v = c.votes.weights;
  $('#wViewer').value = v.viewer; $('#wSub').value = v.subscriber; $('#wVip').value = v.vip;
  $('#wMod').value = v.moderator; $('#wBroadcaster').value = v.broadcaster; $('#wBits').value = v.bitsPerPoint;

  const ch = c.robot.chattiness;
  $('#cMinGap').value = c.robot.minSecondsBetweenLines;
  $('#cReplyChance').value = ch.chatModeReplyChance;
  $('#cMaxPerMin').value = ch.chatModeMaxLinesPerMinute;
  $('#cStreamerMin').value = ch.streamerModeMinGapSeconds;
  $('#cStreamerMax').value = ch.streamerModeMaxGapSeconds;
  $('#cVoiceBrowser').checked = !!c.robot.voice.browser;
  $('#cVoiceRate').value = c.robot.voice.rate;
  $('#cVoicePitch').value = c.robot.voice.pitch;
  $('#cVoiceVolume').value = c.robot.voice.volume;
  $('#cServerTts').checked = !!c.robot.voice.serverTtsEnabled;
  $('#cServerTtsCmd').value = c.robot.voice.serverTtsCommand || '';

  $('#aiProvider').value = c.ai.provider;
  $('#aiModel').value = c.ai.model || '';
  $('#aiKey').value = c.ai.apiKey || '';
  $('#aiBaseUrl').value = c.ai.baseUrl || '';
  $('#aiTemp').value = c.ai.temperature;
  $('#tempOut').textContent = c.ai.temperature;
  $('#aiInterpret').checked = !!c.ai.interpretChat;
}

async function loadProviders() {
  const out = await api('/api/ai/providers');
  const sel = $('#aiProvider');
  sel.innerHTML = out.providers.map((p) => `<option value="${p.id}">${p.label}${p.needsKey ? ' (precisa de chave)' : ''}</option>`).join('');
  sel.value = CONFIG?.ai.provider || 'auto';
  const pill = $('#aiStatusPill');
  const cur = out.current;
  pill.className = `pill ${cur.online ? 'ai' : 'off'}`;
  pill.innerHTML = `<i class="led"></i><span>${cur.online ? `${cur.label} · ${cur.model}` : cur.label}</span>`;
  $('#aiDiag').innerHTML = `
    <span class="k">Provedor</span><span>${cur.provider}</span>
    <span class="k">Cérebro</span><span>${cur.brain === 'llm' ? 'IA externa' : 'local (offline)'}</span>
    <span class="k">Chamadas</span><span>${SNAPSHOT?.ai.calls ?? 0}</span>
    <span class="k">Erros</span><span>${SNAPSHOT?.ai.errors ?? 0}</span>
    <span class="k">Último erro</span><span>${SNAPSHOT?.ai.lastError || '—'}</span>
    <span class="k">Latência</span><span>${SNAPSHOT?.ai.lastLatencyMs || 0} ms</span>
    <span class="k">Votos lidos pela IA</span><span>${SNAPSHOT?.vote.interpretedByAI ?? 0}</span>`;
}

function bindConfig() {
  $('#btnSaveConfig').onclick = async () => {
    const patch = {
      robot: { name: $('#cfgRobotName').value },
      streamer: { name: $('#cfgStreamerName').value, game: $('#cfgGame').value, context: $('#cfgContext').value },
      round: {
        phaseSeconds: Number($('#cfgPhase').value),
        voteWindowSeconds: Number($('#cfgVoteWindow').value),
        startMode: $('#cfgStartMode').value,
        minVotesToChange: Number($('#cfgMinVotes').value),
      },
      chat: {
        twitch: { channel: $('#cfgTwitch').value.trim(), username: $('#cfgTwitchUser').value.trim(), oauthToken: $('#cfgTwitchToken').value.trim() },
        youtube: { videoId: $('#cfgYoutube').value.trim() },
        simulator: { enabled: $('#cfgSim').checked },
      },
    };
    await api('/api/config', patch);
    toast('Configuração salva. Reinicie o servidor para trocar canal/token de chat.', 'ok');
    loadConfig();
  };
  $('#btnReloadConfig').onclick = loadConfig;

  $('#btnSaveAdvanced').onclick = async () => {
    const patch = {
      votes: {
        weights: {
          viewer: Number($('#wViewer').value), subscriber: Number($('#wSub').value), vip: Number($('#wVip').value),
          moderator: Number($('#wMod').value), broadcaster: Number($('#wBroadcaster').value), bitsPerPoint: Number($('#wBits').value),
        },
      },
      robot: {
        minSecondsBetweenLines: Number($('#cMinGap').value),
        chattiness: {
          chatModeReplyChance: Number($('#cReplyChance').value),
          chatModeMaxLinesPerMinute: Number($('#cMaxPerMin').value),
          streamerModeMinGapSeconds: Number($('#cStreamerMin').value),
          streamerModeMaxGapSeconds: Number($('#cStreamerMax').value),
        },
        voice: {
          browser: $('#cVoiceBrowser').checked,
          rate: Number($('#cVoiceRate').value),
          pitch: Number($('#cVoicePitch').value),
          volume: Number($('#cVoiceVolume').value),
          serverTtsEnabled: $('#cServerTts').checked,
          serverTtsCommand: $('#cServerTtsCmd').value,
        },
      },
    };
    await api('/api/config', patch);
    toast('Salvo', 'ok');
    loadConfig();
  };

  $('#aiTemp').oninput = (e) => ($('#tempOut').textContent = e.target.value);

  $('#btnSaveAI').onclick = async () => {
    await api('/api/config', {
      ai: {
        provider: $('#aiProvider').value,
        model: $('#aiModel').value.trim(),
        apiKey: $('#aiKey').value.trim() || undefined,
        baseUrl: $('#aiBaseUrl').value.trim(),
        temperature: Number($('#aiTemp').value),
        interpretChat: $('#aiInterpret').checked,
      },
    });
    toast('IA configurada', 'ok');
    loadConfig();
    loadProviders();
  };

  $('#btnTestAI').onclick = async () => {
    $('#btnTestAI').disabled = true;
    toast('Testando IA…', 'ok');
    const out = await api('/api/ai/test', {});
    $('#btnTestAI').disabled = false;
    toast(out.ok ? `✅ IA OK (${out.provider} · ${out.model})` : `❌ Falhou: ${out.message}`, out.ok ? 'ok' : 'err');
    loadProviders();
  };

  $('#btnModels').onclick = async () => {
    const out = await api('/api/ai/models');
    if (!out.models?.length) return toast('Nenhum modelo listado (endpoint não suporta)', 'err');
    toast(`Modelos: ${out.models.slice(0, 8).join(', ')}${out.models.length > 8 ? '…' : ''}`, 'ok');
    $('#aiModel').value = out.models[0];
  };

  $('#btnAsk').onclick = async () => {
    const q = $('#askInput').value.trim();
    if (!q) return;
    $('#askOut').querySelector('.line').textContent = 'pensando…';
    const out = await api('/api/ai/ask', { q, user: 'painel' });
    $('#askOut').querySelector('.line').textContent = out.text;
    $('#askOut').querySelector('.who').textContent = `resposta · ${out.engine === 'llm' ? out.provider + '/' + out.model : 'cérebro local'}`;
  };
  $('#askInput').onkeydown = (e) => { if (e.key === 'Enter') $('#btnAsk').click(); };
}

/* ------------------------------------------------------------------ */
/* System prompt                                                      */
/* ------------------------------------------------------------------ */
async function loadPromptMeta() {
  const out = await api('/api/prompt');
  if (out.ok) {
    if (!$('#promptBox').value.trim() || out.custom) $('#promptBox').value = out.prompt;
    $('#modeChat').value = out.modeChat || '';
    $('#modeStreamer').value = out.modeStreamer || '';
    $('#promptHistory').innerHTML = (out.history || []).length
      ? out.history.map((h) => `<div title="${escapeHtml(h.preview)}">${new Date(h.at).toLocaleString('pt-BR')}</div>`).join('')
      : '<div>Nenhuma versão anterior salva</div>';
  }
}

function bindPrompt() {
  $('#btnSavePrompt').onclick = async () => {
    await api('/api/prompt', { prompt: $('#promptBox').value });
    toast('System prompt salvo e aplicado', 'ok');
    loadPromptMeta();
  };
  $('#btnResetPrompt').onclick = async () => {
    if (!confirm('Restaurar o system prompt padrão (prompts/system.md)?')) return;
    await api('/api/prompt', { action: 'reset' });
    const out = await api('/api/prompt');
    $('#promptBox').value = out.prompt;
    toast('System prompt restaurado', 'ok');
    loadPromptMeta();
  };
  $('#btnPreviewPrompt').onclick = async () => {
    const out = await api('/api/prompt');
    $('#promptPreview').value = out.preview;
    toast('Prompt final atualizado', 'ok');
  };
  $('#btnSaveModes').onclick = async () => {
    await api('/api/prompt', { action: 'mode', mode: 'chat', text: $('#modeChat').value });
    await api('/api/prompt', { action: 'mode', mode: 'streamer', text: $('#modeStreamer').value });
    toast('Blocos de modo salvos', 'ok');
  };
}

/* ------------------------------------------------------------------ */
/* utilidades                                                        */
/* ------------------------------------------------------------------ */
function fmt(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}
function escapeHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function setPill(sel, cls) {
  const el = $(sel);
  if (el) el.className = `pill ${cls || ''}`;
}
function toast(text, kind = '') {
  const div = document.createElement('div');
  div.className = `toast ${kind}`;
  div.textContent = text;
  $('#toasts').appendChild(div);
  setTimeout(() => div.remove(), 6000);
  while ($('#toasts').children.length > 5) $('#toasts').firstChild.remove();
}

/* ------------------------------------------------------------------ */
/* boot                                                              */
/* ------------------------------------------------------------------ */
bindControls();
bindConfig();
bindPrompt();
connect();

fetch('/api/state').then((r) => r.json()).then((d) => {
  SNAPSHOT = d.state;
  AI = d.ai;
  (d.logs || []).forEach(addLog);
  render();
  loadProviders();
});
