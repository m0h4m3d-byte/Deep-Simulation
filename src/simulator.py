"""
simulator.py - Fast deep-simulation harness over the REAL kaggriculture engine.

Instead of re-implementing game rules (drift risk), this wraps the actual
engine shipped inside kaggle_environments:

    kaggle_environments/envs/kaggriculture/kaggriculture.py

We drive its `interpreter()` directly on lightweight stub objects, bypassing
the heavy kaggle_environments agent-runner / serialization layer. Game rules,
market mechanics, town demand, weeds, RNG streams and turn ordering are
therefore byte-identical to the live competition environment.

Usage:
    from src.simulator import Simulator, evaluate
    from main import Agent

    sim = Simulator(seed=42)
    result = sim.run([Agent(), "pass"])          # {"money": [...], "winner": 0}

CLI:
    python -m src.simulator --seeds 5            # quick sanity run
    python -m src.simulator --seeds 30           # full benchmark
"""

import argparse
import random
import time

from kaggle_environments.envs.kaggriculture import kaggriculture as K


# Defaults mirror kaggriculture.json exactly (note: townCenterSellInterval
# is 24 in the engine spec, not the 12 quoted in the competition overview).
DEFAULT_CONFIG = {
    "episodeSteps": 720,
    "boardSize": 10,
    "startingMoney": 3000,
    "maxMarketOrdersPerTurn": 10,
    "turnsPerDay": 24,
    "shedCapacity": 100,
    "weedSpawnChance": 0.005,
    "townShopUnlockInterval": 3,
    "townShopSellInterval": 4,
    "townCenterSellInterval": 24,
    "farmHandCostMult": 1,
}


