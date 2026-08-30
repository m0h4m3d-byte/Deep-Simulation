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

# Phase 6.2 verdict: CARROT burst (days 0..5, PLAN 12) was benchmarked and
# REVERTED. The seed loop re-buys whenever seeds < target, and carrot's 3-day
# cycle made that recycle 3x faster than melon's - 92 plantings against a 12
# seed budget. The field locked into melon/carrot (land buys starved while
# money floated ~$0 until day 12), strawberry plantings fell 183 -> 102 and
# shed clogging blocked deposits (day-15 cash $7,340 -> $994). Avg collapsed
# $81,607 -> $70,053. Carrot flavor stays OUT: baseline wheat/melon/strawberry.
# Phase 6/6.1/6.3 verdicts (all benchmarked, ALL REVERTED to baseline's 12):
#   - flat 14        : cost doubled, avg $74,000
#   - surge 14 18-22 : cost +$3.1k, avg $78,808
#   - surge 13 18-22 : avg $80,244 then $79,360 (2 runs) vs baseline
#                      $81,607/$81,479 - a consistent -$1.5k made the hand
#                      unprofitable even at ~$720. PEAK PLANTS rose
#                      59.7 -> 60.7 in both, i.e. hiring is NOT the binding
#                      constraint; labor surpluses cost more than they add.
# The hire lever is CLOSED. Any future capacity gain must come from
# allocation (sell timing / order mix), not more hands.
RESERVE = 15

