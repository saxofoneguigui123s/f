"""TTS - voz do robo (gTTS, Windows SAPI ou nenhum).

O motor de IA chama `speak(texto)`; o audio toca em uma thread para nao
travar o loop do robo. Se nao der para tocar, o texto continua no console.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading


class TTSEngine:
    def __init__(self, config=None):
        config = config or {}
        tts = config.get("tts") or {}
        self.enabled = bool(tts.get("enabled", True))
        self.engine = str(tts.get("engine", "gtts")).lower()
        self.language = tts.get("language", "pt")
        self.speed = float(tts.get("speed", 1.0) or 1.0)
        self.keep_files = bool(tts.get("keep_files", False))
        self.max_chars = int(tts.get("max_chars", 300))
        self._lock = threading.Lock()
        self._busy = False
        self.last_file = None
        self.last_error = None

    # ------------------------------------------------------------------
    def speak(self, text):
        """Fala o texto (em background). Devolve False se o TTS esta desligado."""
        text = " ".join(str(text or "").split())
        if not self.enabled or not text:
            return False
        if len(text) > self.max_chars:
            text = text[: self.max_chars].rsplit(" ", 1)[0]

        with self._lock:
            if self._busy:
                return False  # nao enfileira falas: evita atraso no stream
            self._busy = True
        threading.Thread(target=self._speak_worker, args=(text,), daemon=True).start()
        return True

    def _speak_worker(self, text):
        try:
            if self.engine in ("windows", "sapi", "pyttsx3"):
                self._speak_windows(text)
            else:
                self._speak_gtts(text)
        except Exception as error:
            self.last_error = error
            print(f"[TTS erro] {error}")
        finally:
            with self._lock:
                self._busy = False

    # ------------------------------------------------------------------
    def _speak_gtts(self, text):
        from gtts import gTTS

        tts = gTTS(text=text, lang=self.language)
        path = self.last_file if self.keep_files and self.last_file else os.path.join(
            tempfile.gettempdir(), "ai_vs_streamer_tts.mp3"
        )
        tts.save(path)
        self.last_file = path
        self.play_file(path)

    def _speak_windows(self, text):
        try:
            import win32com.client  # type: ignore

            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Speak(text)
            return
        except Exception:
            pass
        print(f"[TTS] (sem voz disponivel nesta maquina): {text}")

    # ------------------------------------------------------------------
    def play_file(self, path):
        """Toca um arquivo de audio com pygame ou com um player do sistema."""
        if not os.path.exists(path):
            print(f"[TTS] arquivo nao encontrado: {path}")
            return False
        try:
            import pygame

            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(120)
            return True
        except Exception:
            pass

        for player, args in (
            ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
            ("mpg123", ["-q"]),
            ("aplay", ["-q"]),
            ("afplay", []),
        ):
            binary = shutil.which(player)
            if binary:
                try:
                    subprocess.run([binary] + args + [path], check=False)
                    return True
                except Exception:
                    continue
        print(f"[TTS] (som nao reproduzido): {path}")
        return False

    def status(self):
        return {
            "enabled": self.enabled,
            "engine": self.engine,
            "language": self.language,
            "busy": self._busy,
            "last_error": str(self.last_error) if self.last_error else None,
        }
