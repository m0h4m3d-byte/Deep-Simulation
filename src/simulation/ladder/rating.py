"""ladder/rating.py — Elo rating that mirrors Kaggle's ladder."""

import math


class EloRating:
    """Minimal Elo tracker. Each submission starts at 600 (Kaggle default)."""

    def __init__(self, initial: float = 600.0, k: float = 32.0):
        self.ratings: dict[str, float] = {}
        self.initial = initial
        self.k = k

    def get(self, name: str) -> float:
        return self.ratings.get(name, self.initial)

    def expected(self, a: str, b: str) -> float:
        ra, rb = self.get(a), self.get(b)
        return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))

    def update(self, winner: str, loser: str) -> None:
        ea = self.expected(winner, loser)
        eb = 1.0 - ea
        self.ratings[winner] = self.get(winner) + self.k * (1 - ea)
        self.ratings[loser] = self.get(loser) + self.k * (0 - eb)

    def update_tie(self, a: str, b: str) -> None:
        ea = self.expected(a, b)
        self.ratings[a] = self.get(a) + self.k * (0.5 - ea)
        self.ratings[b] = self.get(b) + self.k * (0.5 - (1 - ea))
