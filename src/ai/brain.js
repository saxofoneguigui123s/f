/**
 * ai/brain.js — o cérebro do robô.
 *
 * Responsabilidades:
 *   1. LER e INTERPRETAR o chat (digest + interpretação pela IA)
 *   2. Gerar as falas do robô (modo CHAT conversa / modo STREAMER atrapalha)
 *   3. Interpretar os votos, inclusive os escritos em linguagem natural
 *   4. Reagir a eventos (fase concluída, hype, silêncio forçado)
 *
 * Se a IA externa estiver configurada, ela decide as falas com o
 * SYSTEM PROMPT editável (prompt-store.js). Se não, o cérebro local assume.
 */
import { config } from '../config.js';
import { log } from '../log.js';
import { state, emitEvent } from '../state.js';
import { promptStore } from '../prompt-store.js';
import { llmChat, resolveProvider } from './llm.js';
import { chatlog } from '../game/chatlog.js';
import { LINES, fill, pickFresh, pick } from './lines.pt.js';

const vars = (extra = {}) => ({
  robot_name: config.get('robot.name', 'VEX'),
  streamer_name: config.get('streamer.name', 'Streamer'),
  game: config.get('streamer.game', '') || 'o jogo',
  level: state.level,
  mode: state.mode,
  language: config.get('ai.language', 'pt-BR'),
  time_left: fmtTime(state.phase.secondsLeft),
  total_votes: state.vote.total,
  vote_tally: `chat=${state.vote.tally.chat} streamer=${state.vote.tally.streamer}`,
  ...extra,
});

function fmtTime(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  return `${Math.floor(s / 60)}m${String(s % 60).padStart(2, '0')}s`;
}

/* ------------------------------------------------------------------ */
/* Montagem do prompt (system prompt editável + contexto vivo)          */
/* ------------------------------------------------------------------ */
function buildSystemPrompt(mode, extraVars = {}) {
  const streamerCtx = config.get('streamer.context', '') || `(nada específico informado)`;
  return promptStore.render(
    vars({
      mode,
      mode_rules: promptStore.getModeBlock(mode) ? '(veja o bloco do modo acima)' : '',
      streamer_context: streamerCtx,
      chat_digest: chatlog.digestText(150, 40),
      chat_recent: chatlog.last(15).map((m) => `${m.display}: ${m.text}`).join('\n') || '(vazio)',
      ...extraVars,
    }),
  );
}

