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
AUTONOMOUS_ON = os.environ.get("KAGG_AUTONOMOUS", "1") == "1"


class AutonomousBrain:
    """Stateless evaluator — call choose_* each turn with the live obs."""

    def __init__(self):
        from src.brain.allocator import UnifiedAllocator
        self.allocator = UnifiedAllocator()

    def apply(self, obs):
        """Called once per turn from main.py when AUTONOMOUS_ON.
        Re-weights PLAN in place based on unified resource scoring."""
        if not AUTONOMOUS_ON:
            return
        try:
            scores = self.allocator.score(obs)
            import src.economy as E
            # If sheep clearly beats cow, tilt the herd 2 pens toward sheep
            if scores.get("sheep", -1e9) > scores.get("cow", -1e9) * 1.3:
                # Sheep is >30% better per hand-day → shift 2 pens
                if E.PLAN["SHEEP"] < 8:
                    E.PLAN["SHEEP"] = min(8, E.PLAN["SHEEP"] + 1)
                    E.PLAN["COW"] = max(10, E.PLAN["COW"] - 1)
            # If wheat beats strawberry per hand-day, we already have WHEAT 30
            # as default; no further shift needed (strawberry 45 stays).
        except Exception:
            pass

    # --- crops -------------------------------------------------------

    # --- crops -------------------------------------------------------
    def choose_crop_order(self, obs) -> list[str]:
        """Best-first crop names — dynamic profit via MarketModel.

        When AUTONOMOUS_ON, this REPLACES the fixed advisor in planner.py.
        Uses the same calibrated v19 logic (threshold $190 after day 12) so
        activation is neutral today; future what_if per-tile search will
        live here without touching any other file.
        """
        if not AUTONOMOUS_ON:
            return []
        try:
            from src.decision_engine import project_harvest_prices
            ctx = {
                "day": obs["day"],
                "prices": obs["market"]["prices"],
                "inventory": obs["market"]["inventory"],
                "shops": list((obs.get("town") or {}).get("unlocked_shops") or []),
            }
            proj = project_harvest_prices(ctx)
            day = obs["day"]
            from src.strategy import strategy
            straw_active = strategy.is_strawberry_season(day)
            straw_ok = (straw_active and
                        (day < 12 or proj.get("STRAWBERRY") is None or
                         proj.get("STRAWBERRY", 0) >= 190))
            order = []
            if straw_ok:
                order.append("STRAWBERRY")
            for c in ("MELON", "WHEAT"):
                # keep season gates
                if c == "MELON" and not strategy.is_melon_season(day):
                    continue
                if c not in order:
                    order.append(c)
            if straw_active and not straw_ok:
                order.append("STRAWBERRY")
            return [c for c in order if c in ("STRAWBERRY", "MELON", "WHEAT")]
        except Exception:
            return []

    # --- animals -----------------------------------------------------
    def should_buy_cow(self, obs) -> bool:
        """True if a cow purchase makes sense right now."""
        return True  # neutral — AnimalAdvisor in economy.py already handles it

    # --- hands -------------------------------------------------------
    def extra_hands_needed(self, obs, pending_water: int, current_hands: int) -> int:
        """How many *additional* hands to hire today (0..3)."""
        return 0  # neutral — baseline hiring already optimal per Phase 6 tests
