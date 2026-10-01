"""Sistema de votacao."""

import time

class VotingSystem:
    def __init__(self, config):
        self.interval = config.get("voting_interval", 600)
        self.mode = "chat"
        self.votes = {"chat": 0, "troll": 0}
        self.start_time = time.time()
        self.last_troll_voters = []

    def add_vote(self, user, vote):
        if vote in self.votes:
            self.votes[vote] += 1
            if vote == "troll":
                self.last_troll_voters.append(user)

    def check_finished(self):
        if time.time() - self.start_time >= self.interval:
            self.mode = "troll" if self.votes["troll"] > self.votes["chat"] else "chat"
            self.votes = {"chat": 0, "troll": 0}
            self.start_time = time.time()
            return True
        return False

    def get_mode(self):
        return self.mode

    def time_left(self):
        return int(self.interval - (time.time() - self.start_time))

    def set_interval(self, seconds):
        self.interval = seconds

    def force_mode(self, mode):
        self.mode = mode

    def get_last_troll_voters(self):
        return self.last_troll_voters
