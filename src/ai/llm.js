/**
 * ai/llm.js — cliente de LLM (compatível com a API OpenAI /chat/completions).
 *
 * Funciona com: OpenAI, Groq, OpenRouter, Google Gemini, Anthropic,
 * Ollama e LM Studio (rodando na sua máquina) ou qualquer endpoint compatível.
 *
 * Se não houver chave/endpoint, o app NÃO quebra: o cérebro local assume
 * (veja ai/brain.js), então a live roda 100% offline.
 */
import { config } from '../config.js';
import { log } from '../log.js';
import { state } from '../state.js';

export const PRESETS = {
  openai: {
    label: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    model: 'gpt-4o-mini',
    keyEnv: 'OPENAI_API_KEY',
    needsKey: true,
  },
  groq: {
    label: 'Groq (grátis e rápido)',
    baseUrl: 'https://api.groq.com/openai/v1',
    model: 'llama-3.3-70b-versatile',
    keyEnv: 'GROQ_API_KEY',
    needsKey: true,
  },
  openrouter: {
    label: 'OpenRouter',
    baseUrl: 'https://openrouter.ai/api/v1',
    model: 'meta-llama/llama-3.3-70b-instruct',
    keyEnv: 'OPENROUTER_API_KEY',
    needsKey: true,
  },
  gemini: {
    label: 'Google Gemini',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    model: 'gemini-2.0-flash',
    keyEnv: 'GEMINI_API_KEY',
    needsKey: true,
  },
  anthropic: {
    label: 'Anthropic Claude',
    baseUrl: 'https://api.anthropic.com/v1',
    model: 'claude-3-5-haiku-latest',
    keyEnv: 'ANTHROPIC_API_KEY',
    needsKey: true,
  },
  ollama: {
    label: 'Ollama (local, grátis)',
    baseUrl: process.env.OLLAMA_BASE_URL || 'http://localhost:11434/v1',
    model: 'llama3.1',
    keyEnv: null,
    needsKey: false,
  },
  lmstudio: {
    label: 'LM Studio (local)',
    baseUrl: 'http://localhost:1234/v1',
    model: 'local-model',
    keyEnv: null,
    needsKey: false,
  },
  custom: {
    label: 'Endpoint customizado',
    baseUrl: '',
    model: '',
    keyEnv: null,
    needsKey: false,
  },
  none: { label: 'Cérebro local (sem IA externa)', baseUrl: '', model: '', keyEnv: null, needsKey: false },
};

/** Descobre qual provedor usar com base na config + env */
export function resolveProvider() {
  const providerCfg = String(config.get('ai.provider', 'auto') || 'auto').toLowerCase();
  const keyFor = (name) => {
    const preset = PRESETS[name];
    return (
      config.get(`ai.apiKey`) ||
      (preset?.keyEnv ? process.env[preset.keyEnv] : '') ||
      ''
    );
  };

  if (providerCfg === 'none') {
    return { provider: 'none', online: false, baseUrl: '', model: '', apiKey: '', label: PRESETS.none.label };
  }

  if (providerCfg !== 'auto') {
    const preset = PRESETS[providerCfg] || PRESETS.custom;
    const baseUrl = providerCfg === 'custom' ? config.get('ai.baseUrl', '') : preset.baseUrl;
    const apiKey = keyFor(providerCfg);
    const model = config.get('ai.model', '') || preset.model;
    const online = Boolean(baseUrl) && (!preset.needsKey || Boolean(apiKey));
    return { provider: providerCfg, online, baseUrl, model, apiKey, label: preset.label };
  }

  // auto: primeira chave encontrada na ordem de prioridade
  const order = ['groq', 'openai', 'openrouter', 'gemini', 'anthropic'];
  for (const name of order) {
    const key = keyFor(name);
    if (key) {
      const preset = PRESETS[name];
      return {
        provider: name,
        online: true,
        baseUrl: config.get('ai.baseUrl', '') || preset.baseUrl,
        model: config.get('ai.model', '') || preset.model,
        apiKey: key,
        label: preset.label,
      };
    }
  }
  // Ollama local? (testa rápido, sem bloquear)
  return {
    provider: 'local',
    online: false,
    baseUrl: '',
    model: '',
    apiKey: '',
    label: 'Cérebro local (nenhuma chave configurada)',
  };
}

