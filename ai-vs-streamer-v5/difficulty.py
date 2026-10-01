"""Dificuldade escalavel."""

class DifficultyManager:
    def __init__(self):
        self.level = 1
        self.progress = 0

    def get_level(self):
        return self.level

    def set_level(self, lvl):
        self.level = max(1, min(10, lvl))

    def increase_progress(self):
        self.progress += 1
        if self.progress >= 5:
            self.level += 1
            self.progress = 0

    def get_info(self):
        return f"Dificuldade do troll: nivel {self.level}"
