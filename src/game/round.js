/**
 * game/round.js — O ORQUESTRADOR DO FORMATO.
 *
 * Ciclo da live:
 *
 *   ┌──────────────── FASE (600s por padrão) ────────────────┐
 *   │  robô executa o modo atual (CHAT ou STREAMER)          │
 *   │                             ┌── VOTAÇÃO (últimos 60s) ─┤
 *   │                             │  !1 = falar com o chat   │
 *   │                             │  !2 = atrapalhar streamer│
 *   └─────────────────────────────┴──────────────────────────┘
 *                    ↓ resultado aplicado
 *              nova fase (nível +1) e o ciclo recomeça
 *
 * O streamer também controla pelo painel: passar de fase, forçar modo,
 * pular para a votação, pausar o robô.
 */
import { config } from '../config.js';
import { log } from '../log.js';
import { state, bus, emitEvent } from '../state.js';
import { chatlog } from './chatlog.js';
import { voting } from './voting.js';
import { speak, clearQueue } from './speak.js';
import { hub } from '../chat/source.js';
import * as brain from '../ai/brain.js';

let tickTimer = null;
let voteListenerOn = false;
let distractionTimer = null;
let replyDebt = 0;
let lastReplyAt = 0;
let paused = false;

/* ------------------------------------------------------------------ */
/* Ciclo                                                               */
/* ------------------------------------------------------------------ */

export function startRound({ announce = true } = {}) {
  if (state.running) return state;
  state.running = true;
  state.mode = normalizeMode(config.get('round.startMode', 'streamer'));
  state.level = 1;
  log('fase', `RODADA INICIADA — modo inicial: ${label(state.mode).toUpperCase()} | fase de ${config.get('round.phaseSeconds', 600)}s`);

  if (announce) {
    brain.reactToEvent('greeting').then(({ line }) => speak(line, { reason: 'greeting', priority: 2, force: true }));
  }
  beginPhase();

  if (!voteListenerOn) {
    // a votação fecha sozinha e avisa; aqui é onde o modo realmente troca
    bus.on('event', (evt) => {
      if (evt.type !== 'vote-result' || !state.running) return;
      applyVoteResult(evt.result).catch((err) => log('erro', `aplicando votação: ${err.message}`));
    });
    voteListenerOn = true;
  }

  tickTimer = setInterval(tick, 1000);
  tickTimer.unref?.();
  scheduleDistraction();
  emitEvent({ type: 'round-start', mode: state.mode, level: state.level });
  return state;
}

export function stopRound() {
  state.running = false;
  clearInterval(tickTimer);
  clearTimeout(distractionTimer);
  tickTimer = null;
  distractionTimer = null;
  state.phase = { kind: 'idle', startedAt: 0, endsAt: 0, secondsLeft: 0 };
  if (voting.open) voting.forceClose();
  clearQueue();
  emitEvent({ type: 'round-stop' });
  log('fase', 'rodada encerrada');
}

function beginPhase() {
  const phaseSeconds = Number(config.get('round.phaseSeconds', 600));
  state.phase = {
    kind: 'phase',
    startedAt: Date.now(),
    endsAt: Date.now() + phaseSeconds * 1000,
    secondsLeft: phaseSeconds,
  };
  state.chat.messagesThisPhase = 0;
  emitEvent({ type: 'phase-start', level: state.level, mode: state.mode, seconds: phaseSeconds });
}

function tick() {
  if (!state.running || paused) return;
  const now = Date.now();
  const left = Math.max(0, Math.round((state.phase.endsAt - now) / 1000));
  state.phase.secondsLeft = left;

  const voteWindow = Number(config.get('round.voteWindowSeconds', 60));
  if (state.phase.kind === 'phase' && left <= voteWindow && !voting.open) {
    openVoteWindow(left);
  }

  emitEvent({ type: 'tick', secondsLeft: left, kind: state.phase.kind, level: state.level, mode: state.mode });

  // quando o tempo acaba, a própria votação fecha e emite 'vote-result';
  // aqui só cuidamos da rede de segurança (rodada pausada/parada no meio)
  if (left <= 0 && voting.open && Date.now() - state.phase.endsAt > 3000) voting.forceClose();
}

/* ------------------------------------------------------------------ */
/* Votação                                                            */
/* ------------------------------------------------------------------ */

function openVoteWindow(seconds) {
  state.phase.kind = 'vote';
  voting.open_(seconds);
  hub.simulator.setVoteWindow(true);
  hub.sayTwitch(
    `🗳️ VOTAÇÃO ABERTA! !1 = ${config.get('robot.name', 'VEX')} fala com o CHAT | !2 = ${config.get('robot.name', 'VEX')} fala com o STREAMER pra atrapalhar`,
  );
  brain.reactToEvent('vote-open').then(({ line }) => speak(line, { reason: 'vote-open', priority: 2, force: true }));
}