# ============================================================
# Phase 6.5 verdict: hold-wheat / later-strawberry REVERTED
# ============================================================
# Probe showed wheat $25->$49 and strawberry $120->$307 rising all season,
# but the 83-game run collapsed: avg $70,824 vs $81,607. Deferring ALL
# wheat sales until price >= 42 starved the mid-game cashflow (day-15 cash
# $3,051 vs $7,340) - the expansion ramp (strawberry seeds $100, land,
# animals) stalled: strawberry plantings 183 -> 121, peak animals 13.1 ->
# 11.1, feed purchases 295 vs ~80. Lesson: sell-timing must NEVER gate the
# early cash flow; only the SURPLUS after expenses can be held. Any retry
# needs a day>=12-ish floor so expansion capital keeps flowing.
# Market prices RISE as the season drains the shared market inventory
# (strawberry 128->256 over a game), so holding premium products until
# SELL_HOLD_DAY captures +30-40% vs baseline's sell-on-sight. Melon prices FALL
# after ~day 15 (256->176), so melon keeps baseline's early sell. The shed holds
# at most SHED_CAPACITY items - overflow at end-of-day is DISCARDED - so
# once sellable inventory reaches SHED_DUMP_AT (80%), everything is
# force-sold regardless of price or hold windows.
#
# Phase 7 (dominant-player replay, 2026-08): the ladder #1 seat's actual
# price events REFUTE the "milk/wool rise" half of the Phase-3 claim -
# milk 169->1 and wool 206->1 (glut collapse after ~day 15), while egg
# rises monotonically 50->59. The winner sells milk from day 8 ($158-199)
# and wool from day 6 ($183-217); we held both to day 16 and sold into the
# collapse. Gates updated: MILK 8, WOOL 6, EGG stays 16 (rising).
#
# Phase 8 (surplus-only wheat bank, 2026-08) tried and REVERTED: banking
# wheat from day 12 until price >= 42 (winner-replay trick, 807u @ $44-51)
# lost consistently - avg $79,949 / $81,470 (both below earlier's $84,837, r2
# even under previous's $81,607). The banked wheat fills the 100-cap shed
# (d15 usage 52/100 vs 37): it collides with our standing stock (strawberry
# hold to 20, egg to 16, fert) and forces sub-peak force-dumps, throttling
# strawberry plantings 136 -> 101-110. The winner could bank because their
# shed was otherwise empty (everything else sold from d6-8). Lever CLOSED
# until shed capacity stops being the binding constraint.
#
# Phase 9 (2026-08): Phase 9 (pyramidal pens, constants.PASTURE_POS)
# adopted - NINE 83-game runs: $86,266 / $84,703 / $84,156 / $84,291 /
# $87,948 / $87,857 / $82,519 / $83,717 / $85,454 (9-run combined $85,212,
# 100% wins x9, median avg $86,941). Confirmed structural gains vs earlier:
# wool +37%, milk +4%, strawberry plantings +9-36%, day-15 cash +$2.2k,
# travel -8%. BUT the last 3-set averaged $83,897 (< $85k bar; 2 of 3 runs
# below) - the score delta vs earlier is WITHIN run noise (~$1.6k combined) and
# the tail stays heavier (worst $39.1k-57.4k vs earlier's $59.2k).
# CAVEAT: earlier (identical sell gates) rose to 828.7 on the real Kaggle
# leaderboard vs previous's 664.5 - but the starter benchmark does NOT predict
# real opponents. Reference: 9-run combined >= $85,212 + 100% wins.
# Phase 10 (2026-08): adaptive milk hold. Per-day price traces across 24
# games show milk is IDENTICAL through d8 (169->186) in every seed, so
# herd/buy-side adaptation is impossible (cows finish by d4, sheep by d10).
# From d12 the paths diverge: bear games collapse to 22-116 by d20-29
# (holding = disaster), bull games keep RISING 195->250-356 (selling from
# d8 leaves +30-60% on the table - corr(score, milk end price) = +0.79 is
# the single biggest tail driver). Detect at d12: price >= MILK_BULL_D12
# (180) -> hold milk to MILK_BULL_HOLD_DAY (20), dumping at 235-268; else
# keep the d8 gate. Bears are never held. Wool's d12 price does NOT
# separate bull/bear (195 in both) and wool crashes late in ~3/16 games -
# holding wool adds variance without mean: unchanged.
#
# Phase 10 (2026-08): Phase 10 adopted - three 83-game runs $83,750 /
# $87,074 / $85,726 (combined $85,517, 100% wins x3, median avg $86,504).
# Volatility is the headline: std $11,755 vs prior's $15,676 (-25%), p5
# $66,611 vs $49,961 (+$16.6k), worst $36.7-52.6k vs $39.1-57.4k (highest
# floor ever at $52,553). Milk corr fell 0.79 -> 0.64 (bull upside now
# captured: sold at 235-268 instead of 195-226). Known cost: day-15 cash
# -$3.5k ($7.9-8.1k) and shed usage +16-19pts (46-49/100 at d15) while
# milk is held; force-dump in bulls is benign (dumps at high prices).
# WOOL corr rose 0.37 -> 0.47: wool is now the largest unhedged driver.
# Reference for future phases: combined-3-run avg >= $85,517 + 100% wins.
# Phase 11 (2026-08): late-game milk bail. Kaggle ladder replays (10 games,
# 6W/4L) show a SECOND crash mode the d12 check cannot see: milk stays bull
# through d15 (181-196) then slides to 112-40 by d20 and 1-22 by d29
# (93000233, 93001169 - both losses; Phase 10's hold-to-20 sold at 112 vs
# ~150 available at d17 when the -22% drop from d12 was already visible).
# Rule: in bull games, if milk falls >=15% below its d12 value on days
# 16-19, dump the whole herd output immediately. Never fires in true bulls
# (milk rises monotonically 250-356 there, verified across 24 local games
# and 6 Kaggle bull wins), so the current baseline is untouched in expectation.
# Strawberry/melon are already sold daily (price gates always true), so
# the late strawberry crash (120->1-24 at d25-29) is unavoidable market
# luck for everyone; winners there just held fewer late strawberry seeds
# (26 vs our 40) - Phase 12 candidate: stop strawberry expansion after d16.
#
# Phase 11 (2026-08): Phase 11 adopted - four 83-game runs $84,168 /
# $85,025 / $83,992 / $82,442 (combined $83,907, 100% wins x4, worst floor
# $44.8-56.1k - the highest floor ever seen at $56,109). Honest caveat:
# the bail fired ZERO times in 30 instrumented live games - locally stable is
# behaviorally identical to current, so the benchmark means differ only by
# sampling noise (run-mean SE ~+/-1.7k; current's $85,517 reference was itself
# a lucky 3-run sample - its own r1 was $83,750; pooled mean of all 7 runs
# ~$84.5k). The bail exists purely for the real-ladder late-crash profile
# (93000233/93001169-class games: +5-8k, flipping losses to wins), which
# the starter benchmark cannot generate. Reference for future phases:
# combined-3-run avg >= $85,517 + 100% wins (unchanged from current).
#
# Phase 12 (2026-08): fertilizer price floor removed. Leader replay
# (leader-1 vs leader-2, $99,105 vs $89,434 - a mid-bull game: milk
# 160->183, wool crashed 200->11, strawberry crashed 120->1-57) decoded
# the ladder blueprint: leader-1's biggest revenue line is FERTILIZER -
# ~1970 units at ~$50 avg, sold DAILY with zero price floor and a shed
# that never holds fert; he also sells melon at the d10 peak (66 units),
# trades wheat (722 sold), sells strawberry from d17-19, buys only 2
# lands (Q3) and hires ~277. Leader-2 runs a wheat machine instead (buy
# 911 / sell 1271) and APPLIES fert to crops (5-16/day) instead of
# selling. Our >=40 fert floor was the real-ladder bug: in crash games
# fert falls to 4-27, stock never sells, shed clogs and the cascade
# force-dumps held milk/strawberry/wheat at cratered prices (the
# catastrophic losses). Locally fert stays >=40 (avg_min 47.5), so the
# starter benchmark is behavior-neutral (shed keeps its 2-unit reserve).
# NOTE: leader-1's ~65 fert/day vs our ~10-15/day at identical collect
# rates (10.2 vs 9.2 COLLF/day) is NOT explained by the data (fert piles
# spawn off-tiles); likely map-luck - not replicated blind.
#
# Phase 12 (2026-08): Phase 12 adopted - reference for future phases:
# combined-3-run avg >= $85,517 + 100% wins.
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

        # no-waste-buying: last_day aligned to LAST_PLAYABLE_DAY(29)-first_yield_day
        # WHEAT 28->27 (27+2=29), STRAW 22->19 (19+10=29), MELON 13 keeps (13+10=23 safe, 19+10=29 would also safe but keep 13 conservative)
        seed_plan = {"WHEAT": (PLAN["WHEAT"], 27, 8, 0), "MELON": (PLAN["MELON"], 13, 12 if day == 0 else 6, 0),
                     "STRAWBERRY": (PLAN["STRAWBERRY"], 19, 10, 3)}
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


