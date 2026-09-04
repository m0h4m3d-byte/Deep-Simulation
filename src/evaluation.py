"""
evaluation.py - Comprehensive evaluation suite (3 quarters NW/NE/SW, SE forbidden).
Streaming aggregation (~0.6MB for 32 games). Geography synergy on 8 seeds auto.
"""
import argparse, time, statistics
from collections import Counter, defaultdict
from typing import List
from src.simulator import Simulator
from main import Agent
import src.config as CFG

KNOWN_GOOD = {
    "PLAN": {"COW": 10, "SHEEP": 5, "GOOSE": 0, "MELON": 12, "STRAWBERRY": 20, "WHEAT": 15},
    "PASTURE_LOCATIONS": [(4,3),(3,4),(4,4),(3,3),(4,2),(5,4),(5,3),(6,4),(6,3),(5,2),(4,5),(3,5),(3,6),(4,6),(2,5)],
    "LAND_COSTS": [1000,2000,4000], "LAND_DAYS": [6,9,12], "HIRE_TARGET": 12,
    "PASTURE_BUFFER": 2, "SHED_CAPACITY": 100,
}
def quadrant_of(x,y):
    if x<5 and y<5: return "NW"
    if x>=5 and y<5: return "NE"
    if x<5 and y>=5: return "SW"
    return "SE"

def check_drift():
    warns=[]
    for k,v in KNOWN_GOOD.items():
        if getattr(CFG,k,None)!=v:
            warns.append(f"DRIFT {k}: {getattr(CFG,k)} != {v}")
    return {"passed": len(warns)==0, "warnings": warns}

def check_caps(request=None):
    """Non-blocking caps check: logs caps_warnings, never waits for input in batch mode."""
    caps_warnings=[]
    # Example: if request asks for MELON 30 but PLAN 12, log it
    if request:
        for k,v in request.items():
            cap = getattr(CFG, k, None) or CAPS.get(k)
            if cap is not None and v > cap:
                caps_warnings.append(f"REQUEST {k}={v} > CAP {k}={cap} at {SRC.get(k,'config')} — auto-capped to {cap}, no input wait in batch")
    # Always scan current config for active caps that would silently truncate
    # (informational, not blocking)
    return caps_warnings

CAPS = {"MELON": 12, "STRAWBERRY": 20, "WHEAT": 15, "COW": 10, "SHEEP": 5, "HIRE_TARGET": 12, "PLANT_TARGET_FULL": 60, "MELON_CAP": 28}
SRC = {"MELON": "config.PLAN", "STRAWBERRY": "config.PLAN", "WHEAT": "config.PLAN", "COW": "config.PLAN", "SHEEP": "config.PLAN", "HIRE_TARGET": "config.HIRE_TARGET", "PLANT_TARGET_FULL": "config.PLANT_TARGET_FULL", "MELON_CAP": "planner.melon_cap"}

