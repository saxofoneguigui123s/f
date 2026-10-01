"""Votacao com emojis."""

class EmojiVoting:
    def __init__(self, config):
        self.config = config

    def process(self, user, message):
        msg = message.lower()
        if msg in ["👍", "+1", "!chat"]:
            return "chat"
        if msg in ["👎", "-1", "!troll"]:
            return "troll"
        return None
