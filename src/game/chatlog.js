/**
 * game/chatlog.js — memória do chat.
 *
 * Guarda as mensagens, calcula estatísticas e produz a "LEITURA DO CHAT":
 * o resumo interpretado que a IA recebe no system prompt (quem falou,
 * o que estão pedindo, qual o clima, quais memes/tópicos apareceram).
 */
import { config } from '../config.js';

const STOPWORDS = new Set(
  `a o e é de da do das dos em no na nos nas um uma uns umas que pra para por pro com sem sob sobre como mas se sim nao não
   eu tu ele ela nós vocês eles voce você vc eh ai aí tá ta está esta tô to muito mais menos aqui ali isso isto aquilo
   kkk kkkk kkkkk haha hahaha rs rss vlw valeu blz qq q tá bom bem só so ja já ainda depois antes agora entao então
   meu minha seu sua dele dela é ser foi vai vou quer quero tem ter faz fazer n é literalmente tipo mano cara
   the of and to in is it you that on for`.split(/\s+/).filter(Boolean),
);

export class ChatLog {
  constructor() {
    this.maxSeconds = Number(config.get('chat.historySeconds', 600));
    this.messages = [];
    this.total = 0;
    this._dirty = true;
  }

  add(msg) {
    const item = {
      id: msg.id || `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      t: msg.t || Date.now(),
      user: msg.user || 'anônimo',
      display: msg.display || msg.user || 'anônimo',
      text: String(msg.text || '').slice(0, 500),
      platform: msg.platform || 'sim',
      color: msg.color || null,
      badges: msg.badges || [],
      isMod: Boolean(msg.isMod),
      isSub: Boolean(msg.isSub),
      isVip: Boolean(msg.isVip),
      isBroadcaster: Boolean(msg.isBroadcaster),
      bits: Number(msg.bits || 0),
      isBot: Boolean(msg.isBot),
    };
    this.messages.push(item);
    this.total += 1;
    this._dirty = true;
    this.prune();
    return item;
  }

  prune() {
    const cutoff = Date.now() - this.maxSeconds * 1000;
    while (this.messages.length && this.messages[0].t < cutoff) this.messages.shift();
    if (this.messages.length > 1500) this.messages.splice(0, this.messages.length - 1500);
  }

  recent(seconds = 180, limit = 60) {
    const cutoff = Date.now() - seconds * 1000;
    return this.messages.filter((m) => m.t >= cutoff).slice(-limit);
  }

  last(limit = 20) {
    return this.messages.slice(-limit);
  }

  get size() {
    return this.messages.length;
  }

  /** Estatísticas brutas */
  stats(seconds = 180) {
    const msgs = this.recent(seconds, 400);
    const users = new Map();
    let kek = 0;
    let caps = 0;
    let questions = 0;
    let emoteish = 0;
    for (const m of msgs) {
      users.set(m.user, (users.get(m.user) || 0) + 1);
      if (/k{3,}|(ha){3,}|rs{3,}|lol|lmao|😂|🤣/i.test(m.text)) kek += 1;
      if (m.text.length > 6 && m.text === m.text.toUpperCase() && /[A-ZÀ-Ú]/.test(m.text)) caps += 1;
      if (/\?\s*$/.test(m.text.trim())) questions += 1;
      if (/^[\w\s]+$/.test(m.text) && m.text.trim().split(/\s+/).length <= 2) emoteish += 1;
    }
    const top = [...users.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
    return {
      count: msgs.length,
      uniqueUsers: users.size,
      topUsers: top,
      kekRatio: msgs.length ? kek / msgs.length : 0,
      capsRatio: msgs.length ? caps / msgs.length : 0,
      questions,
      spammy: msgs.length ? emoteish / msgs.length : 0,
    };
  }

  /** Palavras mais repetidas (tópicos/memes do momento) */
  topics(n = 8) {
    const freq = new Map();
    for (const m of this.recent(240, 400)) {
      for (const raw of m.text.toLowerCase().split(/[^\p{L}\p{N}]+/u)) {
        const w = raw.trim();
        if (w.length < 3 || STOPWORDS.has(w) || /^\d+$/.test(w)) continue;
        freq.set(w, (freq.get(w) || 0) + 1);
      }
    }
    return [...freq.entries()]
      .filter(([, c]) => c > 1)
      .sort((a, b) => b[1] - a[1])
      .slice(0, n)
      .map(([w, c]) => ({ word: w, count: c }));
  }

  /** Clima do chat (usado pelas reações do robô) */
  mood() {
    const s = this.stats(120);
    if (s.kekRatio > 0.25) return 'morrendo de rir';
    if (s.capsRatio > 0.2) return 'gritando (tudo em CAPS)';
    if (s.questions > s.count * 0.3) return 'fazendo perguntas';
    if (s.count > 40) return 'super agitado';
    if (s.count < 4) return 'quieto (dormindo)';
    return 'de boa, conversando';
  }

  /** Minutos de chat formatados pra IA ler (formato curto e barato em tokens) */
  digest(seconds = 150, limit = 40) {
    const msgs = this.recent(seconds, limit);
    const s = this.stats(seconds);
    const lines = msgs.map((m) => `${m.display}: ${m.text}`).join('\n');
    return {
      windowSeconds: seconds,
      count: s.count,
      uniqueUsers: s.uniqueUsers,
      mood: this.mood(),
      topUsers: s.topUsers.map(([u, c]) => `${u}(${c})`).join(', '),
      topics: this.topics(8).map((t) => t.word).join(', '),
      questions: msgs.filter((m) => /\?\s*$/.test(m.text.trim())).slice(-5).map((m) => `${m.display}: ${m.text}`),
      sample: lines || '(o chat ainda não falou nada)',
      last: msgs.length ? `${msgs.at(-1).display}: ${msgs.at(-1).text}` : '',
    };
  }

  /** Versão em texto corrido — vai direto pro prompt da IA */
  digestText(seconds = 150, limit = 40) {
    const d = this.digest(seconds, limit);
    return [
      `Janela: últimos ${d.windowSeconds}s | ${d.count} mensagens de ${d.uniqueUsers} pessoas | clima: ${d.mood}`,
      d.topUsers ? `Quem mais fala: ${d.topUsers}` : '',
      d.topics ? `Assuntos/palavras que mais repetem: ${d.topics}` : '',
      d.questions.length ? `Perguntas pendentes:\n- ${d.questions.join('\n- ')}` : '',
      `Últimas mensagens:\n${d.sample}`,
    ]
      .filter(Boolean)
      .join('\n');
  }
}

export const chatlog = new ChatLog();
