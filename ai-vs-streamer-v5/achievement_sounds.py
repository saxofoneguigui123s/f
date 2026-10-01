"""Sons customizados por conquista - toca um som quando alguém ganha badge."""

import os, threading
try:
    import pygame
    pygame.mixer.init()
    HAS_PYGAME = True
except Exception:
    HAS_PYGAME = False

ACHIEVEMENT_SOUNDS = {
    "Troll Iniciante": "sounds/badge_bronze.wav",
    "Troll Profissional": "sounds/badge_silver.wav",
    "Troll Lendario": "sounds/badge_gold.wav",
    "Deus do Caos": "sounds/badge_epic.wav",
}

def play_achievement_sound(badge_name, enabled=True):
    if not enabled or not HAS_PYGAME:
        return
    sound_file = ACHIEVEMENT_SOUNDS.get(badge_name)
    if sound_file and os.path.exists(sound_file):
        def _play():
            try:
                s = pygame.mixer.Sound(sound_file)
                s.play()
            except Exception:
                pass
        threading.Thread(target=_play, daemon=True).start()
