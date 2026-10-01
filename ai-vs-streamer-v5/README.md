# AI vs Streamer v5

Robô de stream (Twitch) com **IA de verdade**: ele conversa com o chat e, quando o chat
manda, entra em **modo TROLL** para atrapalhar o streamer. O provedor padrão é o
**[APInex](https://apinex.bond)** — uma key só, vários modelos (GPT, Claude, Gemini,
DeepSeek, GLM, Kimi, Grok), com modelos gratuitos e busca web.

```
chat -> ChatReader (Twitch IRC) -> AIEngine -> provedor (APInex) -> TTS + chat
                                       ^
                            voto !chat / !troll, memórias, XP, ranking
```

## Como rodar

```bash
pip install -r requirements.txt

# 1) coloque sua key do APInex
cp .env.example .env          # e cole a key em APINEX_API_KEY=sk-apx...

# 2) teste tudo (config, chave, saldo e uma chamada real)
python main.py --check

# 3) teste sem Twitch, conversando no terminal
python main.py --simulate

# 4) valendo: Twitch + painel web
python main.py
```

Painel web: <http://localhost:8080/admin> · chat da IA: <http://localhost:8080/chat> ·
API: `/api/status`, `/api/ai`.

## Provedores de IA

| nome        | o que é                                   | key (variável de ambiente)     |
|-------------|-------------------------------------------|--------------------------------|
| `apinex`    | **padrão** — gateway com vários modelos   | `APINEX_API_KEY` (`sk-apx...`) |
| `openai`    | API oficial da OpenAI                     | `OPENAI_API_KEY`               |
| `gemini`    | Google Gemini                             | `GEMINI_API_KEY`               |
| `anthropic` | Claude                                    | `ANTHROPIC_API_KEY`            |
| `offline`   | frases prontas, sem internet/custo        | —                              |

Trocar de provedor: mude `"provider"` no `config.json` **ou** use no chat o comando
`!provedor openai`. Trocar de modelo na hora: `!modelo free/gemini-3.8-flash`.

### APInex em detalhes

- Base URL: `https://api.apinex.bond/v1` (compatível com OpenAI — `/chat/completions`).
- Auth: `Authorization: Bearer sk-apx...` (aceita também `x-api-key`).
- Key grátis em <https://apinex.bond/keys>; os modelos com prefixo `free/`
  (ex.: `free/gpt-6-luna`, `free/gemini-3.8-flash`, `free/deepseek-v4.1-flash`)
  não custam saldo; os pagos debitam do saldo em dólar (`/v1/balance`).
- **Limite de requisições:** ~5 RPM por IP no plano gratuito e ~30 RPM com assinatura.
  Por isso o robô limita as respostas automáticas (`ai.responses_per_minute: 4` e
  `ai.reply_cooldown: 6` no `config.json`). Se estourar, o robozinho responde com
  retry automático (429/5xx) e devolve uma frase educada em vez de travar.
- Busca web na mesma key: comando `!busca <assunto>` (usa `/v1/tools/web/search`).
- Erros tratados: 401 (key inválida), 402 (saldo), 429 (limite), 5xx (instabilidade) —
  cada um explica no console o que fazer. Sem rede/sem chave, o robô cai para o
  provedor reserva (`fallback_provider`, padrão `offline`) para o stream não ficar mudo.

## O que o robô faz

- **Responde o chat**: quando alguém menciona o bot (`robô`, `robo`, `bot`, `ia` — veja
  `ai.bot_names`), ele responde em até 2 frases e fala no TTS.
- **Modo TROLL**: votação a cada `voting_interval` (600s, ou 60s no modo caos com
  `!caos`). O time vencedor é aplicado e o robô trolla com mini-games (dica falsa,
  drama, comando falso...).
- **Memória**: `!lembra o streamer odeia lag` / `!esquece lag` (salvo em `data/`).
- **XP / ranking / badges**: `!xp`, `!ranking`, `!badges`.
- **Dificuldade do troll**: `!level 7`, escala sozinha conforme o jogo anda.
- **Elogio**: `!gg` quando o streamer joga bem.
- **Comandos de voz** (opcional, precisa de microfone): "ei robô, ativa o modo troll".

Comandos completos no chat: `!help`.

## Arquivos