/* ------------------------------------------------------------------ */
/* Falas                                                               */
/* ------------------------------------------------------------------ */
function sanitizeLine(text) {
  let out = String(text || '')
    .replace(/^```[\s\S]*?```$/g, '')
    .replace(/^["'`]+|["'`]+$/g, '')
    .replace(/\*[^*]*\*/g, '')
    .replace(/^\(.*?\)\s*/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  // Se o modelo devolveu JSON sem querer, tenta extrair o campo "fala"
  if (out.startsWith('{')) {
    try {
      const j = JSON.parse(out);
      out = j.fala || j.line || j.text || j.message || out;
    } catch {
      /* ignore */
    }
  }
  const max = Number(config.get('robot.maxLineChars', 220));
  if (out.length > max) {
    const cut = out.slice(0, max);
    const lastPunct = Math.max(cut.lastIndexOf('.'), cut.lastIndexOf('!'), cut.lastIndexOf('?'));
    out = lastPunct > max * 0.55 ? cut.slice(0, lastPunct + 1) : `${cut.trim()}…`;
  }
  return out.trim();
}

async function generate({ mode, reason, extraVars = {}, temperature }) {
  const provider = resolveProvider();
  const contextBits = [];
  if (reason === 'answer') contextBits.push('Você está respondendo a uma mensagem específica do chat ou do streamer.');
  if (reason === 'vote-open') contextBits.push('A votação acabou de abrir: avise o chat em UMA frase curta empolgada.');
  if (reason === 'hype') contextBits.push('O chat está explodindo de mensagens e o streamer está no meio de uma jogada difícil.');
  if (reason === 'interrupt') contextBits.push('Você está INTERROMPENDO de propósito. Fale algo inesperado e curto para quebrar a concentração do streamer.');
  if (reason === 'greeting') contextBits.push('É a primeira fala sua na live. Apresente-se rapidamente.');

  if (provider.online) {
    const messages = [
      { role: 'system', content: buildSystemPrompt(mode, extraVars) },
      { role: 'user', content: buildInstruction(mode, reason, extraVars, contextBits) },
    ];
    try {
      const raw = await llmChat({ messages, temperature });
      const line = sanitizeLine(raw);
      if (line) return { line, engine: 'llm' };
    } catch (err) {
      log('ia', `fallback local (${err.message})`);
    }
  }

  return { line: localLine(mode, reason, extraVars), engine: 'local' };
}

function buildInstruction(mode, reason, extraVars, contextBits) {
  const lines = [
    `# TAREFA AGORA`,
    mode === 'chat'
      ? 'Você está no MODO CHAT: converse com os espectadores. Leia o que eles escreveram acima e responda/interaja com eles.'
      : 'Você está no MODO ATRAPALHAR: perturbe o streamer enquanto ele joga. Fale olhando para ele, sem virar conversa de chat.',
    contextBits.join(' '),
    reason === 'answer' && extraVars.target_message
      ? `Mensagem a responder: "${extraVars.target_message}" de ${extraVars.target_user || 'alguém'}`
      : '',
    reason === 'vote-open' ? `A votação está aberta por ${state.vote.secondsLeft || 60} segundos. Mencione os comandos !1 (falar com o chat) e !2 (atrapalhar o streamer).` : '',
    reason === 'vote-result'
      ? `Resultado da votação: chat=${state.vote.tally.chat} votos, streamer=${state.vote.tally.streamer} votos. Número total: ${state.vote.total}.`
      : '',
    `Fase atual do jogo: ${state.level}.`,
    '',
    '## COMO RESPONDER',
    '- Responda SOMENTE com a fala, uma única frase, em português do Brasil.',
    '- No máximo 2 frases curtas. Precisa ser FALÁVEL em voz alta em menos de 8 segundos.',
    '- Sem emojis, sem markdown, sem aspas, sem rubricas tipo (risos).',
    '- Não repita falas anteriores. Seja específico sobre o que o chat acabou de dizer.',
  ];
  return lines.filter(Boolean).join('\n');
}

function localVars(extraVars = {}) {
  const d = chatlog.digest(150, 25);
  return {
    streamer: config.get('streamer.name', 'Streamer'),
    robo: config.get('robot.name', 'VEX'),
    fase: state.level,
    jogo: config.get('streamer.game', 'esse jogo') || 'esse jogo',
    contexto: d.topics || 'o que o chat estava falando',
    chat: d.topUsers || 'os de sempre',
    usuario: d.last?.split(':')[0] || 'amigo do chat',
    topico: d.topics?.split(',')[0] || 'a vida',
    total: state.chat.messagesThisPhase,
    minutos: Math.round(Number(config.get('round.phaseSeconds', 600)) / 60),
    chat_pct: percent(state.vote.tally.chat),
    streamer_pct: percent(state.vote.tally.streamer),
  };
}

function percent(n) {
  const total = state.vote.tally.chat + state.vote.tally.streamer;
  if (!total) return 0;
  return Math.round((n / total) * 100);
}

function localLine(mode, reason, extraVars = {}) {
  const v = localVars(extraVars);
  const pack = mode === 'chat' ? LINES.chat : LINES.streamer;

  if (reason === 'greeting') return fill(pickFresh(LINES.chat.greeting, 'greet'), v);
  if (reason === 'vote-open') return fill(pickFresh(LINES.chat.voting, 'voteopen'), v);
  if (reason === 'hype') return fill(pickFresh(LINES.chat.hype, 'hype'), v);
  if (reason === 'level-done') return fill(pickFresh(LINES.events.levelUp, 'lvl'), v);
  if (reason === 'result') {
    const t = state.vote.tally;
    const key = t.chat === t.streamer ? 'tie' : t.chat > t.streamer ? 'chat' : 'streamer';
    return fill(pickFresh(LINES.results[key], `res-${key}`), v);
  }

  if (mode === 'chat') {
    const specific = extraVars.target_message && Math.random() < 0.75;
    const pool = specific
      ? LINES.chat.questions
      : Math.random() < 0.35 && chatlog.stats(90).kekRatio > 0.15
        ? LINES.chat.reactionKek
        : Math.random() < 0.4
          ? LINES.chat.rollcall
          : LINES.chat.banter;
    return fill(pickFresh(pool, 'chat'), v);
  }

  // modo streamer: escolhe a categoria pela situação
  const chatBusy = chatlog.stats(60).count;
  let pool = LINES.streamer.levinho;
  if (reason === 'interrupt') pool = LINES.streamer.interrupt;
  else if (chatBusy > 18) pool = LINES.streamer.caos;
  else if (Math.random() < 0.3) pool = LINES.streamer.zoeira;
  else if (Math.random() < 0.25) pool = LINES.streamer.backseat;
  return fill(pickFresh(pool, 'streamer'), v);
}

/* ------------------------------------------------------------------ */
/* API pública usada pelo orquestrador                                 */
/* ------------------------------------------------------------------ */

/** Fala conversando com o chat (lê e interpreta o que mandaram) */
export async function talkToChat(extraVars = {}) {
  const { line, engine } = await generate({ mode: 'chat', reason: extraVars.reason || 'chat', extraVars });
  emitEvent({ type: 'ai', engine, mode: 'chat', line });
  return line;
}

/** Fala atrapalhando o streamer */
export async function distractStreamer(reason = 'streamer', extraVars = {}) {
  const { line, engine } = await generate({ mode: 'streamer', reason, extraVars });
  emitEvent({ type: 'ai', engine, mode: 'streamer', line });
  return line;
}

/** Reconhece o resultado da votação e monta a fala de anúncio */
export async function announceVoteResult({ tally, mode }) {
  const v = localVars();
  const key = tally.chat === tally.streamer ? 'tie' : tally.chat > tally.streamer ? 'chat' : 'streamer';
  if (config.get('round.announceWinnerLine', true)) {
    const { line, engine } = await generate({
      mode,
      reason: 'vote-result',
      extraVars: { ...v, tally },
      temperature: Math.max(0.7, Number(config.get('ai.temperature', 0.95)) - 0.2),
    });
    return { line: line || fill(pick(LINES.results[key]), v), engine };
  }
  return { line: fill(pickFresh(LINES.results[key], key), v), engine: 'local' };
}

/** Reação a eventos do jogo */
export async function reactToEvent(kind, payload = {}) {
  const map = { 'level-done': 'level-done', hype: 'hype', greeting: 'greeting', 'vote-open': 'vote-open' };
  const reason = map[kind] || kind;

  if (kind === 'level-done') {
    const { line, engine } = await generate({ mode: state.mode, reason, extraVars: payload });
    return { line, engine };
  }
  if (kind === 'hype') {
    const { line, engine } = await generate({ mode: 'chat', reason: 'hype', extraVars: payload });
    return { line, engine };
  }
  if (kind === 'vote-open') {
    const { line, engine } = await generate({ mode: 'chat', reason: 'vote-open', extraVars: payload });
    return { line, engine };
  }
  if (kind === 'greeting') {
    const { line, engine } = await generate({ mode: state.mode, reason: 'greeting', extraVars: payload });
    return { line, engine };
  }
  const { line, engine } = await generate({ mode: state.mode, reason: 'event', extraVars: payload });
  return { line, engine };
}

/* ------------------------------------------------------------------ */
/* Interpretação do CHAT pela IA                                       */
/* ------------------------------------------------------------------ */

/**
 * Lê as mensagens novas e devolve a INTERPRETAÇÃO estruturada:
 * comandos detectados, votos ambíguos resolvidos, perguntas ao robô,
 * pedidos, xingamentos, temas.
 */
export async function interpretChat(messages, { mode = state.mode, useAi = true } = {}) {
  const cmds = config.get('commands', {});
  const found = {
    votes: [],
    questions: [],
    requests: [],
    insults: [],
    topics: [],
    commands: [],
    raw: messages.map((m) => ({ user: m.display || m.user, text: m.text })),
  };
  if (!messages.length) return found;

  for (const m of messages) {
    const t = String(m.text || '');
    const lower = t.toLowerCase().trim();

    const vote = matchVote(lower, cmds);
    if (vote) found.votes.push({ mode: vote, user: m.user, display: m.display, text: t, engine: 'lexico' });

    if (/\?\s*$/.test(lower)) found.questions.push({ user: m.display, text: t });

    const robotName = String(config.get('robot.name', 'VEX')).toLowerCase();
    const streamerName = String(config.get('streamer.name', 'Streamer')).toLowerCase();
    if (new RegExp(`\\b(${escapeRe(robotName)}|rob[oô]|ia|bot)\\b`).test(lower)) {
      found.requests.push({ user: m.display, text: t });
    }
    if (new RegExp(`\\b(${escapeRe(streamerName)}|streamer|noob|bot|ruim|lixo|perna de pau)\\b`).test(lower)) {
      found.insults.push({ user: m.display, text: t });
    }
  }

  if (useAi && config.get('ai.interpretChat', true) && found.questions.length + found.votes.length > 0) {
    const aiResult = await interpretWithAi(messages, { mode });
    if (aiResult) {
      found.questions.push(...(aiResult.questions || []).filter((q) => !found.questions.some((f) => f.text === q.text)));
      found.topics.push(...(aiResult.topics || []));
      for (const v of aiResult.votes || []) {
        if (v?.user && v?.mode && !found.votes.some((f) => f.user === v.user)) {
          found.votes.push({ ...v, engine: 'ia' });
        }
      }
      if (aiResult.mood) found.mood = aiResult.mood;
      if (aiResult.summary) found.summary = aiResult.summary;
      found.interpretedByAI = true;
    }
  }

  found.topics.push(...chatlog.topics(6).map((t) => t.word));
  found.topics = [...new Set(found.topics)].slice(0, 12);
  return found;
}

function matchVote(lower, cmds) {
  const clean = lower.replace(/^[!/.#]+/, '').trim();
  const chatWords = cmds.voteChat || ['1'];
  const streamerWords = cmds.voteStreamer || ['2'];
  if (chatWords.some((w) => w && (clean === w || clean.startsWith(`${w} `)))) return 'chat';
  if (streamerWords.some((w) => w && (clean === w || clean.startsWith(`${w} `)))) return 'streamer';
  return null;
}

function escapeRe(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

async function interpretWithAi(messages, { mode }) {
  const provider = resolveProvider();
  if (!provider.online) return null;
  const sample = messages.slice(-25).map((m) => `${m.display || m.user}: ${m.text}`).join('\n');
  const sys = `Você é o interpretador de chat de uma live de games em português do Brasil.
Analise as mensagens e devolva SOMENTE JSON válido neste formato:
{"votes":[{"user":"nome","mode":"chat|streamer","why":"curto"}],"questions":[{"user":"nome","text":"pergunta"}],"topics":["tema1","tema2"],"mood":"clima do chat em 3 palavras","summary":"resumo de 1 frase do que o chat quer"}
Regras: só marque voto quando a intenção for clara (quer que o robô converse com o chat = "chat"; quer que o robô atrapalhe o streamer = "streamer"). Nunca invente usuários. Se não houver nada, devolva arrays vazios.
Modo atual do robô: ${mode}.`;
  try {
    const raw = await llmChat({
      messages: [
        { role: 'system', content: sys },
        { role: 'user', content: `Mensagens:\n${sample}` },
      ],
      temperature: 0.2,
      maxTokens: 400,
      json: true,
      timeoutMs: 12000,
    });
    return JSON.parse(extractJson(raw));
  } catch (err) {
    log('ia', `interpretação falhou: ${err.message}`);
    return null;
  }
}

function extractJson(text) {
  const s = String(text).trim();
  const start = s.indexOf('{');
  const end = s.lastIndexOf('}');
  if (start === -1 || end === -1) return '{}';
  return s.slice(start, end + 1);
}

/** A IA lê o chat e devolve uma resposta direta a uma mensagem */
export async function replyToMessage(msg) {
  const extra = {
    target_message: msg.text,
    target_user: msg.display || msg.user,
    reason: 'answer',
  };
  const { line, engine } = await generate({ mode: state.mode, reason: 'answer', extraVars: extra });
  return { line, engine };
}
