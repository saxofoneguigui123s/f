#!/usr/bin/env node
/**
 * vote-report.js — relatório das votações da live.
 *
 * Lê data/votes.jsonl (gravado a cada voto) e mostra:
 *   - placar geral chat x streamer
 *   - quem mais votou e pra qual lado
 *   - quantos votos vieram da IA interpretando linguagem natural
 *   - votos por fase
 *
 *   npm run votes
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const FILE = path.join(ROOT, 'data', 'votes.jsonl');

if (!fs.existsSync(FILE)) {
  console.log('\n  Nenhum voto registrado ainda. Rode a live (ou `npm run demo`) e vote pelo painel/chat.\n');
  process.exit(0);
}

const votes = fs
  .readFileSync(FILE, 'utf8')
  .split('\n')
  .filter(Boolean)
  .map((l) => {
    try {
      return JSON.parse(l);
    } catch {
      return null;
    }
  })
  .filter(Boolean);

const total = votes.length;
const byMode = { chat: 0, streamer: 0 };
const byWeight = { chat: 0, streamer: 0 };
const users = new Map();
const byLevel = new Map();
let viaAI = 0;

for (const v of votes) {
  byMode[v.mode] = (byMode[v.mode] || 0) + 1;
  byWeight[v.mode] = (byWeight[v.mode] || 0) + (v.weight || 1);
  if (v.engine === 'ia') viaAI += 1;
  const u = users.get(v.user) || { chat: 0, streamer: 0, weight: 0, last: 0 };
  u[v.mode] += 1;
  u.weight += v.weight || 1;
  u.last = Math.max(u.last, v.t);
  users.set(v.user, u);
  const lvl = byLevel.get(v.level) || { chat: 0, streamer: 0 };
  lvl[v.mode] += 1;
  byLevel.set(v.level, lvl);
}

const bar = (n, max, size = 34) => '█'.repeat(Math.round((n / Math.max(1, max)) * size)).padEnd(size, '·');
const pct = (n, t) => `${Math.round((n / Math.max(1, t)) * 100)}%`;

console.log('\n  ══════════ AI VS STREAMER — RELATÓRIO DE VOTAÇÃO ══════════\n');
console.log(`  Votos totais: ${total}   |   lidos pela IA (linguagem natural): ${viaAI} (${pct(viaAI, total)})`);
console.log(`  Pessoas diferentes: ${users.size}\n`);

console.log('  Placar (peso dos votos):');
console.log(`   💬 CHAT     ${bar(byWeight.chat, Math.max(byWeight.chat, byWeight.streamer))} ${byWeight.chat} (${pct(byWeight.chat, byWeight.chat + byWeight.streamer)})`);
console.log(`   😈 STREAMER ${bar(byWeight.streamer, Math.max(byWeight.chat, byWeight.streamer))} ${byWeight.streamer} (${pct(byWeight.streamer, byWeight.chat + byWeight.streamer)})`);

console.log('\n  Top 10 quem mais votou:');
[...users.entries()]
  .sort((a, b) => b[1].weight - a[1].weight)
  .slice(0, 10)
  .forEach(([name, u], i) => {
    const side = u.chat > u.streamer ? '💬' : u.streamer > u.chat ? '😈' : '⚖️';
    console.log(`   ${String(i + 1).padStart(2)}. ${side} ${name.padEnd(22)} ${String(u.weight).padStart(4)} pts  (chat ${u.chat} / streamer ${u.streamer})`);
  });

console.log('\n  Votos por fase do jogo:');
[...byLevel.entries()]
  .sort((a, b) => a[0] - b[0])
  .forEach(([lvl, l]) => console.log(`   Fase ${String(lvl).padStart(3)} — chat ${String(l.chat).padStart(4)} | streamer ${String(l.streamer).padStart(4)}`));

const first = votes[0].t;
const last = votes[votes.length - 1].t;
const mins = Math.max(1, (last - first) / 60000);
console.log(`\n  Ritmo: ${(total / mins).toFixed(1)} votos por minuto (janela de ${mins.toFixed(0)} min)\n`);
console.log('  ══════════════════════════════════════════════════════════\n');