export function aiStatus() {
  const r = resolveProvider();
  return {
    provider: r.provider,
    label: r.label,
    online: r.online,
    model: r.model,
    brain: r.online ? 'llm' : 'local',
  };
}

/**
 * Chama o modelo. Retorna texto puro.
 * @param {object} opts
 * @param {Array<{role:string,content:string}>} opts.messages
 * @param {number} [opts.temperature]
 * @param {number} [opts.maxTokens]
 * @param {boolean} [opts.json]  força resposta em JSON (quando suportado)
 * @param {number} [opts.timeoutMs]
 */
export async function llmChat({ messages, temperature, maxTokens, json = false, timeoutMs } = {}) {
  const r = resolveProvider();
  if (!r.online) throw new Error('IA externa não configurada (usando cérebro local)');

  const url = `${r.baseUrl.replace(/\/$/, '')}/chat/completions`;
  const body = {
    model: r.model,
    messages,
    temperature: temperature ?? Number(config.get('ai.temperature', 0.95)),
    max_tokens: maxTokens ?? Number(config.get('ai.maxTokens', 240)),
    stream: false,
  };
  if (json) body.response_format = { type: 'json_object' };

  const ac = new AbortController();
  const ms = timeoutMs ?? Number(config.get('ai.timeoutMs', 25000));
  const timer = setTimeout(() => ac.abort(), ms);
  const started = Date.now();
  try {
    const headers = { 'Content-Type': 'application/json' };
    if (r.apiKey) headers.Authorization = `Bearer ${r.apiKey}`;
    if (r.provider === 'openrouter') {
      headers['HTTP-Referer'] = 'http://localhost';
      headers['X-Title'] = 'AI vs Streamer';
    }
    const res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body), signal: ac.signal });
    const text = await res.text();
    if (!res.ok) throw new Error(`HTTP ${res.status} — ${text.slice(0, 300)}`);
    const data = JSON.parse(text);
    const content =
      data?.choices?.[0]?.message?.content ??
      data?.choices?.[0]?.text ??
      '';
    state.ai.calls += 1;
    state.ai.lastLatencyMs = Date.now() - started;
    state.ai.online = true;
    state.ai.brain = 'llm';
    state.ai.provider = r.provider;
    state.ai.model = r.model;
    state.ai.lastError = null;
    return String(content).trim();
  } catch (err) {
    state.ai.errors += 1;
    state.ai.lastError = err.message;
    if (!state.ai.lastErrorShown || Date.now() - state.ai.lastErrorShown > 30000) {
      state.ai.lastErrorShown = Date.now();
      log('erro', `IA falhou: ${err.message}`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/** Testa a conexão com o provedor atual (botão "Testar IA" do painel) */
export async function testAi() {
  const r = resolveProvider();
  if (!r.online) return { ok: false, provider: r.provider, message: r.label };
  try {
    const out = await llmChat({
      messages: [
        { role: 'system', content: 'Responda somente com a palavra OK.' },
        { role: 'user', content: 'ping' },
      ],
      maxTokens: 10,
      temperature: 0,
      timeoutMs: 15000,
    });
    return { ok: true, provider: r.provider, model: r.model, message: out };
  } catch (err) {
    return { ok: false, provider: r.provider, model: r.model, message: err.message };
  }
}

/** Lista modelos (útil para Ollama/LM Studio no painel) */
export async function listModels() {
  const r = resolveProvider();
  if (!r.online) return [];
  try {
    const res = await fetch(`${r.baseUrl.replace(/\/$/, '')}/models`, {
      headers: r.apiKey ? { Authorization: `Bearer ${r.apiKey}` } : {},
    });
    if (!res.ok) return [];
    const data = await res.json();
    return (data.data || []).map((m) => m.id).slice(0, 200);
  } catch {
    return [];
  }
}