/** Aplica o resultado da votação: troca de modo + anúncio + nova fase */
export async function applyVoteResult(result) {
  hub.simulator.setVoteWindow(false);
  if (!result) {
    endPhaseCycle();
    return;
  }

  const changed = result.winner !== state.mode;
  if (changed) {
    state.previousMode = state.mode;
    state.mode = result.winner;
    state.stats.modeSwitches += 1;
    log('fase', `modo trocado: ${label(result.previousMode)} → ${label(state.mode)}`);
  }

  const { line } = await brain.announceVoteResult({ tally: result.tally, mode: state.mode });
  speak(line, { reason: 'vote-result', priority: 3, force: true });

  if (changed) emitEvent({ type: 'mode-change', mode: state.mode, previous: result.previousMode, result, changed });
  endPhaseCycle();
}

function endPhaseCycle() {
  state.stats.phasesCompleted += 1;
  state.level += 1;
  log('fase', `nova fase: nível ${state.level} | modo ${label(state.mode)}`);
  beginPhase();
  scheduleDistraction();
  emitEvent({ type: 'level-up', level: state.level, mode: state.mode });
}

/* ------------------------------------------------------------------ */
/* Mensagens do chat → comandos, votos, perguntas                      */
/* ------------------------------------------------------------------ */

export function handleChatMessage(msg) {
  if (!state.running) return;
  interpretAndRoute(msg).catch((err) => log('erro', `roteamento: ${err.message}`));
}

