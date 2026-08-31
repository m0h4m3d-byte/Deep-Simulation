"""
constants.py - All game constants for Kaggriculture competition
"""

# ============================================================
# Crops
# ============================================================
WHEAT = "WHEAT"
CARROT = "CARROT"
TOMATO = "TOMATO"
STRAWBERRY = "STRAWBERRY"
MELON = "MELON"
CROPS = (WHEAT, CARROT, TOMATO, STRAWBERRY, MELON)

# ============================================================
# Animals
# ============================================================
GOOSE = "GOOSE"
COW = "COW"
SHEEP = "SHEEP"
ANIMALS = (GOOSE, COW, SHEEP)

# ============================================================
# Products
# ============================================================
EGG = "EGG"
MILK = "MILK"
WOOL = "WOOL"
FERTILIZER = "FERTILIZER"
PRODUCTS = (WHEAT, CARROT, TOMATO, STRAWBERRY, MELON, EGG, MILK, WOOL, FERTILIZER)

# ============================================================
# Farmer Actions
# ============================================================
PASS = "PASS"
NORTH = "NORTH"
SOUTH = "SOUTH"
EAST = "EAST"
WEST = "WEST"

PLANT = "PLANT"
WATER = "WATER"
HARVEST = "HARVEST"
FERTILIZE = "FERTILIZE"
DIG = "DIG"

PICKUP = "PICKUP"
DROP = "DROP"
PLACE = "PLACE"

FEED = "FEED"
CARE = "CARE"
COLLECT_FERTILIZER = "COLLECT_FERTILIZER"

BUILD_COOP = "BUILD_COOP"
BUILD_PASTURE = "BUILD_PASTURE"

# ============================================================
# Market Actions
# ============================================================
BUY_SEED = "BUY_SEED"
BUY_ANIMAL = "BUY_ANIMAL"
BUY_PRODUCT = "BUY_PRODUCT"
SELL = "SELL"
HIRE = "HIRE"
BUY_LAND = "BUY_LAND"

# ============================================================
# Tile Kinds
# ============================================================
TILE_EMPTY = "EMPTY"
TILE_LOCKED = "LOCKED"
TILE_PLANT = "PLANT"
TILE_WEED = "WEED"
TILE_COOP = "COOP"
TILE_PASTURE = "PASTURE"

# ============================================================
# Quadrants
# ============================================================
NW = "NW"
NE = "NE"
SW = "SW"
SE = "SE"
QUADRANTS = (NW, NE, SW, SE)

# ============================================================
# Crop Configuration
# ============================================================
CROP_CONFIG = {
    "WHEAT": {
        "seed_cost": 10,
        "base_price": 25,
        "first_yield_day": 2,
        "max_yield_day": 4,
        "max_yield": 6,
        "max_yield_no_fertilizer": 4,
        "is_ongoing": False,
    },
    "CARROT": {
        "seed_cost": 20,
        "base_price": 35,
        "first_yield_day": 2,
        "max_yield_day": 3,
        "max_yield": 4,
        "max_yield_no_fertilizer": 3,
        "is_ongoing": False,
    },
    "TOMATO": {
        "seed_cost": 50,
        "base_price": 60,
        "first_yield_day": 8,
        # P3 (Batch-1): aligned to referee CROPS (was 11). Latent field —
        # no production-path consumer reads max_yield_day.
        "max_yield_day": 8,
        "max_yield": 4,
        "max_yield_no_fertilizer": 4,
        "is_ongoing": True,
    },
    "STRAWBERRY": {
        "seed_cost": 100,
        "base_price": 120,
        "first_yield_day": 10,
        # P3 (Batch-1): aligned to referee CROPS (was 16). Latent field —
        # no production-path consumer reads max_yield_day.
        "max_yield_day": 10,
        "max_yield": 4,
        "max_yield_no_fertilizer": 4,
        "is_ongoing": True,
    },
    "MELON": {
        "seed_cost": 80,
        "base_price": 250,
        "first_yield_day": 10,
        # P3 (Batch-1): aligned to referee CROPS (was 10). Latent field —
        # no production-path consumer reads max_yield_day.
        "max_yield_day": 12,
        "max_yield": 6,
        "max_yield_no_fertilizer": 6,
        "is_ongoing": False,
    },
}

# ============================================================
# Default Configuration
# ============================================================
DEFAULT_BOARD_SIZE = 10
DEFAULT_TURNS_PER_DAY = 24
DEFAULT_EPISODE_STEPS = 720
DEFAULT_STARTING_MONEY = 3000
DEFAULT_SHED_CAPACITY = 100
DEFAULT_MAX_MARKET_ORDERS = 10

# ============================================================
# Board layout (ported verbatim from src/main.py baseline)
# ============================================================
SHED_TILES = [(4, 4), (5, 4), (4, 5), (5, 5)]

COOP_POS = [(0, 0)]