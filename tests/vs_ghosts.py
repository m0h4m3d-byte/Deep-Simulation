"""
Benchmark our production agent against leader "ghost" opponents.

    python -m tests.vs_ghosts --seeds 5
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.simulator import Simulator  # noqa: E402
from src.opponent_model import GhostOpponent, LEADERS  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=5)
    args = parser.parse_args()
    seeds = list(range(args.seeds))

    from main import Agent

    print(f"{'ghost':<18} {'side':>4} {'mean':>9} {'best':>9} {'worst':>9} {'wins':>6}")
    for name in LEADERS:
        for side in (0, 1):
            scores, wins = [], 0
            for s in seeds:
                if side == 0:
                    r = Simulator(seed=s).run([GhostOpponent(LEADERS[name], 0), Agent()])
                    mine, won = r["money"][1], r["winner"] == 1
                else:
                    r = Simulator(seed=s).run([Agent(), GhostOpponent(LEADERS[name], 1)])
                    mine, won = r["money"][0], r["winner"] == 0
                scores.append(mine)
                wins += won
            print(f"{name:<18} {side:>4} {sum(scores)/len(scores):>9,.0f} "
                  f"{max(scores):>9,.0f} {min(scores):>9,.0f} {wins:>3}/{len(seeds)}")


if __name__ == "__main__":
    main()
