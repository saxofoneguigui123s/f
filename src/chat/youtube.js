/**
 * chat/youtube.js — leitor de chat do YouTube (opcional).
 *
 * Requer o pacote `youtube-chat` (está em optionalDependencies).
 * Se não estiver instalado, o app avisa e segue funcionando com Twitch/simulador.
 */
import { EventEmitter } from 'node:events';
import { config } from '../config.js';
import { log } from '../log.js';

export class YouTubeChat extends EventEmitter {
  constructor() {
    super();
    this.chat = null;
    this.videoId = '';
    this.running = false;
  }

  async connect(videoId = config.get('chat.youtube.videoId', '')) {
    this.videoId = String(videoId || '').trim();
    if (!this.videoId) {
      this.emit('error', new Error('YOUTUBE_VIDEO_ID não configurado'));
      return;
    }
    let YoutubeChat;
    try {
      const mod = await import('youtube-chat');
      YoutubeChat = mod.YoutubeChat || mod.default?.YoutubeChat || mod.default || mod.LiveChat;
    } catch (err) {
      log('erro', 'pacote "youtube-chat" não instalado — rode: npm install youtube-chat');
      this.emit('error', new Error('youtube-chat ausente'));
      return;
    }
    if (!YoutubeChat) {
      log('erro', 'não encontrei a classe YoutubeChat no pacote instalado');
      return;
    }

    const opts = {};
    const apiKey = config.get('chat.youtube.apiKey');
    if (apiKey) opts.apiKey = apiKey;

    this.chat = new YoutubeChat(this.videoId, opts);

    this.chat.on('start', () => {
      this.running = true;
      log('youtube', `conectado no vídeo ${this.videoId}`);
      this.emit('connect', { videoId: this.videoId });
    });

    this.chat.on('error', (err) => {
      log('erro', `youtube: ${err?.message || err}`);
      this.emit('error', err);
    });

    this.chat.on('end', () => {
      this.running = false;
      this.emit('disconnect');
    });

    this.chat.on('chat', (item) => {
      const author = item.author || {};
      const text = (item.message || [])
        .map((m) => m.text || m.emojiText || '')
        .join('')
        .trim();
      if (!text) return;
      let bits = 0;
      if (item.isSuperChat && item.superChat) bits = Math.min(1000, Math.round((item.superChat.amount || 0) / 100));
      this.emit('message', {
        platform: 'youtube',
        id: item.id || `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        user: String(author.name || 'anônimo').toLowerCase(),
        display: author.name || 'anônimo',
        text,
        color: '#ff5252',
        badges: item.isOwner ? ['broadcaster'] : item.isModerator ? ['moderator'] : [],
        isMod: Boolean(item.isModerator),
        isSub: Boolean(item.isMembership),
        isVip: Boolean(item.isMembership),
        isBroadcaster: Boolean(item.isOwner),
        bits,
        t: item.timestamp ? new Date(item.timestamp).getTime() : Date.now(),
      });
    });

    try {
      await this.chat.start();
    } catch (err) {
      this.running = false;
      log('erro', `youtube: ${err.message}`);
      this.emit('error', err);
    }
  }

  /** YouTube não permite enviar mensagens por API pública — só leitura */
  say() {
    return false;
  }

  disconnect() {
    try {
      this.chat?.stop();
    } catch {
      /* ignore */
    }
    this.running = false;
  }
}
