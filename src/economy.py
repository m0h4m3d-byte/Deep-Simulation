"""
economy.py - Economic engine for the Kaggriculture agent.
Contains the market order logic V15_FIXED production agent.

Parity guarantee: tests/test_market_parity.py replays the monolith agent and
asserts this engine produces IDENTICAL market orders at every step. Any
change to the numbers below must be reflected there or the test fails.
"""

from typing import Dict, List
import os

# ============================================================
# Economy tunables (ported verbatim from src/main.py baseline)
# ============================================================
# Phase 14 DEFAULT (DeepSim live-replay analysis): cow-heavy herd. Ladder
# opponents who beat us run ~17 COW / 7 SHEEP; cows produce every 2 days at
# $160+ and double the fertilizer stream. 30-seed benchmark: $89,373 avg vs
# $85,486 for the old 6/12 split (worst case also improves $42k -> $52k).
# KAGG_COW_PLAN="COW:SHEEP" overrides for benchmarking (e.g. "6:12" restores
# the pre-Phase-14 split).
# Phase 17 DEFAULT (60-seed benchmark: $93,209 vs $89,321 at 140). Ladder
# opponents who beat us buy ~60 wheat seeds vs our ~195; wheat tiles are
# better spent on strawberry/melon, and feed wheat still flows via
# BUY_PRODUCT when the shed runs dry (price-gated <= $70).
PLAN = {"COW": 15, "SHEEP": 3, "GOOSE": 0, "MELON": 12, "STRAWBERRY": 45, "WHEAT": 30}
if os.environ.get("KAGG_COW_PLAN"):
    try:
        _cow_n, _sheep_n = (int(x) for x in os.environ["KAGG_COW_PLAN"].split(":"))
        PLAN = dict(PLAN)
        PLAN["COW"] = _cow_n
        PLAN["SHEEP"] = _sheep_n
    except ValueError:
        pass
# Phase 6.2 verdict: CARROT burst (days 0..5, PLAN 12) was benchmarked and
# REVERTED. The seed loop re-buys whenever seeds < target, and carrot's 3-day
# cycle made that recycle 3x faster than melon's - 92 plantings against a 12
# seed budget. The field locked into melon/carrot (land buys starved while
# money floated ~$0 until day 12), strawberry plantings fell 183 -> 102 and
# shed clogging blocked deposits (day-15 cash $7,340 -> $994). Avg collapsed
# $81,607 -> $70,053. Carrot flavor stays OUT: baseline wheat/melon/strawberry.
FEED_RESERVE = 4
FERT_RESERVE = 0

# Phase 15: AnimalAdvisor (milk-crash herd pivot). See build_orders.
ANIMAL_ADVISOR_ON = os.environ.get("KAGG_ANIMAL_ADVISOR", "1") == "1"
MILK_CRASH_PRICE = 120
ANIMAL_ADVISOR_MIN_DAY = 10
# Phase 16: trend trigger — fire when price slides this fraction off its
# running per-game peak (0.75 = a 25% drop).
MILK_TREND_DROP = 0.75
# Phase 5 verdict: strict just-in-time pastures (build ONLY for unplaced
# animals, buffer 0) were benchmarked and REVERTED: purchase-wave latency
# shrank the herd (wool 118 -> 69 units, day-15 cash $7,138 -> $438) and
# score fell $81,479 -> $74,982. The empirically best policy stays the
# Phase-4 one: build pens at ordered + PASTURE_BUFFER - purchases arrive in
# a continuous stream, so pens are ready just before animals, and the 2-tile
# buffer is the ONLY empty-pen waste (vs baseline's unbounded empty pens).
PASTURE_BUFFER = 2
# NOTE: the Phase-2 hire law (workers = 2 + day//3) was tried and REVERTED:
# the game RESETS hired hands to zero every day, so baseline's aggressive daily
# ramp (min(HIRE_TARGET, HIRE_RAMP + day)) is required - the slow law left
# the farm with ~37% fewer worker-days and crashed the score to $25.5k
# (vs baseline's $71k). Worker specialization (planner) stays; hiring is baseline.
HIRE_TARGET = 12  # baseline baseline
HIRE_RAMP = 3
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
SHED_CAPACITY = 100
SHED_DUMP_AT = 80
# P8 FIX: sell EVERYTHING immediately — in competitive play, holding inventory
# means losing market share. Convert to cash instantly for reinvestment.
SELL_HOLD_DAY = {"MILK": 0, "WOOL": 0, "EGG": 0, "STRAWBERRY": 0}
MILK_BULL_D12 = 180
MILK_BULL_HOLD_DAY = 20
MILK_BAIL_FROM_DAY = 16
MILK_BAIL_FACTOR = 0.85

