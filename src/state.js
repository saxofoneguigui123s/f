/**
 * state.js — estado global da live + barramento de eventos.
 *
 * Todo mundo (painel, overlay, chat, IA) escuta o bus:
 *   bus.on('event', (evt) => ...)   // evt = { type, ... }
 */
import { EventEmitter } from 'node:events';
import { config } from './config.js';

export const bus = new EventEmitter();
bus.setMaxListeners(100);

export function emitEvent(evt) {
  bus.emit('event', { ...evt, t: evt.t ?? Date.now() });
  return evt;
}

export const state = {
  bootedAt: Date.now(),
  running: false,
  level: 1,
  /** 'chat' (o robô conversa com o chat) | 'streamer' (o robô atrapalha o streamer) */
  mode: config.get('round.startMode', 'streamer'),
  previousMode: null,
  silenceUntil: 0,
  phase: {
    kind: 'idle', // idle | phase | vote
    startedAt: 0,
    endsAt: 0,
    secondsLeft: 0,
  },
  vote: {
    open: false,
    endsAt: 0,
    secondsLeft: 0,
    tally: { chat: 0, streamer: 0 },
    voters: {},
    total: 0,
    interpretedByAI: 0,
    lastResult: null,
  },
  robot: {
    name: config.get('robot.name', 'VEX'),
    speaking: false,
    queue: 0,
    lastLine: null,
    linesTotal: 0,
  },
  chat: {
    connected: false,
    platform: null,
    channel: '',
    messages: 0,
    messagesThisPhase: 0,
    lastMessageAt: 0,
    hype: 0,
  },
  ai: {
    online: false,
    brain: 'local', // local | llm
    provider: config.get('ai.provider', 'auto'),
    model: '',
    calls: 0,
    errors: 0,
    lastError: null,
    lastLatencyMs: 0,
  },
  tts: { lastSpokenAt: 0, speaking: false, engine: 'browser' },
  stats: {
    lines: 0,
    votes: 0,
    modeSwitches: 0,
    phasesCompleted: 0,
    chatMessagesRead: 0,
    startedAt: Date.now(),
  },
};

/** Snapshot serializável para o painel/overlay */
export function snapshot() {
  return {
    ...structuredClone(state),
    config: {
      phaseSeconds: config.get('round.phaseSeconds', 600),
      voteWindowSeconds: config.get('round.voteWindowSeconds', 60),
      startMode: config.get('round.startMode', 'streamer'),
      minVotesToChange: config.get('round.minVotesToChange', 3),
      streamer: config.get('streamer', {}),
      robot: config.get('robot', {}),
      overlay: config.get('overlay', {}),
      ai: { provider: config.get('ai.provider'), model: config.get('ai.model') },
      votes: config.get('votes.weights', {}),
    },
    now: Date.now(),
  };
}
