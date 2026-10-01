# Meu chatbot / Minha versão de um chatbot de streamer

O robô responde o chat pro streamer (e ele lê a resposta em voz alta). O código está em
[`ai-vs-streamer-v5/`](ai-vs-streamer-v5/) — saiu do `ai-vs-streamer-v5.txt.rar` e agora
tem **provedor de IA APInex** integrado.

## O que faz

- Lê o chat da Twitch (IRC, com reconexão) e responde quando é mencionado.
- Vota a cada X segundos entre **modo CHAT** e **modo TROLL** (o troll atrapalha o
  streamer com dicas falsas, drama, comandos inventados...).
- Fala as respostas no TTS, guarda memórias do stream (`!lembra`), dá XP, badges e
  ranking de trolls, e tem painel web (`/admin`, `/chat`).

## Provedor de IA: APInex

Padrão no `config.json` (`"provider": "apinex"`, base `https://api.apinex.bond/v1`),
com fallback automático para `offline` se faltar chave/rede. Também dá para usar
`openai`, `gemini`, `anthropic` ou `offline`.

```bash
cd ai-vs-streamer-v5
cp .env.example .env         # cole a key: APINEX_API_KEY=sk-apx...
                             # e o token do chat: TWITCH_OAUTH=...
python main.py --check       # testa IA + Twitch e diz o que falta
python main.py --check --say "ola chat"   # manda uma mensagem de teste no chat
python main.py --simulate    # conversa no terminal, sem Twitch
python main.py               # valendo
```

> **Conectou mas o robô não responde no chat?** Sem o token do Twitch
> (`TWITCH_OAUTH` no `.env`, escopos `chat:read` + `chat:edit`) ele conecta em modo
> anônimo e **só consegue ler**. Rode `python main.py --check` — ele aponta a causa
> (token faltando, token recusado, falta de key da IA ou `ai.reply_mode`).

Detalhes, comandos e limitações: [ai-vs-streamer-v5/README.md](ai-vs-streamer-v5/README.md).
