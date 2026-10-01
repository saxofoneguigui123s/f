"""Sistema de conquistas - badges."""

import os, json

BADGES = {
    "Troll Iniciante": {"trolls": 5, "icon": "bronze"},
    "Troll Profissional": {"trolls": 15, "icon": "silver"},
    "Troll Lendario": {"trolls": 30, "icon": "gold"},
    "Deus do Caos": {"trolls": 50, "icon": "epic"},
}
FILE = "achievements/badges.json"

def _load():
    if os.path.exists(FILE):
        with open(FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save(data):
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def check_badges(username, troll_count):
    data = _load()
    user = data.get(username, {"badges": []})
    new_badges = []
    for name, req in BADGES.items():
        if troll_count >= req["trolls"] and name not in user["badges"]:
            user["badges"].append(name)
            new_badges.append(name)
    if new_badges:
        data[username] = user
        _save(data)
    return new_badges

def get_user_badges(username):
    data = _load()
    badges = data.get(username, {"badges": []})["badges"]
    return f"@{username} Badges: {', '.join(badges) if badges else 'nenhuma ainda'}"


class AchievementSystem:
    """Classe usada pelo main.py (envolve as funcoes de badges)."""

    BADGES = BADGES

    def check_badges(self, username, troll_count):
        return check_badges(username, troll_count)

    def get_user_badges(self, username):
        return get_user_badges(username)

    def list_badges(self):
        return {name: data["trolls"] for name, data in BADGES.items()}
