/**
 * config.js — configuração do AI VS STREAMER
 *
 * Ordem de precedência (o último ganha):
 *   1. config/default.json         (padrões versionados no repo)
 *   2. .env                        (variáveis de ambiente)
 *   3. data/settings.json          (o que você salva pelo PAINEL ou por código)
 *
 * Tudo pode ser lido/escrito em runtime:
 *   import { config } from './config.js';
 *   config.get('robot.name');                 // -> "VEX"
 *   config.set('ai.model', 'gpt-4o-mini');    // salva e notifica o app todo
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import url from 'node:url';
import { EventEmitter } from 'node:events';

export const ROOT = path.resolve(path.dirname(url.fileURLToPath(import.meta.url)), '..');
/** Em hospedagens serverless (Vercel) só /tmp é gravável */
export const DATA_DIR = process.env.VERCEL
  ? path.join(os.tmpdir(), 'ai-vs-streamer')
  : path.join(ROOT, 'data');
export const PUBLIC_DIR = path.join(ROOT, 'public');
export const PROMPTS_DIR = path.join(ROOT, 'prompts');
export const CONFIG_DIR = path.join(ROOT, 'config');

try {
  fs.mkdirSync(DATA_DIR, { recursive: true });
} catch {
  /* ambiente somente-leitura: segue com o que já existe */
}

/* ------------------------------------------------------------------ */
/* .env leve (sem dependência externa)                                  */
/* ------------------------------------------------------------------ */
export function loadDotEnv(file = path.join(ROOT, '.env')) {
  if (!fs.existsSync(file)) return;
  const raw = fs.readFileSync(file, 'utf8');
  for (const line of raw.split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith('#')) continue;
    const eq = t.indexOf('=');
    if (eq === -1) continue;
    const key = t.slice(0, eq).trim();
    let val = t.slice(eq + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    if (process.env[key] === undefined) process.env[key] = val;
  }
}
loadDotEnv();

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */
const isPlainObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

export function deepMerge(base, patch) {
  if (!isPlainObject(patch)) return patch === undefined ? base : patch;
  const out = isPlainObject(base) ? { ...base } : {};
  for (const [k, v] of Object.entries(patch)) {
    if (v === undefined) continue;
    out[k] = isPlainObject(v) ? deepMerge(out[k], v) : v;
  }
  return out;
}

const bool = (v, dflt) => {
  if (v === undefined || v === '' || v === null) return dflt;
  return /^(1|true|sim|yes|on)$/i.test(String(v));
};

/* ------------------------------------------------------------------ */
/* Config                                                              */
/* ------------------------------------------------------------------ */
class Config extends EventEmitter {
  constructor() {
    super();
    this.setMaxListeners(50);
    this.defaults = {};
    this.env = {};
    this.user = {};
    this.data = {};
    this.file = path.join(DATA_DIR, 'settings.json');
    this.reload();
  }

  reload() {
    this.defaults = readJson(path.join(CONFIG_DIR, 'default.json'), {});
    this.user = readJson(this.file, {});
    this.env = envOverrides();
    this.data = deepMerge(deepMerge(this.defaults, this.env), this.user);
    return this.data;
  }

  all() {
    return structuredCloneSafe(this.data);
  }

  get(pathStr, fallback) {
    const val = pathStr.split('.').reduce((acc, k) => (acc == null ? acc : acc[k]), this.data);
    return val === undefined ? fallback : val;
  }

  /** Sobrescreve em runtime e persiste em data/settings.json */
  set(pathStr, value, { save = true } = {}) {
    const keys = pathStr.split('.');
    let node = this.user;
    for (const k of keys.slice(0, -1)) {
      if (!isPlainObject(node[k])) node[k] = {};
      node = node[k];
    }
    node[keys.at(-1)] = value === '' ? '' : value;
    this.data = deepMerge(deepMerge(this.defaults, this.env), this.user);
    if (save) this.persist();
    this.emit('change', { path: pathStr, value, config: this.data });
    return this.data;
  }