async function interpretAndRoute(msg) {
  const cmds = config.get('commands', {});
  const prefix = String(cmds.prefix ?? '!');
  const lower = String(msg.text || '').toLowerCase().trim();
  const isCmd = lower.startsWith(prefix) || /^[!./#]/.test(lower);
  const body = lower.replace(/^[!/.#]+/, '').trim();

  // 1) VOTO (direto ou por palavra-chave)
  const directVote = matchVote(body, cmds);
  if (directVote && (isCmd || voting.open)) {
    registerVote(msg, directVote, 'lexico');
    return;
  }

  // 2) COMANDOS DE CONTROLE
  if (isCmd) {
    if (inList(body, cmds.robotStfu)) {
      const seconds = 45;
      state.silenceUntil = Date.now() + seconds * 1000;
      clearQueue();
      log('robo', `chat pediu silêncio por ${seconds}s (${msg.display})`);
      speak(`${msg.display} mandou eu calar a boca. Vou ficar quieto ${seconds} segundos. Aproveitem.`, { reason: 'stfu', force: true, priority: 4 });
      emitEvent({ type: 'robot-muted', seconds, by: msg.display });
      return;
    }
    if (inList(body, cmds.rules)) {
      const robo = config.get('robot.name', 'VEX');
      speak(
        `Regras rápidas: a cada ${Math.round(Number(config.get('round.phaseSeconds', 600)) / 60)} minutos vocês votam. ${prefix}1 faz o ${robo} conversar com o chat e ${prefix}2 faz ele atrapalhar o streamer. Também valem: ${prefix}${cmds.robotStfu?.[0]} pra me calar, ${prefix}${cmds.levelDone?.[0]} pra marcar fase concluída e perguntas diretas com o meu nome.`,
        { reason: 'rules', priority: 4, force: true },
      );
      return;
    }
    if (inList(body, cmds.levelDone) && (msg.isMod || msg.isBroadcaster || msg.isVip)) {
      markLevelDone(msg);
      return;
    }
  }

  // 3) O CHAT ESTÁ FALANDO COM O ROBÔ?
  const robotName = String(config.get('robot.name', 'VEX')).toLowerCase();
  const callingRobot =
    lower.includes(robotName) ||
    /\b(rob[oô]|bot|ia|vexi?)\b/.test(lower) ||
    (isCmd && inList(body, cmds.askRobot));

  // 3a) votação aberta: tenta interpretar intenções ambíguas com a IA
  if (voting.open) {
    const guess = await aiIntent(msg);
    if (guess) {
      registerVote(msg, guess.mode, guess.engine);
      return;
    }
  }

  // 3b) perguntou/perguntou pro robô
  if (callingRobot || (/\?\s*$/.test(lower) && state.mode === 'chat')) {
    const chance = state.mode === 'chat' ? 0.85 : 0.35;
    if (Math.random() < chance) {
      const { line, engine } = await brain.replyToMessage(msg);
      const text = line || localReply(msg);
      speak(text, { reason: 'answer', mode: state.mode, priority: 1, force: true });
      hub.sayTwitch(text);
      emitEvent({ type: 'ai-reply', engine, to: msg.display, text });
      lastReplyAt = Date.now();
      return;
    }
  }

  // 3c) modo conversa: interage por conta própria
  if (state.mode === 'chat') {
    maybeChatter(msg);
  }

  // 3d) hype extremo: interrompe o que estiver fazendo
  if (hub.isHype() && config.get('robot.chattiness.interruptOnChatHype', true)) {
    if (Date.now() - lastHypeBurst > 45000) {
      lastHypeBurst = Date.now();
      const { line } = await brain.reactToEvent('hype');
      if (line) speak(line, { reason: 'hype', priority: 2, force: true });
    }
  }
}

let lastHypeBurst = 0;

function localReply(msg) {
  const name = msg.display || 'amigo';
  const base = chatlog.digest(90, 20);
  const topic = base.topics ? base.topics.split(',')[0] : 'isso';
  const pool = [
    `${name}, eu li o que você escreveu e vou fingir que entendi. Sobre ${topic}: sim.`,
    `${name}, ótima pergunta. A resposta é "depende" e o depoimento do streamer confirma.`,
    `${name}, anotado no meu banco de dados. É um bloco de notas, mas é meu.`,
    `${name}, você digitou isso tão rápido que meu parser quase pediu demissão.`,
  ];
  return pool[Math.floor(Math.random() * pool.length)];
}

function matchVote(body, cmds) {
  const chatWords = cmds.voteChat || [];
  const streamerWords = cmds.voteStreamer || [];
  if (chatWords.some((w) => w && (body === String(w) || body.startsWith(`${w} `)))) return 'chat';
  if (streamerWords.some((w) => w && (body === String(w) || body.startsWith(`${w} `)))) return 'streamer';
  return null;
}

function inList(body, arr = []) {
  return (arr || []).some((w) => w && (body === String(w) || body.startsWith(`${w} `)));
}

function registerVote(msg, mode, engine) {
  const res = voting.cast(msg, mode, { engine });
  if (!res.ok) {
    if (res.reason === 'fechada' && !msg.isBot) {
      // fora da janela: responde com bom humor, mas sem floodar
      if (Math.random() < 0.12) {
        speak(
          `${msg.display}, a votação não está aberta agora. Guarda o voto pra quando faltar ${config.get('round.voteWindowSeconds', 60)} segundos pro fim da fase.`,
          { reason: 'vote-closed' },
        );
      }
    }
    return;
  }
  if (engine === 'ia') voting.noteAiVote();
  if (res.repeat) return;
  // agradecimento ocasional
  if (Math.random() < 0.15) {
    speak(
      `${msg.display} votou em ${mode === 'chat' ? 'falar com o chat' : 'atrapalhar o streamer'}. Obrigado por participar da democracia.`,
      { reason: 'vote-thanks' },
    );
  }
}

/**
 * Decide se uma mensagem ambígua é voto.
 * Usa a IA quando ela estiver configurada; senão, uma heurística de palavras.
 */
async function aiIntent(msg) {
  if (!config.get('ai.interpretChat', true)) return null;
  const text = String(msg.text || '').toLowerCase();
  // heurística rápida e barata antes de gastar uma chamada de IA
  const wantsChat = /(fala|convers|papo|amig|paz|deixa ele|quieto|calma)/.test(text) && /(chat|nós|nos|gente|comigo)/.test(text);
  const wantsStreamer = /(atrapalha|perturb|incomoda|zoeira|caos|encher|estressa)/.test(text);
  const online = config.get('ai.provider', 'auto') !== 'none' && Boolean(config.get('ai.apiKey') || process.env.GROQ_API_KEY || process.env.OPENAI_API_KEY || process.env.OPENROUTER_API_KEY || process.env.GEMINI_API_KEY || process.env.ANTHROPIC_API_KEY);
  if (wantsStreamer && !wantsChat) return { mode: 'streamer', engine: online ? 'ia' : 'heuristica' };
  if (wantsChat && !wantsStreamer) return { mode: 'chat', engine: online ? 'ia' : 'heuristica' };
  return null;
}

/* ------------------------------------------------------------------ */
/* Falar por conta própria (ritmo do robô)                             */
/* ------------------------------------------------------------------ */

function scheduleDistraction() {
  clearTimeout(distractionTimer);
  if (!state.running) return;
  const c = config.get('robot.chattiness', {});
  const min = Number(c.streamerModeMinGapSeconds ?? 22);
  const max = Math.max(min + 5, Number(c.streamerModeMaxGapSeconds ?? 55));
  const delay = (min + Math.random() * (max - min)) * 1000;

  distractionTimer = setTimeout(async () => {
    if (process.env.ROUND_DEBUG === '1') {
      log('ok', `[dbg] timer disparou: running=${state.running} paused=${paused} mode=${state.mode} queue=${state.robot.queue} silencio=${Date.now() < state.silenceUntil}`);
    }
    if (state.running && !paused && state.mode === 'streamer' && Date.now() >= state.silenceUntil) {
      if (state.robot.queue < 2) {
        // distractStreamer devolve a fala (string) já pronta
        const line = await brain.distractStreamer('streamer', {});
        if (line) {
          speak(line, { reason: 'distraction', mode: 'streamer', force: true });
          hub.sayTwitch(line);
        }
      }
    }
    scheduleDistraction();
  }, delay);
  distractionTimer.unref?.();
}

function maybeChatter(msg) {
  const c = config.get('robot.chattiness', {});
  const chance = Number(c.chatModeReplyChance ?? 0.4);
  const maxPerMinute = Number(c.chatModeMaxLinesPerMinute ?? 8);
  replyDebt += 1;
  const now = Date.now();
  if (replyDebt % 5 !== 0) return; // olha o chat em blocos, não mensagem por mensagem
  if (now - lastReplyAt < Math.ceil(60000 / maxPerMinute)) return;
  if (Math.random() > chance + 0.3) return;
  if (Date.now() < state.silenceUntil) return;

  brain
    .talkToChat({ reason: 'chat' })
    .then((line) => {
      if (!line) return;
      lastReplyAt = Date.now();
      speak(line, { reason: 'chat', mode: 'chat' });
      hub.sayTwitch(line);
    })
    .catch((err) => log('erro', `chat reply: ${err.message}`));
  void msg;
}

/* ------------------------------------------------------------------ */
/* Controles (painel do streamer)                                      */
/* ------------------------------------------------------------------ */

export function markLevelDone(by = null) {
  log('fase', `fase ${state.level} marcada como CONCLUÍDA${by ? ` por ${by.display || by}` : ''}`);
  brain.reactToEvent('level-done', { level: state.level }).then(({ line }) => {
    if (line) speak(line, { reason: 'level-done', priority: 3, force: true });
  });
  if (voting.open) voting.forceClose();
  endPhaseCycle();
}

export function forceMode(mode, { silent = false } = {}) {
  const next = normalizeMode(mode);
  if (next === state.mode) return state.mode;
  state.previousMode = state.mode;
  state.mode = next;
  state.stats.modeSwitches += 1;
  log('fase', `modo forçado pelo painel: ${label(next)}`);
  emitEvent({ type: 'mode-change', mode: next, previous: state.previousMode, forced: true, changed: true });
  if (!silent) {
    speak(
      next === 'chat'
        ? 'Modo conversa ativado manualmente. Chat, chegou a minha vez de falar com vocês.'
        : 'Modo caos ativado manualmente. Streamer, senti muito.',
      { reason: 'force-mode', priority: 3, force: true },
    );
  }
  if (state.mode === 'chat') scheduleDistraction();
  return state.mode;
}

export function skipToVote(seconds = 15) {
  if (!state.running) return null;
  state.phase.endsAt = Date.now() + seconds * 1000;
  state.phase.secondsLeft = seconds;
  log('fase', `votação antecipada pelo painel (${seconds}s)`);
  return state.phase;
}

export function forceVoteOpen(seconds = 60) {
  if (!state.running) return null;
  state.phase.kind = 'vote';
  openVoteWindow(seconds);
  return voting;
}

export function pause(value = true) {
  paused = Boolean(value);
  emitEvent({ type: 'paused', paused });
  log('fase', paused ? 'robô PAUSADO pelo streamer' : 'robô retomado');
  return paused;
}

export function isPaused() {
  return paused;
}

export function talkNow(mode = state.mode, reason = 'manual') {
  const promise = mode === 'chat' ? brain.talkToChat({ reason }) : brain.distractStreamer(reason, {});
  return promise.then((line) => {
    if (line) {
      speak(line, { reason, mode, priority: 3, force: true });
      hub.sayTwitch(line);
    }
    return line;
  });
}

export function muteFor(seconds = 45, by = 'painel') {
  state.silenceUntil = Date.now() + seconds * 1000;
  clearQueue();
  emitEvent({ type: 'robot-muted', seconds, by });
  log('robo', `silêncio forçado por ${seconds}s (${by})`);
  return state.silenceUntil;
}

function normalizeMode(m) {
  const v = String(m || '').toLowerCase();
  return v === 'chat' ? 'chat' : 'streamer';
}

function label(m) {
  return m === 'chat' ? 'conversar com o chat' : 'atrapalhar o streamer';
}

export function status() {
  return {
    running: state.running,
    paused,
    mode: state.mode,
    level: state.level,
    phase: state.phase,
    silenceUntil: state.silenceUntil,
  };
}
