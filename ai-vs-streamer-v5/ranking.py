"""Ranking de trolls."""

import os, json

class RankingSystem:
    FILE = "ranking/trolls.json"
    def __init__(self):
        os.makedirs("ranking", exist_ok=True)

    def _load(self):
        if os.path.exists(self.FILE):
            with open(self.FILE, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save(self, data):
        with open(self.FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def add_troll_point(self, voters):
        data = self._load()
        for v in voters:
            data[v] = data.get(v, 0) + 1
        self._save(data)

    def get_top(self, n=5):
        data = self._load()
        top = sorted(data.items(), key=lambda x: x[1], reverse=True)[:n]
        return "Ranking trolls: " + ", ".join(f"{u}({p})" for u, p in top) if top else "Ninguem trollou ainda."