ANIMALS = {
    "COW": {"cost": 400, "struct": "PASTURE", "product": "MILK"},
    "SHEEP": {"cost": 500, "struct": "PASTURE", "product": "WOOL"},
    "GOOSE": {"cost": 300, "struct": "COOP", "product": "EGG"},
}

# Seed cost per crop (matches src/constants.CROP_CONFIG[..]["seed_cost"]).
SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}

# Base (reference) sale price per product.
BASE = {"WHEAT": 25, "CARROT": 35, "TOMATO": 60, "STRAWBERRY": 120, "MELON": 250,
        "EGG": 50, "MILK": 160, "WOOL": 200, "FERTILIZER": 100}

# ============================================================
# BATCH-2 (P1) ENGINE #2: fertilizer working-stock buyer
# ============================================================
# Keeps a working stock of fertilizer in the shed so the planner's
# strawberry FERTILIZE jobs (ongoing crop: watered+fertilized doubles the
# scheduled yield 1 -> 2) can actually execute. Today GB collects ~10-15
# fert/day from animals but SELLS everything above a 2-unit reserve while
# emitting daily fertilize jobs for ~40+ mature plants - most starve.
# Ladder evidence (Phase-12 decode): leader-2 APPLIES fert to crops
# (5-16/day) instead of selling it.
# Cash priority: this block runs LAST in build_orders - land / seeds /
# animals / hiring always have first claim on capital. Purchases stop at
# FERT_BUY_LAST_DAY because later applications cannot pay back within the
# season.
#
# TOGGLE: default OFF = bit-exact baseline/GOLDEN_BASELINE behaviour (the OFF
# path is guarded by G0 toggle-off parity). Local benchmark arms flip it
# via KAGG_FERT_BUY_V1=1 WITHOUT any source divergence between arms.
FERT_BUY_ENGINE_V1 = os.environ.get("KAGG_FERT_BUY_V1", "").strip().lower() in ("1", "true", "on")
FERT_STOCK_TARGET = 8      # shed units to maintain when engine is ON
FERT_BUY_CAP_PER_DAY = 6   # max units ordered per day (order-cap safety)
FERT_BUY_LAST_DAY = 26     # no purchases that cannot pay back in-season
FERT_BUY_MIN_MONEY = 800   # never buy below this cash level
FERT_BUY_MAX_PRICE = 130   # skip when market price exceeds this

# ============================================================
# BATCH-3 (P5): regime-adaptive WOOL release gate
# ============================================================
# Signal: obs.town.unlocked_shops (shared, updated by the referee every
# day-multiple-of-3; drawn WITH replacement from 8 types, cap 8 copies).
# WOOL has exactly ONE consumer shop type: YARN_STORE. Sweep evidence
# (tools/out/p5_obs_sweep.json, seeds 1-30 OFF-mode):
#   yarn==0 worlds (n=9): score avg $74,050 | wool path slides 218(d6) ->
#     129(d18) -> $1(d22+); our own ~500-unit production floods the market
#     (elasticity -$0.40/unit above I0) and late shears realize ~$0.
#   yarn>=1 worlds (n=21): score avg $89,724 | wool rises to ~$243.
# Gate v1 (evidence-corrected during probe):
#   * YARN_STORE present  -> HOLD wool to P5_WOOL_HOLD_DAY: in these worlds
#     drain lifts wool 206 -> ~243 monotonically, so early selling leaves
#     +$30/unit on ~110 units. Bail: if wool falls >=25% below its season
#     max on/after day 16 (late-crash insurance, MILK_BAIL pattern), dump.
#   * YARN_STORE absent   -> keep the day-6 gate: price peaks ~d6 (218) and
#     the slide is caused by our own flood volume, not timing - early cash
#     and shed space beat a doomed hold.
# TOGGLE: default OFF = bit-exact GB; arms flip via KAGG_P5_RELEASE_V1=1.
P5_RELEASE_V1 = os.environ.get("KAGG_P5_RELEASE_V1", "").strip().lower() in ("1", "true", "on")
P5_WOOL_KEPT_UNITS = 25
P5_WOOL_BAIL_FROM_DAY = 16
P5_WOOL_BAIL_FACTOR = 0.75

