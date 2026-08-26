"""
ladder_simulator.py - N-player DeepSim that reproduces real ladder market pressure.

The installed kaggriculture engine hardcodes 2 players in _process_market
(`quoted = [None, None]`). Ladder games are 2-player, but when 2 competent
farmers both flood the SAME shared market the dilution is only ~2x. To
stress-test our agent we simulate 3-4 clones sharing the market — the
prices finally crash to $1 exactly as seen on the ladder (avg min MILK $89
in our last 26 games, solo sim never below $160).

We monkey-patch the engine once at import so existing Simulator code plus
any future kaggle_environments upgrades keep working. Use:

    from src.ladder_simulator import LadderSimulator
    LadderSimulator(n_players=4).run_n([Agent(), Agent(), Agent(), Agent()])
"""

from kaggle_environments.envs.kaggriculture import kaggriculture as K

# ----------------------------------------------------------------------
# One-time patch: generalize _process_market to N players.
# ----------------------------------------------------------------------
if not getattr(K, "_patched_for_N", False):
    _orig_pm = K._process_market

    def _patched_process_market(state, env):
        # Same body as original but with dynamic quoted length.
        import math as _m  # keep local
        obs0 = state[0].observation
        market = obs0.market
        farms = obs0.farms
        privates = [s.observation.private for s in state]
        board_size = int(K.get(env.configuration, "boardSize", 10))
        max_orders = max(1, int(K.get(env.configuration, "maxMarketOrdersPerTurn", 10)))
        hire_mult = int(K.get(env.configuration, "farmHandCostMult", K.FARM_HAND_COST_MULT))
        shed_capacity = int(K.get(env.configuration, "shedCapacity", 100))
        n = len(state)

        queues = []
        for s in state:
            action = s.action if isinstance(s.action, dict) else {}
            m = action.get("market", []) if isinstance(action, dict) else []
            q = list(m) if isinstance(m, list) else []
            queues.append(q[:max_orders])

        max_len = max((len(q) for q in queues), default=0)
        for i in range(max_len):
            order_states = []
            for player_id, q in enumerate(queues):
                ostate = None
                if i < len(q):
                    ostate = K._parse_order(q[i])
                order_states.append(ostate)

            for player_id, ostate in enumerate(order_states):
                if ostate is None:
                    continue
                op = ostate["type"]
                if op == "HIRE":
                    K._do_hire(farms[player_id], privates[player_id], board_size, hire_mult)
                    order_states[player_id] = None
                elif op == "BUY_LAND":
                    K._do_buy_land(farms[player_id], board_size)
                    order_states[player_id] = None

            idx_esc = 0
            while True:
                idx_esc += 1
                if idx_esc >= 100_000:
                    print("WARNING: kaggriculture market loop exceeded 100k iterations; aborting")
                    break
                quoted = [None] * n
                for player_id, ostate in enumerate(order_states):
                    if ostate is None or ostate["remaining"] <= 0:
                        continue
                    op = ostate["type"]
                    item = ostate["item"]
                    if op == "SELL" and item in K.PRODUCTS:
                        quoted[player_id] = ("SELL", item, K.market_price(item, market["inventory"][item], market.get("params")), ostate)
                    elif op == "BUY_PRODUCT" and item in ("WHEAT", "FERTILIZER"):
                        quoted[player_id] = ("BUY_PRODUCT", item, K.market_price(item, market["inventory"][item] - 1, market.get("params")), ostate)
                    elif op == "BUY_SEED" and item in K.CROPS:
                        quoted[player_id] = ("BUY_SEED", item, K.CROPS[item]["seed"], ostate)
                    elif op == "BUY_ANIMAL" and item in K.ANIMALS:
                        quoted[player_id] = ("BUY_ANIMAL", item, K.ANIMALS[item]["cost"], ostate)
                    else:
                        order_states[player_id] = None

                if all(q is None for q in quoted):
                    break

                committed_any = False
                for player_id, q in enumerate(quoted):
                    if q is None:
                        continue
                    op, item, price, ostate = q
                    ok = K._commit_unit(op, item, price, farms[player_id], privates[player_id], market, shed_capacity)
                    if ok:
                        ostate["remaining"] -= 1
                        committed_any = True
                    else:
                        order_states[player_id] = None

                if not committed_any:
                    break

            K._refresh_prices(market)

    K._process_market = _patched_process_market
    K._patched_for_N = True

# ----------------------------------------------------------------------
# N-player simulator harness (extends the 2-player Simulator pattern).
# ----------------------------------------------------------------------
from src.simulator import Simulator as _Base  # noqa: E402  (after patch)
import copy as _copy  # noqa: E402


class LadderSimulator:
    """Shared-market N-player season. Each of the N agents sees the SAME
    market/town and competes for price. Use n_players=4 to reproduce ladder
    dilution (empirically: avg min MILK ~$30 with 4 clones)."""

    def __init__(self, seed=None, config=None, n_players=4):
        self.n = n_players
        self._base = _Base(seed=seed, config=config)
        self._base.n_players = n_players  # hint for repr

    def run_n(self, agents):
        """agents: list of N callables(obs)->action. Returns {money, winner}."""
        assert len(agents) == self.n, f"need {self.n} agents, got {len(agents)}"
        # Build N-slot state via the patched engine
        from src.simulator import _Configuration, _EnvStub, _Obs, _StateSlot
        import random as _rnd

        # Replicate Simulator.reset but for N players
        seed = self._base._seed_in
        if seed is None:
            seed = _rnd.randrange(2 ** 31)
        self._base.seed = seed
        cfg = _Configuration(self._base.config)
        env = _EnvStub(cfg, seed)
        state = [_StateSlot() for _ in range(self.n)]
        done = False

        # Initialize (hasattr check triggers _initialize on first interpreter call)
        K.interpreter(state, env)
        # After init, state[0].observation holds shared farms/market/town

        def views_at(step):
            obs0 = state[0].observation
            return [
                {"player": p, "step": step, "day": obs0.day, "hour": obs0.hour,
                 "farms": obs0.farms, "market": obs0.market, "town": obs0.town,
                 "private": state[p].observation.private}
                for p in range(self.n)
            ]

        step = 0
        state[0].observation.step = 0
        views = views_at(0)
        while True:
            actions = [agents[p](views[p]) for p in range(self.n)]
            for slot, a in zip(state, actions):
                slot.action = a
            K.interpreter(state, env)
            step += 1
            state[0].observation.step = step
            if state[0].status == "DONE":
                env.done = True
                break
            views = views_at(step)
            if step >= 720:
                break

        money = [float(f["money"]) for f in state[0].observation.farms]
        winner = max(range(self.n), key=lambda i: money[i])
        if len(set(money)) < self.n:  # tie handling not critical
            winner = None if money.count(max(money)) > 1 else winner
        return {"money": money, "winner": winner, "seed": seed}