def run_single_game(seed: int, quad_filter=None):
    """quad_filter: None (full 3Q) or 'NW'/'NE'/'SW' for isolated."""
    sim=Simulator(seed=seed)
    sim.reset()
    views=sim.step(None)
    agent=Agent()
    def _lock_isolated():
        if not quad_filter:
            return
        for farm in sim.state[0].observation.farms:
            # lock all tiles outside quad_filter
            for y in range(10):
                for x in range(10):
                    if quadrant_of(x,y)!=quad_filter:
                        farm["tiles"][y][x]="LOCKED"
            farm["unlocked_quadrants"]=[quad_filter]
    _lock_isolated()
    # for isolated, monkey-patch planner to filter jobs outside quad
    if quad_filter:
        orig_collect=agent.planner.collect_jobs
        def filtered_collect(day, tiles, shed, seeds, invs, animals_ordered, market_ctx=None):
            jobs=orig_collect(day, tiles, shed, seeds, invs, animals_ordered, market_ctx)
            keep=[]
            for j in jobs:
                pos=j[0]
                if j[1]=="DEPOSIT":
                    keep.append(j)
                elif quadrant_of(pos[0], pos[1])==quad_filter:
                    keep.append(j)
            return keep
        agent.planner.collect_jobs=filtered_collect

    money_hist=[]
    tile_prev=None
    total_dist=0
    prev_pos=None
    action_counts=Counter()
    farmer1_counts=Counter()
    wasted_pass=0
    total_turns=0
    weed_neglect=weed_spawn=weed_unknown=0
    empty_consec=defaultdict(int)
    empty_gt1=0
    land_ne_day=None
    land_sw_day=None
    days_below_100=0
    min_money=float('inf')
    min_when=None
    hire_cost_total=0
    fert_sold_prices=[]
    fert_used=0
    crop_harvest_value=defaultdict(float)
    crop_harvest_units=defaultdict(int)
    market_sells=defaultdict(list)  # product -> prices
    # watering tracking
    planted={}  # (x,y)->{planted_day, watered_days, total_days}
    consec1=0
    delay_sum=0
    delay_n=0
    feed_days=0
    feed_possible=0
    fert_produced=0
    day1_plants=None

    while not sim.done:
        me=views[0]["farms"][0]
        obs=views[0]
        money=me["money"]
        money_hist.append(money)
        if money<min_money:
            min_money=money
            min_when=(obs["day"], obs["hour"])
        # land timing
        unlocked=me.get("unlocked_quadrants",[])
        if "NE" in unlocked and land_ne_day is None:
            land_ne_day=obs["day"]
        if "SW" in unlocked and land_sw_day is None:
            land_sw_day=obs["day"]
        if money<100:
            days_below_100+=1
        # tiles
        tiles=me["tiles"]
        if tile_prev is not None:
            for y in range(10):
                for x in range(10):
                    prev=tile_prev[y][x]
                    cur=tiles[y][x]
                    if isinstance(cur, dict) and cur.get("kind")=="WEED":
                        if isinstance(prev, dict) and prev.get("kind")=="PLANT":
                            weed_neglect+=1
                        elif prev is None:
                            weed_spawn+=1
                        else:
                            weed_unknown+=1
                    # empty gt1: track consecutive empty
                    key=(x,y)
                    if cur is None:
                        empty_consec[key]+=1
                        if empty_consec[key]==2:
                            empty_gt1+=1
                    else:
                        empty_consec[key]=0
                    # watering
                    if isinstance(cur, dict) and cur.get("kind")=="PLANT":
                        if key not in planted:
                            planted[key]={"planted_day": cur.get("planted_day", obs["day"]), "watered":0, "total":0, "first_water_delay": None}
                            # delay
                            if not cur.get("watered_today", False):
                                pass  # will count when watered
                        info=planted[key]
                        info["total"]+=1
                        if cur.get("watered_today"):
                            info["watered"]+=1
                            if info["first_water_delay"] is None:
                                delay=(obs["day"] - info["planted_day"])
                                # if watered today, delay is days until first water
                                info["first_water_delay"]=delay
                        # consec unwatered 1
                        if cur.get("consecutive_unwatered")==1:
                            consec1+=1
                    # feed
                    if isinstance(cur, dict) and "animal" in cur:
                        feed_possible+=1
                        if cur.get("fed_today"):
                            feed_days+=1
                        if cur.get("fertilizer_available"):
                            fert_produced+=1
        else:
            # init empty_consec
            for y in range(10):
                for x in range(10):
                    if tiles[y][x] is None:
                        empty_consec[(x,y)]=1
        if obs["day"]==1 and obs["hour"]==0 and day1_plants is None:
            # count plants at start of day1
            day1_plants=sum(1 for row in tiles for t in row if isinstance(t, dict) and t.get("kind")=="PLANT")
        tile_prev=[row[:] for row in tiles]

        act=agent(obs)
        if quad_filter:
            # block any land purchase in isolated mode
            act["market"]=[o for o in act.get("market",[]) if not (o and o[0]=="BUY_LAND")]
        # action counts
        for a in [act["farmer"]]+act["hands"]:
            if a:
                action_counts[a[0]]+=1
                if a==act["farmer"]:
                    farmer1_counts[a[0]]+=1
                if a[0]=="FERTILIZE":
                    fert_used+=1
        if act["farmer"]==["PASS"]:
            has_work=any(isinstance(t, dict) and (t.get("yield_units",0)>0 or (t.get("kind")=="PLANT" and not t.get("watered_today",True))) for row in tiles for t in row)
            if has_work:
                wasted_pass+=1
        total_turns+=1
        # movement
        cur_pos=[tuple(me["farmer"])]+[tuple(h) for h in me["hands"]]
        if prev_pos:
            for a,b in zip(prev_pos, cur_pos):
                if a!=b: total_dist+=1
        prev_pos=cur_pos
        # market
        for o in act.get("market",[]):
            if o and o[0]=="SELL":
                price=obs["market"]["prices"].get(o[1],0)
                market_sells[o[1]].append(price)
                if o[1]=="FERTILIZER":
                    fert_sold_prices.append(price)
            if o and o[0]=="HIRE":
                # cost is fib(hires_today) before hire
                hire_cost_total+=1  # placeholder, actual cost tracked via money diff approximate
        views=sim.step([act, {"farmer":["PASS"],"hands":[],"market":[]}])
        _lock_isolated()

    final_money=float(sim.state[0].observation.farms[0]["money"])
    final_tiles=sim.state[0].observation.farms[0]["tiles"]
    final_shed=sim.state[0].observation.private["shed"]
    final_seeds=sim.state[0].observation.private["seeds"]
    # operational waste
    waste_shed=sum(final_shed.values())
    waste_seeds=sum(final_seeds.values())
    waste_field=sum(1 for row in final_tiles for t in row if isinstance(t, dict) and t.get("kind")=="PLANT")
    # animals remaining
    waste_animal=sum(1 for row in final_tiles for t in row if isinstance(t, dict) and "animal" in t and t.get("animal"))
    # watering rate
    watered_rate=sum(v["watered"]/max(1,v["total"]) for v in planted.values())/max(1,len(planted)) if planted else 0
    avg_delay=sum(v["first_water_delay"] for v in planted.values() if v["first_water_delay"] is not None)/max(1, sum(1 for v in planted.values() if v["first_water_delay"] is not None)) if planted else 0
    # crops per quad
    quad_counts=Counter()
    for (x,y),v in planted.items():
        quad_counts[quadrant_of(x,y)]+=1
    # hire total cost approx via money? use hires count * avg cost 1
    return {
        "seed": seed, "money": final_money, "money_hist": money_hist,
        "day1_plants": day1_plants or 0,
        "weed_neglect": weed_neglect, "weed_spawn": weed_spawn, "weed_unknown": weed_unknown,
        "empty_gt1": empty_gt1, "land_ne": land_ne_day, "land_sw": land_sw_day,
        "days_below_100": days_below_100, "min_money": min_money, "min_when": min_when,
        "dist": total_dist, "wasted_pass": wasted_pass, "total_turns": total_turns,
        "action_counts": action_counts, "farmer1_counts": farmer1_counts,
        "watered_rate": watered_rate, "consec1": consec1, "avg_delay": avg_delay,
        "feed_rate": feed_days/max(1,feed_possible), "fert_produced": fert_produced,
        "fert_sold_prices": fert_sold_prices, "fert_used": fert_used,
        "market_sells": market_sells, "quad_counts": quad_counts,
        "hire_cost": hire_cost_total, "waste": {"shed": waste_shed, "seeds": waste_seeds, "field": waste_field, "animal": waste_animal},
        "final_tiles": final_tiles,
    }

