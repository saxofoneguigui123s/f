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
| `omnirouter`| gateway local (OmniRoute) ou na nuvem     | `OMNIROUTER_API_KEY` (opcional no local) |
| `openai`    | API oficial da OpenAI                     | `OPENAI_API_KEY`               |
| `gemini`    | Google Gemini                             | `GEMINI_API_KEY`               |
| `anthropic` | Claude                                    | `ANTHROPIC_API_KEY`            |
| `offline`   | frases prontas, sem internet/custo        | —                              |

Trocar de provedor: mude `"provider"` no `config.json` **ou** use no chat o comando
`!provedor openai`. Trocar de modelo na hora: `!modelo free/gemini-3.8-flash`.
Para testar qualquer provedor sem editar nada: `python main.py --check --provider omnirouter`.

> O bloco `providers.<nome>` manda mais que os atalhos do topo do `config.json`
> (`model`, `api_key_env`, `base_url`). É assim que trocar `"provider"` não faz o
> OmniRouter herdar o modelo do APInex (`free/gpt-6-luna`) em vez de `auto`.

### OmniRouter / OmniRoute

Um provedor cobre os três serviços com esse nome (todos falam a API da OpenAI):

| serviço | base URL | key | modelo |
|---|---|---|---|
| **OmniRoute** (open-source, auto-hospedado) | `http://localhost:20128/v1` | qualquer/nenhuma | `auto` |
| **omnirouter.li** (SaaS) | `https://omnirouter.li/v1` | `sk_live_...` | o que o painel oferece |
| **omnirouter.cc** (SaaS) | `https://omnirouter-api.cc/v1` | `Bearer $OMNI_KEY` | idem |

```jsonc
// config.json
"provider": "omnirouter",
"providers": {
  "omnirouter": {
    "base_url": "http://localhost:20128/v1",  // omita para detectar sozinho
    "api_key_env": "OMNIROUTER_API_KEY",      // aceita OMNI_API_KEY, OMNIROUTE_API_KEY, OMNI_KEY
    "model": "auto",
    "auto_detect": true,     // procura o gateway local antes de usar a nuvem
    "allow_keyless": true,   // gateway local costuma rodar sem key (REQUIRE_API_KEY=false)
    "timeout": 60
  }
}
```

- **Detecção automática:** sem `base_url`, o robô sonda `localhost:20128` e, se
  responder (mesmo 401 = gateway no ar pedindo key), usa esse endereço; senão cai para
  omnirouter.li → omnirouter.cc. Desligue com `"auto_detect": false`.
- **Sem chave só no local:** `allow_keyless` vale apenas para endereços da própria
  máquina/rede (localhost, 127.0.0.1, 192.168.x, 10.x). Serviço na nuvem **exige** key.
- Modelos: `auto` deixa o gateway escolher; também dá para fixar a rota, ex.
  `cc/claude-opus-4-6`, `gg/gemini-2.5-pro`, `if/kimi-k2-thinking` — use `!modelo <id>`.
- Erros vêm com dica: 401 (key do painel), 402 (créditos), 429 (reduza
  `ai.responses_per_minute`), e se for o gateway local fora do ar o robô avisa.

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
| `providers/`                | clientes de IA (`apinex.py`, `omnirouter.py`, `openai_*`, `gemini_*`, ...) |
| `providers/http_client.py`  | HTTP com retry/backoff, SSE e erros amigáveis               |
| `chat_reader.py`            | Twitch IRC (TLS, reconexão) + fila de mensagens             |
| `terminal_chat.py`          | chat simulado no terminal (para testar)                     |
| `voting.py`, `emoji_voting.py` | votação `!chat` / `!troll` e por emoji                   |
| `mini_games.py`, `troll_logic.py` | conteúdo do modo troll                                |
| `tts_engine.py`             | voz do robô (gTTS, com pygame ou player do sistema)         |
| `web_panel.py`              | painel Flask (`/admin`, `/chat`, `/api/...`)                |
| `achievements.py`, `chat_levels.py`, `ranking.py` | badges, XP e ranking          |
| `tests/`                    | 163 testes rodando sem internet (IA + Twitch falso)          |
| `tests/fake_twitch.py`      | servidor IRC de mentira para testar o chat                   |
| `tests/fake_apinex.py`      | APInex de mentira: dá para rodar o robô inteiro sem gastar saldo |

## Teste em 60 segundos (o robô tem que provar que está vivo)

Com `python main.py` rodando, olhe o console e faça isto no chat, nesta ordem:

