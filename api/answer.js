/**
 * api/answer.js — função serverless (Vercel) do site "A IA responde".
 *
 * Faça deploy deste repositório na Vercel e o link
 *   https://SEU-PROJETO.vercel.app/answer?q=sua+pergunta
 * funciona pra qualquer pessoa, sem instalar nada.
 *
 * Sem chave de IA configurada, responde com o cérebro local (offline).
 * Com AI_PROVIDER + AI_API_KEY nas Environment Variables do projeto na
 * Vercel, responde com o LLM de verdade.
 */
import { answerQuestion } from '../src/ai/answer.js';

export default async function handler(req, res) {
  const query = req.query || {};
  const q = query.q || query.pergunta || '';
  const user = query.de || 'anônimo';
  const format = query.format || (req.headers.accept || '').includes('application/json') ? query.format : 'text';

  try {
    const answer = await answerQuestion(q, { user });
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Access-Control-Allow-Origin', '*');
    if (format === 'json') {
      res.status(200).json({ ok: true, ...answer });
      return;
    }
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.status(200).send(answer.text);
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
}
