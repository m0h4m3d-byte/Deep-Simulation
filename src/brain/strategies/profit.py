"""brain/strategies/profit.py — ماذا نزرع (what_if)."""

from src.brain.interface import BrainStrategy


class ProfitStrategy(BrainStrategy):
    @property
    def name(self) -> str:
        return "profit"

    def choose(self, obs: dict, sim) -> dict | None:
        # v1: محايد — يستدعي sim.what_if لكل بديل لاحقاً.
        return None
