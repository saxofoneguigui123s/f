/**
 * game/speak.js — a boca do robô.
 *
 * Fila de fala com espaçamento mínimo, respeitando o "cala a boca"
 * do chat (!calaboca / !mute) e o modo atual.
 *
 * Cada fala vira um evento `speak` no bus:
 *   { text, mode, reason, level, t, voice }
 *
 * O OVERLAY (overlay.html) escuta e toca a voz. Assim o áudio sai pelo
 * navegador do streamer (OBS/Chrome), no mesmo mix da live.
 * Também é possível usar um TTS de servidor: robot.voice.serverTtsCommand.
 */
import { spawn } from 'node:child_process';
import { config } from '../config.js';
import { log } from '../log.js';
import { state, emitEvent } from '../state.js';

const queue = [];
let pumping = false;
let lastSpokenAt = 0;
let counter = 0;
/** últimas falas: evita repetir a mesma frase na mesma janela de tempo */
const recentLines = [];
const RECENT_WINDOW = 10;

export function queueLength() {
  return queue.length;
}

/**
 * @param {string} text
 * @param {{mode?:string, reason?:string, priority?:number, force?:boolean}} opts
 */
export function speak(text, opts = {}) {
  const clean = String(text || '').trim();
  if (!clean) return false;

  const now = Date.now();
  if (!opts.force) {
    if (now < state.silenceUntil) {
      log('robo', `(silenciado pelo chat) ${clean}`);
      emitEvent({ type: 'line-suppressed', text: clean, reason: 'silence' });
      return false;
    }
    const minGap = Number(config.get('robot.minSecondsBetweenLines', 6)) * 1000;
    const mode = opts.mode || state.mode;
    const modeGap =
      mode === 'streamer'
        ? rand(
            Number(config.get('robot.chattiness.streamerModeMinGapSeconds', 22)),
            Number(config.get('robot.chattiness.streamerModeMaxGapSeconds', 55)),
          ) * 1000
        : 0;
    const gap = Math.max(minGap, modeGap);
    if (now - lastSpokenAt < gap && queue.length < 2) {
      // deixa na fila com um pequeno atraso em vez de perder a fala
      setTimeout(() => speak(clean, { ...opts, force: false }), Math.min(gap - (now - lastSpokenAt), 8000));
      return false;
    }
  }

  const item = {
    id: ++counter,
    text: clean,
    mode: opts.mode || state.mode,
    reason: opts.reason || 'fala',
    priority: opts.priority ?? 0,
    t: Date.now(),
  };
  queue.push(item);
  queue.sort((a, b) => b.priority - a.priority || a.t - b.t);
  pump();
  return true;
}

function rand(a, b) {
  return a + Math.random() * (b - a);
}

async function pump() {
  if (pumping) return;
  pumping = true;
  try {
    while (queue.length) {
      const item = queue.shift();
      const norm = item.text.toLowerCase().slice(0, 80);
      if (recentLines.includes(norm)) {
        log('robo', `(fala repetida descartada)`);
        continue;
      }
      recentLines.push(norm);
      if (recentLines.length > RECENT_WINDOW) recentLines.shift();
      lastSpokenAt = Date.now();

      state.robot.speaking = true;
      state.robot.queue = queue.length;
      state.robot.lastLine = item.text;
      state.robot.linesTotal += 1;
      state.stats.lines += 1;

      const voice = {
        rate: Number(config.get('robot.voice.rate', 1.05)),
        pitch: Number(config.get('robot.voice.pitch', 0.8)),
        volume: Number(config.get('robot.voice.volume', 1)),
        browser: config.get('robot.voice.browser', true),
      };

      log('robo', `» ${item.text}`);
      emitEvent({ type: 'speak', ...item, voice, level: state.level });
      serverTts(item.text, voice);

      // tempo estimado da fala (~150ms por palavra) para dar ritmo
      const words = item.text.split(/\s+/).length;
      await sleep(Math.min(9000, 700 + words * 160));

      state.robot.speaking = false;
      state.robot.queue = queue.length;
    }
  } finally {
    pumping = false;
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** TTS opcional por linha de comando (espeak-ng, say, piper, powershell…) */
function serverTts(text, voice) {
  if (!config.get('robot.voice.serverTtsEnabled', false)) return;
  const template = String(config.get('robot.voice.serverTtsCommand', '') || '').trim();
  if (!template) return;
  const cmd = template.replace(/\{text\}/gi, shellQuote(text));
  try {
    const child = spawn(cmd, { shell: true, stdio: 'ignore', windowsHide: true });
    child.on('error', (err) => log('erro', `tts: ${err.message}`));
    emitEvent({ type: 'tts', engine: 'server', text });
    log('tts', `servidor: ${text.slice(0, 60)}`);
  } catch (err) {
    log('erro', `tts: ${err.message}`);
  }
  void voice;
}

function shellQuote(s) {
  const clean = String(s).replace(/[`"$\\]/g, '');
  return `"${clean.replace(/"/g, '')}"`;
}

/** Marca que o robô está falando (usado pelo overlay) */
export function markSpeaking(isSpeaking) {
  state.robot.speaking = Boolean(isSpeaking);
  emitEvent({ type: 'robot-speaking', speaking: state.robot.speaking });
}

export function clearQueue() {
  queue.length = 0;
  emitEvent({ type: 'queue-cleared' });
}
