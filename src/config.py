"""
config.py — Single source of truth for ALL decision numbers
Effective values as actually used on main a2debda (v26, mean 90225)
AFTER cleanup: NO os.environ / KAGG_* toggles — every value is explicit.

Principle: any KAGG_* that was ON/OFF is now frozen as a plain constant.
To change a value, edit it HERE ONLY. No hidden env var can override it.
"""

# ============================================================
# Core economy — frozen effective values (were KAGG_* defaults)
# ============================================================
PLAN = {"COW": 6, "SHEEP": 3, "GOOSE": 0, "MELON": 12, "STRAWBERRY": 20, "WHEAT": 15}

LAND_COSTS = [1000, 2000, 4000]
LAND_DAYS = [6, 9, 12]

HIRE_TARGET = 12
HIRE_RAMP = 3
PASTURE_BUFFER = 2
RESERVE = 15
SHED_CAPACITY = 100
SHED_DUMP_AT = 80

SELL_HOLD_DAY = {"MILK": 0, "WOOL": 0, "EGG": 0, "STRAWBERRY": 0}
MILK_BULL_D12 = 180
MILK_BULL_HOLD_DAY = 20
MILK_BAIL_FROM_DAY = 16
MILK_BAIL_FACTOR = 0.85

MARKET_AWARE_ON = True  # was KAGG_MARKET_AWARE=1 default ON
MARKET_AWARE_CAPS = {
    "MELON": 25,
    "WOOL": 30,
    "MILK": 40,
    "STRAWBERRY": 50,
    "EGG": 80,
    "WHEAT": 150,
    "FERTILIZER": 80,
    "CARROT": 60,
    "TOMATO": 40,
}

ANIMALS = {
    "COW": {"cost": 400, "struct": "PASTURE", "product": "MILK"},
    "SHEEP": {"cost": 500, "struct": "PASTURE", "product": "WOOL"},
    "GOOSE": {"cost": 300, "struct": "COOP", "product": "EGG"},
}
SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}
BASE = {"WHEAT": 25, "CARROT": 35, "TOMATO": 60, "STRAWBERRY": 120, "MELON": 250, "EGG": 50, "MILK": 160, "WOOL": 200, "FERTILIZER": 100}

FEED_RESERVE = 4
FERT_RESERVE = 0

# AnimalAdvisor — was KAGG_ANIMAL_ADVISOR=1 default ON
ANIMAL_ADVISOR_ON = True
MILK_CRASH_PRICE = 120
ANIMAL_ADVISOR_MIN_DAY = 10
MILK_TREND_DROP = 0.75

# ============================================================
# Board layout — authoritative copy from src/constants.py
# ============================================================
SHED_TILES = [(4, 4), (5, 4), (4, 5), (5, 5)]
PASTURE_POS = [(3, 3), (4, 3), (3, 4), (2, 3), (2, 4), (3, 2), (4, 2), (2, 2),
               (1, 3), (1, 4), (2, 1), (3, 1), (1, 2), (0, 3), (1, 1), (0, 2),
               (2, 0), (4, 1), (0, 1), (1, 0), (5, 3), (6, 4), (3, 5), (6, 5),
               (5, 2), (4, 0), (0, 4), (1, 5)]
COOP_POS = [(0, 0)]

CROP_CONFIG = {
    "WHEAT": {"seed_cost": 10, "base_price": 25, "first_yield_day": 2, "max_yield_day": 4, "max_yield": 6, "max_yield_no_fertilizer": 4, "is_ongoing": False},
    "CARROT": {"seed_cost": 20, "base_price": 35, "first_yield_day": 2, "max_yield_day": 3, "max_yield": 4, "max_yield_no_fertilizer": 3, "is_ongoing": False},
    "TOMATO": {"seed_cost": 50, "base_price": 60, "first_yield_day": 8, "max_yield_day": 8, "max_yield": 4, "max_yield_no_fertilizer": 4, "is_ongoing": True},
    "STRAWBERRY": {"seed_cost": 100, "base_price": 120, "first_yield_day": 10, "max_yield_day": 10, "max_yield": 4, "max_yield_no_fertilizer": 4, "is_ongoing": True},
    "MELON": {"seed_cost": 80, "base_price": 250, "first_yield_day": 10, "max_yield_day": 12, "max_yield": 6, "max_yield_no_fertilizer": 6, "is_ongoing": False},
}