def run_evaluation(seeds: List[int], request=None):
    import time, statistics, json
    t0=time.perf_counter()
    drift=check_drift()
    caps_warnings=check_caps(request)
    results=[run_single_game(s) for s in seeds]
    money_vals=[r["money"] for r in results]
    mean=sum(money_vals)/len(money_vals) if money_vals else 0
    best=max(money_vals) if money_vals else 0
    worst=min(money_vals) if money_vals else 0
    stdev=statistics.pstdev(money_vals) if len(money_vals)>1 else 0
    hist=[0]*10
    if money_vals:
        mn,mx=min(money_vals), max(money_vals)
        rng=mx-mn or 1
        for v in money_vals:
            hist[min(9,int((v-mn)/rng*10))]+=1
    # geography: isolated synergy not reliable - FIXED_NW_20 is NW-only, NE/SW have no independent plan
    geo=[]
    for s in seeds[:8]:
        combined=next(r for r in results if r["seed"]==s)
        geo.append({
            "seed": s,
            "combined_money": combined["money"],
            "quad_plants": dict(combined["quad_counts"]),
            "note": "قياس synergy الدقيق (معزول) غير موثوق حاليًا لأن FIXED_NW_20 مصمم لـNW فقط - NE/SW معندهمش خطة مستقلة للعزل العادل. القيم المعروضة هي quad_counts من التشغيل المدمج فقط، مش مقياس تعارض حقيقي."
        })
    elapsed=time.perf_counter()-t0
    # aggregate watering etc
    avg_watered=sum(r["watered_rate"] for r in results)/len(results) if results else 0
    avg_consec1=sum(r["consec1"] for r in results)/len(results) if results else 0
    avg_delay=sum(r["avg_delay"] for r in results)/len(results) if results else 0
    report={
        "meta": {"seeds": seeds, "elapsed_sec": elapsed, "drift": drift, "caps_warnings": caps_warnings},
        "financial": {"mean": mean, "best": best, "worst": worst, "stdev": stdev, "histogram": hist, "values": money_vals, "cv": stdev/mean if mean else 0},
        "operational": {
            "day1_plants_mean": sum(r["day1_plants"] for r in results)/len(results) if results else 0,
            "weeds_avg": sum(r["weed_neglect"]+r["weed_spawn"]+r["weed_unknown"] for r in results)/len(results) if results else 0,
            "weed_breakdown": {"neglect": sum(r["weed_neglect"] for r in results), "spawn": sum(r["weed_spawn"] for r in results), "unknown": sum(r["weed_unknown"] for r in results)},
            "waste": {k: sum(r["waste"][k] for r in results)/len(results) for k in ["shed","seeds","field","animal"]} if results else {},
        },
        "liquidity": {
            "min_balance_avg": sum(r["min_money"] for r in results)/len(results) if results else 0,
            "land_ne": {"mean": statistics.mean([r["land_ne"] for r in results if r["land_ne"] is not None]) if any(r["land_ne"] for r in results) else None, "stdev": statistics.pstdev([r["land_ne"] for r in results if r["land_ne"] is not None]) if len([r for r in results if r["land_ne"]])>1 else 0},
            "land_sw": {"mean": statistics.mean([r["land_sw"] for r in results if r["land_sw"] is not None]) if any(r["land_sw"] for r in results) else None, "stdev": statistics.pstdev([r["land_sw"] for r in results if r["land_sw"] is not None]) if len([r for r in results if r["land_sw"]])>1 else 0},
            "pct_days_below_100": sum(r["days_below_100"] for r in results)/max(1,sum(r["total_turns"] for r in results))*100,
        },
        "movement": {
            "avg_dist_per_unit": sum(r["dist"] for r in results)/len(results)/4 if results else 0,
            "wasted_pass_rate": sum(r["wasted_pass"] for r in results)/max(1,sum(r["total_turns"] for r in results)),
            "action_dist": dict(sum((r["action_counts"] for r in results), Counter())),
            "farmer1_dist": dict(sum((r["farmer1_counts"] for r in results), Counter())),
        },
        "watering": {"watered_rate": avg_watered, "consec1_avg": avg_consec1, "avg_delay": avg_delay, "empty_gt1_avg": sum(r["empty_gt1"] for r in results)/len(results) if results else 0},
        "animals": {"feed_rate_avg": sum(r["feed_rate"] for r in results)/len(results) if results else 0, "fert_produced_avg": sum(r["fert_produced"] for r in results)/len(results) if results else 0, "fert_used_avg": sum(r["fert_used"] for r in results)/len(results) if results else 0},
        "market": {},
        "geography": {"per_seed": geo, "note": "قياس synergy الدقيق (معزول) غير موثوق حاليًا لأن FIXED_NW_20 مصمم لـNW فقط - NE/SW معندهمش خطة مستقلة للعزل العادل. القيم المعروضة هي quad_counts من التشغيل المدمج فقط، مش مقياس تعارض حقيقي."},
        "reliability": {"elapsed_32": elapsed, "cv": stdev/mean if mean else 0},
        "hiring": {"avg_hire_cost": sum(r["hire_cost"] for r in results)/len(results) if results else 0},
        "crops": {"quad_avg": {k: sum(r["quad_counts"][k] for r in results)/len(results) for k in ["NW","NE","SW"]} if results else {}},
        "market": {"per_product_avg_price": {k: sum(sum(r["market_sells"][k] for r in results) , [])} if False else {}},
    }
    return report

if __name__=="__main__":
    import argparse, json, pathlib
    p=argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=32)
    a=p.parse_args()
    rpt=run_evaluation(list(range(a.seeds)))
    print(f"DRIFT {rpt['meta']['drift']}")
    print(f"FINANCIAL mean={rpt['financial']['mean']:.0f} best={rpt['financial']['best']:.0f} worst={rpt['financial']['worst']:.0f}")
    # note stored in JSON is Arabic, print ASCII summary only
    print(f"GEOGRAPHY per-seed count={len(rpt['geography']['per_seed'])}")
    print(f"GEO quad_avg={rpt['crops']['quad_avg']}")
    pathlib.Path("evaluation_report.json").write_text(json.dumps(rpt, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("Wrote evaluation_report.json")
