/**
 * chat/source.js — junta Twitch + YouTube + Simulador num só fluxo.
 *
 * Toda mensagem que chega passa por aqui:
 *   1. entra na memória (chatlog)
 *   2. gera estatísticas + detecção de hype
 *   3. é entregue ao orquestrador (round.js) → que decide falar/votar
 *   4. vira evento no bus (painel + overlay + IA)
 */
import { config } from '../config.js';
import { log } from '../log.js';
import { state, emitEvent } from '../state.js';
import { chatlog } from '../game/chatlog.js';
import { TwitchChat } from './twitch.js';
import { YouTubeChat } from './youtube.js';
import { ChatSimulator } from './simulator.js';

export class ChatHub {
  constructor() {
    this.twitch = new TwitchChat();
    this.youtube = new YouTubeChat();
    this.simulator = new ChatSimulator();
    this.handlers = [];
    this.hypeWindow = [];
    this.started = false;
  }

  onMessage(fn) {
    this.handlers.push(fn);
  }

  start() {
    if (this.started) return this;
    this.started = true;

    // ---- Twitch ----
    this.twitch.on('message', (m) => this.ingest(m));
    this.twitch.on('connect', ({ channel }) => {
      state.chat.connected = true;
      state.chat.platform = 'twitch';
      state.chat.channel = channel;
      emitEvent({ type: 'chat-connection', platform: 'twitch', connected: true, channel });
    });
    this.twitch.on('disconnect', () => {
      state.chat.connected = false;
      emitEvent({ type: 'chat-connection', platform: 'twitch', connected: false });
    });
    this.twitch.on('error', (err) => {
      state.chat.connected = false;
      emitEvent({ type: 'chat-error', platform: 'twitch', message: err.message });
    });

    const twitchChannel = config.get('chat.twitch.channel', '');
    if (config.get('chat.twitch.enabled', true) && twitchChannel) {
      this.twitch.connect(twitchChannel);
    } else {
      log('twitch', 'sem canal configurado (defina TWITCH_CHANNEL no .env ou no painel)');
    }

    // ---- YouTube ----
    if (config.get('chat.youtube.enabled', false) && config.get('chat.youtube.videoId', '')) {
      this.youtube.on('message', (m) => this.ingest(m));
      this.youtube.on('connect', ({ videoId }) => {
        state.chat.connected = true;
        state.chat.platform = 'youtube';
        emitEvent({ type: 'chat-connection', platform: 'youtube', connected: true, channel: videoId });
      });
      this.youtube.on('error', (err) => emitEvent({ type: 'chat-error', platform: 'youtube', message: err.message }));
      this.youtube.connect(config.get('chat.youtube.videoId', ''));
    }

    // ---- Simulador ----
    if (config.get('chat.simulator.enabled', false)) {
      this.simulator.on('message', (m) => this.ingest(m));
      this.simulator.connect();
    }

    return this;
  }

  /** Ponto único de entrada de mensagens */
  ingest(raw) {
    if (!raw || !raw.text) return null;
    const msg = chatlog.add(raw);
    state.chat.messages += 1;
    state.chat.messagesThisPhase += 1;
    state.chat.lastMessageAt = msg.t;
    state.stats.chatMessagesRead += 1;

    this.trackHype();
    emitEvent({ type: 'chat-message', message: msg });
    for (const fn of this.handlers) {
      try {
        fn(msg);
      } catch (err) {
        log('erro', `handler de chat: ${err.message}`);
      }
    }
    return msg;
  }

  /** Conta mensagens por 10s para detectar hype */
  trackHype() {
    const now = Date.now();
    this.hypeWindow.push(now);
    this.hypeWindow = this.hypeWindow.filter((t) => now - t < 10000);
    const perMinute = this.hypeWindow.length * 6;
    state.chat.hype = perMinute;
    return perMinute;
  }

  isHype() {
    const trigger = Number(config.get('robot.chattiness.hypeMessagesToTrigger', 12));
    return this.hypeWindow.length >= Math.max(4, Math.round(trigger / 3));
  }

  /** Fala no chat da Twitch (se tiver token) */
  sayTwitch(text) {
    return this.twitch.say(text);
  }

  /** Texto de ajuda que o robô fala quando alguém pede !regras */
  helpText() {
    const prefix = config.get('commands.prefix', '!');
    const robo = config.get('robot.name', 'VEX');
    const minutes = Math.round(Number(config.get('round.phaseSeconds', 600)) / 60);
    return `A cada ${minutes} minutos o chat vota: ${prefix}1 para ${robo} conversar com vocês e ${prefix}2 para ${robo} atrapalhar o streamer.`;
  }

  stop() {
    this.twitch.disconnect();
    this.youtube.disconnect();
    this.simulator.disconnect();
    this.started = false;
  }
}

export const hub = new ChatHub();
