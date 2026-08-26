"""
main.py - Kaggriculture agent: thin wiring layer over the modular port.

Production agent modules:
    src/constants.py - game constants + board layout
    src/economy.py   - MarketEngine (all market orders) + tunables
    src/strategy.py  - day-phase gates
    src/planner.py   - FarmPlanner (job queue + per-unit dispatch)

Equivalence with the proven baseline behavior is enforced at runtime by the
parity suites in tests/ (frozen oracle: tests/monolith_ref.py):
    market, strategy, navigation, and the full-pipeline planner replay.
Any drift of the modules vs the oracle fails those tests loudly.

Kaggle packaging: a single-file submission needs this module's logic
bundled with its src/ package (see docs/AGENTS.md).
"""

from src.economy import MarketEngine
from src.planner import FarmPlanner
from src.autonomous import AutonomousBrain

_brain = AutonomousBrain()


class Agent:
    """Parses observations and delegates to the modular engines."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.day = 0
        self.hour = 0
        self.market = MarketEngine()
        self.planner = FarmPlanner()

    # Live views kept for introspection / regression tests.
    @property
    def ordered_today(self):
        return self.market.ordered_today

    @property
    def sold_today(self):
        return self.market.sold_today

    @property
    def animals_ordered(self):
        return self.market.animals_ordered

    @property
    def unit_task(self):
        return self.planner.unit_task

    def __call__(self, obs):
        if obs.get("step", 0) == 0:
            self.reset()
        day = obs.get("day", 0)
        self.hour = obs.get("hour", 0)
        player = obs["player"]
        me = obs["farms"][player]
        private = obs["private"]
        market = obs["market"]
        money = me["money"]
        prices = market["prices"]
        shed = private["shed"]
        seeds = private["seeds"]
        tiles = me["tiles"]
        units = [list(me["farmer"])] + [list(h) for h in me["hands"]]
        invs = private["inventories"]

        orders = self.market.build_orders(day, self.hour, me, shed, seeds, prices, money, invs,
                                          unlocked_shops=list((obs.get("town") or {}).get("unlocked_shops") or []))
        market_ctx = {
            "day": day,
            "prices": prices,
            "inventory": market["inventory"],
            "shops": list((obs.get("town") or {}).get("unlocked_shops") or []),
            "milk_crash": getattr(self.market, "milk_crash_active", False),
        }
        # Autonomous unified allocator — re-weights PLAN in place each turn
        try:
            _brain.apply(obs)
        except Exception:
            pass
        self.planner.on_day(day)
        jobs = self.planner.collect_jobs(day, tiles, shed, seeds, invs,
                                         self.market.animals_ordered,
                                         market_ctx=market_ctx)
        # Autonomous hands: hire extra when watering is bottleneck
        try:
            pending_water = sum(1 for j in jobs if j[1] == "WATER")
            extra = _brain.extra_hands_needed(obs, pending_water, len(units) - 1)
            for _ in range(extra):
                if len(orders) < 10:
                    orders.append(["HIRE"])
        except Exception:
            pass
        actions = []
        used_jobs = set()
        for u_idx, pos in enumerate(units):
            inv = invs[u_idx] if u_idx < len(invs) else {}
            actions.append(self.planner.unit_action(pos, u_idx, jobs, used_jobs, inv, shed))
        return {"farmer": actions[0], "hands": actions[1:], "market": orders}


agent = Agent()


def agent_function(obs):
    return agent(obs)