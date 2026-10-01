#!/usr/bin/env node
/**
 * self-test.js — checagem rápida: arquivos, imports, cérebro local,
 * votação, parser de IRC da Twitch e render do system prompt.
 *
 *   npm run self-test
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let pass = 0;
let fail = 0;

function ok(name, cond, extra = '') {
  if (cond) {
    pass += 1;
    console.log(`  ✅ ${name}${extra ? ` — ${extra}` : ''}`);
  } else {
    fail += 1;
    console.log(`  ❌ ${name}${extra ? ` — ${extra}` : ''}`);
  }
}

function section(title) {
  console.log(`\n▸ ${title}`);
}

/* ---------------- arquivos essenciais ---------------- */
section('Arquivos do projeto');
const files = [
  'package.json',
  'config/default.json',
  'prompts/system.md',
  'prompts/mode-chat.md',
  'prompts/mode-streamer.md',
  'public/index.html',
  'public/overlay.html',
  'public/robo.html',
  'public/app.js',
  'public/style.css',
  'public/answer/index.html',
  'src/index.js',
  'src/server.js',
  'src/config.js',
  'src/state.js',
  'src/prompt-store.js',
  'src/ai/brain.js',
  'src/ai/llm.js',
  'src/ai/answer.js',
  'src/ai/lines.pt.js',
  'src/chat/twitch.js',
  'src/chat/youtube.js',
  'src/chat/simulator.js',
  'src/chat/source.js',
  'src/game/round.js',
  'src/game/voting.js',
  'src/game/speak.js',
  'src/game/chatlog.js',
];
for (const f of files) ok(f, fs.existsSync(path.join(ROOT, f)));

/* ---------------- imports ---------------- */
section('Carregamento dos módulos (ESM)');
const mods = [
  'src/config.js',
  'src/log.js',
  'src/state.js',
  'src/prompt-store.js',
  'src/ai/llm.js',
  'src/ai/lines.pt.js',
  'src/ai/brain.js',
  'src/ai/answer.js',
  'src/game/chatlog.js',
  'src/game/voting.js',
  'src/game/speak.js',
  'src/game/round.js',
  'src/chat/twitch.js',
  'src/chat/youtube.js',
  'src/chat/simulator.js',
  'src/chat/source.js',
  'src/server.js',
];
const loaded = {};
for (const m of mods) {
  try {
    loaded[m] = await import(path.join(ROOT, m));
    ok(m, true);
  } catch (err) {
    ok(m, false, err.message);
  }
}

/* ---------------- cérebro local ---------------- */
section('Cérebro local (offline)');
try {
  const { LINES, fill, pickFresh, pick } = loaded['src/ai/lines.pt.js'];
  ok('banco de falas carregado', Object.keys(LINES).length > 0, `${Object.keys(LINES).length} categorias`);
  const filled = fill('Olá {streamer}, fase {fase}', { streamer: 'Fulano', fase: 3 });
  ok('substituição de variáveis', filled.includes('Fulano') && filled.includes('3'), filled);
  ok('pick/pickFresh retornam fala', typeof pick(LINES.chat.banter) === 'string' && typeof pickFresh(LINES.chat.banter) === 'string');
  const brain = loaded['src/ai/brain.js'];
  ok('exports do brain', ['talkToChat', 'distractStreamer', 'interpretChat', 'announceVoteResult', 'replyToMessage', 'reactToEvent'].every((k) => typeof brain[k] === 'function'));
} catch (err) {
  ok('cérebro local', false, err.message);
}

/* ---------------- system prompt ---------------- */
section('System prompt');
try {
  const { promptStore } = loaded['src/prompt-store.js'];
  const rendered = promptStore.render({ mode: 'streamer', chat_digest: 'chat: oi', level: 2 });
  ok('render sem variáveis cruas', !rendered.includes('{{'), rendered.slice(0, 60).replace(/\n/g, ' ') + '…');
  ok('prompt não vazio', rendered.length > 200, `${rendered.length} caracteres`);
  const original = promptStore.isCustom() ? promptStore.get() : null;
  promptStore.set('# teste\nVocê é o robô de teste.');
  ok('troca de system prompt em runtime', promptStore.get().includes('teste'));
  promptStore.reset();
  ok('reset volta ao padrão', promptStore.get() === promptStore.base && !promptStore.isCustom());
  if (original) {
    promptStore.set(original);
    ok('override original preservado', promptStore.isCustom() && promptStore.get() === original);
  }
} catch (err) {
  ok('system prompt', false, err.message);
}