| o que fazer no chat | o que o console tem que mostrar |
|---------------------|----------------------------------|
| (nada — é só esperar a conexão) | `Robô online! Digite !help para ver os comandos.` aparece **no seu chat** sozinho (é a `twitch.startup_message`) |
| digite algo qualquer, ex: `bom dia` | `[CHAT] seu_nick: bom dia` e, se ninguém citou o robô, `[IA] nao respondi "bom dia" -> nao citaram o robo (modo 'mentions')...` |
| digite `!ping` | no chat: `@seu_nick estou vivo! provedor=apinex modelo=... modo=chat \| escrevendo: chat` |
| digite `ei robô, funciona?` | `[IA] respondi para seu_nick` e a resposta no chat |

Interpretação:

- **Nada aparece no console quando o chat digita** → o robô não está recebendo o chat
  (token/canal) — rode `python main.py --check`.
- **Aparece `[CHAT] ...` mas nunca a resposta** → leia o motivo na linha seguinte
  (`nao citaram o robo`, `limite de respostas`, `sem token`, ...).
- **`!ping` responde mas as mensagens normais não** → está tudo certo: o robô só
  responde quando é chamado (`ai.reply_mode`). Use `"all"` para responder tudo.
- Sem querer esse comportamento? `"log_chat": false` no bloco `ai` desliga o log de
  cada mensagem (as explicações continuam).

## Socorro: "conecta, mas não responde"

Rode **um** comando e ele diz exatamente o que está faltando:

```bash
python main.py --check                        # testa IA + Twitch
python main.py --check --say "ola chat"       # ...e manda uma mensagem de teste no seu chat
```

Ele começa mostrando **de onde leu cada chave** (a seu pedido de "pus tudo certinho"):

```
== Arquivos e chaves ==
Pasta: /caminho/ai-vs-streamer-v5
  .env ........... encontrado em /caminho/ai-vs-streamer-v5/.env
  chaves no .env . APINEX_API_KEY, TWITCH_OAUTH
  python-dotenv .. instalado
  chaves (com o miolo escondido):
    APINEX_API_KEY   definida (sk-apx...1234) via .env
    TWITCH_OAUTH     definida (oauth:...lido) via .env
```

O `.env` é lido **sem depender do `python-dotenv`** (leitor próprio, aceita BOM
do Windows, CRLF, `export`, aspas e comentários) e o robô procura o arquivo na
pasta atual, na pasta do projeto e na pasta acima (raiz do repositório).

As 4 causas, em ordem de frequência:

| Sintoma no console / painel                                   | Causa                                            | Solução |
|---------------------------------------------------------------|--------------------------------------------------|---------|
| `NAO DEFINIDA` na seção "Arquivos e chaves"                    | o `.env` existe mas com outra chave/nome errado   | o check mostra o nome certo e sugere a correção |
| `.env ........... NAO ENCONTRADO`                              | arquivo com outro nome (`.env.txt`) ou na pasta errada | renomeie para `.env` na pasta `ai-vs-streamer-v5/` |
| `!!! SEM TOKEN: modo anonimo (so leitura)`                     | falta o token do Twitch                          | ponha `TWITCH_OAUTH=<token>` no `.env` (escopos `chat:read` **e** `chat:edit`) |
| `!!! TOKEN DO TWITCH RECUSADO: Login authentication failed`    | token expirado/errado (o antigo vazou no GitHub) | gere outro em twitchtokengenerator.com |
| `nao respondi "..." -> nao citaram o robo (modo 'mentions')`   | ninguém chamou o robô pelo nome                  | diga `robô`/`bot`, use `!pergunta`, ou mude `ai.reply_mode` para `"all"` |
| `nao respondi "..." -> limite de respostas atingido`           | cota do provedor (APInex grátis: ~5 RPM)         | espere alguns segundos ou aumente `ai.responses_per_minute` |
| `tentei responder X mas nao saiu texto`                        | a IA falhou (rede/saldo/modelo) naquele momento   | veja a linha de erro acima; o robô já tenta o plano B |
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
- **Menção é palavra inteira:** dizer "bom **dia**" não chama o robô (antes chamava,
  porque "ia" aparecia dentro de "dia" — bug corrigido). Vale `robô`, `robo`, `bot`
  ou `ia` como palavra separada (`!help` mostra tudo).
- O TTS depende de `gTTS` + um player (`pygame`, `ffplay`, `mpg123`...). Sem isso o robô
  continua respondendo no chat e imprimindo no console, só não sai som.

## Rodar sem gastar nada (dry run)

Suba o APInex de mentira e aponte o config para ele — o robô inteiro funciona,
com respostas, saldo, busca e contagem de tokens, sem gastar 1 centavo:

```bash
python tests/fake_apinex.py 8099      # em outro terminal
# config.json -> "providers": {"apinex": {"base_url": "http://127.0.0.1:8099/v1"}},
#                "api_key": "sk-apx_teste"
python main.py --check
```

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
