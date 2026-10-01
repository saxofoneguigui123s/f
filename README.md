# 🤖 AI vs Streamer

**O chat vota a cada 10 minutos: o robô de IA conversa com o público ou atrapalha o streamer enquanto ele tenta passar de fase?**

Um robô de IA que vive na sua live. Ele **lê o chat inteiro**, **fala em voz alta** (com o áudio entrando direto no OBS), **responde perguntas** e, a cada fase de 600 segundos, o chat decide com quem ele fala:

| Voto | O que acontece |
|---|---|
| `!1` | 💬 **Modo CHAT** — o robô conversa com os espectadores, lê e responde as mensagens, comenta os memes |
| `!2` | 😈 **Modo STREAMER** — o robô fala com o streamer pra atrapalhar de propósito (e ele morre no jogo) |

Por padrão, a live **começa com o robô atrapalhando o streamer**. A cada votação ganha, ele troca de vítima e a fase reinicia com o nível +1.

**Funciona sem configurar nada.** Sem chave de IA, o robô usa o cérebro local (falas prontas). Sem estar ao vivo, você testa com o chat simulado. Com chave de IA (Groq tem plano grátis, ou Ollama local de graça), ele passa a **ler o chat e criar as falas na hora** usando o **system prompt que você edita sem mexer no código**.

---

## 🚀 Início rápido

```bash
# 1. dependências (só uma: ws)
npm install

# 2. teste tudo antes de ir ao ar
npm run self-test

# 3. demo com chat SIMULADO — perfeito pra gravar o vídeo de apresentação
npm run demo
```

Abra **http://localhost:8787** — esse é o painel do streamer:

- **▶ Iniciar rodada** começa o ciclo de 600s
- **🗣️ Falar agora** faz o robô falar na hora
- **🗳️ Antecipar votação** abre a votação sem esperar
- **📜 System Prompt** é onde você muda a personalidade dele
- **🧠 IA** é onde você cola a chave do modelo (ou aponta pro Ollama)
- **📡 Logs** mostra tudo: cada mensagem lida, cada voto, cada fala

Para ir ao vivo de verdade:

```bash
cp .env.example .env
# edite TWITCH_CHANNEL=seu_canal
npm start
```

---

## 📺 OBS: como o robô fala na live

Adicione **duas Fontes de Navegador** no OBS:

| Fonte | URL | Tamanho |
|---|---|---|
| Overlay completo (timer, votação, legenda + voz) | `http://localhost:8787/overlay.html` | 1920×1080 |
| Só o rosto do robô (opcional) | `http://localhost:8787/robo.html?voice=0&size=1.2` | 520×560 |

Na fonte do overlay, marque ☑ **Controlar áudio via OBS** — assim a voz do robô (`speechSynthesis` em pt-BR) entra direto na transmissão, no mesmo mix da sua live.

Parâmetros úteis do overlay:

- `?voice=0` desliga a voz (deixa só as legendas)
- `?chat=0` esconde o feed do chat
- `?scale=0.9` reduz tudo se você usa resolução menor

---

## 🎛️ Configuração

Tudo pode ser configurado de três formas, na ordem de prioridade (a última vence):

1. **`config/default.json`** — padrões do projeto
2. **`.env`** — variáveis de ambiente
3. **Painel** (salvo em `data/settings.json`) — muda ao vivo, sem reiniciar

O essencial no `.env`:

```env
TWITCH_CHANNEL=seu_canal          # lê o chat (funciona sem token!)
TWITCH_OAUTH=oauth:xxxxx          # opcional: robô escreve no chat
TWITCH_USERNAME=seu_bot           # opcional: junto com o token

AI_PROVIDER=auto                  # auto | groq | openai | openrouter | gemini | anthropic | ollama | lmstudio | custom | none
GROQ_API_KEY=                     # grátis em console.groq.com/keys
OLLAMA_BASE_URL=http://localhost:11434/v1   # IA local, 100% de graça

ROBOT_NAME=VEX
STREAMER_NAME=SeuNome
GAME_NAME=Hollow Knight

PHASE_SECONDS=600                 # duração da fase (o formato original)
VOTE_WINDOW_SECONDS=60            # janela de votação no fim da fase
START_MODE=streamer               # streamer = atrapalha | chat = conversa

SIM=1                             # chat simulado pra testar
```

