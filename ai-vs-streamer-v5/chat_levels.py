"""Sistema de nives pro chat - XP + level."""

import os, json

LEVELS_FILE = "ranking/levels.json"

def _load():
    if os.path.exists(LEVELS_FILE):
        with open(LEVELS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save(data):
    os.makedirs(os.path.dirname(LEVELS_FILE), exist_ok=True)
    with open(LEVELS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def add_xp(username, amount=10):
    data = _load()
    user = data.get(username, {"xp": 0, "level": 1})
    user["xp"] += amount
    new_level = 1 + (user["xp"] // 100)
    leveled_up = new_level > user["level"]
    user["level"] = new_level
    data[username] = user
    _save(data)
    return leveled_up, user

def get_level(username):
    data = _load()
    return data.get(username, {"xp": 0, "level": 1})["level"]

def get_xp(username):
    data = _load()
    return data.get(username, {"xp": 0, "level": 1})["xp"]

def get_rank():
    data = _load()
    return sorted(data.items(), key=lambda x: x[1]["level"], reverse=True)


class ChatLevels:
    """Classe usada pelo main.py (XP e nivel do chat)."""

    def add_xp(self, username, amount=10):
        return add_xp(username, amount)

    def get_level(self, username):
        return get_level(username)

    def get_xp(self, username):
        return get_xp(username)

    def get_rank(self):
        return get_rank()