class _Configuration(dict):
    """dict that also supports attribute access (engine reads cfg.episodeSteps)."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)


class _EnvStub:
    def __init__(self, configuration, seed):
        self.configuration = configuration
        self.info = {"seed": seed}
        self.done = False


class _Obs:
    pass


class _StateSlot:
    __slots__ = ("observation", "action", "status", "reward")

    def __init__(self):
        self.observation = _Obs()
        self.action = None
        self.status = "ACTIVE"
        self.reward = 0.0


def _pass_agent(obs):
    return {"farmer": ["PASS"], "hands": [], "market": []}


def _random_agent(obs):
    return K.random_agent(obs)


_OPPONENTS = {
    "pass": _pass_agent,
    "random": _random_agent,
}


class Simulator:
    """One deterministic episode of Kaggriculture (720 turns)."""

    def __init__(self, seed=None, config=None):
        cfg = dict(DEFAULT_CONFIG)
        if config:
            cfg.update(config)
        self._seed_in = seed
        cfg["seed"] = seed
        self.config = _Configuration(cfg)
        self.steps_run = 0

    # ------------------------------------------------------------------
    def reset(self):
        seed = self._seed_in
        if seed is None:
            seed = random.randrange(2 ** 31)
        self.seed = seed
        self.env = _EnvStub(_Configuration(self.config), seed)
        self.state = [_StateSlot(), _StateSlot()]
        self.initialized = False
        self.done = False
        self.steps_run = 0
        return self

    # ------------------------------------------------------------------
    def _views(self, step):
        """Per-player observation dicts in the exact format agents expect."""
        obs0 = self.state[0].observation
        privates = [s.observation.private for s in self.state]
        views = []
        for player in range(2):
            views.append({
                "player": player,
                "step": step,
                "day": obs0.day,
                "hour": obs0.hour,
                "farms": obs0.farms,
                "market": obs0.market,
                "town": obs0.town,
                "private": privates[player],
            })
        return views

    def step(self, actions):
        """Feed one turn of actions (list of 2 action dicts) to the engine."""
        if not self.initialized:
            K.interpreter(self.state, self.env)  # triggers _initialize
            self.initialized = True
            return self._views(0)
        for slot, action in zip(self.state, actions):
            slot.action = action
        K.interpreter(self.state, self.env)
        self.steps_run += 1
        step = self.steps_run
        self.state[0].observation.step = step
        if self.state[0].status == "DONE":
            self.env.done = True
            self.done = True
        return self._views(step)

    # ------------------------------------------------------------------
    def run(self, agents, copy_obs=False):
        """Play a full season. `agents` = [agent0, agent1]; each may be a
        callable(obs)->action or one of 'pass'/'random'. Returns final money."""
        import copy as _copy

        resolved = [_OPPONENTS.get(a, a) for a in agents]
        assert all(callable(a) for a in resolved), "agents must be callable or 'pass'/'random'"
        self.reset()
        views = self.step(None)  # initialize
        while not self.done:
            actions = []
            for agent, view in zip(resolved, views):
                obs = _copy.deepcopy(view) if copy_obs else view
                actions.append(agent(obs))
            views = self.step(actions)
        money = [float(f["money"]) for f in self.state[0].observation.farms]
        winner = 0 if money[0] > money[1] else 1 if money[1] > money[0] else None
        return {"money": money, "winner": winner, "steps": self.steps_run, "seed": self.seed}


# ----------------------------------------------------------------------
# Batch evaluation helpers
# ----------------------------------------------------------------------

def evaluate(player0_factory, seeds, opponent="pass"):
    """Run one episode per seed. `player0_factory()` must return a FRESH agent.
    Returns aggregate stats for player 0."""
    results = []
    for seed in seeds:
        agent = player0_factory()
        res = Simulator(seed=seed).run([agent, opponent])
        results.append(res["money"][0])
    n = len(results)
    stats = {
        "seeds": list(seeds),
        "scores": results,
        "mean": sum(results) / n,
        "best": max(results),
        "worst": min(results),
    }
    return stats


def summarize(label, stats):
    print(f"\n=== {label} ===")
    print(f"  seeds : {len(stats['seeds'])}")
    print(f"  mean  : ${stats['mean']:,.0f}")
    print(f"  best  : ${stats['best']:,.0f}")
    print(f"  worst : ${stats['worst']:,.0f}")


# ----------------------------------------------------------------------
# Parity check against the full kaggle_environments pipeline
# ----------------------------------------------------------------------

def parity_check(seeds, opponent="pass", verbose=True):
    """Run identical episodes through this fast harness AND the official
    kaggle_environments runner; report max absolute money difference."""
    from kaggle_environments import make
    from main import Agent

    opp_map = {"pass": "pass", "random": "random"}
    opp_name = opp_map[opponent]
    worst_diff = 0.0
    rows = []
    for seed in seeds:
        # Fast path
        res_fast = Simulator(seed=seed).run([Agent(), _OPPONENTS[opponent]])
        # Official path
        env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed}, debug=False)
        env.run(["main.py", opp_name])
        official = [float(s.reward) for s in env.steps[-1]]
        diff = abs(res_fast["money"][0] - official[0])
        worst_diff = max(worst_diff, diff)
        rows.append((seed, res_fast["money"][0], official[0], diff))
        if verbose:
            status = "OK " if diff == 0 else "DIFF"
            print(f"  [{status}] seed={seed:>3}  fast=${res_fast['money'][0]:,.0f}  "
                  f"official=${official[0]:,.0f}  |diff|={diff:,.0f}")
    return worst_diff, rows


# ----------------------------------------------------------------------
# Benchmark our production agent
# ----------------------------------------------------------------------

def benchmark(seeds, opponent="pass"):
    from main import Agent
    t0 = time.perf_counter()
    stats = evaluate(lambda: Agent(), seeds, opponent=opponent)
    elapsed = time.perf_counter() - t0
    summarize(f"Our agent vs {opponent} ({len(seeds)} seeds)", stats)
    print(f"  time  : {elapsed:.1f}s total, {elapsed/len(seeds)*1000:.0f} ms/episode "
          f"({len(seeds)/elapsed:.2f} eps/sec)")
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DeepSim fast simulator")
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--parity", action="store_true", help="verify vs official runner")
    parser.add_argument("--opponent", choices=["pass", "random"], default="pass")
    args = parser.parse_args()

    seed_list = list(range(args.seeds))

    if args.parity:
        print("Parity check (fast harness vs official kaggle_environments):")
        worst, _ = parity_check(seed_list, opponent=args.opponent)
        verdict = "PERFECT PARITY" if worst == 0 else f"MISMATCH (worst |diff| = ${worst:,.0f})"
        print(f"  ==> {verdict}")

    benchmark(seed_list, opponent=args.opponent)
