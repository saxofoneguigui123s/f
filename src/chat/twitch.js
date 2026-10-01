/**
 * chat/twitch.js — leitor (e escritor) de chat da Twitch SEM dependências externas.
 *
 * Usa o IRC sobre WebSocket (wss://irc-ws.chat.twitch.tv:443) com o mesmo
 * protocolo que os bots usam. Funciona anonimamente só para LER (não
 * precisa de token). Para o robô poder ESCREVER no chat, informe
 * TWITCH_OAUTH + TWITCH_USERNAME no .env (escopos chat:read chat:edit).
 */
import { EventEmitter } from 'node:events';
import WebSocket from 'ws';
import { config } from '../config.js';
import { log } from '../log.js';

const IRC_URL = 'wss://irc-ws.chat.twitch.tv:443';
const SEND_INTERVAL_MS = 1600; // evita rate limit (20 msgs/30s)

export class TwitchChat extends EventEmitter {
  constructor() {
    super();
    this.ws = null;
    this.connected = false;
    this.channel = '';
    this.closedByUser = false;
    this.reconnectDelay = 2000;
    this.sendQueue = [];
    this.sending = false;
  }

  get canWrite() {
    return Boolean(config.get('chat.twitch.oauthToken')) && Boolean(config.get('chat.twitch.username'));
  }

  connect(channel = config.get('chat.twitch.channel', '')) {
    this.channel = String(channel || '').replace(/^#/, '').trim().toLowerCase();
    if (!this.channel) {
      this.emit('error', new Error('canal da Twitch não configurado'));
      return;
    }
    this.closedByUser = false;
    this._open();
  }

  _open() {
    try {
      this.ws = new WebSocket(IRC_URL, { handshakeTimeout: 12000 });
    } catch (err) {
      this.emit('error', err);
      return this._scheduleReconnect();
    }

    this.ws.on('open', () => {
      const token = String(config.get('chat.twitch.oauthToken', '') || '').trim();
      const hasToken = token && this.canWrite;
      if (hasToken) {
        const pass = token.startsWith('oauth:') ? token : `oauth:${token}`;
        this._raw(`PASS ${pass}`);
        this._raw(`NICK ${config.get('chat.twitch.username')}`);
      } else {
        this._raw('PASS SCHMOOPIIE');
        this._raw(`NICK justinfan${10000 + Math.floor(Math.random() * 89999)}`);
      }
      this._raw('CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership');
      this._raw(`JOIN #${this.channel}`);
    });

    this.ws.on('message', (buf) => {
      const data = buf.toString('utf8');
      for (const line of data.split('\r\n')) if (line) this._handleLine(line);
    });

    this.ws.on('close', () => {
      this.connected = false;
      this.emit('disconnect');
      if (!this.closedByUser) {
        log('twitch', `desconectado — reconectando em ${this.reconnectDelay / 1000}s`);
        this._scheduleReconnect();
      }
    });

    this.ws.on('error', (err) => {
      this.emit('error', err);
      log('erro', `twitch: ${err.message}`);
    });
  }

  _scheduleReconnect() {
    setTimeout(() => {
      if (!this.closedByUser) this._open();
    }, this.reconnectDelay);
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, 60000);
  }

  _raw(line) {
    try {
      this.ws?.send(`${line}\r\n`);
    } catch {
      /* ignore */
    }
  }

  _handleLine(line) {
    if (line.startsWith('PING')) {
      this._raw('PONG :tmi.twitch.tv');
      return;
    }
    if (line.includes(' 001 ') || line.includes('JOIN #')) {
      if (!this.connected && line.includes(`JOIN #${this.channel}`)) {
        this.connected = true;
        this.reconnectDelay = 2000;
        log('twitch', `conectado em #${this.channel}${this.canWrite ? ' (pode escrever)' : ' (só leitura)'}`);
        this.emit('connect', { channel: this.channel });
      }
      return;
    }
    if (line.includes('PRIVMSG')) this._handlePrivmsg(line);
  }

  _handlePrivmsg(line) {
    const parsed = parseIrc(line);
    if (!parsed) return;
    const { tags, prefix, params } = parsed;
    const text = params[1] ?? '';
    const msg = {
      platform: 'twitch',
      id: tags.id || `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      user: (prefix.user || tags['display-name'] || 'anon').toLowerCase(),
      display: tags['display-name'] || prefix.user || 'anon',
      text,
      color: tags.color || null,
      badges: String(tags.badges || '')
        .split(',')
        .filter(Boolean),
      isMod: tags.mod === '1',
      isSub: tags.subscriber === '1',
      isVip: tags.vip === '1',
      isBroadcaster: String(tags.badges || '').includes('broadcaster'),
      bits: Number(tags.bits || 0),
      isBot: /bot$/i.test(tags['display-name'] || ''),
      t: Number(tags['tmi-sent-ts'] || Date.now()),
    };
    this.emit('message', msg);
  }

  /** Envia uma mensagem no chat (precisa de token) */
  say(text, { silent = false } = {}) {
    if (!this.canWrite || !this.connected) {
      if (!silent) log('twitch', `(não enviei — sem token) ${text}`);
      return false;
    }
    this.sendQueue.push(String(text).slice(0, 480));
    this._flush();
    return true;
  }

  _flush() {
    if (this.sending || !this.sendQueue.length) return;
    this.sending = true;
    const next = this.sendQueue.shift();
    this._raw(`PRIVMSG #${this.channel} :${next}`);
    log('twitch', `enviado: ${next}`);
    setTimeout(() => {
      this.sending = false;
      this._flush();
    }, SEND_INTERVAL_MS);
  }

  disconnect() {
    this.closedByUser = true;
    try {
      if (this.ws && this.connected) this._raw('PART ' + `#${this.channel}`);
      this.ws?.close();
    } catch {
      /* ignore */
    }
  }
}

/** Parser IRC com tags (formato: @tags :nick!user@host PRIVMSG #canal :mensagem) */
export function parseIrc(line) {
  try {
    let rest = line;
    const tags = {};
    if (rest.startsWith('@')) {
      const sp = rest.indexOf(' ');
      const tagStr = rest.slice(1, sp);
      rest = rest.slice(sp + 1);
      for (const pair of tagStr.split(';')) {
        const eq = pair.indexOf('=');
        if (eq === -1) tags[pair] = '1';
        else {
          const k = pair.slice(0, eq);
          let v = pair.slice(eq + 1);
          v = v.replace(/\\s/g, ' ').replace(/\\:/g, ';').replace(/\\\\/g, '\\').replace(/\\r/g, '\r').replace(/\\n/g, '\n');
          tags[k] = v;
        }
      }
    }
    let prefix = {};
    if (rest.startsWith(':')) {
      const sp = rest.indexOf(' ');
      const raw = rest.slice(1, sp);
      rest = rest.slice(sp + 1);
      const [nick, host] = raw.split('@');
      const [user] = nick.split('!');
      prefix = { raw, user, host };
    }
    const parts = rest.split(' ');
    const command = parts.shift();
    const params = [];
    while (parts.length) {
      const p = parts.shift();
      if (p.startsWith(':')) {
        params.push([p.slice(1), ...parts].join(' '));
        break;
      }
      params.push(p);
    }
    return { tags, prefix, command, params };
  } catch {
    return null;
  }
}
