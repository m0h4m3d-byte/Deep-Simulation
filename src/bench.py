"""
bench.py - Unified DeepSim benchmark (default = ladder realism).

Runs the agent under BOTH regimes so no improvement can hide behind solo optimism:

  solo   : vs pass (old metric, ~$95k)
  mirror : vs itself (2-player shared market, ~$58k — ladder-like)
  ladder : vs 4 diverse archetypes (kshitiz/aibaba/dairy/strawmax)

    python -m src.bench --seeds 12
    python -m src.bench --seeds 30 --quick   # solo only, fast

The ladder bench is now the GATE for any submission: it must not regress there.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description="DeepSim unified bench")
    parser.add_argument("--seeds", type=int, default=12)
    parser.add_argument("--quick", action="store_true", help="solo only")
    args = parser.parse_args()
    seeds = list(range(args.seeds))

    from src.simulator import evaluate
    from main import Agent
    import src.economy as E

    print("=" * 60)
    print(f"DeepSim bench — {args.seeds} seeds — PLAN {E.PLAN['COW']}:{E.PLAN['SHEEP']} W{ E.PLAN['WHEAT']}")
    print("=" * 60)

    # 1. solo (legacy)
    st = evaluate(lambda: Agent(), seeds, opponent="pass")
    print(f"\n[solo vs pass] mean ${st['mean']:,.0f}  best ${st['best']:,.0f} worst ${st['worst']:,.0f}")

    if args.quick:
        return

    # 2. mirror (2-player shared market)
    from tests.mirror_bench import run_mirror
    run_mirror(seeds, "mirror (agent vs itself)")

    # 3. ladder bench (diverse archetypes)
    from tests.ladder_bench import run_bench
    print()
    run_bench(seeds)


if __name__ == "__main__":
    main()
