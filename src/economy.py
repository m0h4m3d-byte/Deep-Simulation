"""
economy.py - Economic engine for the Kaggriculture agent.
Contains the market order logic V15_FIXED production agent.

Parity guarantee: tests/test_market_parity.py replays the monolith agent and
asserts this engine produces IDENTICAL market orders at every step. Any
change to the numbers below must be reflected there or the test fails.
"""

from typing import Dict, List

# All tunables imported from single source of truth — src/config.py is the ONLY
# place that holds numbers. No os.environ / KAGG_* reads exist anywhere.
from src.config import (
    PLAN, FEED_RESERVE, FERT_RESERVE,
    ANIMAL_ADVISOR_ON, MILK_CRASH_PRICE, ANIMAL_ADVISOR_MIN_DAY, MILK_TREND_DROP,
    PASTURE_BUFFER, HIRE_TARGET, HIRE_RAMP,
)

RESERVE = 15
from src.config import (
    SHED_CAPACITY, SHED_DUMP_AT, SELL_HOLD_DAY,
    MILK_BULL_D12, MILK_BULL_HOLD_DAY, MILK_BAIL_FROM_DAY, MILK_BAIL_FACTOR,
    ANIMALS, SEED_COST, BASE,
    MARKET_AWARE_ON, MARKET_AWARE_CAPS,
)

from src.config import (
    FERT_BUY_ENGINE_V1, FERT_STOCK_TARGET, FERT_BUY_CAP_PER_DAY,
    FERT_BUY_LAST_DAY, FERT_BUY_MIN_MONEY, FERT_BUY_MAX_PRICE,
    P5_RELEASE_V1, P5_WOOL_KEPT_UNITS, P5_WOOL_BAIL_FROM_DAY, P5_WOOL_BAIL_FACTOR,
    P4_SHEEP_CAP_V1, P4_NO_YARN_SHEEP_TARGET,
    P4_SHEEP_CAP_V2, P4_SHEEP_CAP_V2B, P4_SHEEP_CAP_V2A, P4V2_FLOOR, P4V2_RESUME_DAY,
    P4_V3_ADAPTIVE, P4V3_QUIET_WINDOW0, P4V3_QUIET_WINDOW1, P4V3_WOOL_THRESHOLD,
    P7_RELEASE_V1, P7_WOOL_HOLD_DAY, P7_WOOL_EARLY_DAY, P7_WOOL_SELL_CAP,
    LAND_COSTS, LAND_DAYS,
)


def _fib(n: int) -> int:
    """Fibonacci with _fib(0)=1, _fib(1)=1, _fib(2)=2..."""
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


