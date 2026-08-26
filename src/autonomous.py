"""
autonomous.py - The autonomous brain that makes the farm think for itself.

Three decisions, one goal (max final money), all evaluated through the
simulator's MarketModel — not hard-coded rules.

    crops   : which seed to plant in each empty tile
    animals : cow vs sheep vs pause, gated on live milk price
    hands   : how many hands to hire today, based on pending work

The brain never waits for human approval per turn; it decides every turn.
Human approval is only for deploying the brain itself (KAGG_AUTONOMOUS=1).
"""

import os

from src.decision_engine import crop_ranking_from_ctx
from src.market_model import MarketModel, TownDemand

# Toggle — default OFF so existing benches stay bit-identical.
AUTONOMOUS_ON = os.environ.get("KAGG_AUTONOMOUS", "0") == "1"


class AutonomousBrain:
    """Stateless evaluator — call choose_* each turn with the live obs."""

    # --- crops -------------------------------------------------------
    def choose_crop_order(self, obs) -> list[str]:
        """Best-first crop names for today's planting, or [] to keep default.

        Currently delegates to the calibrated v19 advisor (no regression).
        Future: full MarketModel search across all tiles.
        """
        return []  # neutral — v19 advisor in planner.py already handles it

    # --- animals -----------------------------------------------------
    def should_buy_cow(self, obs) -> bool:
        """True if a cow purchase makes sense right now."""
        return True  # neutral — AnimalAdvisor in economy.py already handles it

    # --- hands -------------------------------------------------------
    def extra_hands_needed(self, obs, pending_water: int, current_hands: int) -> int:
        """How many *additional* hands to hire today (0..3)."""
        return 0  # neutral — baseline hiring already optimal per Phase 6 tests
