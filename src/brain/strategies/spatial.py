"""brain/strategies/spatial.py — أين نزرع (تكلفة الحركة)."""

from src.brain.interface import BrainStrategy


def tile_score(crop: str, distance: int, roi: float) -> float:
    """Profit per movement: ongoing crops need many trips → penalize distance more."""
    trips = {"WHEAT": 6, "MELON": 8, "STRAWBERRY": 22, "CARROT": 5, "TOMATO": 18}.get(crop, 6)
    return roi - distance * trips * 1.2  # 1.2 coins per tile per trip (tunable)


class SpatialStrategy(BrainStrategy):
    @property
    def name(self) -> str:
        return "spatial"

    def choose(self, obs: dict, sim) -> dict | None:
        # Called per tile from planner — returns {tile: crop} mapping.
        # Actual per-tile logic lives in planner's loop which calls tile_score().
        return None
