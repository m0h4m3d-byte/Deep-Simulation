"""
decision_engine.py - Evaluates candidate decisions with the market model.

Components:
    SellAdvisor   - sell-now vs hold, per product, using price projection
    CropAdvisor   - ranks crops by projected ROI for the current day
    AdaptiveAgent - wraps the production agent and replaces its SELL orders
                    with market-model-optimal ones (experiment vehicle;
                    production src/ is never modified)

Usage:
    from src.decision_engine import AdaptiveAgent
    stats = evaluate(AdaptiveAgent, range(30), opponent="pass")
"""

from src.market_model import MarketModel, TownDemand
from kaggle_environments.envs.kaggriculture import kaggriculture as K_CROPS_HOST

K_CROPS = K_CROPS_HOST.CROPS

# Products we may strategically hold back (perishables excluded).
HOLDABLE = {"MILK", "WOOL", "WHEAT", "CARROT", "EGG", "TOMATO", "STRAWBERRY", "MELON", "FERTILIZER"}
MIN_ORDER_UNITS = 5      # don't waste a market slot on tiny piles
DEFAULT_HORIZON = 4      # days to project when comparing hold vs sell


# Typical dump size per crop when OUR field flushes. Volume crops (melon)
# crater their own price; pricing the tranche marginally captures that.
CROP_TRANCHE = {"WHEAT": 60, "CARROT": 30, "TOMATO": 15,
                "STRAWBERRY": 15, "MELON": 30}


def project_harvest_prices(market_ctx):
    """{crop: projected price at its typical harvest day} for planting today."""
    day = market_ctx["day"]
    mm = MarketModel(market_ctx["inventory"],
                     town=TownDemand(market_ctx.get("shops") or [], day))
    out = {}
    for crop, cd in K_CROPS.items():
        h = day + cd["max_yield_day"]
        if h <= 29:
            out[crop] = mm.projected_price(crop, h - day)
    return out


def crop_ranking_from_ctx(market_ctx):
    """[(crop, roi)] sorted best-first by projected net $/tile for planting today.

    Uses the MARGINAL price of our typical flush tranche (not the flat
    snapshot price) so volume crops don't look better than they are, plus
    per-day normalization by occupancy so ongoing crops compare fairly
    against one-time ones.
    """
    day = market_ctx["day"]
    mm = MarketModel(market_ctx["inventory"],
                     town=TownDemand(market_ctx.get("shops") or [], day))
    scored = []
    for crop in ("MELON", "STRAWBERRY", "WHEAT", "CARROT", "TOMATO"):
        cd = K_CROPS[crop]
        harvest_day = day + cd["max_yield_day"]
        if harvest_day > 29 or (day + cd["first_yield_day"]) > 29:
            scored.append((-10 ** 9, crop))
            continue
        tranche = CROP_TRANCHE[crop]
        inv_h = mm.project_inventory(crop, harvest_day - day)
        later = MarketModel({crop: inv_h}, mm.params, mm.town)
        avg_price = later.sell_revenue(crop, tranche) / tranche
        # Ongoing crops produce their max_yield across several productions;
        # one-time crops yield once. Occupancy days differ -> normalize /tile/day.
        occupancy = (17 if crop == "STRAWBERRY" else
                     12 if crop == "TOMATO" else
                     cd["max_yield_day"] + 1)
        roi_per_day = (cd["max_yield"] * avg_price - cd["seed"]) / occupancy
        scored.append((roi_per_day, crop))
    scored.sort(reverse=True)
    return [(crop, roi) for roi, crop in scored]


class SellAdvisor:
    """Chooses the best dump-day per product: sell now, or hold until day d*.

    For each candidate offset d in [0 .. max_horizon] we project inventory
    forward d days (town drain only) and compute the revenue of dumping the
    whole pile on that day, discounted by REINVEST_RATE per day — early cash
    compounds into seeds/animals, so future revenue must beat that growth.
    """

    def __init__(self, horizon_days=DEFAULT_HORIZON, reinvest_rate=0.03,
                 min_hold_edge=1.05):
        self.horizon = horizon_days
        self.reinvest_rate = reinvest_rate
        # Hold only when the projected discounted gain clears this multiple
        # of sell-now revenue. Our drain projection ignores OUR OWN future
        # sales (which raise inventory and depress prices), so demanding a
        # healthy edge compensates for that systematic optimism.
        self.min_hold_edge = min_hold_edge

    def advise(self, obs):
        day, hour = obs["day"], obs["hour"]
        days_left = 29 - day
        mm = MarketModel.from_obs(obs)
        shed = obs["private"]["shed"]
        # Season ending: dump everything regardless of projections.
        force_sell = days_left <= 1
        plan = {}
        for item, n in shed.items():
            if item not in HOLDABLE or n <= 0:
                continue
            n = int(n)
            if force_sell or n < MIN_ORDER_UNITS:
                plan[item] = ("SELL", n)
                continue
            max_d = min(self.horizon, days_left)
            rev_now = mm.sell_revenue(item, n)
            best_score, best_d = -1.0, 0
            for d in range(1, max_d + 1):
                inv_d = mm.project_inventory(item, d)
                later = MarketModel({item: inv_d}, mm.params, mm.town)
                rev = later.sell_revenue(item, n)
                score = rev * ((1 - self.reinvest_rate) ** d)
                if score > best_score:
                    best_score, best_d = score, d
            if best_score >= rev_now * self.min_hold_edge:
                plan[item] = ("HOLD", n)
            else:
                plan[item] = ("SELL", n)
        return plan


