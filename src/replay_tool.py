"""
src/replay_tool.py - Replay a ladder episode inside DeepSim and compare money.

Re-runs the SAME seed with the SAME opponent ghost and checks that final
money matches the recorded ladder replay. Any divergence means the simulator
or agent has drifted.

    python -m src.replay_tool replays/LIVE/v18/episode-99865519-replay.json
    python -m src.replay_tool --all replays/LIVE/v18_all/
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.simulator import Simulator  # noqa: E402
from src.opponent_model import GhostOpponent  # noqa: E402


def replay_one(path, verbose=True):
    replay = json.load(open(path, encoding="utf-8"))
    seed = replay.get("info", {}).get("seed")
    # Fall back: replay["info"]["seed"] or configuration seed
    if seed is None:
        seed = replay.get("configuration", {}).get("seed", 0)
    names = (replay.get("info") or {}).get("TeamNames") or []
    our_idx = 0
    for i, n in enumerate(names):
        if "m0h4m3d" in str(n).lower():
            our_idx = i
    opp_idx = 1 - our_idx
    rewards = replay.get("rewards", [None, None])
    ghost = GhostOpponent(path, player=opp_idx)

    # Determine which side we were in the replay
    # If we were p0, ghost replays p1's actions against our fresh agent as p0.
    from main import Agent
    if our_idx == 0:
        res = Simulator(seed=seed).run([Agent(), ghost])
        sim_money = res["money"][0]
    else:
        res = Simulator(seed=seed).run([ghost, Agent()])
        sim_money = res["money"][1]
    recorded = rewards[our_idx]
    diff = sim_money - recorded
    status = "MATCH" if abs(diff) < 1 else "DRIFT"
    if verbose:
        print(f"{Path(path).name}: recorded ${recorded:,.0f}  sim ${sim_money:,.0f}  "
              f"diff {diff:+,.0f} [{status}]  ghost={names[opp_i][:20] if (opp_i:=opp_idx) < len(names) else '?'}")
    return diff


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", help="single replay file")
    parser.add_argument("--all", dest="folder", help="folder of replays")
    args = parser.parse_args()
    if args.folder:
        import glob
        diffs = []
        for p in sorted(glob.glob(f"{args.folder}/*.json")):
            diffs.append(abs(replay_one(p)))
        print(f"\nmax |diff| ${max(diffs):,.0f}  mean |diff| ${sum(diffs)/len(diffs):,.0f}")
    elif args.path:
        replay_one(args.path)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
