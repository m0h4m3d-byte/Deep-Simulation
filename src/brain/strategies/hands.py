"""brain/strategies/hands.py — كم يد نستأجر."""

from src.brain.interface import BrainStrategy


class HandsStrategy(BrainStrategy):
    @property
    def name(self) -> str:
        return "hands"

    def choose(self, obs: dict, sim) -> dict | None:
        return None
