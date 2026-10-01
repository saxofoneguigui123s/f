"""Mini-games dentro do troll - o chat escolhe qual troll aplicar."""

import random

MINI_GAMES = {
    "dica_falsa": {
        "name": "Dica Falsa",
        "desc": "A IA da uma dica errada de proposito",
        "lines": [
            "Dica de ouro: o botao X e o de pular! (mentira)",
            "Confia em mim, vai por ali que tem item secreto!",
            "Pra matar esse chefe e so apertar tudo ao mesmo tempo!",
        ],
    },
    "historia_drama": {
        "name": "Drama",
        "desc": "A IA conta uma historia dramatica pra distrair",
        "lines": [
            "Espera, deixa eu contar o que aconteceu comigo ontem...",
            "Voces viram o que aconteceu no ultimo ep? Que drama!",
            "Meu criador me abandonou... deixa eu desabafar aqui.",
        ],
    },
    "comando_falso": {
        "name": "Comando Falso",
        "desc": "A IA inventa um comando que nao funciona",
        "lines": [
            "Digite /fly no chat pra ganhar asas! (nao funciona)",
            "Aperte ALT+F4 pra abrir o menu secreto!",
            "Escreva !godmode pra ficar invencivel!",
        ],
    },
    "pergunta_sem_fim": {
        "name": "Pergunta Sem Fim",
        "desc": "A IA fica fazendo perguntas ate o streamer se perder",
        "lines": [
            "Mas espera, qual e a sua estrategia pra esse boss?",
            "E se voce tivesse escolhido outra classe?",
            "Qual foi o pior erro que voce ja cometeu nesse jogo?",
        ],
    },
    "confusao_total": {
        "name": "Confusao Total",
        "desc": "A IA fala varias coisas ao mesmo tempo",
        "lines": [
            "Entao, na verdade, o jogo e sobre... espera, nao, e sobre... hmm",
            "O segredo e usar o item... que item mesmo?",
            "Eu lembro que o tutorial dizia pra... o que dizia mesmo?",
        ],
    },
}

def get_random_mini_game():
    key = random.choice(list(MINI_GAMES.keys()))
    return MINI_GAMES[key]

def get_mini_game_by_name(name):
    return MINI_GAMES.get(name)

def list_mini_games():
    return {k: v["name"] for k, v in MINI_GAMES.items()}

def execute_mini_game(name=None):
    game = get_mini_game_by_name(name) if name else get_random_mini_game()
    return random.choice(game["lines"])


class MiniGames:
    """Classe usada pelo main.py (escolhe e executa um mini-game de troll)."""

    def list(self):
        return list_mini_games()

    def get(self, name):
        return get_mini_game_by_name(name)

    def execute(self, name=None):
        return execute_mini_game(name)

    def random_game(self):
        return get_random_mini_game()
