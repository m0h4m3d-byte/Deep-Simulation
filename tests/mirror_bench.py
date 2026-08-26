"""
tests/mirror_bench.py - Mirror-match benchmarks: our agent vs ITSELF.

Solo ("pass"-opponent) benchmarks flatter us: nobody else sells into the
shared market, so town drain lifts prices monotonically and milk never
crashes. On the ladder, several competent farmers dump into the SAME market
— that is what killed our cow-heavy builds (P(MILK) $185 -> $1).

Mirror matches reproduce this: two copies of our agent compete, both flood
milk/wheat/fertilizer, and the shared-market dynamics finally look like the
ladder. Use it to A/B configs UNDER PRESSURE.

    python -m tests.mirror_bench --seeds 20
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run_mirror(seeds, label=""):
    """Fresh Agent instances both sides; returns (our_scores, opp_scores, stats)."""
    from src.simulator import Simulator
    from main import Agent

    ours, opps, milk_min, wins = [], [], [], 0
    for s in seeds:
        sim = Simulator(seed=s).reset()
        a0, a1 = Agent(), Agent()
        views = sim.step(None)
        min_milk = None
        while not sim.done:
            acts = [a0(views[0]), a1(views[1])]
            views = sim.step(acts)
            if views[0]["hour"] == 0:
                p = views[0]["market"]["prices"]["MILK"]
                min_milk = p if min_milk is None else min(min_milk, p)
        m0 = float(sim.state[0].observation.farms[0]["money"])
        m1 = float(sim.state[0].observation.farms[1]["money"])
        ours.append(m0)
        opps.append(m1)
        milk_min.append(min_milk or 0)
        wins += m0 > m1
    n = len(seeds)
    print(f"[{label}] {n} mirror games: p0 mean ${sum(ours)/n:,.0f} "
          f"(min ${min(ours):,.0f} max ${max(ours):,.0f}) | p0 winrate {wins}/{n} | "
          f"avg min P(MILK) ${sum(milk_min)/n:,.0f}")
    return ours, opps, {"mean": sum(ours)/n, "winrate": wins/n, "minmilk": sum(milk_min)/n}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=10)
    args = parser.parse_args()
    seeds = list(range(args.seeds))

    # Current defaults (whatever the tree holds) under mirror pressure.
    import importlib
    import src.economy as E
    importlib.reload(E)
    print("PLAN:", {k: E.PLAN[k] for k in ("COW", "SHEEP", "WHEAT", "STRAWBERRY")})
    run_mirror(seeds, "current tree")


if __name__ == "__main__":
    main()
