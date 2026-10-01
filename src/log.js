/**
 * log.js — log colorido no terminal + histórico em arquivo + ring buffer
 * para o painel mostrar tudo o que aconteceu na live.
 */
import fs from 'node:fs';
import path from 'node:path';
import { DATA_DIR } from './config.js';

const COLORS = {
  reset: '\x1b[0m',
  gray: '\x1b[90m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  magenta: '\x1b[35m',
  cyan: '\x1b[36m',
  bold: '\x1b[1m',
};

const TAG_STYLE = {
  chat: COLORS.cyan,
  robo: COLORS.magenta,
  ia: COLORS.magenta,
  voto: COLORS.yellow,
  votacao: COLORS.yellow,
  twitch: COLORS.blue,
  youtube: COLORS.red,
  sim: COLORS.gray,
  tts: COLORS.green,
  fase: COLORS.bold + COLORS.green,
  erro: COLORS.red,
  ok: COLORS.green,
  painel: COLORS.blue,
};

const LOG_FILE = path.join(DATA_DIR, 'log.txt');
const ring = [];
const MAX_RING = 500;

function stamp() {
  return new Date().toISOString().slice(11, 19);
}

export function log(tag, ...args) {
  const text = args
    .map((a) => (typeof a === 'string' ? a : safeJson(a)))
    .join(' ');
  const line = { t: Date.now(), tag, text };
  ring.push(line);
  if (ring.length > MAX_RING) ring.shift();

  const color = TAG_STYLE[tag] || COLORS.gray;
  const label = tag.padEnd(8).slice(0, 8);
  process.stdout.write(`${COLORS.gray}${stamp()}${COLORS.reset} ${color}${label}${COLORS.reset} ${text}\n`);

  try {
    fs.appendFileSync(LOG_FILE, `${new Date().toISOString()} [${tag}] ${text}\n`);
  } catch {
    /* ignore */
  }
  return line;
}

function safeJson(v) {
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

export function recentLogs(limit = 200) {
  return ring.slice(-limit);
}

export const logger = { log, recentLogs };
export default log;
