/**
 * prompt-store.js — o SYSTEM PROMPT do robô, editável pelo código.
 *
 * Camadas (a última ganha):
 *   1. prompts/system.md          → template padrão (versionado)
 *   2. data/prompt.md             → override salvo pelo painel OU por código
 *   3. prompts/mode-chat.md       → bloco anexado no modo "fala com o chat"
 *      prompts/mode-streamer.md   → bloco anexado no modo "atrapalha o streamer"
 *
 * API pra usar no SEU código (é só importar):
 *   import { promptStore } from './src/prompt-store.js';
 *
 *   promptStore.get()                       // template atual
 *   promptStore.set('Você é o ROBÔ...')     // troca o system prompt em runtime
 *   promptStore.render({ audience: 'chat' })// prompt final com variáveis aplicadas
 *   promptStore.reset()                     // volta pro prompts/system.md
 *   promptStore.on('change', cb)            // reage a mudanças (inclusive edição do arquivo)
 *
 * Variáveis disponíveis no template (troque no arquivo/painel):
 *   {{robot_name}} {{streamer_name}} {{game}} {{level}} {{mode}} {{mode_rules}}
 *   {{streamer_context}} {{chat_digest}} {{chat_recent}} {{total_votes}}
 *   {{vote_tally}} {{time_left}} {{language}}
 */
import fs from 'node:fs';
import path from 'node:path';
import { EventEmitter } from 'node:events';
import { DATA_DIR, PROMPTS_DIR, config } from './config.js';
import { log } from './log.js';
import { state } from './state.js';

const OVERRIDE_FILE = path.join(DATA_DIR, 'prompt.md');
const HISTORY_DIR = path.join(DATA_DIR, 'prompt-history');
const MODE_CHAT_FILE = path.join(PROMPTS_DIR, 'mode-chat.md');
const MODE_STREAMER_FILE = path.join(PROMPTS_DIR, 'mode-streamer.md');

class PromptStore extends EventEmitter {
  constructor() {
    super();
    this.promptFile = path.join(PROMPTS_DIR, 'system.md');
    this.base = '';
    this.override = '';
    this.modeChat = '';
    this.modeStreamer = '';
    this.watcher = null;
    this.reload({ silent: true });
  }

  reload({ silent = false } = {}) {
    this.base = readText(this.promptFile, FALLBACK_SYSTEM);
    this.override = readText(OVERRIDE_FILE, '');
    this.modeChat = readText(MODE_CHAT_FILE, '');
    this.modeStreamer = readText(MODE_STREAMER_FILE, '');
    if (!silent) this.emit('change', { source: 'file' });
    return this;
  }

  /** Observa os arquivos e aplica mudanças ao vivo (sem reiniciar o app) */
  watch() {
    if (this.watcher) return;
    const targets = [PROMPTS_DIR, DATA_DIR];
    const onChange = (dir) => {
      try {
        this.reload({ silent: false });
        log('ia', `system prompt recarregado (${path.basename(dir)})`);
      } catch (err) {
        log('erro', `recarregando prompt: ${err.message}`);
      }
    };
    // fs.watch é meio instável entre SOs; usamos um poll leve e barato
    let lastHash = this.hash();
    this.watcher = setInterval(() => {
      const h = this.hash();
      if (h !== lastHash) {
        lastHash = h;
        onChange(PROMPTS_DIR);
      }
    }, 1500);
    this.watcher.unref?.();
    return this;
  }

  hash() {
    return [
      readText(this.promptFile, FALLBACK_SYSTEM),
      readText(OVERRIDE_FILE, ''),
      readText(MODE_CHAT_FILE, ''),
      readText(MODE_STREAMER_FILE, ''),
    ].join('\u0000');
  }

  isCustom() {
    return Boolean(this.override.trim());
  }

  /** Template "cru", com as variáveis {{...}} */
  get() {
    return this.isCustom() ? this.override : this.base;
  }

  /** Salva um novo system prompt (persistente + histórico versionado) */
  set(text) {
    const clean = String(text ?? '');
    if (!clean.trim()) throw new Error('system prompt vazio');
    fs.mkdirSync(HISTORY_DIR, { recursive: true });
    if (this.isCustom()) {
      const stamp = new Date().toISOString().replace(/[:.]/g, '-');
      try {
        fs.writeFileSync(path.join(HISTORY_DIR, `${stamp}.md`), this.override, 'utf8');
      } catch {
        /* ignore */
      }
    }
    fs.writeFileSync(OVERRIDE_FILE, clean, 'utf8');
    this.override = clean;
    this.emit('change', { source: 'api' });
    log('ia', 'system prompt atualizado pelo código/painel');
    return true;
  }