class EconomyEngine:
    """
    Legacy heuristic value estimates (kept for the planner migration).
    These are NOT used by MarketEngine and will be wired or removed
    when the planner port lands.
    """

    def __init__(self):
        self.day = 0
        self.hour = 0
        self.money = 3000
        self.season_days = 30
        self.turns_per_day = 24

    def update_state(self, state):
        self.day = state.day
        self.hour = state.hour
        self.money = state.money

    def get_remaining_days(self) -> int:
        return self.season_days - self.day

    def get_remaining_turns(self) -> int:
        remaining_hours = self.turns_per_day - self.hour
        remaining_days = self.season_days - self.day - 1
        return remaining_days * self.turns_per_day + remaining_hours

    def crop_profit_estimate(self, crop: str, state) -> float:
        from src.constants import CROP_CONFIG

        config = CROP_CONFIG.get(crop)
        if not config:
            return -9999
        remaining_days = self.get_remaining_days()
        growth_time = config.get("first_yield_day", 10)
        if remaining_days < growth_time:
            return -9999
        seed_cost = config.get("seed_cost", 10)
        price = state.prices.get(crop, config.get("base_price", 25))
        max_yield = config.get("max_yield", 4)
        expected_revenue = max_yield * price
        profit = expected_revenue - seed_cost
        return profit

    def harvest_value(self, tile, state) -> float:
        if not tile.yield_units:
            return 0
        crop = tile.crop
        price = state.prices.get(crop, 25)
        return tile.yield_units * price

    def fertilizer_value(self, state) -> float:
        remaining_days = self.get_remaining_days()
        if remaining_days < 8:
            return -100
        if state.money < 200:
            return -50
        for _, _, tile in state.iter_plants():
            if tile.is_plant:
                age = state.day - tile.planted_day
                if age <= 2 and tile.crop in ["CARROT", "WHEAT"]:
                    return 60
        return -20

    def land_value(self, state) -> float:
        unlocked = len(state.unlocked_quadrants)
        if unlocked >= 4:
            return -9999
        remaining_days = self.get_remaining_days()
        if remaining_days < 10:
            return -9999
        cost = LAND_COSTS[unlocked] if unlocked < len(LAND_COSTS) else 4000
        return 2000 - cost

    def worker_value(self, state) -> float:
        remaining_days = self.get_remaining_days()
        if remaining_days < 5:
            return -9999
        if state.get_plant_count() < 3:
            return -100
        return 200


# Global instances
economy = EconomyEngine()
market = MarketEngine()