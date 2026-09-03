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

# Re-export single source of truth from config.py to prevent drift.
from src.config import CROP_CONFIG, SHED_TILES, COOP_POS  # noqa: F401

DEFAULT_BOARD_SIZE = 10
DEFAULT_TURNS_PER_DAY = 24
DEFAULT_EPISODE_STEPS = 720
DEFAULT_STARTING_MONEY = 3000
DEFAULT_SHED_CAPACITY = 100
DEFAULT_MAX_MARKET_ORDERS = 10