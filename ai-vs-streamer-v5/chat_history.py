"""Chat visual da IA - historico de conversas."""

import os, json, time

class ChatHistory:
    def __init__(self, folder="chat_history"):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self.file = f"{folder}/history.jsonl"
        self.entries = []

    def add(self, author, text, kind="message"):
        entry = {
            "time": time.time(),
            "author": author,
            "text": text,
            "kind": kind
        }
        self.entries.append(entry)
        with open(self.file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_all(self):
        return self.entries

    def get_recent(self, n=50):
        return self.entries[-n:]
