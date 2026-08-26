"""
strategy.py - Day-phase gates for the Kaggriculture agent.

Every gate is ported VERBATIM from src/main.py (production baseline) - the numbers
below are the monolith's inline day thresholds. tests/test_strategy_parity.py
asserts each gate against the monolith's values across all 30 days, so any
drift fails loudly.

Source lines in main.py:
    seed windows / melon cap : _market_orders (156-166)
    land due                : _market_orders (141-145)
    hire target             : _market_orders (124-127)
    animal buy window       : _market_orders (168)
    melon/strawberry sell   : _sell (202, 206)
    full liquidation        : _sell (218)
    crop seasons / plant    : _collect_jobs (281, 284)
"""

from src.economy import HIRE_TARGET, HIRE_RAMP, PLAN, LAND_DAYS

# ============================================================
# Day gates (ported from main.py)
# ============================================================
WHEAT_LAST_DAY = 28          # main.py:156 seed_plan last_day
MELON_LAST_DAY = 13          # main.py:156/281
STRAWBERRY_START_DAY = 8     # P8 FIX: delay strawberry so wheat fills field first
STRAWBERRY_LAST_DAY = 22     # main.py:156/281
MELON_DAY0_CAP = 12          # main.py:156 12 if day == 0 else 6
MELON_REGULAR_CAP = 6        # main.py:156
ANIMAL_LAST_BUY_DAY = 24     # main.py:168
MELON_SELL_DAY = 12          # main.py:202
STRAWBERRY_SELL_DAY = 20     # main.py:206 was 14; Phase 3: hold for rising prices
MILK_SELL_DAY = 8            # Phase 7 (ladder #1 replay): milk gluts after ~d15
WOOL_SELL_DAY = 6            # and crashes 199->1 / 217->1; the winner sells
EGG_SELL_DAY = 16            # from d8/d6 at the peak. Egg rises (50->59): stays.
LIQUIDATE_DAY = 27           # main.py:218
PLANT_TARGET_FULL = 55       # Phase 19 (60-seed: $94.7k vs $93.3k at 75). The
                             # field always runs at watering-capacity edge
                             # (0 thirst deaths, but ~500 weed tile-days in
                             # days 10-29); a smaller fully-tended field
                             # out-yields a larger straggling one. MEDIUM
                             # confidence - within noise on 30 seeds, held up
                             # on 60. PLANT_TARGET_LATE stays baseline.
PLANT_TARGET_LATE = 30       # baseline optimal