# ============================================================
# BATCH-4 (P4): YARN-gated conditional sheep cap
# ============================================================
# WOOL has a single consumer shop type (YARN_STORE - proven in the P5
# sweep). In yarn-less worlds our own ~500-unit production floods the
# market to the $1 floor regardless of timing, so sheep #5..#12 produce
# near-zero-value wool while consuming $500 each plus daily FEED/CARE
# labor, shed slots and manure-pen tiles.
#
# Gate v1 (progressive, decision refreshes each morning):
#   * YARN_STORE seen            -> full PLAN["SHEEP"] (baseline behaviour)
#   * still absent on day >= 3   -> sheep target floors at
#     P4_NO_YARN_SHEEP_TARGET(4). Day 0-2 waves (2+1+1 = exactly 4 sheep)
#     run BEFORE any shop draw exists, so the floor aligns perfectly with
#     the pre-information accumulation - nothing changes pre-d3 for anyone.
#   * late YARN unlock (d6..d24) -> target snaps back to 12 and the
#     1-sheep/day stream resumes (late sheep still net-positive when a
#     drainer exists).
# Side effects (capped worlds only): pens are JIT-built from actual
# animals_ordered + buffer, so ~6 pasture tiles revert to crops; FEED/
# CARE labor frees up; feed-wheat purchases drop; manure income drops.
# TOGGLE: default OFF = bit-exact GB; arms flip via KAGG_P4_SHEEP_CAP_V1=1.
P4_SHEEP_CAP_V1 = os.environ.get("KAGG_P4_SHEEP_CAP_V1", "").strip().lower() in ("1", "true", "on")
P4_NO_YARN_SHEEP_TARGET = 4

# ============================================================
# BATCH-5 (P4-v2): softer floor (v2a) + deadline resume (v2b)
# ============================================================
# v1 RED-by-rule diagnosis: (a) floor 4 amputated the manure->
# FERTILIZER line and CARE labor in some no-yarn worlds (seed 8 lost
# -$13.8k WITH zero yarn) and (b) late-yarn worlds stayed capped through
# the cash-rich mid-game, then the 8-sheep post-YARN top-up collided
# with end-season order/cash pressure (seed 27 lost -$20.3k).
#
# v2a: floor rises 4 -> 8. Only sheep #9-#12 are ever skipped, keeping
#      the manure/CARE economy largely intact in drainless worlds.
# v2b: from RESUME_DAY(10) the cap lifts entirely even without YARN -
#      the normal 1/day stream finishes the herd inside the cash-rich
#      window, so a late YARN unlock finds us already complete and the
#      end-season collision cannot happen.
# Arms are mutually exclusive; if several flags are set the first match
# in the build_orders resolution order wins (documented precedence):
#   KAGG_P4_SHEEP_CAP_V2  : floor 8 until d9, full resume from d10 (AB)
#   KAGG_P4_V2A           : floor 8, no self-resume            (A)
#   KAGG_P4_V2B           : floor 4 until d9, full resume d10+ (B)
#   KAGG_P4_SHEEP_CAP_V1  : floor 4, no self-resume (batch-4 arm)
P4_SHEEP_CAP_V2 = os.environ.get("KAGG_P4_SHEEP_CAP_V2", "").strip().lower() in ("1", "true", "on")
P4_SHEEP_CAP_V2B = os.environ.get("KAGG_P4_V2B", "").strip().lower() in ("1", "true", "on")
# BATCH-6a PROMOTION: V2A won its GREEN gate (mean $86,355, paired
# +$1,333, tails thinner than GB) and is now the SHIPPED default. The
# env var flipped to an opt-OUT: KAGG_P4_V2A=0 restores pristine GB
# behaviour for parity/replay harnesses.
_p4v2a_raw = os.environ.get("KAGG_P4_V2A", "1").strip().lower()
P4_SHEEP_CAP_V2A = _p4v2a_raw not in ("0", "false", "off", "no")
P4V2_FLOOR = 8
P4V2_RESUME_DAY = 10

# BATCH-6 (P4-v3): PRICE-ADAPTIVE sheep floor (experimental, default OFF).
# If no YARN_STORE is visible and the d10-d14 WOOL price is low, cap the
# herd at 4 (the v1 floor) instead of 8 (the V2A floor). Rationale: in
# drainless worlds a rock-bottom WOOL price is a *leading* signal that the
# drainer never arrives; the remaining #9-#12 sheep then only burn cash,
# feed labor and pen tiles. Worlds with YARN (or WOOL still healthy on the
# decision window) keep the V2A floor 8. Mutually exclusive with the other
# P4 arms (checked in coded precedence order below). Default OFF.
P4_V3_ADAPTIVE = os.environ.get("KAGG_P4_V3_ADAPTIVE", "").strip().lower() in ("1", "true", "on")
P4V3_QUIET_WINDOW0 = 10
P4V3_QUIET_WINDOW1 = 14
# WOOL < this on days 10-14 (no-YARN world) -> drop floor 8 -> 4.
P4V3_WOOL_THRESHOLD = 60

