"""
Analyze the worst seed: instrument money over time, market state, shops,
and agent activity to find why the agent collapsed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.simulator import Simulator  # noqa: E402
from main import Agent  # noqa: E402

SEED = 11


def run_instrumented():
    sim = Simulator(seed=SEED).reset()
    agent = Agent()
    views = sim.step(None)  # init
    trace = []  # (day, money, prices_wheat/carrot/egg, shops)
    while not sim.done:
        actions = [agent(views[0]), {"farmer": ["PASS"], "hands": [], "market": []}]
        # snapshot at start of each day
        step = views[0]["step"]
        if views[0]["hour"] == 0 and views[0]["day"] % 3 == 0 or True:
            pass
        views = sim.step(actions)
        v = views[0]
        if v["hour"] == 0:
            m = v["farms"][0]["money"]
            p = v["market"]["prices"]
            shops = len(v["town"]["unlocked_shops"])
            tiles = v["farms"][0]["tiles"]
            plants = sum(1 for row in tiles for t in row if isinstance(t, dict) and t.get("kind") == "PLANT")
            animals = sum(1 for row in tiles for t in row
                          if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE") and t.get("animal"))
            weeds = sum(1 for row in tiles for t in row if isinstance(t, dict) and t.get("kind") == "WEED")
            quads = len(v["farms"][0]["unlocked_quadrants"])
            shed = sum(v["private"]["shed"].values())
            seeds_total = sum(v["private"]["seeds"].values())
            trace.append((v["day"], int(m), p["WHEAT"], p["CARROT"], p["EGG"],
                          shops, plants, animals, weeds, quads, shed, seeds_total))
    return sim, trace


sim, trace = run_instrumented()
final_money = float(sim.state[0].observation.farms[0]["money"])
print(f"SEED {SEED}: final money ${final_money:,.0f}\n")
print(f"{'day':>3} {'money':>8} {'wht':>4} {'crt':>4} {'egg':>4} | "
      f"{'shops':>5} {'plants':>6} {'animals':>7} {'weeds':>5} {'quads':>5} {'shed':>4} {'seeds':>5}")
for day, money, w, c, e, sh, pl, an, wd, q, sd, st in trace:
    print(f"{day:>3} {money:>8,} {w:>4} {c:>4} {e:>4} | {sh:>5} {pl:>6} {an:>7} {wd:>5} {q:>5} {sd:>4} {st:>5}")
