"""brain/allocator.py — Unified resource allocator.

Every investment competes for the SAME budget: money + tiles + hands×days.
The allocator scores each candidate by (expected final money) / (resource cost)
and picks the portfolio that maximizes final money — no task starves another
unless it is genuinely less profitable.

Candidates:
  cow, sheep, wheat×10, strawberry×10, melon×10, hire×1
"""

from src.market_model import MarketModel, TownDemand


# Resource costs (tunable via config/brain.yaml later)
HAND_DAYS_PER_COW = 1.0      # feed+care+collect+harvest per day
HAND_DAYS_PER_SHEEP = 0.7
HAND_DAYS_PER_WHEAT10 = 0.4  # planting + watering 10 tiles
HAND_DAYS_PER_STRAW10 = 1.2  # ongoing: many waters/harvests


class UnifiedAllocator:
    def score(self, obs, sim=None) -> dict[str, float]:
        """Return {candidate: score} — higher is better. Negative = don't do it."""
        day = obs["day"]
        money = obs["farms"][obs["player"]]["money"]
        prices = obs["market"]["prices"]
        inv = obs["market"]["inventory"]
        shops = list((obs.get("town") or {}).get("unlocked_shops") or [])
        hands = len(obs["farms"][obs["player"]].get("hands", [])) + 1

        mm = MarketModel(inv, TownDemand(shops, day))
        scores: dict[str, float] = {}

        # --- animals: ROI per hand-day ---
        # Cow: milk every 2 days @ projected price, needs daily feed
        milk_p = mm.projected_price("MILK", 6)
        wool_p = mm.projected_price("WOOL", 6)
        # Expected milk in remaining season if we buy a cow today
        days_left = 30 - day
        if days_left >= 8:
            cow_milk_units = max(0, (days_left - 8) // 2 + 1)
            cow_rev = cow_milk_units * milk_p
            cow_cost = 400 + cow_milk_units * 25  # feed wheat @ ~$25
            cow_hands = cow_milk_units * HAND_DAYS_PER_COW
            scores["cow"] = (cow_rev - cow_cost) / max(1, cow_hands) if money >= 400 else -1e9
        else:
            scores["cow"] = -1e9

        if days_left >= 6:
            sheep_wool_units = max(0, (days_left - 6) // 3 + 1)
            sheep_rev = sheep_wool_units * wool_p
            sheep_cost = 500 + sheep_wool_units * 25
            sheep_hands = sheep_wool_units * HAND_DAYS_PER_SHEEP
            scores["sheep"] = (sheep_rev - sheep_cost) / max(1, sheep_hands) if money >= 500 else -1e9
        else:
            scores["sheep"] = -1e9

        # --- crops: ROI per tile per hand-day ---
        for crop, hand_cost, n_tiles in [
            ("WHEAT", HAND_DAYS_PER_WHEAT10, 10),
            ("STRAWBERRY", HAND_DAYS_PER_STRAW10, 10),
            ("MELON", 0.8, 10),
        ]:
            try:
                roi, _ = mm.crop_roi(crop, day)
                if roi is None or roi < 0:
                    scores[crop.lower()] = -1e9
                else:
                    # ROI is per tile; scale to n_tiles then per hand-day
                    total_roi = roi * n_tiles
                    scores[crop.lower()] = total_roi / max(1, hand_cost * n_tiles)
            except Exception:
                scores[crop.lower()] = -1e9

        # --- hands: marginal value of one more hand ---
        # A hand lets us water ~12 more tiles/day. Value = extra harvests enabled.
        # Rough: if we have >40 plants and hands < 8, an extra hand is worth ~$800/season
        plants = sum(1 for row in obs["farms"][obs["player"]]["tiles"]
                     for t in row if isinstance(t, dict) and t.get("kind") == "PLANT")
        if plants > 30 and hands < 10 and money > 800:
            scores["hire"] = 50  # positive but low priority vs direct investments
        else:
            scores["hire"] = -1e9

        return scores

    def choose(self, obs, sim=None) -> str | None:
        """Best candidate name or None if nothing is profitable."""
        scores = self.score(obs, sim)
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else None
