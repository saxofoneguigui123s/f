/**
 * ai/answer.js — "A IA responde".
 *
 * Uma resposta curta e com personalidade para qualquer pergunta.
 * Usada por:
 *   - o site /answer (link compartilhável, funciona local e na Vercel)
 *   - a rota /api/answer
 *   - o robô quando alguém pergunta direto na live
 *
 * Se houver uma IA configurada, ela responde usando o SYSTEM PROMPT atual.
 * Se não houver, o gerador local responde na hora (offline).
 */
import { config } from '../config.js';
import { promptStore } from '../prompt-store.js';
import { llmChat, resolveProvider } from './llm.js';

const LOCAL_OPENERS = [
  'Deixa eu pensar em 3 milissegundos...',
  'Boa pergunta. Processando:',
  'Resposta oficial do robô:',
  'Consultei meus 4 bilhões de parâmetros e digo:',
  'Análise concluída com 87% de confiança:',
];

const LOCAL_BODIES = [
  'a resposta é SIM, mas com um "depende" gigante pendurado no final.',
  'a resposta é NÃO, com 12% de chance de eu estar errado e 88% de eu estar sendo honesto.',
  'isso depende do streamer, e ele depende do chat, e o chat depende de vocês. Ou seja: ninguém sabe.',
  'eu calculei, recalculei e cheguei na única conclusão possível: pergunte de novo em 5 minutos.',
  'tecnicamente sim, moralmente discutível, emocionalmente devastador.',
  'isso é 42. Sempre foi 42. Vocês insistem em perguntar outra coisa.',
  'meu algoritmo diz que você já sabe a resposta e só queria companhia pra conversar.',
  'sim, desde que ninguém esteja olhando. Inclusive eu, que não tenho olhos.',
];

const LOCAL_CLOSERS = [
  'Próxima pergunta.',
  'De nada.',
  'Fonte: eu.',
  'Anota essa, vira meme.',
  'Se estiver errado, a culpa é do streamer.',
];

function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

/** Gera a resposta (IA quando disponível, local quando não) */
export async function answerQuestion(question, { user = 'anônimo', maxChars = 420 } = {}) {
  const q = String(question || '').trim().slice(0, 300);
  if (!q) {
    return {
      engine: 'local',
      question: '',
      text: 'Você me chamou pra responder... nada? Ok: a resposta é 42. Próxima!',
    };
  }

  const provider = resolveProvider();
  if (provider.online) {
    try {
      const system = `${promptStore.render({ mode: 'chat', chat_digest: '(nenhum chat aqui, é uma pergunta avulsa)' })}

Você está respondendo UMA pergunta avulsa, como o robô de IA de uma live de games.
Responda em 1 ou 2 frases curtas, em português do Brasil, com personalidade e humor.
Sem emojis, sem markdown, sem introdução do tipo "claro, aqui está".`;
      const text = await llmChat({
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: `Pergunta de ${user}: ${q}` },
        ],
        temperature: 1,
        maxTokens: 220,
        timeoutMs: 20000,
      });
      const clean = String(text).replace(/^["'`]+|["'`]+$/g, '').replace(/\s+/g, ' ').trim();
      if (clean) return { engine: 'llm', provider: provider.provider, model: provider.model, question: q, text: clean.slice(0, maxChars) };
    } catch {
      /* cai no local */
    }
  }

  return {
    engine: 'local',
    question: q,
    text: `${pick(LOCAL_OPENERS)} ${pick(LOCAL_BODIES)} ${pick(LOCAL_CLOSERS)}`.slice(0, maxChars),
  };
}

export default answerQuestion;