# ============================================================
# BATCH-7 (P7): price-adaptive WOOL SELL timing gated on the
# YARN signal. Independent of the P5 tranche gate; when ON it
# fully replaces the wool HOLD/SELL logic with a simpler,
# price-adaptive timing. Mutually exclusive in spirit with P5
# wool logic (P7 wins, P5 wins otherwise; both OFF == V2A GB).
#   * YARN present  -> the d22+ premium (~$240) is the high-water
#     mark of the rising-regime price curve; hold ALL wool until
#     d22 and dump the full tranche once (late full-tranche). The
#     P5 probe variant held 25 units at d6 - that missed the d22
#     premium entirely, leaving ~$840/unit of value on the table.
#   * YARN absent   -> d15+ glut collapses WOOL to $1-5 (proven by
#     the P4-v3 yarn probe: WOOL stays 181-200 through d10-14 then
#     craters only AFTER d15). Liquidate the standard early gate
#     (V2A's d6) = bit-identical to V2A on the no-yarn side; the
#     entire expected gain is concentrated in YARN worlds.
# TOGGLE: default OFF = bit-identical GB (P5 OFF path untouched).
# Arms flip via KAGG_P7_SELL_V1=1.
P7_RELEASE_V1 = os.environ.get("KAGG_P7_SELL_V1", "").strip().lower() in ("1", "true", "on")
P7_WOOL_HOLD_DAY = 22            # YARN world: hold-all until the late premium
P7_WOOL_EARLY_DAY = SELL_HOLD_DAY["WOOL"]  # 6; no-YARN world: early liquidation
P7_WOOL_SELL_CAP = 80            # full-shed dump (matches the existing sell_capped cap)

LAND_COSTS = [1000, 2000, 4000]
LAND_DAYS = [6, 9, 12]


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

        # Land is the highest-ROI investment; finance it before feed/seeds.
        unlocked = len(me.get("unlocked_quadrants", []))
        if 0 < unlocked < len(LAND_COSTS) + 1 and day >= LAND_DAYS[unlocked - 1]:
            buy("land", 1, LAND_COSTS[unlocked - 1], ["BUY_LAND"])

        wheat_price = prices.get("WHEAT", 25)
        need_reserve = 4 if wheat_price <= 35 else 0
        feed_need = animals_now + need_reserve
        if shed.get("WHEAT", 0) < feed_need and wheat_price <= 70:
            q = min(feed_need - shed.get("WHEAT", 0), 6)
            if q > 0 and q * wheat_price <= money - pending:
                feed_cap = 4 if animals_now <= 2 else 2 if animals_now < 8 else 3
                buy("feed", feed_cap, q * wheat_price, ["BUY_PRODUCT", "WHEAT", q], floor=0)

        seed_plan = {"WHEAT": (PLAN["WHEAT"], 28, 8, 0), "MELON": (PLAN["MELON"], 13, 12 if day == 0 else 6, 0),
                     "STRAWBERRY": (PLAN["STRAWBERRY"], 22, 10, 3)}
        for crop, (target, last_day, cap, start_day) in seed_plan.items():
            if day > last_day or day < start_day:
                continue
            have = seeds.get(crop, 0)
            if have < target:
                q = min(target - have, cap)
                if q > 0:
                    buy("seed_" + crop, cap, q * SEED_COST[crop], ["BUY_SEED", crop, q], units=q, floor=0)

        if day <= 24:
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
                sell_capped(p, amt, 80)

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
            sell_capped("FERTILIZER", fert - fert_reserve, 80)

        melon = shed.get("MELON", 0)
        if melon > 0 and (force_dump or prices.get("MELON", 250) >= 30 or day >= 12):
            sell_capped("MELON", melon, 80)

        strawberry = shed.get("STRAWBERRY", 0)
        if strawberry > 0 and (force_dump or prices.get("STRAWBERRY", 120) >= 30
                               or day >= SELL_HOLD_DAY["STRAWBERRY"]):
            sell_capped("STRAWBERRY", strawberry, 80)

        wheat = shed.get("WHEAT", 0)
        sell_wheat_min = 0 if force_dump else animals_now + FEED_RESERVE
        if wheat > sell_wheat_min and (force_dump or prices.get("WHEAT", 25) >= 25):
            sell_capped("WHEAT", wheat - sell_wheat_min, 150)

        for p in ("CARROT", "TOMATO"):
            if shed.get(p, 0) > 0:
                sell_capped(p, shed[p], 40)

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