/**
 * index.js — sobe tudo: painel, overlay, chat (Twitch/YouTube/simulador),
 * votação a cada 600s e o robô de IA.
 *
 * Uso:
 *   npm start          → produção/normal
 *   npm run demo       → com chat SIMULADO (testa sem estar ao vivo)
 *   npm run dev        → reinicia sozinho ao salvar arquivos
 */
import { config, ROOT } from './config.js';
import { log } from './log.js';
import { state, bus, snapshot, emitEvent } from './state.js';
import { promptStore } from './prompt-store.js';
import { createServer } from './server.js';
import { hub } from './chat/source.js';
import { aiStatus, testAi } from './ai/llm.js';
import * as round from './game/round.js';
import { voting } from './game/voting.js';
import { chatlog } from './game/chatlog.js';

const BANNER = `
   ▄▄▄       ██▓     ██▒   █▓   ██████     ██▓
  ▒████▄    ▓██▒    ▓██░   █▒ ▒██    ▒    ▓██▒
  ▒██  ▀█▄  ▒██░     ▓██  █▒░ ░ ▓██▄      ▒██▒
  ░██▄▄▄▄██ ▒██░      ▒██ █░░   ▒   ██▒   ░██░
   ▓█   ▓██▒░██████▒   ▒▀█░   ▒██████▒▒   ░██░
   ▒▒   ▓▒█░░ ▒░▓  ░   ░ ▐░   ▒ ▒▓▒ ▒ ░   ░▓
    ▒   ▒▒ ░░ ░ ▒  ░   ░ ░░   ░ ░▒  ░ ░    ▒ ░
    ░   ▒     ░ ░        ░░   ░  ░  ░      ▒ ░
        ░       ░  ░      ░         ░      ░
  ═══════════════════════════════════════════════════════════
     A I   V S   S T R E A M E R   —   o chat decide tudo
  ═══════════════════════════════════════════════════════════`;

function banner() {
  console.log(BANNER);
  const ai = aiStatus();
  const sim = config.get('chat.simulator.enabled', false);
  const twitch = config.get('chat.twitch.channel', '');
  console.log(`   Robô: ${config.get('robot.name')}  |  Streamer: ${config.get('streamer.name')}  |  Fase: ${config.get('round.phaseSeconds')}s`);
  console.log(`   Cérebro: ${ai.online ? `${ai.label} (${ai.model})` : 'LOCAL (offline) — configure uma IA no painel para respostas geradas por LLM'}`);
  console.log(`   Chat: ${twitch ? `twitch/#${twitch}` : 'twitch não configurada'}${sim ? ' + SIMULADO' : ''}${config.get('chat.youtube.enabled') ? ' + youtube' : ''}`);
  console.log('');
}

async function main() {
  banner();

  // system prompt: observa prompts/system.md e data/prompt.md e aplica ao vivo
  promptStore.watch();

  // servidor (painel + overlay + API + WebSocket)
  const port = Number(config.get('server.port', 8787));
  const host = config.get('server.host', '0.0.0.0');
  const server = createServer();
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, host, resolve);
  });

  // chat → orquestrador (cada mensagem é lida, interpretada e votada)
  hub.onMessage((msg) => round.handleChatMessage(msg));
  hub.start();

  // eventos de ciclo de vida
  bus.on('event', (evt) => {
    if (evt.type === 'mode-change') {
      hub.simulator.setMode(evt.mode);
      state.robot.name = config.get('robot.name', 'VEX');
    }
    if (evt.type === 'speak') {
      state.tts.lastSpokenAt = Date.now();
      state.tts.speaking = true;
      setTimeout(() => {
        state.tts.speaking = false;
      }, 1500);
    }
  });

  // teste de IA no boot (só avisa, não bloqueia)
  testAi().then((r) => {
    if (r.ok) log('ia', `IA conectada: ${r.provider} / ${r.model}`);
    else if (aiStatus().provider !== 'local' && aiStatus().provider !== 'none') log('ia', `IA indisponível (${r.message}) — seguindo com o cérebro local`);
  });

  // inicia a rodada
  if (config.get('round.autoStart', true)) {
    setTimeout(() => round.startRound(), 1500);
  } else {
    log('fase', 'auto-start desligado — clique em INICIAR RODADA no painel');
  }

  // desligamento limpo
  const shutdown = (signal) => {
    log('ok', `recebi ${signal} — encerrando...`);
    try {
      round.stopRound();
      hub.stop();
      server.close();
      const summary = {
        endedAt: new Date().toISOString(),
        ...state.stats,
        level: state.level,
        mode: state.mode,
        chatMessages: chatlog.total,
      };
      console.log('   Resumo da sessão:', JSON.stringify(summary));
    } catch {
      /* ignore */
    }
    process.exit(0);
  };
  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));

  // atalhos de console:
  //   ENTER = o robô fala agora | m = troca de modo | v = abre votação
  //   p = pausa/retoma | s = marcar fase concluída | x = encerrar rodada
  //   qualquer outro texto = o robô fala lendo essa frase como pedido
  if (process.stdin.isTTY) {
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', async (chunk) => {
      const input = String(chunk).trim();
      if (!input) return round.talkNow(state.mode, 'console');
      if (input === 'm') return round.forceMode(state.mode === 'chat' ? 'streamer' : 'chat');
      if (input === 'v') return round.forceVoteOpen(60);
      if (input === 'p') return round.pause(!round.isPaused());
      if (input === 's') return round.markLevelDone({ display: 'console' });
      if (input === 'x') return round.stopRound();
      hub.ingest({ platform: 'console', user: 'streamer', display: config.get('streamer.name', 'Streamer'), text: input, isBroadcaster: true });
    });
  }

  emitEvent({ type: 'boot', at: state.bootedAt, root: ROOT });
  void snapshot;
  void voting;
}

main().catch((err) => {
  console.error('Falha ao iniciar:', err);
  process.exit(1);
});
