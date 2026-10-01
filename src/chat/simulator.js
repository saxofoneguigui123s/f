/**
 * chat/simulator.js — CHAT FALSO para testar/demonstrar o projeto.
 *
 * Ative com SIM=1 (ou `npm run demo`). Finge espectadores que conversam,
 * pedem coisas pro robô, xingam o streamer gentilmente e VOTAM na hora
 * certa — é assim que você testa tudo sem estar ao vivo.
 */
import { EventEmitter } from 'node:events';
import { config } from '../config.js';
import { log } from '../log.js';

const USERS = [
  { name: 'pixel_br', badges: [] },
  { name: 'ZéDoSalto', badges: [] },
  { name: 'maria_gamer', badges: ['subscriber'], isSub: true },
  { name: 'CapivaraSuprema', badges: ['subscriber'], isSub: true },
  { name: 'xX_noobmaster_Xx', badges: [] },
  { name: 'mod_karol', badges: ['moderator'], isMod: true },
  { name: 'vitin_2009', badges: [] },
  { name: 'AnaComSono', badges: ['vip'], isVip: true },
  { name: 'peruano_do_grau', badges: [] },
  { name: 'lu_cas', badges: [] },
  { name: 'GamerDePote', badges: [] },
  { name: 'sofia.exe', badges: ['subscriber'], isSub: true },
];

const CHATTER = {
  geral: [
    'kkkkkkkkk perdeu de novo',
    'streamer tá jogando no hardcore do sofrimento',
    'olha isso, que vergonha alheia',
    'eu já vi essa fase 4 vezes hoje',
    'mano, desiste e vai fazer um café',
    'esse pulo foi pessoal contra o chão',
    'isso aí é bug ou é falta de talento?',
    'chat, alguém anota quantas vezes ele morreu',
    'eu tô aqui só pelo robô',
    'AO VIVO E PASSANDO VERGONHA',
    'Coloca no modo difícil, esse tá fácil demais pra você',
    'kkkkkk o robô falou mais que ele em 10 min',
    'fala comigo robo',
    'robo, você é melhor que o streamer?',
    'VEX me conta uma fofoca',
    'robo vc me ama?',
    'quanto é 7x8 robô?',
    'robo, manda o streamer calar a boca',
    'essa música da live é boa dms',
    'boa noite galera, cheguei agora',
    'primeira vez aqui, o que tá perdendo?',
    'nossa, o gráfico tá lindo hoje',
    'meu irmão joga melhor que isso com os pés',
    'ele vai passar? aposto 5 reais que não',
    'isso foi calculado? não parece',
    'VAI VAI VAI VAI',
    'AEEEEEE passou!!',
    'kkkkkkkkkkkkkkkkkk',
    'HAHAHAHAHA não acredito nisso',
    'o robô tá certo nessa discussão',
    'streamer, calma, respira',
    'chat tá mais interessante que o jogo',
    'esse jogo é bom? tô pensando em comprar',
    'meu deus ele tá travado nessa parede há 2 minutos',
  ],
  atrapalha: [
    'robo, fala com o streamer agora, por favor',
    'VEX ATRAPALHA ELE',
    'atrapalha, atrapalha, atrapalha',
    'eu pago pra ver esse caos',
    'fala da vida pessoal dele agora kkkk',
    'queremos o robô incomodando',
  ],
  falaComigo: [
    'robo fala comigo!!',
    'VEX, me responde',
    'chat mode ON, quero conversar',
    'robô, to triste, me anima',
    'conversa com a gente, deixa o streamer em paz',
    'quero saber a opinião do robô sobre pizza',
  ],
  votacao: ['!1', '!2', '!1 quero conversa', '!2 atrapalha ele', 'voto no caos', '!1', '!2', 'deixa o robô zoar o streamer'],
};

export class ChatSimulator extends EventEmitter {
  constructor() {
    super();
    this.timer = null;
    this.users = USERS.map((u) => ({ ...u, color: undefined }));
    this.voteWindow = false;
    this.mode = config.get('round.startMode', 'streamer');
    this.msgsThisPhase = 0;
  }

  connect() {
    const mpm = Math.max(2, Number(config.get('chat.simulator.messagesPerMinute', 14)));
    const intervalMs = Math.round(60000 / mpm);
    this.timer = setInterval(() => this._tick(), intervalMs);
    this.timer.unref?.();
    log('sim', `chat SIMULADO ativo (${mpm} mensagens/minuto) — teste sem estar ao vivo`);
    this.emit('connect', { channel: 'simulador' });
    return this;
  }

  setMode(mode) {
    this.mode = mode;
  }

  setVoteWindow(open) {
    this.voteWindow = open;
  }

  _tick() {
    this.prune();
    if (Math.random() < 0.12) return; // chat nunca é previsível

    const user = pick(this.users);
    let text;

    if (this.voteWindow && Math.random() < 0.55) {
      text = pick(CHATTER.votacao);
    } else if (this.mode === 'streamer' && Math.random() < 0.2) {
      text = pick(CHATTER.atrapalha);
    } else if (this.mode === 'chat' && Math.random() < 0.25) {
      text = pick(CHATTER.falaComigo);
    } else {
      text = pick(CHATTER.geral);
    }

    this.emit('message', {
      platform: 'sim',
      id: `sim-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      user: user.name.toLowerCase(),
      display: user.name,
      text,
      color: null,
      badges: user.badges || [],
      isMod: Boolean(user.isMod),
      isSub: Boolean(user.isSub),
      isVip: Boolean(user.isVip),
      isBroadcaster: false,
      bits: Math.random() < 0.02 ? 100 : 0,
      t: Date.now(),
    });
    this.msgsThisPhase += 1;
  }

  prune() {
    // mantém as "personalidades" girando pra parecer gente de verdade
    if (Math.random() < 0.01) {
      const idx = Math.floor(Math.random() * USERS.length);
      this.users[idx] = { ...USERS[idx] };
    }
  }

  say() {
    return false;
  }

  disconnect() {
    clearInterval(this.timer);
    this.timer = null;
  }
}

function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}
