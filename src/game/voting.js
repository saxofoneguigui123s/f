/**
 * game/voting.js — a votação do chat.
 *
 * A cada rodada (600s por padrão), nos últimos 60s, o chat vota:
 *   !1  → o robô fala COM O CHAT
 *   !2  → o robô fala COM O STREAMER (para atrapalhar)
 *
 * - votos valem por usuário (o último voto conta)
 * - pesos por cargo (sub/mod/vip) e por bits (ataque do caos)
 * - votos escritos em linguagem natural são lidos pela IA (brain.interpretChat)
 */
import path from 'node:path';
import { config, DATA_DIR, writeJsonLine } from '../config.js';
import { log } from '../log.js';
import { state, emitEvent } from '../state.js';

export class VoteSession {
  constructor() {
    this.open = false;
    this.endsAt = 0;
    this.tally = { chat: 0, streamer: 0 };
    this.votes = new Map(); // user -> { mode, weight, at, platform, engine }
    this.messagesSeen = 0;
    this._timer = null;
  }

  get total() {
    return this.tally.chat + this.tally.streamer;
  }

  /** Abre a votação por `seconds` segundos */
  open_(seconds) {
    if (this.open) return;
    this.open = true;
    this.startedAt = Date.now();
    this.endsAt = Date.now() + seconds * 1000;
    state.vote.open = true;
    state.vote.endsAt = this.endsAt;
    state.vote.tally = this.tally;
    log('votacao', `ABERTA por ${seconds}s — !1 = falar com o CHAT | !2 = atrapalhar o STREAMER`);
    emitEvent({ type: 'vote-open', seconds, endsAt: this.endsAt });
    this._tick();
    this._timer = setInterval(() => this._tick(), 1000);
    this._timer.unref?.();
  }

  _tick() {
    const left = Math.max(0, Math.round((this.endsAt - Date.now()) / 1000));
    state.vote.secondsLeft = left;
    emitEvent({ type: 'vote-tick', secondsLeft: left, tally: this.tally, total: this.total });
    if (left <= 0) this.forceClose();
  }

  weightFor(msg) {
    const w = config.get('votes.weights', {});
    let weight = Number(w.viewer ?? 1);
    if (msg.isSub) weight = Math.max(weight, Number(w.subscriber ?? 2));
    if (msg.isVip) weight = Math.max(weight, Number(w.vip ?? 2));
    if (msg.isMod) weight = Math.max(weight, Number(w.moderator ?? 3));
    if (msg.isBroadcaster) weight = Math.max(weight, Number(w.broadcaster ?? 3));
    const bits = Number(msg.bits || 0);
    const bitsPerPoint = Number(w.bitsPerPoint ?? 10);
    if (bits > 0 && bitsPerPoint > 0) weight += Math.floor(bits / bitsPerPoint);
    return Math.max(1, Math.min(50, weight));
  }

  /**
   * Registra um voto.
   * @returns {{ok:boolean, reason?:string, weight?:number}}
   */
  cast(msg, mode, { engine = 'lexico' } = {}) {
    if (!this.open) return { ok: false, reason: 'fechada' };
    if (mode !== 'chat' && mode !== 'streamer') return { ok: false, reason: 'invalido' };

    const key = `${msg.platform}:${String(msg.user || '').toLowerCase()}`;
    const weight = this.weightFor(msg);
    const prev = this.votes.get(key);

    if (prev) {
      if (!config.get('round.allowVoteChange', true)) return { ok: false, reason: 'ja-votou' };
      if (prev.mode === mode) return { ok: true, weight: prev.weight, repeat: true };
      this.tally[prev.mode] = Math.max(0, this.tally[prev.mode] - prev.weight);
    }

    this.votes.set(key, {
      mode,
      weight,
      at: Date.now(),
      platform: msg.platform,
      display: msg.display || msg.user,
      user: msg.user,
      engine,
      text: msg.text,
    });
    this.tally[mode] += weight;
    state.stats.votes += 1;
    state.vote.tally = this.tally;
    state.vote.total = this.total;
    state.vote.voters = this.votesSummary();

    const kind = mode === 'chat' ? 'chat' : 'streamer';
    // histórico em JSONL (o relatório `npm run votes` lê este arquivo)
    writeJsonLine(path.join(DATA_DIR, 'votes.jsonl'), {
      t: Date.now(),
      level: state.level,
      user: msg.display || msg.user,
      platform: msg.platform,
      mode: kind,
      weight,
      engine,
      text: String(msg.text || '').slice(0, 200),
    });
    log('voto', `${msg.display || msg.user} → ${kind.toUpperCase()} (peso ${weight}${engine === 'ia' ? ', via IA' : ''}) | chat ${this.tally.chat} x ${this.tally.streamer} streamer`);
    emitEvent({
      type: 'vote',
      mode: kind,
      user: msg.display || msg.user,
      weight,
      engine,
      tally: { ...this.tally },
      total: this.total,
    });
    return { ok: true, weight };
  }

  votesSummary() {
    const out = {};
    for (const [k, v] of this.votes) out[k] = { mode: v.mode, weight: v.weight, display: v.display };
    return out;
  }

  /** Fecha agora, calcula o resultado (sem trocar o modo ainda) */
  forceClose() {
    if (!this.open) return null;
    this.open = false;
    clearInterval(this._timer);
    const chat = this.tally.chat;
    const streamer = this.tally.streamer;
    const total = chat + streamer;
    const minVotes = Number(config.get('round.minVotesToChange', 3));

    let winner;
    let reason;
    if (total < minVotes) {
      winner = state.mode; // sem quórum, mantém
      reason = 'sem-quorum';
    } else if (chat === streamer) {
      winner = config.get('round.tieKeepsCurrentMode', true) ? state.mode : Math.random() < 0.5 ? 'chat' : 'streamer';
      reason = 'empate';
    } else {
      winner = chat > streamer ? 'chat' : 'streamer';
      reason = 'maioria';
    }

    const result = {
      winner,
      reason,
      tally: { chat, streamer },
      total,
      voters: this.votes.size,
      changed: winner !== state.mode,
      previousMode: state.mode,
      pct: {
        chat: total ? Math.round((chat / total) * 100) : 0,
        streamer: total ? Math.round((streamer / total) * 100) : 0,
      },
      at: Date.now(),
    };

    state.vote.open = false;
    state.vote.secondsLeft = 0;
    state.vote.lastResult = result;
    state.vote.interpretedByAI = this._aiVotes || 0;

    log(
      'votacao',
      `ENCERRADA — chat ${chat} x ${streamer} streamer | vencedor: ${winner.toUpperCase()} (${reason})${result.changed ? ' → TROCA DE MODO' : ' → mantém'}`,
    );
    emitEvent({ type: 'vote-result', result });

    this.tally = { chat: 0, streamer: 0 };
    this.votes = new Map();
    return result;
  }

  noteAiVote() {
    this._aiVotes = (this._aiVotes || 0) + 1;
    state.vote.interpretedByAI = this._aiVotes;
  }
}

export const voting = new VoteSession();
