"""Logica do troll."""

class TrollLogic:
    def __init__(self, config):
        self.config = config
        self.active = False

    def activate(self):
        self.active = True
