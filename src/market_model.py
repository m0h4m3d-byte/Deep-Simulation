"""
market_model.py - Deterministic market price projection for decision making.

The competition's price function is fully known and deterministic given
inventory, so "prediction" reduces to projecting INVENTORY forward:

    inventory(t+1) = inventory(t) - player_buys - town_drain + player_sales

We reuse the engine's own `market_price` / `_shape` so there is zero drift,
and validate projections against the live simulator in tests.

Usage:
    from src.market_model import MarketModel

    mm = MarketModel.from_obs(obs)
    mm.sell_revenue("MILK", 20)          # exact $ from selling 20 milk now
    mm.project_price("MILK", days=5)     # price if only town drains it
"""

import math

from kaggle_environments.envs.kaggriculture import kaggriculture as K

PRODUCTS = K.PRODUCTS


def _shape(func, x):
    return K._shape(func, x)


class TownDemand:
    """Expected per-day consumption of each product by town center + shops."""

    SHOPS = K.SHOPS  # name -> [products]

    def __init__(self, unlocked_shops=None, day=0):
        self.shops = list(unlocked_shops or [])
        self.day = day

    def daily_drain(self, item, day=None):
        """Expected units/day removed from market inventory at a given day.
        Uses current shops; future unlocks are random draws so we add their
        expectation separately via expected_future_shops()."""
        d = self.day if day is None else day
        drain = 0.0
        # Town center: every 24 turns = once/day, scaled after day 10/20.
        if item != "FERTILIZER":
            mult = 1 if d < 10 else 2 if d < 20 else 4
            drain += mult
        # Shops tick every 4 turns => 6 ticks/day.
        for shop in self.shops:
            products = self.SHOPS[shop]
            mult = 2 if len(products) == 1 else 1
            if item in products:
                drain += 6 * mult
        return drain

    def expected_future_shops_per_day(self, day=None):
        """Expected number of NEW shop instances unlocking per remaining day."""
        d = self.day if day is None else day
        next_day = d + 1
        unlocks_left = max(0, min(K.MAX_SHOP_INSTANCES - len(self.shops),
                                  (30 - next_day) // K.DEFAULT_TOWN_SHOP_UNLOCK_INTERVAL
                                  if hasattr(K, "DEFAULT_TOWN_SHOP_UNLOCK_INTERVAL") else (30 - next_day) // 3))
        return unlocks_left / max(1, 30 - next_day)

    def avg_products_per_shop(self, item):
        """Probability a random new shop demands `item` (incl. 2x weight)."""
        total_weight = 0.0
        hit = 0.0
        for products in self.SHOPS.values():
            total_weight += len(products)
            if item in products:
                hit += 2 if len(products) == 1 else 1
        return hit / total_weight if total_weight else 0.0


class MarketModel:
    """Price/revenue calculator over a snapshot of shared market state."""

    def __init__(self, inventory, params=None, town=None):
        self.inventory = dict(inventory)
        self.params = params or K.MARKET_PARAMS
        self.town = town or TownDemand()

    @classmethod
    def from_obs(cls, obs):
        market = obs["market"]
        town = TownDemand(obs.get("town", {}).get("unlocked_shops") or [], obs["day"])
        return cls(market["inventory"], market.get("params"), town)

    # ------------------------------------------------------------------
    # Exact price math (delegates to the engine)
    # ------------------------------------------------------------------
    def price_at(self, item, inventory):
        return K.market_price(item, int(inventory), self.params)

    @property
    def prices(self):
        return {item: self.price_at(item, inv) for item, inv in self.inventory.items()}

    # ------------------------------------------------------------------
    # Trade evaluation
    # ------------------------------------------------------------------
    def sell_revenue(self, item, n, apply=False):
        """Exact revenue from selling n units one-at-a-time now.
        Sell price quoted at PRE-sell inventory; units sold at $1 floor do not
        raise inventory (engine behavior), so we mirror that."""
        inv = self.inventory[item]
        total = 0
        for _ in range(int(n)):
            p = self.price_at(item, inv)
            total += p
            if p > 1:
                inv += 1
        if apply:
            self.inventory[item] = inv
        return total

    def buy_cost(self, item, n, apply=False):
        """Exact cost of BUY_PRODUCT n units (only WHEAT/FERTILIZER legal).
        Buy price quoted at POST-buy inventory."""
        inv = self.inventory[item]
        total = 0
        for _ in range(int(n)):
            p = self.price_at(item, inv - 1)
            total += p
            inv -= 1
        if apply:
            self.inventory[item] = inv
        return total

    def marginal_price(self, item, n):
        """Average $/unit of selling n units now."""
        return self.sell_revenue(item, n) / max(1, n)

    # ------------------------------------------------------------------
    # Projection
    # ------------------------------------------------------------------
    def project_inventory(self, item, days, sales=0, buys=0, include_expected_unlocks=True):
        """Projected inventory after `days` of town drain and optional trades."""
        inv = float(self.inventory[item]) - sales + buys
        start_day = self.town.day
        for k in range(1, int(days) + 1):
            inv -= self.town.daily_drain(item, start_day + k)
            if include_expected_unlocks:
                rate = self.town.expected_future_shops_per_day(start_day + k)
                inv -= rate * 6 * self.town.avg_products_per_shop(item)
        return inv

    def projected_price(self, item, days, sales=0, buys=0):
        inv = self.project_inventory(item, days, sales, buys)
        return self.price_at(item, inv)

    def hold_vs_sell_now(self, item, n, horizon_days):
        """Compare selling now vs holding `n` units for `horizon_days`.
        Returns (revenue_now, projected_revenue_later, verdict)."""
        rev_now = self.sell_revenue(item, n)
        inv_later = self.project_inventory(item, horizon_days)
        later_model = MarketModel({item: inv_later}, self.params, self.town)
        rev_later = later_model.sell_revenue(item, n)
        verdict = "SELL NOW" if rev_now >= rev_later else "HOLD"
        return rev_now, rev_later, verdict

    # ------------------------------------------------------------------
    # Crop economics (for decision_engine)
    # ------------------------------------------------------------------
    def crop_roi(self, crop, plant_day, watered_daily=True):
        """Expected net $ per tile for one cycle of `crop`, using projected
        harvest-day prices. Conservative: no fertilizer bonus."""
        cd = K.CROPS[crop]
        harvest_day = plant_day + cd["max_yield_day"]
        if harvest_day > 29:
            return -cd["seed"], None  # won't finish before season end
        yield_units = cd["max_yield"] if watered_daily else cd["max_yield_no_fertilizer"]
        price = self.projected_price(crop, harvest_day - self.town.day)
        return yield_units * price - cd["seed"], price


if __name__ == "__main__":
    obs = {
        "day": 0,
        "town": {"unlocked_shops": []},
        "market": {"inventory": {p: 10000 for p in PRODUCTS}},
    }
    mm = MarketModel.from_obs(obs)
    print("prices @I0:", mm.prices["WHEAT"], mm.prices["MELON"])
    print("sell 100 wheat:", mm.sell_revenue("WHEAT", 100))
    print("buy 50 fertilizer:", mm.buy_cost("FERTILIZER", 50))
    print("milk price in 5d:", mm.projected_price("MILK", 5))