class Strategy:
    """
    Day-phase strategy. Tracks the current day/hour/money and exposes the
    monolith's day gates. All gates take an optional explicit day so they
    stay pure and testable; the default uses the last tracked state.
    """

    PHASE_EARLY = "EARLY"
    PHASE_MID = "MID"
    PHASE_LATE = "LATE"
    PHASE_LIQUIDATE = "LIQUIDATE"

    def __init__(self):
        self.day = 0
        self.hour = 0
        self.money = 3000
        self.phase = self.PHASE_EARLY

    def update(self, state):
        """Track day/hour/money from a GameState (or any object exposing them)."""
        self.day = state.day
        self.hour = state.hour
        self.money = state.money
        self.phase = self._phase_for(self.day)

    # ---------------- gates (monolith parity) ----------------

    def _d(self, day):
        return self.day if day is None else day

    def is_melon_season(self, day=None) -> bool:
        """main.py:281 active MELON = day <= 13."""
        return self._d(day) <= MELON_LAST_DAY

    def is_strawberry_season(self, day=None) -> bool:
        """main.py:281 active STRAWBERRY = day <= 22."""
        return self._d(day) <= STRAWBERRY_LAST_DAY

    def seed_buy_open(self, crop: str, day=None) -> bool:
        """main.py:156-159 seed_plan window (start_day <= day <= last_day)."""
        d = self._d(day)
        if crop == "WHEAT":
            return d <= WHEAT_LAST_DAY
        if crop == "MELON":
            return d <= MELON_LAST_DAY
        if crop == "STRAWBERRY":
            return STRAWBERRY_START_DAY <= d <= STRAWBERRY_LAST_DAY
        return False  # CARROT (Phase 6.2) reverted: seed-rebuy flood crashed

    def melon_buy_cap(self, day=None) -> int:
        """main.py:156 12 if day == 0 else 6."""
        return MELON_DAY0_CAP if self._d(day) == 0 else MELON_REGULAR_CAP

    def buy_animals_open(self, day=None) -> bool:
        """main.py:168 animal buying only on day <= 24."""
        return self._d(day) <= ANIMAL_LAST_BUY_DAY

    def plant_target(self, day=None) -> int:
        """main.py:284 75 if day <= 22 else 30."""
        return PLANT_TARGET_FULL if self._d(day) <= STRAWBERRY_LAST_DAY else PLANT_TARGET_LATE

    def is_liquidating(self, day=None) -> bool:
        """main.py:218 full liquidation starts day >= 27."""
        return self._d(day) >= LIQUIDATE_DAY

    def sell_melon_open(self, day=None) -> bool:
        """main.py:202 melon sells unconditionally from day >= 12 (melon
        prices FALL after mid-season - sell early)."""
        return self._d(day) >= MELON_SELL_DAY

    def sell_strawberry_open(self, day=None) -> bool:
        """Phase 3: strawberry sells from day >= 20 (was 14) - prices rise
        as the season drains, so holding captures +30-40%. (Phase 6.5 tried
        22 and the whole sell-timing bundle was reverted - see economy.py.)"""
        return self._d(day) >= STRAWBERRY_SELL_DAY

    def sell_milk_open(self, day=None) -> bool:
        """Phase 7: milk sells from day 8 (was 16) - the ladder #1 replay
        shows milk glut-crash 199->1 after ~d15; the winner sells d8-14 at
        $158-199. Wool 6, egg stays 16 (egg rises 50->59)."""
        return self._d(day) >= MILK_SELL_DAY

    def hire_target(self, day=None) -> int:
        """main.py:126 min(HIRE_TARGET, HIRE_RAMP + day). baseline kept: the game
        resets hired hands to zero every day, so the daily ramp is required.
        (Phases 6/6.1/6.3 hire variants all benchmarked and reverted - the
        hire lever is closed until a non-labor bottleneck is addressed.)"""
        return min(HIRE_TARGET, HIRE_RAMP + self._d(day))

    def land_due(self, unlocked: int, day=None) -> bool:
        """main.py:144 0 < unlocked < 4 and day >= land_days[unlocked-1]."""
        d = self._d(day)
        return 0 < unlocked < len(LAND_DAYS) + 1 and d >= LAND_DAYS[unlocked - 1]

    def seed_target(self, crop: str) -> int:
        """main.py:32 PLAN seed target per crop."""
        return PLAN.get(crop, 0)

    # ---------------- legacy API (WIP planner compatibility) ----------------
    # Aligned to the monolith gates above; replaced once the planner is ported.

    def _phase_for(self, day: int) -> str:
        if day >= LIQUIDATE_DAY:
            return self.PHASE_LIQUIDATE
        if day >= STRAWBERRY_LAST_DAY:
            return self.PHASE_LATE
        if day >= 10:
            return self.PHASE_MID
        return self.PHASE_EARLY

    def is_late(self, day=None) -> bool:
        return self._d(day) >= STRAWBERRY_LAST_DAY

    def is_early(self, day=None) -> bool:
        return self._d(day) < 10

    def should_use_fertilizer(self, state) -> bool:
        """Legacy heuristic from the WIP planner; monolith fertilizer logic
        (ongoing crops only, _collect_jobs 251-253) lands with the planner."""
        if state.shed.get("FERTILIZER", 0) <= 0:
            return False
        if self.phase == self.PHASE_LIQUIDATE:
            return False
        if self.phase == self.PHASE_EARLY:
            return True
        if self.phase == self.PHASE_MID and self.money > 500:
            return True
        return False


# Global instance
strategy = Strategy()