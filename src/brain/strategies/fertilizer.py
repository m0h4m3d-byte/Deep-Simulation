"""brain/strategies/fertilizer.py — أين نضع السماد."""

from src.brain.interface import BrainStrategy


class FertilizerStrategy(BrainStrategy):
    @property
    def name(self) -> str:
        return "fertilizer"

    def choose(self, obs: dict, sim) -> dict | None:
        return None
