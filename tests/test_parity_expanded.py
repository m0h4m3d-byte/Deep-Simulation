"""
tests/test_parity_expanded.py - 20-seed parity vs official kaggle_environments.

    python -m pytest tests/test_parity_expanded.py -v
    python -m tests.test_parity_expanded          # standalone
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_parity_20_seeds():
    from src.simulator import parity_check
    worst, rows = parity_check(list(range(20)), opponent="pass", verbose=False)
    assert worst == 0, f"parity broken on 20 seeds: worst |diff| = ${worst:,.0f}"
    print(f"parity OK on 20 seeds (worst diff ${worst})")


if __name__ == "__main__":
    test_parity_20_seeds()
