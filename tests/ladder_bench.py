"""
tests/ladder_bench.py - Heterogeneous challenger bench for DeepSim.

Pits our production agent against clones of the ladder archetypes that
actually beat us, each running its OWN plan inside the same episode
(per-turn plan swapping keeps production code untouched):

    kshitiz   : strawberry-heavy, sheep-lean, near-zero wheat (+$21k vs us)
    aibaba    : pure wheat farm, small diversified herd   (+$21k vs us)
    dairy     : cow-heavy mirror of our old self
    leader ghosts: recorded openings from KAWASHIGI / Ryo / tetsuya

    python -m tests.ladder_bench --seeds 8
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class PlanSwappedAgent:
    """Wraps an agent so it sees `overrides` in src.economy.PLAN only during
    its own turn. Sequential turns make this safe."""

    def __init__(self, inner, overrides):
        self.inner = inner
        self.overrides = overrides

    def __call__(self, obs):
        import src.economy as E
        saved = dict(E.PLAN)
        E.PLAN.update(self.overrides)
        try:
            return self.inner(obs)
        finally:
            E.PLAN.clear()
            E.PLAN.update(saved)

    def reset(self):
        if hasattr(self.inner, "reset"):
            self.inner.reset()


CHALLENGERS = {
    # name -> plan overrides (PLAN keys: COW SHEEP GOOSE MELON STRAWBERRY WHEAT)
    "kshitiz":  {"COW": 4,  "SHEEP": 6, "GOOSE": 0, "WHEAT": 20,
                 "STRAWBERRY": 60, "MELON": 12},
    "aibaba":   {"COW": 5,  "SHEEP": 3, "GOOSE": 2, "WHEAT": 200,
                 "STRAWBERRY": 10, "MELON": 8},
    "dairy":    {"COW": 15, "SHEEP": 3, "GOOSE": 0, "WHEAT": 140,
                 "STRAWBERRY": 45, "MELON": 12},
    "strawmax": {"COW": 2,  "SHEEP": 8, "GOOSE": 0, "WHEAT": 40,
                 "STRAWBERRY": 80, "MELON": 15},
}


def run_bench(seeds, names=None):
    from src.simulator import Simulator
    from main import Agent
    import src.economy as E

    # Lock OUR plan to current tree defaults regardless of challenger swaps.
    our_plan = dict(E.PLAN)

    class OurLockedAgent(Agent):
        def __call__(self, obs):
            saved = dict(E.PLAN)
            E.PLAN.update(our_plan)
            try:
                return super().__call__(obs)
            finally:
                E.PLAN.clear()
                E.PLAN.update(saved)

    names = names or list(CHALLENGERS)
    print(f"our plan: {{k: our_plan[k] for k in ('COW','SHEEP','WHEAT','STRAWBERRY')}}"
          .format())if False else print("our plan:", {k: our_plan[k] for k in ("COW", "SHEEP", "WHEAT", "STRAWBERRY")})
    total_w = total_g = 0
    results = {}
    for name in names:
        overrides = CHALLENGERS[name]
        w = l = t = 0
        mine_all, opp_all = [], []
        for s in seeds:
            challenger_inner = Agent()
            challenger = PlanSwappedAgent(challenger_inner, overrides)
            me = OurLockedAgent()
            sim = Simulator(seed=s).reset()
            views = sim.step(None)
            while not sim.done:
                acts = [me(views[0]), challenger(views[1])]
                views = sim.step(acts)
            m0 = float(sim.state[0].observation.farms[0]["money"])
            m1 = float(sim.state[0].observation.farms[1]["money"])
            mine_all.append(m0)
            opp_all.append(m1)
            if m0 > m1:
                w += 1
            elif m0 < m1:
                l += 1
            else:
                t += 1
        total_w += w
        total_g += len(seeds)
        results[name] = {"winrate": w / len(seeds),
                         "mine": sum(mine_all) / len(mine_all),
                         "opp": sum(opp_all) / len(opp_all)}
        print(f"{name:<10} {w}W-{l}L-{t}T  our avg ${sum(mine_all)/len(mine_all):,.0f} "
              f"vs theirs ${sum(opp_all)/len(opp_all):,.0f}")
    print(f"\nTOTAL: {total_w}/{total_g} wins "
          f"({100*total_w/max(1,total_g):.0f}% winrate)")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--names", nargs="*", default=None)
    args = parser.parse_args()
    run_bench(list(range(args.seeds)), args.names)
