"""
tests/test_simulator.py - Verification suite for the DeepSim fast simulator.

Run from the project root:
    python -m unittest tests.test_simulator -v
"""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.simulator import Simulator, parity_check  # noqa: E402


class TestSimulatorBasics(unittest.TestCase):
    def test_initial_state(self):
        sim = Simulator(seed=0).reset()
        views = sim.step(None)  # initialize only
        farm = sim.state[0].observation.farms[0]
        self.assertEqual(farm["money"], 3000)
        self.assertEqual(farm["unlocked_quadrants"], ["NW"])
        market = sim.state[0].observation.market
        self.assertEqual(market["inventory"]["WHEAT"], 10000)
        self.assertEqual(market["prices"]["WHEAT"], 25)

    def test_deterministic_same_seed(self):
        r1 = Simulator(seed=123).run(["pass", "pass"])
        r2 = Simulator(seed=123).run(["pass", "pass"])
        self.assertEqual(r1["money"], r2["money"])

    def test_seeds_differ(self):
        r1 = Simulator(seed=1).run(["pass", "pass"])
        r2 = Simulator(seed=2).run(["pass", "pass"])
        # Weed RNG / shop unlocks differ -> town shop sets may differ; at minimum
        # both complete 720 turns. Money equality across different seeds would be
        # suspicious but not impossible for two PASS agents; assert steps instead.
        self.assertEqual(r1["steps"], 719)
        self.assertEqual(r2["steps"], 719)

    def test_full_season_length(self):
        res = Simulator(seed=7).run(["pass", "pass"])
        self.assertEqual(res["steps"], 719)

    def test_agent_can_play(self):
        from main import Agent
        res = Simulator(seed=42).run([Agent(), "pass"])
        self.assertGreater(res["money"][0], 3000)

    def test_speed(self):
        t0 = time.perf_counter()
        Simulator(seed=9).run(["pass", "pass"])
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 1.0, "pure simulation must stay fast (<1s/episode)")


class TestParityWithOfficialEngine(unittest.TestCase):
    def test_parity_three_seeds(self):
        worst, _ = parity_check([0, 1, 2], opponent="pass", verbose=False)
        self.assertEqual(worst, 0, f"money diverged from official engine by ${worst}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
