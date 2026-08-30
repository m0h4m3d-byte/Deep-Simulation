"""Phase 6: one-day Simulator (24 turns, seed0) detailed log"""
from src.simulator import Simulator
from main import Agent
import copy

seed = 0
sim = Simulator(seed=seed)
sim.reset()
views = sim.step(None)
agent = Agent()

# track
for turn in range(24):
    day = views[0]["day"]
    obs = views[0]
    # call agent and capture internal planner state
    # we need to peek after collect_jobs
    # monkey: call agent manually to get actions and then inspect planner
    action = agent(obs)  # this internally does collect_jobs + unit_action
    # planner state after call
    planner = agent.planner
    zones = getattr(planner, 'zones', [])
    num_workers = len(obs["farms"][0]["hands"]) + 1
    # count workers per zone via fixed assignment
    zone_counts = {}
    for wi in range(num_workers):
        z = wi % len(zones) if zones else 0
        zone_counts[z] = zone_counts.get(z, 0) + 1
    # count PASS
    all_actions = [action["farmer"]] + action["hands"]
    pass_cnt = sum(1 for a in all_actions if a == ["PASS"])
    # jobs for debug
    # we can re-collect jobs count? Use planner's last zones already
    # To get plants at this turn, inspect tiles
    tiles = obs["farms"][0]["tiles"]
    plant_cnt = sum(1 for row in tiles for t in row if isinstance(t, dict) and t.get("kind")=="PLANT")
    weed_cnt = sum(1 for row in tiles for t in row if (isinstance(t, str) and t=="WEED") or (isinstance(t, dict) and t.get("kind")=="WEED"))
    # zones debug
    zones_str = "; ".join([f"Z{i}[{x0},{y0}-{x1},{y1}]" for i,(x0,y0,x1,y1) in enumerate(zones)]) if zones else "no zones yet"
    print(f"turn {turn:2d} day {day} workers {num_workers} zones {len(zones)} | per_zone {zone_counts} | PASS {pass_cnt}/{num_workers} | plants {plant_cnt} weeds {weed_cnt} | zones: {zones_str}")
    for wi, act in enumerate(all_actions):
        print(f"  w{wi} at {obs['farms'][0]['farmer'] if wi==0 else obs['farms'][0]['hands'][wi-1]} -> {act}")
    # step simulator
    opp_action = {"farmer": ["PASS"], "hands": [], "market": []}
    views = sim.step([action, opp_action])
    if sim.done:
        break

# end of day plants
final_tiles = views[0]["farms"][0]["tiles"] if not sim.done else sim.state[0].observation.farms[0]["tiles"] if hasattr(sim.state[0].observation, 'farms') else tiles
# actually after loop, views is next day's obs
try:
    final_plant = sum(1 for row in views[0]["farms"][0]["tiles"] for t in row if isinstance(t, dict) and t.get("kind")=="PLANT")
    print(f"\n=== End of Day 0 (after 24 turns) plants={final_plant} ===")
    # also print per zone plants
    zones = agent.planner.zones
    from collections import Counter
    per_zone = Counter()
    for y in range(10):
        for x in range(10):
            t = views[0]["farms"][0]["tiles"][y][x]
            if isinstance(t, dict) and t.get("kind")=="PLANT":
                # find zone
                for zi,(x0,y0,x1,y1) in enumerate(zones):
                    if x0<=x<=x1 and y0<=y<=y1:
                        per_zone[zi]+=1
                        break
    print(f"per zone plants: {dict(per_zone)}")
except Exception as e:
    print("err final", e)
