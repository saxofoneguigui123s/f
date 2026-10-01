"""Comandos de voz do streamer."""

import threading

class VoiceCommands:
    def __init__(self, config, ai_engine, troll_logic):
        self.enabled = config.get("voice", {}).get("enabled", True)
        self.trigger = config.get("voice", {}).get("trigger", "ei robo")
        self.language = config.get("voice", {}).get("language", "pt-BR")
        self.ai = ai_engine
        self.troll = troll_logic
        self.listening = False
        self.running = False

    def start(self):
        if not self.enabled:
            return
        self.running = True
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def _listen_loop(self):
        try:
            import speech_recognition as sr
        except Exception as error:
            print(f"[VOZ] desligada: instale SpeechRecognition + pyaudio ({error})")
            self.running = False
            return
        try:
            r = sr.Recognizer()
            mic = sr.Microphone()
        except Exception as error:
            print(f"[VOZ] microfone indisponivel: {error}")
            self.running = False
            return
        with mic as source:
            r.adjust_for_ambient_noise(source)
        while self.running:
            try:
                with mic as source:
                    audio = r.listen(source, timeout=1, phrase_time_limit=5)
                text = r.recognize_google(audio, language=self.language).lower()
                if self.trigger in text:
                    command = text.replace(self.trigger, "").strip()
                    self._handle(command)
            except sr.WaitTimeoutError:
                pass
            except Exception:
                pass

    def _handle(self, command):
        if "para" in command:
            self.listening = False
            self.ai.speak("Ok, parei de ouvir.")
        elif "atrapalha" in command or "troll" in command:
            self.listening = True
            self.troll.activate()
            self.ai.speak("Modo troll ativado! Vamos atrapalhar!")
        elif "dica" in command:
            self.ai.speak("Dica? Eu nao dou dica. Eu atrapalho!")
        elif "joguei bem" in command or "gg" in command:
            self.ai.speak("Muito bem! Voce jogou incrivel! Recompensa pro chat!")
        else:
            self.ai.speak(f"Voce disse: {command}")