/* ---------------- chatlog + votação ---------------- */
section('Chat, leitura e votação');
try {
  const { chatlog } = loaded['src/game/chatlog.js'];
  for (let i = 0; i < 12; i++) {
    chatlog.add({ user: `user${i % 3}`, display: `User${i % 3}`, text: i % 2 ? 'kkkkkk que fase ruim' : 'robo, qual a resposta?', platform: 'sim' });
  }
  const digest = chatlog.digestText(300, 40);
  ok('digest do chat gerado', digest.includes('Janela') && digest.includes('User'), `${chatlog.size} mensagens na memória`);
  ok('tópicos detectados', Array.isArray(chatlog.topics(5)));
  ok('clima do chat', typeof chatlog.mood() === 'string', chatlog.mood());

  const { voting } = loaded['src/game/voting.js'];
  voting.open_(30);
  const r1 = voting.cast({ platform: 'sim', user: 'a', display: 'A', text: '!1' }, 'chat');
  const r2 = voting.cast({ platform: 'sim', user: 'b', display: 'B', isSub: true, text: '!2' }, 'streamer');
  const r3 = voting.cast({ platform: 'sim', user: 'a', display: 'A', text: '!2' }, 'streamer'); // troca de voto
  ok('voto registrado', r1.ok && r2.ok, `chat=${voting.tally.chat} streamer=${voting.tally.streamer}`);
  ok('mudança de voto conta certo', voting.tally.chat === 0 && voting.tally.streamer === 3, `${voting.tally.chat} / ${voting.tally.streamer}`);
  ok('peso de inscrito', r2.weight === 2, `peso ${r2.weight}`);
  ok('voto duplicado é ignorado', r3.ok === true && voting.tally.streamer === 3);
  const result = voting.forceClose();
  ok('resultado da votação', result && result.winner === 'streamer' && result.reason === 'maioria', JSON.stringify(result.tally));
} catch (err) {
  ok('votação', false, err.message);
}

/* ---------------- parser IRC da Twitch ---------------- */
section('Parser IRC da Twitch');
try {
  const { parseIrc } = loaded['src/chat/twitch.js'];
  const line = '@badges=moderator/1;color=#FF0000;display-name=Fulano;id=abc-123;mod=1;subscriber=1;tmi-sent-ts=1700000000000 :fulano!fulano@fulano.tmi.twitch.tv PRIVMSG #canal :!2 atrapalha ele \\s kkk';
  const p = parseIrc(line);
  ok('tags lidas', p.tags['display-name'] === 'Fulano' && p.tags.mod === '1');
  ok('nick lido', p.prefix.user === 'fulano');
  ok('canal lido', p.params[0] === '#canal');
  ok('mensagem lida', p.params[1].startsWith('!2 atrapalha'), p.params[1]);
} catch (err) {
  ok('parser IRC', false, err.message);
}

/* ---------------- resposta pública ---------------- */
section('Site "IA responde" (offline)');
try {
  const { answerQuestion } = loaded['src/ai/answer.js'];
  const a = await answerQuestion('o robô é melhor que o streamer?', { user: 'teste' });
  ok('resposta gerada', typeof a.text === 'string' && a.text.length > 10, a.text.slice(0, 70) + '…');
} catch (err) {
  ok('resposta', false, err.message);
}

/* ---------------- servidor ---------------- */
section('Servidor');
try {
  const { createServer } = loaded['src/server.js'];
  const server = createServer();
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const port = server.address().port;
  const res = await fetch(`http://127.0.0.1:${port}/api/state`);
  const data = await res.json();
  ok('rota /api/state', res.ok && data.ok && data.state && typeof data.state.level === 'number', `fase ${data.state?.level}`);
  const res2 = await fetch(`http://127.0.0.1:${port}/`);
  const html = await res2.text();
  ok('painel servido em /', res2.ok && html.includes('AI vs Streamer'));
  const res3 = await fetch(`http://127.0.0.1:${port}/api/answer?q=2%2B2&format=json`);
  const d3 = await res3.json();
  ok('rota /api/answer', res3.ok && d3.text, d3.text.slice(0, 50) + '…');
  server.close();
} catch (err) {
  ok('servidor', false, err.message);
}

/* ---------------- resultado ---------------- */
console.log(`\n${'─'.repeat(56)}`);
console.log(`  ${fail === 0 ? '🎉 TUDO OK' : '⚠️  COM PROBLEMAS'} — ${pass} verificações passaram, ${fail} falharam`);
console.log(`${'─'.repeat(56)}\n`);
process.exit(fail === 0 ? 0 : 1);