> **Sem token da Twitch** o robô lê o chat anonimamente (o padrão pra bots de leitura). Para ele **escrever** no chat, gere um *Bot Chat Token* em [twitchtokengenerator.com](https://twitchtokengenerator.com) com os escopos `chat:read chat:edit`.

---

## 🧠 Comandos do chat

| Comando | O que faz |
|---|---|
| `!1` ou `1` | vota pro robô falar com o **chat** |
| `!2` ou `2` | vota pro robô falar com o **streamer** (atrapalhar) |
| `robo, <pergunta>` | o robô lê e responde aquela pessoa |
| `!calaboca` | cala o robô por 45s (o clássico) |
| `!regras` | o robô explica o formato em voz alta |
| `!passou` | mod/vip marca fase concluída → fase nova |

**Votação com peso:** inscritos valem 2, VIPs 2, mods 3, o streamer 3, e **bits contam voto extra** (a cada 10 bits = +1 ponto). O último voto de cada pessoa é o que conta, e votos em linguagem natural ("fala com a gente", "atrapalha ele") são **interpretados pela IA** quando estão ambíguos.

---

## 📜 O system prompt (o coração do personagem)

A personalidade do robô é um arquivo de texto. Nada de código:

```
prompts/system.md         ← personalidade base (com variáveis {{...}})
prompts/mode-chat.md      ← como ele age no modo CHAT
prompts/mode-streamer.md  ← como ele age no modo STREAMER
data/prompt.md            ← seu override salvo pelo painel
```

Edite pela aba **📜 System Prompt** do painel ou direto no arquivo: o servidor **detecta a mudança e aplica na hora**, sem reiniciar. Cada versão salva fica no histórico.

Variáveis que você pode usar dentro do prompt:

```
{{robot_name}} {{streamer_name}} {{game}} {{level}} {{mode}} {{mode_rules}}
{{time_left}} {{vote_tally}} {{total_votes}} {{language}}
{{streamer_context}}   ← o que você escreveu sobre você na aba Configuração
{{chat_digest}}        ← A LEITURA DO CHAT (clima, tópicos, quem falou, perguntas)
{{chat_recent}}        ← as últimas mensagens cruas
```

### Usando pelo código

```js
import { promptStore } from './src/prompt-store.js';

// troca o system prompt em runtime e persiste em data/prompt.md
promptStore.set('Você é o VEX, um robô sarcástico que vive numa live de speedrun...');

// lê o prompt final já renderizado com o chat do momento
console.log(promptStore.render({ mode: 'streamer' }));

// restaura o padrão de prompts/system.md
promptStore.reset();

// reage a qualquer alteração (inclusive edição manual do arquivo)
promptStore.on('change', (info) => console.log('prompt mudou!', info.source));
```

---

## 🗣️ Lendo o chat com IA

O robô não recebe mensagens soltas: ele recebe uma **leitura interpretada** do chat, montada a cada fala:

```
Janela: últimos 150s | 43 mensagens de 17 pessoas | clima: morrendo de rir
Quem mais fala: CapivaraSuprema(9), pixel_br(7), xX_noobmaster_Xx(5)
Assuntos que mais repetem: pulo, boss, desiste, robô, fase
Perguntas pendentes:
- robo, você é melhor que o streamer?
Últimas mensagens:
pixel_br: kkkkkkk perdeu de novo
CapivaraSuprema: VEX me conta uma fofoca
```

Com `ai.interpretChat` ligado, cada mensagem passa por um **interpretador** que extrai votos, perguntas, pedidos, xingamentos e temas — e decide os votos escritos em linguagem natural.

---

## 🌐 "A IA responde" (link viral)

Existe um site pronto pra compartilhar no chat:

```
http://localhost:8787/answer?q=o+robo+e+melhor+que+o+streamer%3F
```

Ele responde na hora e tem botão de copiar o link. Quer isso **hospedado e público de graça**? Faça deploy na Vercel (`vercel.json` já configurado) — o link vira `https://seu-projeto.vercel.app/answer?q=...`. Configure `AI_PROVIDER` e a chave nas *Environment Variables* do projeto pra respostas com LLM de verdade; sem chave ele responde com o cérebro local.

---

## 🔌 API (pra automatizar tudo)

| Rota | Método | Para que serve |
|---|---|---|
| `/api/state` | GET | estado completo da live |
| `/api/config` | GET/POST | ler e mudar configuração |
| `/api/prompt` | GET/POST | ler, salvar e pré-visualizar o system prompt |
| `/api/ai/test` | POST | testar se a IA conecta |
| `/api/ai/ask` | POST | perguntar pro robô |
| `/api/chat/simulate` | POST | injetar mensagem no chat (teste) |
| `/api/control` | POST | `start`, `stop`, `pause`, `mode`, `talk`, `next-level`, `vote-open`, `vote-close`, `skip-to-vote`, `mute` |
| `/api/answer?q=` | GET | resposta pública (usada pelo site) |
| `/ws` | WebSocket | estado + eventos em tempo real (o painel e o overlay usam isso) |

Exemplo:

```bash
curl -X POST localhost:8787/api/control -H 'Content-Type: application/json' \
  -d '{"action":"mode","mode":"streamer"}'
```

---

## 🧱 Estrutura

```
src/
  index.js            entrada: sobe servidor, chat, rodada
  server.js           HTTP + WebSocket + API (painel, overlay, answer)
  config.js           configuração em camadas (default → .env → painel)
  state.js            estado global + barramento de eventos
  prompt-store.js     system prompt editável em runtime
  ai/
    brain.js          pensa e escreve as falas (LLM ou local)
    llm.js            cliente OpenAI-compatível (Groq, OpenAI, Gemini, Ollama…)
    lines.pt.js       banco de falas do cérebro local
    answer.js         "a IA responde"
  chat/
    twitch.js         IRC da Twitch via WebSocket (leitura anônima + escrita)
    youtube.js        chat do YouTube (opcional)
    simulator.js      chat falso pra testar
    source.js         junta tudo e alimenta o robô
  game/
    round.js          o ciclo: fase → votação → troca de modo
    voting.js         votação com pesos e bits
    speak.js          fila de fala, silêncio, TTS
    chatlog.js        memória e leitura do chat
public/
  index.html app.js style.css   painel do streamer
  overlay.html                  overlay pro OBS (com voz e legendas)
  robo.html                     rosto animado do robô
  answer/index.html             site "a IA responde"
prompts/                        personalidade do robô (editável)
config/default.json             padrões
scripts/self-test.js            verificação completa do projeto
scripts/vote-report.js          relatório das votações
api/answer.js                   função serverless (Vercel)
```

---

## 📊 Relatório de votação

```bash
npm run votes
```

Mostra placar geral, quem mais votou, quantos votos vieram da IA, votos por fase e votos por minuto — ótimo pra cortes de vídeo ("o chat mandou o robô atrapalhar 78% das vezes").

---

## 💡 Dicas pro formato viralizar

- **Coloque o rosto do robô numa câmera secundária** e o overlay por cima do jogo. O público se apega ao personagem.
- **Deixe o chat escolher o nome do robô** na primeira live (troque em Configuração) — a audiência vota na identidade dele.
- **Momento "cala a boca"**: quando o `!calaboca` passa de 100 votos no chat, o robô obedece e solta uma última frase dramática.
- **Wooden board**: deixe o cérebro local ligado de vez em quando (aba IA → provedor `none`) pra ele responder coisa nonsense — as melhores reações vêm daí.
- **Bits = caos**: com `votes.weights.bitsPerPoint` baixo, alguém pode virar a votação sozinho. Divulgue isso.
- **Corte de 30s**: a troca de modo (flash na tela) + a fala de anúncio do vencedor é o gancho perfeito pra TikTok/Shorts.

---

## ❓ Problemas comuns

| Sintoma | Solução |
|---|---|
| Robô não fala | Clique em **🗣️ Falar agora**; confira se o overlay está aberto (é ele que toca a voz) e se o OBS está capturando o áudio da fonte |
| Sem voz no OBS | Marque *Controlar áudio via OBS* na fonte de navegador; teste `/overlay.html` no Chrome |
| Chat da Twitch vazio | Confira `TWITCH_CHANNEL` (sem `#`) e reinicie; leitura anônima funciona sem token |
| IA não conecta | Aba **IA** → **Testar conexão**; confira chave/modelo; ou rode Ollama local |
| Respostas repetitivas | Desligue o cérebro local configurando um LLM, ou aumente `ai.temperature` |
| Quero reiniciar o placar | Apague `data/votes.jsonl` |

---

Feito pra ser ao vivo, caótico e imprevisível. **O chat decide quem o robô atrapalha.** 🤖