class MarketEngine:
    """
    Builds the market orders (sell / hire / land / feed / seeds / animals).

    Ported verbatim from Agent._market_orders + Agent._sell in src/main.py (baseline).
    Accepts the same raw observation slices the monolith passes around,
    so the port is a line-for-line move with no number changes.

    State kept here mirrors the monolith's Agent attributes:
        ordered_today: per-day BUY dedupe (reset on day change / new game)
        sold_today:    per-day SELL dedupe (reset on day change / new game)
        animals_ordered: cumulative animal purchases (reset only per game)
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.day = -1
        self.ordered_today = {}
        self.sold_today = {}
        self.animals_ordered = {"COW": 0, "SHEEP": 0, "GOOSE": 0}
        self.milk_bull = None
        self.milk_d12_price = None
        self.bail_fires = 0
        self.wool_season_max = None
        self.milk_peak = 0.0
        self.milk_crash_active = False
        self.milk_history: list[float] = []

    def _on_day(self, day: int):
        """Roll over day-trackers; a fresh game looks like a day reset."""
        if day == self.day:
            return
        if day == 0 or day < self.day:
            self.reset()
            self.day = 0
        else:
            self.day = day
            self.ordered_today = {}
            self.sold_today = {}

    @staticmethod
    def _animal_counts(me):
        animal_tiles = []
        for row in me["tiles"]:
            for t in row:
                if isinstance(t, dict) and "animal" in t:
                    animal_tiles.append(t)
        cows = sum(1 for t in animal_tiles if t["animal"] == "COW")
        sheep = sum(1 for t in animal_tiles if t["animal"] == "SHEEP")
        geese = sum(1 for t in animal_tiles if t["animal"] == "GOOSE")
        return len(animal_tiles), cows, sheep, geese

    @staticmethod
    def _unplaced_animal(invs, shed, animal):
        total = shed.get(animal, 0)
        for inv in invs:
            total += inv.get(animal, 0)
        return total

    def build_orders(self, day: int, hour: int, me, shed, seeds, prices, money, invs,
                     unlocked_shops=None) -> List[list]:
        """Return the market orders list. Mirrors Agent._market_orders exactly.

        unlocked_shops: obs.town.unlocked_shops (P5 signal); None/absent on
        the OFF path so behaviour stays bit-identical to GOLDEN_BASELINE.
        """
        self._on_day(day)
        orders = []
        pending = 0
        animals_now, cows, sheep, geese = self._animal_counts(me)

        def can(cost):
            return money - pending - cost >= RESERVE

        def buy(key, cap, cost, order, floor=RESERVE, units=1):
            nonlocal pending
            if self.ordered_today.get(key, 0) + units > cap:
                return False
            if money - pending - cost < floor:
                return False
            if len(orders) >= 10:
                return False
            self.ordered_today[key] = self.ordered_today.get(key, 0) + units
            orders.append(order)
            pending += cost
            return True

        self._sell(orders, shed, prices, day, animals_now,
                   unlocked_shops=unlocked_shops)

        if day < 30:
            hired = me.get("hires_today", 0)
            target = min(HIRE_TARGET, HIRE_RAMP + day)  # baseline: hands reset daily
            if hired < target:
                # Pace hiring across the day (a few per turn) so the 10-order
                # market cap is not exhausted on the first hour.
                step = min(2, 10 - len(orders), 24 - hour)
                planned = 0
                while hired + planned < target and planned < step:
                    cost = _fib(hired + planned)
                    if money - pending - cost < 5:
                        break
                    orders.append(["HIRE"])
                    pending += cost
                    planned += 1

        # no-4th-land experiment: stop at 3 quarters (75 tiles) like leaders — 4th land $4k is fixed rule with ~75% usage, ROI negative late
        unlocked = len(me.get("unlocked_quadrants", []))
        # was: 0 < unlocked < len(LAND_COSTS)+1 (allows 4th at day12); now cap at 3 quadrants
        if 0 < unlocked < len(LAND_COSTS) and day >= LAND_DAYS[unlocked - 1]:
            buy("land", 1, LAND_COSTS[unlocked - 1], ["BUY_LAND"])

        wheat_price = prices.get("WHEAT", 25)
        need_reserve = 4 if wheat_price <= 35 else 0
        feed_need = animals_now + need_reserve
        if shed.get("WHEAT", 0) < feed_need and wheat_price <= 70:
            q = min(feed_need - shed.get("WHEAT", 0), 6)
            if q > 0 and q * wheat_price <= money - pending:
                feed_cap = 4 if animals_now <= 2 else 2 if animals_now < 8 else 3
                buy("feed", feed_cap, q * wheat_price, ["BUY_PRODUCT", "WHEAT", q], floor=0)

        # Crop Dusta: WHEAT 24 MELON 10 STRAW 14 as base
        seed_plan = {"WHEAT": (PLAN["WHEAT"], 24, 8, 0), "MELON": (PLAN["MELON"], 10, 12 if day == 0 else 6, 0),
                     "STRAWBERRY": (PLAN["STRAWBERRY"], 14, 10, 3)}
        for crop, (target, last_day, cap, start_day) in seed_plan.items():
            if day > last_day or day < start_day:
                continue
            have = seeds.get(crop, 0)
            if have < target:
                q = min(target - have, cap)
                if q > 0:
                    buy("seed_" + crop, cap, q * SEED_COST[crop], ["BUY_SEED", crop, q], units=q, floor=0)

        # no-waste-buying: per-animal last day to guarantee at least one yield before day29
        # GOOSE 4d -> 25 (25+4=29), SHEEP 6d -> 23 (23+6=29), COW 8d -> 21 (21+8=29); GOOSE not bought (PLAN 0) but keep for completeness
        _ANIMAL_LAST_DAY = {"GOOSE": 25, "SHEEP": 23, "COW": 21}
        if day <= 25:  # max cutoff
            day0_n = {"SHEEP": 2, "COW": 2}
            # BATCH-4/5 (P4 family): YARN-gated sheep-cap arms. Day-0-2
            # waves (exactly 4 sheep) precede the first shop draw, so
            # gating only from d3 keeps every world identical until
            # information exists. Arms (mutually exclusive, precedence
            # order as coded - see constants block):
            #   V2  master : floor 8 until d9, full resume from d10
            #   V2A        : floor 8, never self-resumes
            #   V2B        : floor 4 until d9, full resume from d10
            #   V1         : floor 4, never self-resumes (batch-4 arm)
            # Any YARN_STORE sighting snaps the target back to PLAN.
            sheep_target = PLAN["SHEEP"]
            _cap_floor, _cap_resume = None, None
            if P4_SHEEP_CAP_V2:
                _cap_floor, _cap_resume = P4V2_FLOOR, P4V2_RESUME_DAY
            elif P4_SHEEP_CAP_V2A:
                _cap_floor = P4V2_FLOOR
            elif P4_SHEEP_CAP_V2B:
                _cap_floor, _cap_resume = (P4_NO_YARN_SHEEP_TARGET,
                                           P4V2_RESUME_DAY)
            elif P4_V3_ADAPTIVE:
                # price-adaptive floor: 8 normally, 4 on a d10-d14 dip
                _cap_floor = P4V2_FLOOR
                if (P4V3_QUIET_WINDOW0 <= day <= P4V3_QUIET_WINDOW1
                        and prices.get("WOOL", 200) < P4V3_WOOL_THRESHOLD):
                    _cap_floor = P4_NO_YARN_SHEEP_TARGET
            elif P4_SHEEP_CAP_V1:
                _cap_floor = P4_NO_YARN_SHEEP_TARGET
            if (_cap_floor is not None
                    and unlocked_shops is not None
                    and day >= 3
                    and "YARN_STORE" not in unlocked_shops
                    and (_cap_resume is None or day < _cap_resume)):
                sheep_target = min(sheep_target, _cap_floor)
            # Phase 15 (v17 ladder autopsies): milk-crash worlds killed the
            # cow-heavy build. ep 99812812: P(MILK) $185 -> $1 while wool held
            # $240; we kept pouring $400/cow into a dead market. When the
            # realized milk price collapses, freeze the cow herd and point
            # the remaining pen budget at sheep (wool was $200+ throughout).
            # Phase 16: trend detection — a >25% slide off the running peak
            # fires BEFORE the absolute floor does (ep 99840272 bought cows
            # at $185 that were worth $1 a week later). Peak is tracked
            # per-game from day 3 on; reset() clears it.
            milk_now = prices.get("MILK", 160)
            if day >= 3:
                if milk_now > self.milk_peak:
                    self.milk_peak = milk_now
            # Early indicator: rate of change over last 3-4 days (not absolute value)
            self.milk_history.append(float(milk_now))
            if len(self.milk_history) > 4:
                self.milk_history.pop(0)
            early_slowdown = False
            if len(self.milk_history) >= 3 and day >= ANIMAL_ADVISOR_MIN_DAY:
                d1 = self.milk_history[-1] - self.milk_history[-2]
                d2 = self.milk_history[-2] - self.milk_history[-3]
                # Only fire early if price is already softening below $150 —
                # avoids false positives when price is $180+ and dips slightly
                # but will recover (healthy worlds).
                if milk_now < 150:
                    if d2 > 5 and d1 < d2 * 0.5:
                        early_slowdown = True
                    if d1 < 0 and d1 < d2:
                        early_slowdown = True
            cow_target = PLAN["COW"]
            crash_fired = False
            if ANIMAL_ADVISOR_ON and day >= ANIMAL_ADVISOR_MIN_DAY:
                trend_broken = (self.milk_peak >= 100
                                and milk_now < MILK_TREND_DROP * self.milk_peak)
                if milk_now < MILK_CRASH_PRICE or trend_broken or early_slowdown:
                    crash_fired = True
                    cow_frozen = cows + self._unplaced_animal(invs, shed, "COW")
                    cow_target = cow_frozen
                    sheep_target = max(sheep_target,
                                       PLAN["COW"] + PLAN["SHEEP"] - cow_frozen)
            self.milk_crash_active = crash_fired
            for animal, target in (("SHEEP", sheep_target), ("COW", cow_target)):
                # no-waste-buying: skip if beyond last viable day for this animal
                if day > _ANIMAL_LAST_DAY.get(animal, 24):
                    continue
                have = (cows if animal == "COW" else sheep if animal == "SHEEP" else geese) \
                    + self._unplaced_animal(invs, shed, animal)
                missing = target - have
                if missing <= 0:
                    continue
                n = min(missing, day0_n.get(animal, 1) if day == 0 else 1)
                if self._unplaced_animal(invs, shed, animal) >= 10:
                    n = 0
                cost = ANIMALS[animal]["cost"]
                if n > 0 and buy("animal_" + animal, n, n * cost, ["BUY_ANIMAL", animal, n], units=n, floor=0):
                    self.animals_ordered[animal] = self.animals_ordered.get(animal, 0) + n

        # BATCH-2 (P1) ENGINE #2: refill the fertilizer working stock.
        # Deliberately LAST: expansion capital (land/seeds/animals) has
        # first claim; this only spends flush cash. One multi-unit order
        # per turn at most; the day gate stops purchases that cannot pay
        # back before the season ends.
        if FERT_BUY_ENGINE_V1 and day <= FERT_BUY_LAST_DAY:
            have_fert = shed.get("FERTILIZER", 0)
            want = FERT_STOCK_TARGET - have_fert
            price_ok = prices.get("FERTILIZER", 100) <= FERT_BUY_MAX_PRICE
            if want > 0 and price_ok:
                q = min(want, FERT_BUY_CAP_PER_DAY)
                cost = q * BASE["FERTILIZER"]
                # floor guarantees POST-purchase cash stays >= the reserve,
                # so tomorrow's seed/land/animal buys are never crowded out.
                buy("fert_stock", FERT_BUY_CAP_PER_DAY, cost,
                    ["BUY_PRODUCT", "FERTILIZER", q], units=q,
                    floor=FERT_BUY_MIN_MONEY)

        return orders

    def _sell(self, orders, shed, prices, day, animals_now, unlocked_shops=None):
        sold = self.sold_today

        def sell_capped(item, amount, cap):
            amount = min(amount, cap - sold.get(item, 0))
            if amount > 0 and len(orders) < 10:
                sold[item] = sold.get(item, 0) + amount
                orders.append(["SELL", item, amount])

        # Phase 3: overflow guard - sellable inventory at 80% of shed
        # capacity means end-of-day overflow discards are imminent; force
        # everything out (capacity trumps hold windows and feed reserves).
        sellable = ("MILK", "WOOL", "EGG", "FERTILIZER", "MELON",
                    "STRAWBERRY", "WHEAT", "CARROT", "TOMATO")
        force_dump = sum(shed.get(p, 0) for p in sellable) >= SHED_DUMP_AT

        # Phase 10: adaptive milk hold - classify the market once on d12
        # (prices are constant per day, so the hour-0 snapshot is exact).
        if day == 12 and self.milk_bull is None:
            self.milk_bull = prices.get("MILK", 160) >= MILK_BULL_D12
            self.milk_d12_price = prices.get("MILK", 160)
        milk_gate = MILK_BULL_HOLD_DAY if self.milk_bull else SELL_HOLD_DAY["MILK"]
        # Phase 11: late-game bail - bulls that start sliding at d16+ (the
        # d12 check cannot see a d21-29 collapse) dump at the visible
        # -15% level instead of riding the hold to crash prices.
        if (self.milk_bull and self.milk_d12_price
                and MILK_BAIL_FROM_DAY <= day < MILK_BULL_HOLD_DAY
                and prices.get("MILK", 160) < MILK_BAIL_FACTOR * self.milk_d12_price):
            milk_gate = day
            self.bail_fires += 1
        # BATCH-3 (P5): regime-adaptive wool tranche. Track season max
        # price every day (harmless state when OFF).
        # FIX: initialize wool_gate BEFORE conditional to prevent
        # UnboundLocalError on subsequent calls when price <= season max.
        wool_gate = SELL_HOLD_DAY["WOOL"]
        if prices.get("WOOL") is not None:
            w = prices["WOOL"]
            if self.wool_season_max is None or w > self.wool_season_max:
                self.wool_season_max = w
        wool_keep = 0
        yarn_present = (unlocked_shops is not None
                        and "YARN_STORE" in unlocked_shops)
        # BATCH-7 (P7): price-adaptive wool SELL timing. ON replaces the
        # P5/default wool hold+gate with a simple YARN-regime timing:
        #   - YARN present -> hold ALL wool until d22, full tranche dump.
        #   - YARN absent  -> early liquidation at V2A's d6 gate.
        # OFF leaves the P5 / default path untouched -> bit-identical GB.
        if P7_RELEASE_V1:
            wool_keep = 0
            if yarn_present:
                wool_gate = P7_WOOL_HOLD_DAY
            else:
                wool_gate = P7_WOOL_EARLY_DAY
        elif P5_RELEASE_V1 and yarn_present:
            # Rising regime (drain lifts wool 206 -> ~243): hold a SMALL
            # tranche back for the climb but flow everything above it, so
            # the 100-slot shed never crowds out strawberry (the full-hold
            # probe variant cost -$2.9k on seed 3 via shed collisions).
            # Bail: a >=25% slide off the season max releases the tranche
            # immediately (late-crash insurance, MILK_BAIL analog).
            wool_keep = P5_WOOL_KEPT_UNITS
            wool_gate = SELL_HOLD_DAY["WOOL"]
            if (day >= P5_WOOL_BAIL_FROM_DAY and self.wool_season_max
                    and prices.get("WOOL", 200)
                    < P5_WOOL_BAIL_FACTOR * self.wool_season_max):
                wool_keep = 0
                self.bail_fires += 1
        for p, gate in (("MILK", milk_gate), ("WOOL", wool_gate),
                        ("EGG", SELL_HOLD_DAY["EGG"])):
            amt = shed.get(p, 0)
            if p == "WOOL" and not force_dump:
                amt -= wool_keep
            if amt > 0 and (force_dump or day >= gate):
                cap = MARKET_AWARE_CAPS.get(p, 80) if MARKET_AWARE_ON else 80
                sell_capped(p, amt, cap)

        fert = shed.get("FERTILIZER", 0)
        # Phase 12: no fertilizer price floor - sell everything above the
        # reserve every day. The >=40 floor was a real-ladder bug: in
        # crash games fert falls to 4-27, the stock never sells, the shed
        # clogs and the cascade force-dumps milk/strawberry/wheat at
        # cratered prices (leader-1 of the real ladder sells ~1970 fert
        # at ~$50 avg = their single biggest revenue line). Locally the
        # price rarely drops below 40, so this is behavior-neutral in the
        # starter benchmark (shed stays ~2 units either way).
        # BATCH-2 (P1) engine #2: when ON, the reserve becomes the working
        # stock (collected surplus above it is still sold); OFF keeps the
        # exact baseline reserve of 2.
        fert_reserve = FERT_STOCK_TARGET if FERT_BUY_ENGINE_V1 else 2
        if fert > fert_reserve:
            cap = MARKET_AWARE_CAPS["FERTILIZER"] if MARKET_AWARE_ON else 80
            sell_capped("FERTILIZER", fert - fert_reserve, cap)

        melon = shed.get("MELON", 0)
        if melon > 0 and (force_dump or prices.get("MELON", 250) >= 30 or day >= 12):
            cap = MARKET_AWARE_CAPS["MELON"] if MARKET_AWARE_ON else 80
            sell_capped("MELON", melon, cap)

        strawberry = shed.get("STRAWBERRY", 0)
        if strawberry > 0 and (force_dump or prices.get("STRAWBERRY", 120) >= 30
                               or day >= SELL_HOLD_DAY["STRAWBERRY"]):
            cap = MARKET_AWARE_CAPS["STRAWBERRY"] if MARKET_AWARE_ON else 80
            sell_capped("STRAWBERRY", strawberry, cap)

        wheat = shed.get("WHEAT", 0)
        sell_wheat_min = 0 if force_dump else animals_now + FEED_RESERVE
        if wheat > sell_wheat_min and (force_dump or prices.get("WHEAT", 25) >= 25):
            cap = MARKET_AWARE_CAPS["WHEAT"] if MARKET_AWARE_ON else 150
            sell_capped("WHEAT", wheat - sell_wheat_min, cap)

        for p in ("CARROT", "TOMATO"):
            if shed.get(p, 0) > 0:
                cap = MARKET_AWARE_CAPS.get(p, 40) if MARKET_AWARE_ON else 40
                sell_capped(p, shed[p], cap)

        if day >= 27:
            for p, q in list(shed.items()):
                if p not in ("COW", "SHEEP", "GOOSE") and q > 0:
                    sell_capped(p, q, 999)


# Global instance
market = MarketEngine()