| arquivo                     | o que faz                                                   |
|-----------------------------|-------------------------------------------------------------|
| `main.py`                   | loop principal + CLI (`--check`, `--simulate`, `--no-web`)  |
| `ai_engine.py`              | prompt, memórias, histórico, limites e troca de provedor    |
| `providers/`                | clientes de IA (`apinex.py`, `openai_*`, `gemini_*`, ...)   |
| `providers/http_client.py`  | HTTP com retry/backoff, SSE e erros amigáveis               |
| `chat_reader.py`            | Twitch IRC (TLS, reconexão) + fila de mensagens             |
| `terminal_chat.py`          | chat simulado no terminal (para testar)                     |
| `voting.py`, `emoji_voting.py` | votação `!chat` / `!troll` e por emoji                   |
| `mini_games.py`, `troll_logic.py` | conteúdo do modo troll                                |
| `tts_engine.py`             | voz do robô (gTTS, com pygame ou player do sistema)         |
| `web_panel.py`              | painel Flask (`/admin`, `/chat`, `/api/...`)                |
| `achievements.py`, `chat_levels.py`, `ranking.py` | badges, XP e ranking          |
| `tests/`                    | 100 testes rodando sem internet (IA + Twitch falso)          |
| `tests/fake_twitch.py`      | servidor IRC de mentira para testar o chat                   |

## Socorro: "conecta, mas não responde"

Rode **um** comando e ele diz exatamente o que está faltando:

```bash
python main.py --check                        # testa IA + Twitch
python main.py --check --say "ola chat"       # ...e manda uma mensagem de teste no seu chat
```

As 4 causas, em ordem de frequência:

| Sintoma no console / painel                                   | Causa                                            | Solução |
|---------------------------------------------------------------|--------------------------------------------------|---------|
| `!!! SEM TOKEN: modo anonimo (so leitura)`                     | falta o token do Twitch                          | ponha `TWITCH_OAUTH=<token>` no `.env` (escopos `chat:read` **e** `chat:edit`) |
| `!!! TOKEN DO TWITCH RECUSADO: Login authentication failed`    | token expirado/errado (o antigo vazou no GitHub) | gere outro em twitchtokengenerator.com |
| `nao respondi "..." -> nao citaram o robo (modo 'mentions')`   | ninguém chamou o robô pelo nome                  | diga `robô`/`bot`, use `!pergunta`, ou mude `ai.reply_mode` para `"all"` |
| `IA: apinex / ... (sem chave - usando frases prontas)`         | falta a `APINEX_API_KEY` no `.env`               | pegue uma key em apinex.bond/keys |

Detalhes que ajudam a entender:

- **Conectar ≠ poder falar.** Sem token, o IRC da Twitch aceita a conexão anônima: o robô
  lê o chat, mas a Twitch não deixa escrever. O código agora avisa isso na hora e o
  painel (`/admin` e `/api/status`) mostra `can_send: false` com o motivo.
- **Token recusado:** o robô deixava de dizer "conectada" antes de autenticar (bug
  corrigido). Agora ele espera o `001 Welcome`, e se a Twitch recusar ele grita o motivo
  e continua em modo anônimo (lendo) em vez de fingir que está tudo bem.
- **Limite de respostas:** `ai.responses_per_minute` (4) e `ai.reply_cooldown` (6s)
  seguram a cota do APInex — mensagens do chat podem ser ignoradas de propósito; o
  console explica isso também.
- O TTS depende de `gTTS` + um player (`pygame`, `ffplay`, `mpg123`...). Sem isso o robô
  continua respondendo no chat e imprimindo no console, só não sai som.

## Testes

```bash
python -m unittest discover -s tests -t .
```

Rodam com um transporte HTTP falso e um servidor IRC de mentira — não gastam cota, não
precisam de chave e não precisam de internet.

## Avisos

- **Rotacione o token do Twitch.** O token antigo estava escrito no `config.json`
  publicado (e continua no histórico do Git). Ele foi removido do arquivo: agora o
  token vem do `.env`/ambiente (`TWITCH_OAUTH`, via `"oauth": "env:TWITCH_OAUTH"` no
  config). Gere um novo em <https://twitchtokengenerator.com>
  (escopos `chat:read` + `chat:edit`).
- Sem token, o robô entra no Twitch em modo anônimo: **só leitura** — ele vê o chat,
  mas não consegue responder. O console e o painel avisam.
- **YouTube ainda não está implementado** (`chat_reader.py` era um stub vazio); o
  áudio do TTS depende do `gTTS` e de um player (`pygame`, `ffplay`, `mpg123`...).
- Os arquivos de som em `sounds/` (`ding.wav`, `sinister.wav`...) são opcionais: se não
  existirem, o robô simplesmente não toca efeito.
