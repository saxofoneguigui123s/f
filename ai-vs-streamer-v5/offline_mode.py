"""Modo streamer offline - a IA roda sozinha com o chat."""

import random, time

OFFLINE_LINES = [
    "O streamer saiu pra pegar uma agua... ou fugiu de voces?",
    "Enquanto ele nao volta, quem quer historia?",
    "O chefe ta esperando, mas o streamer nao ta...",
    "Chat, voces tao me pagando pra trollar?",
    "Ele disse 'volto ja'. Ja faz 20 minutos. #mentira",
]

class OfflineMode:
    def __init__(self, ai_engine, chat_reader):
        self.ai_engine = ai_engine
        self.chat_reader = chat_reader
        self.running = False
        self.last_line_time = 0

    def start(self):
        self.running = True
        self.last_line_time = time.time()

    def stop(self):
        self.running = False

    def tick(self):
        if not self.running:
            return
        now = time.time()
        if now - self.last_line_time > 60:
            self.last_line_time = now
            line = random.choice(OFFLINE_LINES)
            self.ai_engine.speak(line)
            self.chat_reader.send_message(line)
