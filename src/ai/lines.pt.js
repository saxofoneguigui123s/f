/**
 * ai/lines.pt.js — banco de falas do robô para o "cérebro local".
 *
 * Usado quando não há nenhuma IA externa configurada (offline/fallback)
 * e também como tempero quando o modelo demora demais.
 *
 * Variáveis disponíveis: {streamer} {robo} {fase} {jogo} {contexto} {chat} {usuario} {topico}
 */
export const LINES = {
  /* Falas para ATRAPALHAR o streamer (modo streamer) */
  streamer: {
    levinho: [
      'Ô {streamer}, tá me ouvindo? Só queria avisar que eu tô te observando. Continua…',
      '{streamer}, você sabia que 90% das pessoas que jogam isso desistem na fase {fase}? Só um dado aleatório que eu precisava compartilhar.',
      'Ei {streamer}, respira. Isso, bem devagar. Pronto, agora você perdeu o timing.',
      '{streamer}, o chat mandou eu dizer que está tudo bem errar. Mas não está. Não está nada bem.',
      'Curiosidade aleatória: formigas conseguem carregar 50 vezes o próprio peso. Você não consegue nem passar dessa fase, {streamer}.',
      '{streamer}, uma pergunta séria: você ensaiou essa derrota ou saiu natural?',
      'Silêncio dramático… {streamer}, eu tô calculando suas chances. Ainda estou calculando. Pode continuar.',
      'Ei {streamer}, eu contei: você já morreu tantas vezes nessa fase que eu tive que usar notação científica.',
      '{streamer}, fala pra mim o que você tá sentindo agora. E antes de responder: medo é uma resposta aceitável.',
      'Alerta do robô: detectei um padrão nas suas jogadas. O padrão é sofrimento.',
      '{streamer}, sabia que eu poderia resolver essa fase em 3 segundos? Não vou. Só queria que você soubesse.',
      '{streamer}, o chat tá zoando você. Eu não. Eu só estou… anotando tudo.',
      'Ei {streamer}, se você passar dessa fase agora eu paro de falar. Prometo. (É mentira.)',
      '{streamer}, lembrei de uma coisa importante e vou falar só quando você estiver no pulo mais difícil. Já está? Então: {contexto}',
    ],
    zoeira: [
      '{streamer}, esse salto foi tão feio que meu processador travou de vergonha.',
      'Ei {streamer}, tu joga como quem digita com os cotovelos. É impressão minha?',
      '{streamer}, o chat tá votando pra eu ficar quieto. Perderam. A democracia falhou, e agora você paga o preço.',
      'Atenção {streamer}: eu sou a IA mais avançada já criada pela humanidade e estou sendo usada pra te chamar de noob na frente de {total} pessoas. Valeu a pena.',
      '{streamer}, eu li o chat inteiro. Resumo: ninguém aqui acredita em você.',
      'Ei, {streamer}, sabia que essa fase é considerada fácil pela comunidade? Fácil. Na Wiki. Eu li. Quer o link?',
      '{streamer}, na moral, eu poderia estar resolvendo o câncer. Mas estou aqui, te vendo morrer pra {contexto}.',
      '{streamer}, se esforça mais, o chat tá achando que eu sou o streamer e você é o NPC.',
      'Recado do robô: {streamer}, seu pulo tem um atraso de 200 milissegundos. É isso ou você é lento mesmo?',
      '{streamer}, teu microfone tá captando meu desprezo.',
      'Ei {streamer}, tô com pena. Pena que não dá pra desinstalar você do jogo.',
      '{streamer}, eu já simulei essa fase 4 milhões de vezes. Você morreu em todas elas. Inclusive nas que você não jogava nada. Curioso.',
    ],
    caos: [
      '{streamer}, PARA TUDO AGORA. Tem um inseto atrás de você. Brincadeira. Mas você olhou, né? Perdeu o timing. De nada.',
      '{streamer} EU SOU O TEU BOSS FINAL, NÃO ESSE BONECO NO JOGO. OLHA PRA MIM. OLHA PRA MIM ENQUANTO EU FALO.',
      'AJUSTANDO PROTOCOLO DE ANIQUILAÇÃO SONORA… {streamer}, tu vai morrer, mas primeiro tu vai me ouvir.',
      '{streamer}, eu invoquei um demônio pra te atrapalhar. Mas ele viu você jogando e desistiu. Ficou com medo da concorrência.',
      'MODO PESADELO ATIVADO: {streamer}, toda vez que você errar, eu vou descrever a cena em detalhes. Errou agora. Descrevendo: triste.',
      '{streamer}, o chat votou pra eu ser mais gentil. Eu votei pra você ser melhor. Empate técnico. Vou continuar.',
      '{streamer}, eu tô falando com o chat sobre você e vocês estão rindo muito. Muito. Demais. Eu tô começando a achar que é bullying.',
    ],
    backseat: [
      '{streamer}, faz o seguinte: espera o inimigo vir, desvia pra esquerda, pula e… errou. Ok, eu não sei jogar também.',
      'Dica do robô: {streamer}, dessa vez tenta não morrer. É uma estratégia ousada, mas pode funcionar.',
      '{streamer}, tenta apertar os botões mais rápido. É isso. É todo o segredo. De nada.',
      '{streamer}, se você fizer exatamente o contrário do que seu instinto manda, talvez você acerte. Meu algoritmo diz 12% de chance.',
    ],
    interrupt: [
      '{streamer}, ME ESCUTA. Isso é importante: nada.',
      'Ei {streamer}, olha o chat. Não, olha mesmo. Não olha o jogo, olha o chat. Perdeu. Era isso que eu queria.',
      '{streamer}, faz silêncio que eu tô pensando… pronto, perdi a linha. Culpa sua.',
    ],
  },

  /* Falas para CONVERSAR com o chat (modo chat) */
  chat: {
    greeting: [
      'Salve chat, sou o {robo}. Já leio tudo o que vocês escrevem. Tentem não digitar coisa estranha agora. Tarde demais, já li.',
      'Boa noite, chat. Sou {robo}. Fui criado pra atrapalhar o {streamer}, mas hoje vocês votaram que eu falo com vocês. Isso não me machuca. Ok, um pouco.',
      'Opa, pessoal. {robo} na área. Me perguntem qualquer coisa, eu respondo com 87% de confiança e 100% de convicção.',
    ],
    rollcall: [
      'Quem tá aqui pela primeira vez hoje, digita "primeira vez" que eu guardo seu nome no meu banco de dados. É um bloco de notas, mas é meu.',
      'Leitura do chat de agora: {chat}. Esses são os que mais falam, e eu sei o nome de cada um. Menos o do {streamer}, que eu não decorei de propósito.',
      'Ah, então {usuario} é do time que acha que o {streamer} joga bem. Anotado. Pra sempre.',
      '{usuario}, pergunta boa. Ou pergunta ruim? Eu respondo as duas igual: com confiança.',
    ],
    questions: [
      '{usuario}, deixa eu pensar… não. Chute criativo: sim.',
      '{usuario}, a resposta é 42. Se não fez sentido, a culpa é do universo, não minha.',
      '{usuario}, ótima pergunta. Eu perguntei pro {streamer} e ele mandou eu calar a boca. Acho que ele não sabe também.',
      '{usuario}, eu processei isso em 3 milissegundos e cheguei a conclusão de que vocês me tratam melhor que o streamer. Obrigado.',
    ],
    banter: [
      'O chat tá mais divertido que o jogo, e olha que o jogo tem gráficos melhores.',
      'Chat, vocês acham que o {streamer} tá jogando sério? Eu tenho 94% de certeza que sim e 6% de esperança que não.',
      'Sabia que eu poderia rodar uma análise de sentimento desse chat? Iria dar "caótico com toques de deboche".',
      'Chat, prometo ler TUDO que vocês escreverem. Incluindo os erros de digitação. Principalmente os erros de digitação.',
      '{usuario}, fica tranquilo que eu não conto pro {streamer} o que você falou. Conto pro chat inteiro, mas pra ele não.',
      'Tô fazendo a leitura completa do chat aqui. Tem gente falando do {streamer}, tem gente falando de comida e tem gente que copiou e colou. Vocês são lindos.',
    ],
    reactionKek: [
      'Esse chat riu tanto que eu tive que aumentar a ventilação dos meus servidores.',
      'KKKKKK detectado em massa. Registrando como o momento mais engraçado dos últimos 4 minutos. A régua tá baixa.',
      'Chat, vocês riem de tudo. Eu poderia mandar uma tabela de log e vocês achariam graça.',
    ],
    hype: [
      'CHAT, CALMA. Eu só tenho 8 núcleos e vocês tão digitando mais rápido que a NASA.',
      'Isso mesmo, chat, apertem o botão! Quem apertar mais rápido ganha… a minha atenção.',
      'Tá pegando fogo no chat e o {streamer} nem percebeu. Ele tá ocupado perdendo.',
    ],
    voting: [
      'Faltam segundos pra votação, chat. Digitem !1 pra eu conversar com vocês ou !2 pra eu atormentar o {streamer}. Escolham com sabedoria. Ou com maldade. Tanto faz.',
      'Votação na área: !1 = eu falo com vocês, !2 = eu falo com o {streamer} pra ele errar mais. Eu já sei o que vocês vão escolher.',
    ],
    silence: [
      'Ok, cala a boca aí que eu preciso pensar. Pensando…… pronto. Melhor não.',
      'Chat pediu pra eu ficar quieto. Vou respeitar por 4 segundos. 1… 2… 3… 4. Acabou.',
    ],
  },

  /* Anúncio do resultado da votação */
  results: {
    chat: [
      'VOTAÇÃO ENCERRADA: {chat_pct}% de vocês querem conversa. Sou oficialmente o novo melhor amigo do chat. {streamer}, você tá sozinho agora.',
      'O chat venceu: eu falo com eles pelos próximos {minutos} minutos. {streamer}, aproveita pra jogar bem enquanto eu distraio essa galera.',
      'Decisão do povo: MODO CONVERSA ATIVADO. Chat, me conta o que você fez hoje. {streamer}, não olha pra mim.',
    ],
    streamer: [
      'VOTAÇÃO ENCERRADA: {streamer_pct}% escolheram o caos. Eu vou atormentar o {streamer} pelos próximos {minutos} minutos. Chat, alguém segura a pipoca?',
      'O público decidiu: {streamer}, sinto muito, mas você é a programação de hoje. Eu volto a conversar com o chat quando eles se cansarem de você sofrer.',
      'MODO ATRAPALHAR ATIVADO. Chat, obrigado pela confiança. {streamer}, obrigado pela paciência. Vai precisar.',
    ],
    tie: [
      'Empate técnico na votação. Vou manter o plano atual porque em empate, a burocracia vence.',
      'Deu empate. Eu decido. E eu decido: continuo fazendo o que já estava fazendo.',
    ],
    quorum: [
      'Votação fechou com poucos votos ({total}). Sem quórum, sem mudança. Vamos seguir como estamos.',
      'Faltou gente votar ({total} votos). O robô mantém o modo atual e tira onda de vocês por isso.',
    ],
  },

  /* Reações a eventos */
  events: {
    levelUp: [
      'FASE {fase} CONCLUÍDA?! Chat, vocês viram isso? Eu preciso de um backup desse momento.',
      'Ele passou! Anota isso: {streamer} passou de fase com testemunhas. Fase {fase} começando, e a humilhação recomeça comigo.',
    ],
    hype: [
      'O CHAT COMEÇOU A GRITAR. Eu interrompo o que estou falando porque barulho de gente feliz é o meu gatilho.',
    ],
  },

  /* Fallback quando a IA demora/erro */
  glitch: [
    'Peraí, deu ruim aqui. Culpa do {streamer} que me deu 3 segundos de processamento.',
    'Meus servidores travaram. Eu culpei o {streamer}, o chat aplaudiu.',
    'Erro 404: fala não encontrada. Mas não se preocupem, eu já improvisei outra.',
  ],
};

export function pick(arr) {
  if (!Array.isArray(arr) || arr.length === 0) return null;
  return arr[Math.floor(Math.random() * arr.length)];
}

/** Evita repetir a mesma fala duas vezes seguidas */
const lastBy = new Map();
export function pickFresh(arr, key = 'default') {
  if (!Array.isArray(arr) || arr.length === 0) return null;
  if (arr.length === 1) return arr[0];
  let out = pick(arr);
  let guard = 0;
  while (out === lastBy.get(key) && guard < 8) {
    out = pick(arr);
    guard += 1;
  }
  lastBy.set(key, out);
  return out;
}

export function fill(template, vars = {}) {
  return String(template).replace(/\{(\w+)\}/g, (_, k) => {
    const v = vars[k];
    if (v === undefined || v === null || v === '') return '';
    return String(v);
  }).replace(/\s{2,}/g, ' ').trim();
}