class CropAdvisor:
    def __init__(self):
        pass

    def rank(self, obs):
        """Crops ranked best-first by projected net $/tile."""
        mm = MarketModel.from_obs(obs)
        day = obs["day"]
        scored = []
        for crop in ("MELON", "STRAWBERRY", "WHEAT", "CARROT", "TOMATO"):
            roi, price = mm.crop_roi(crop, day)
            scored.append((roi, crop, price))
        scored.sort(reverse=True)
        return scored


class DecisionEngine:
    def __init__(self, sell_advisor=None):
        self.sell = sell_advisor or SellAdvisor()
        self.crop = CropAdvisor()

    def review(self, obs):
        return {
            "sell_plan": self.sell.advise(obs),
            "crop_rank": self.crop.rank(obs),
        }


class AdaptiveAgent:
    """Wraps any agent callable.

    mode="replace": swaps its SELL orders for model-optimal ones.
    mode="veto"   : keeps ALL original orders; only suppresses a product's
                    sell when the model says HOLD *and* the shed has plenty
                    of headroom (never risks overflow discards).
    """

    SHED_SAFE_LIMIT = 55   # total sellable units below which holding is safe
    # Crash-prone premium goods: the production agent's tuned bull/bail
    # gates already handle these better than our naive drain projection.
    VETO_BLACKLIST = {"MILK", "MELON", "STRAWBERRY"}

    def __init__(self, inner_factory=None, engine=None, mode="veto"):
        from main import Agent as ProdAgent
        self._inner_factory = inner_factory or ProdAgent
        self.engine = engine or DecisionEngine()
        self.mode = mode
        self._hold_baseline = {}   # item -> price when we first started holding

    def __call__(self, obs):
        inner_agent = getattr(self, "_inner", None)
        if inner_agent is None or obs.get("step", 0) == 0:
            self._inner = self._inner_factory()
            inner_agent = self._inner
            self._hold_baseline = {}
        action = inner_agent(obs)
        if self.mode == "replace":
            return self._rewrite_sells(action, obs)
        return self._veto_sells(action, obs)

    def _veto_sells(self, action, obs):
        try:
            plan = self.engine.sell.advise(obs)
        except Exception:
            return action
        shed = obs["private"]["shed"]
        sellable = ("MILK", "WOOL", "EGG", "FERTILIZER", "MELON",
                    "STRAWBERRY", "WHEAT", "CARROT", "TOMATO")
        shed_load = sum(shed.get(p, 0) for p in sellable)
        if shed_load > self.SHED_SAFE_LIMIT:
            return action  # overflow risk: never hold
        prices = obs["market"]["prices"]
        market = [list(o) for o in (action.get("market") or [])]
        kept = []
        for o in market:
            if o and o[0] == "SELL" and plan.get(o[1], ("SELL",))[0] == "HOLD":
                item = o[1]
                if item in self.VETO_BLACKLIST:
                    kept.append(o)
                    continue
                # Bail: if the live price slid >=10% since we began holding,
                # our drain projection was wrong -> release the veto.
                base = self._hold_baseline.setdefault(item, prices.get(item, 0))
                if prices.get(item, 0) < 0.90 * base:
                    self._hold_baseline[item] = prices.get(item, 0)
                    kept.append(o)
                    continue
                kept.append(None)  # vetoed
            else:
                kept.append(o)
        final = [o for o in kept if o is not None]
        if len(final) == len(market):
            return action
        action = dict(action)
        action["market"] = final[:10]
        return action

    def _rewrite_sells(self, action, obs):
        try:
            plan = self.engine.sell.advise(obs)
        except Exception:
            return action
        market = [list(o) for o in (action.get("market") or [])]
        kept = []
        for o in market:
            # Keep non-SELL orders and SELLs for items the model doesn't manage.
            if o and o[0] == "SELL" and o[1] in plan:
                continue
            kept.append(o)
        shed = obs["private"]["shed"]
        for item, (verdict, n) in plan.items():
            available = min(n, shed.get(item, 0))
            if verdict == "SELL" and available > 0:
                kept.append(["SELL", item, available])
        action = dict(action)
        action["market"] = kept[:10]
        return action


if __name__ == "__main__":
    obs = {
        "day": 12,
        "hour": 5,
        "town": {"unlocked_shops": ["BAKERY", "PIZZA_SHOP"]},
        "market": {"inventory": {"MILK": 9900, "WOOL": 10100, "WHEAT": 9950,
                                 "CARROT": 10000, "EGG": 10000, "TOMATO": 10000,
                                 "STRAWBERRY": 10000, "MELON": 10000, "FERTILIZER": 10000}},
        "private": {"shed": {"MILK": 30, "WOOL": 25, "WHEAT": 80}},
    }
    eng = DecisionEngine()
    review = eng.review(obs)
    print("sell plan:", review["sell_plan"])
    print("crop rank:", [(c, f"${roi:,.0f}") for roi, c, _ in review["crop_rank"]])
