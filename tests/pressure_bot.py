"""
tests/pressure_bot.py - A ladder-like sparring opponent for DeepSim.

Mimics the observed behavior of mid-tier ladder agents that beat us:
cow-heavy herd, aggressive daily liquidation of everything harvested,
early land expansion. Its constant SELLing floods the shared market,
reproducing the price suppression missing from solo ("pass") benchmarks.

Usage:
    python -m tests.pressure_bot            # benchmark vs PressureBot
    from tests.pressure_bot import PressureBot
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class PressureBot:
    """Cow-heavy farmer that dumps its whole shed every turn."""

    SELLABLE = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
                "EGG", "MILK", "WOOL", "FERTILIZER")

    def __init__(self, cow_budget=10, sheep_budget=4):
        self.cow_budget = cow_budget
        self.sheep_budget = sheep_budget
        self.bought_cows = 0
        self.bought_sheep = 0
        self.land_bought = False

    def reset(self):
        self.__init__(self.cow_budget, self.sheep_budget)

    def _pens(self, tiles):
        return [(x, y) for y in range(10) for x in range(10)
                if isinstance(tiles[y][x], dict) and "animal" not in tiles[y][x]
                and tiles[y][x] != "LOCKED"]

    def __call__(self, obs):
        step = obs.get("step", 0)
        if step == 0:
            self.reset()
        day = obs["day"]
        me = obs["farms"][obs["player"]]
        priv = obs["private"]
        shed = priv["shed"]
        tiles = me["tiles"]

        # Simple state machine per unit: farmer tends animals/crops nearby,
        # hands harvest-and-haul. We keep it crude — the point is MARKET
        # PRESSURE (volume of sells), not playing well.
        farmer_ops = ["PASS"]
        fx, fy = me["farmer"]
        tile = tiles[fy][fx]
        if isinstance(tile, dict):
            if tile.get("kind") == "PLANT":
                cd_ready = tile.get("yield_units", 0) > 0
                if cd_ready:
                    farmer_ops = ["HARVEST"]
                elif not tile.get("watered_today"):
                    farmer_ops = ["WATER"]
            elif tile.get("kind") == "WEED":
                farmer_ops = ["DIG"]
            elif "animal" in tile:
                if not tile.get("fed_today"):
                    farmer_ops = ["FEED"]
                elif tile.get("yield_units", 0) > 0:
                    farmer_ops = ["HARVEST"]
                elif not tile.get("cared_today"):
                    farmer_ops = ["CARE"]
        # shed-adjacent deposit
        if (fx, fy) in ((4, 4), (5, 4), (4, 5), (5, 5)) and any(
                v > 0 for k, v in priv["inventories"][0].items()):
            farmer_ops = ["DROP"]

        market = []
        # animals: buy up to budget over days 0-10
        if day <= 10:
            cows_have = sum(1 for row in tiles for t in row
                            if isinstance(t, dict) and t.get("animal") == "COW")
            sheep_have = sum(1 for row in tiles for t in row
                             if isinstance(t, dict) and t.get("animal") == "SHEEP")
            unplaced_cow = sum(1 for row in tiles for t in row
                               if isinstance(t, dict) and t.get("animal") == "COW")
            if cows_have < self.cow_budget and me["money"] > 800:
                market.append(["BUY_ANIMAL", "COW", 1])
            elif sheep_have < self.sheep_budget and me["money"] > 900:
                market.append(["BUY_ANIMAL", "SHEEP", 1])
        # land expansion days 6-12
        if 6 <= day <= 12 and not self.land_bought and me["money"] > 2500:
            market.append(["BUY_LAND"])
            self.land_bought = True
        # hire help every day while affordable
        if me["money"] > 60 and day >= 1:
            market.append(["HIRE"])
        # dump everything sellable, always — this is the pressure part
        for item in self.SELLABLE:
            n = shed.get(item, 0)
            reserve = 6 if item == "WHEAT" else 0  # keep some feed wheat
            if item == "WHEAT":
                animals = sum(1 for row in tiles for t in row
                              if isinstance(t, dict) and t.get("animal"))
                reserve = max(4, animals)
            if n > reserve:
                market.append(["SELL", item, n - reserve])
        # buy seeds to keep planting
        if day <= 22:
            seeds = priv["seeds"]
            if seeds.get("STRAWBERRY", 0) < 8 and me["money"] > 300:
                market.append(["BUY_SEED", "STRAWBERRY", 4])
            if seeds.get("WHEAT", 0) < 6 and me["money"] > 120:
                market.append(["BUY_SEED", "WHEAT", 6])
            if day <= 13 and seeds.get("MELON", 0) < 4 and me["money"] > 200:
                market.append(["BUY_SEED", "MELON", 3])

        return {"farmer": farmer_ops, "hands": [], "market": market[:10]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=10)
    args = parser.parse_args()

    from src.simulator import evaluate, summarize
    from main import Agent

    factory = lambda: PressureBot()
    st_ours = evaluate(lambda: Agent(), range(args.seeds), opponent=factory)
    summarize(f"v18-default agent vs PressureBot ({args.seeds} seeds)", st_ours)
    wins = sum(1 for s in st_ours["scores"])
    st_bot = evaluate(factory, range(args.seeds), opponent=lambda: Agent())
    print("(PressureBot as p0 scores shown above are OUR side)")


if __name__ == "__main__":
    main()