  /** Volta ao prompts/system.md */
  reset() {
    try {
      if (fs.existsSync(OVERRIDE_FILE)) {
        fs.mkdirSync(HISTORY_DIR, { recursive: true });
        const stamp = new Date().toISOString().replace(/[:.]/g, '-');
        fs.copyFileSync(OVERRIDE_FILE, path.join(HISTORY_DIR, `${stamp}-antes-do-reset.md`));
      }
      fs.rmSync(OVERRIDE_FILE, { force: true });
    } catch {
      /* ignore */
    }
    this.override = '';
    this.emit('change', { source: 'reset' });
    log('ia', 'system prompt restaurado para o padrão');
    return true;
  }

  history() {
    try {
      return fs
        .readdirSync(HISTORY_DIR)
        .filter((f) => f.endsWith('.md'))
        .sort()
        .reverse()
        .slice(0, 30)
        .map((f) => ({
          file: f,
          preview: readText(path.join(HISTORY_DIR, f), '').slice(0, 200),
          at: fs.statSync(path.join(HISTORY_DIR, f)).mtimeMs,
        }));
    } catch {
      return [];
    }
  }

  readHistory(file) {
    const safe = path.basename(String(file));
    return readText(path.join(HISTORY_DIR, safe), '');
  }

  /** Troca só um bloco (ex.: só o modo caos) e persiste */
  patchModePrompt(mode, text) {
    const file = mode === 'chat' ? MODE_CHAT_FILE : MODE_STREAMER_FILE;
    fs.writeFileSync(file, String(text ?? ''), 'utf8');
    this.reload({ silent: true });
    this.emit('change', { source: 'mode' });
    log('ia', `bloco de modo "${mode}" atualizado`);
    return true;
  }

  getModeBlock(mode) {
    return mode === 'chat' ? this.modeChat : this.modeStreamer;
  }

  /**
   * Monta o prompt final: template + bloco do modo + variáveis preenchidas.
   * Variáveis que você não passar usam o valor atual da live (config + estado).
   * @param {object} vars
   * @returns {string}
   */
  render(vars = {}) {
    const mode = vars.mode === 'chat' ? 'chat' : 'streamer';
    const block = this.getModeBlock(mode);
    const template = [this.get().trim(), block.trim() ? `\n\n---\n\n${block.trim()}` : ''].join('');
    const filled = fillVars(template, { ...defaultVars(mode), ...vars });
    // nenhuma variável deve escapar pro modelo como {{...}}
    return filled.replace(/\{\{\s*[\w.]+\s*\}\}/g, '').replace(/[ \t]{2,}/g, ' ').replace(/\n{4,}/g, '\n\n\n').trim();
  }
}

export function fillVars(template, vars = {}) {
  const flat = {};
  for (const [k, v] of Object.entries(vars)) {
    if (v === undefined || v === null) continue;
    flat[k] = typeof v === 'object' ? safeStringify(v) : String(v);
  }
  return String(template).replace(/\{\{\s*([\w.]+)\s*\}\}/g, (m, key) => (key in flat ? flat[key] : m));
}

/** Valores vivos da live para as variáveis que não forem passadas */
function defaultVars(mode) {
  const phase = state?.phase || {};
  const vote = state?.vote || {};
  const tally = vote.tally || { chat: 0, streamer: 0 };
  return {
    robot_name: config.get('robot.name', 'VEX'),
    streamer_name: config.get('streamer.name', 'Streamer'),
    game: config.get('streamer.game', '') || 'o jogo',
    level: state?.level ?? 1,
    mode,
    mode_rules: mode === 'chat' ? 'conversar com o chat' : 'atrapalhar o streamer',
    time_left: fmtSeconds(phase.secondsLeft || 0),
    total_votes: vote.total ?? 0,
    vote_tally: `chat=${tally.chat} streamer=${tally.streamer}`,
    streamer_context: config.get('streamer.context', '') || '(nada específico informado)',
    language: config.get('ai.language', 'pt-BR'),
    chat_digest: '(sem leitura do chat)',
    chat_recent: '(vazio)',
  };
}

function fmtSeconds(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  return `${Math.floor(s / 60)}m${String(s % 60).padStart(2, '0')}s`;
}

function safeStringify(v) {
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

function readText(file, fallback) {
  try {
    if (!fs.existsSync(file)) return fallback;
    return fs.readFileSync(file, 'utf8');
  } catch {
    return fallback;
  }
}

export const FALLBACK_SYSTEM = `Você é {{robot_name}}, um robô de IA que vive dentro da live de {{streamer_name}}. Você fala português brasileiro, é rápido, engraçado e levemente insolente.`;

export const promptStore = new PromptStore();
export { OVERRIDE_FILE, MODE_CHAT_FILE, MODE_STREAMER_FILE };