  /** Aplica um objeto inteiro (usado pelo painel) */
  patch(obj, opts) {
    for (const [k, v] of Object.entries(flatten(obj))) this.set(k, v, { save: false });
    if (opts?.save !== false) this.persist();
    this.emit('change', { path: '*', value: obj, config: this.data });
    return this.data;
  }

  reset() {
    this.user = {};
    this.persist();
    this.data = deepMerge(deepMerge(this.defaults, this.env), this.user);
    this.emit('change', { path: '*', value: {}, config: this.data });
    return this.data;
  }

  persist() {
    writeJsonAtomic(this.file, this.user);
  }
}

function flatten(obj, prefix = '', out = {}) {
  for (const [k, v] of Object.entries(obj || {})) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (isPlainObject(v)) flatten(v, key, out);
    else out[key] = v;
  }
  return out;
}

function structuredCloneSafe(obj) {
  try {
    return structuredClone(obj);
  } catch {
    return JSON.parse(JSON.stringify(obj));
  }
}

export function readJson(file, fallback) {
  try {
    if (!fs.existsSync(file)) return fallback;
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (err) {
    console.error(`[config] falha ao ler ${file}:`, err.message);
    return fallback;
  }
}

export function writeJsonAtomic(file, obj) {
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2), 'utf8');
  fs.renameSync(tmp, file);
}

export function writeJsonLine(file, obj) {
  try {
    fs.appendFileSync(file, `${JSON.stringify(obj)}\n`, 'utf8');
  } catch (err) {
    console.error('[config] jsonl error', err.message);
  }
}

function envOverrides() {
  const e = process.env;
  return {
    server: { port: e.PORT ? Number(e.PORT) : undefined, host: e.HOST || undefined },
    streamer: { name: e.STREAMER_NAME || undefined, game: e.GAME_NAME || undefined },
    robot: { name: e.ROBOT_NAME || undefined },
    round: {
      phaseSeconds: e.PHASE_SECONDS ? Number(e.PHASE_SECONDS) : undefined,
      voteWindowSeconds: e.VOTE_WINDOW_SECONDS ? Number(e.VOTE_WINDOW_SECONDS) : undefined,
      startMode: e.START_MODE || undefined,
      autoStart: bool(e.AUTO_START, undefined),
    },
    chat: {
      twitch: {
        channel: e.TWITCH_CHANNEL || undefined,
        username: e.TWITCH_USERNAME || undefined,
        oauthToken: e.TWITCH_OAUTH || undefined,
      },
      youtube: { videoId: e.YOUTUBE_VIDEO_ID || undefined, enabled: e.YOUTUBE_VIDEO_ID ? true : undefined },
      simulator: {
        enabled: bool(e.SIM, undefined),
        messagesPerMinute: e.SIM_MESSAGES_PER_MINUTE ? Number(e.SIM_MESSAGES_PER_MINUTE) : undefined,
      },
    },
    ai: {
      provider: e.AI_PROVIDER || undefined,
      model: e.AI_MODEL || undefined,
      baseUrl: e.AI_BASE_URL || undefined,
      apiKey: e.AI_API_KEY || undefined,
      temperature: e.AI_TEMPERATURE ? Number(e.AI_TEMPERATURE) : undefined,
    },
  };
}

export const config = new Config();

/** Mostra a config sem vazar chaves de API */
export function redactedConfig() {
  const clone = structuredCloneSafe(config.data);
  const mask = (v) => (v ? `${String(v).slice(0, 6)}…${String(v).slice(-4)}` : '');
  for (const p of ['ai.apiKey', 'chat.twitch.oauthToken', 'chat.youtube.apiKey']) {
    const keys = p.split('.');
    let node = clone;
    for (const k of keys.slice(0, -1)) node = node?.[k];
    if (node && keys.at(-1) in node) node[keys.at(-1)] = mask(node[keys.at(-1)]);
  }
  return clone;
}
