"""Sons/efeitos quando o modo muda."""

import os, threading

class SoundEffects:
    def __init__(self, config):
        self.enabled = config.get("sound", {}).get("enabled", True)
        self.chat_sound = config.get("sound", {}).get("chat", "sounds/ding.wav")
        self.troll_sound = config.get("sound", {}).get("troll", "sounds/sinister.wav")

    def play(self, kind):
        if not self.enabled:
            return
        sound = self.chat_sound if kind == "chat" else self.troll_sound
        if kind == "chaos":
            sound = "sounds/chaos.wav"
        if kind == "reward":
            sound = "sounds/reward.wav"
        if not os.path.exists(sound):
            return
        def _play():
            try:
                import pygame
                pygame.mixer.init()
                s = pygame.mixer.Sound(sound)
                s.play()
            except Exception:
                pass
        threading.Thread(target=_play, daemon=True).start()