# ============================================================
# Planner / strategy — day gates (were in src/strategy.py)
# ============================================================
# Day gates ported verbatim from main.py baseline
WHEAT_LAST_DAY = 28
MELON_LAST_DAY = 13
STRAWBERRY_START_DAY = 8
STRAWBERRY_LAST_DAY = 22
MELON_DAY0_CAP = 12
MELON_REGULAR_CAP = 6
ANIMAL_LAST_BUY_DAY = 24
MELON_SELL_DAY = 12
STRAWBERRY_SELL_DAY = 20
MILK_SELL_DAY = 8
WOOL_SELL_DAY = 6
EGG_SELL_DAY = 16
LIQUIDATE_DAY = 27

PLANT_TARGET_FULL = 55
PLANT_TARGET_LATE = 30
PLANT_TARGET_SWITCH_DAY = 22
LAST_PLAYABLE_DAY = 29
STRAW_LEAD_THRESHOLD = 190
ADVISOR_MIN_DAY = 12
P4_SHEEP_FLOOR = 8
P4_RESUME_DAY = 10
WEED_PRIORITY_THRESHOLD = 15
WEED_PRIORITY_PRIO = 1

# CropAdvisor — was KAGG_CROP_ADVISOR=1 default ON
CROP_ADVISOR_ON = True

# ============================================================
# Experimental toggles — FROZEN to effective values
# (were KAGG_* env vars; now plain constants, no environ read)
# ============================================================
# Fertilizer working-stock buyer — was KAGG_FERT_BUY_V1, default OFF
FERT_BUY_ENGINE_V1 = False
FERT_STOCK_TARGET = 8
FERT_BUY_CAP_PER_DAY = 6
FERT_BUY_LAST_DAY = 26
FERT_BUY_MIN_MONEY = 800
FERT_BUY_MAX_PRICE = 130

# Batch-3 P5 wool tranche — was KAGG_P5_RELEASE_V1, default OFF
P5_RELEASE_V1 = False
P5_WOOL_KEPT_UNITS = 25
P5_WOOL_BAIL_FROM_DAY = 16
P5_WOOL_BAIL_FACTOR = 0.75

# Batch-4 P4 sheep cap V1 — was KAGG_P4_SHEEP_CAP_V1, default OFF
P4_SHEEP_CAP_V1 = False
P4_NO_YARN_SHEEP_TARGET = 4

# Batch-5 P4-v2 family — were KAGG_P4_SHEEP_CAP_V2 / KAGG_P4_V2B / KAGG_P4_V2A
# Effective: V2A=ON (floor 8, no resume), V2=OFF, V2B=OFF
P4_SHEEP_CAP_V2 = False
P4_SHEEP_CAP_V2B = False
P4_SHEEP_CAP_V2A = True
P4V2_FLOOR = 8
P4V2_RESUME_DAY = 10

# Batch-6 P4-v3 price-adaptive — was KAGG_P4_V3_ADAPTIVE, default OFF
P4_V3_ADAPTIVE = False
P4V3_QUIET_WINDOW0 = 10
P4V3_QUIET_WINDOW1 = 14
P4V3_WOOL_THRESHOLD = 60

# Batch-7 P7 wool sell timing — was KAGG_P7_SELL_V1, default OFF
P7_RELEASE_V1 = False
P7_WOOL_HOLD_DAY = 22
P7_WOOL_EARLY_DAY = 0  # == SELL_HOLD_DAY["WOOL"]
P7_WOOL_SELL_CAP = 80

# Legacy aliases kept for import compatibility (planner/tests may import these)
FERT_BUY_ON = FERT_BUY_ENGINE_V1
P5_WOOL_ON = P5_RELEASE_V1
P4_V2_ON = P4_SHEEP_CAP_V2
P4_V2B_ON = P4_SHEEP_CAP_V2B
P5_V3_ADAPTIVE = P4_V3_ADAPTIVE
P7_WOOL_ON = P7_RELEASE_V1
FERT_STOCK_TARGET_ALIAS = 2  # OFF-path reserve used in tests
