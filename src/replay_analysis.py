"""
replay_analysis.py - Opponent replay analysis (3 levels) with executable decisions.

Levels:
  1. Intra-player stability (2 episodes per player)
  2. Inter-player consensus vs divergence (3 players)
  3. Us vs them opportunity gaps + likely_cause + suggest_experiments

Each Experiment has actual_result: None (filled after running on evaluation.py) to track
expected_gain vs actual_result over time.
"""
import json, pathlib
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional
from collections import Counter, defaultdict

def quadrant_of(x,y):
    if x<5 and y<5: return "NW"
    if x>=5 and y<5: return "NE"
    if x<5 and y>=5: return "SW"
    return "SE"

@dataclass
class PlayerReplayMetrics:
    player: str
    episode_id: int
    seed: int
    opponent: str
    final_money: int
    land_timeline: List[Dict]  # {quad, day, hour, money_before, cost}
    crop_dist: Dict[str, Dict[str, float]]  # quad -> {crop: %}
    animal_dist: Dict[str, Dict[str, int]]
    efficiency: Dict  # day1_plants, weeds_total, weed_cause, escapes
    sell_pattern: List[Dict]
    raw: Dict = field(default_factory=dict)  # for debugging

@dataclass
class OpportunityGap:
    metric: str
    ours: float
    best_them: float
    gap: float
    priority: str
    likely_cause: Optional[str] = None  # for gap_high only, inferred vs our code

@dataclass
class Experiment:
    title: str
    linked_gap: str
    expected_gain: str
    effort: str
    command: str
    actual_result: Optional[float] = None  # filled after running on evaluation.py
    priority: int = 0

def extract_metrics(path: str, player_name: str = None) -> PlayerReplayMetrics:
    data=json.load(open(path, encoding="utf-8"))
    info=data.get("info",{})
    team_names=info.get("TeamNames",[])
    # find player index
    p_idx=0
    if player_name:
        for i,n in enumerate(team_names):
            if player_name.lower() in n.lower():
                p_idx=i
                break
    else:
        # default first player matching Crop Dusta if present
        for i,n in enumerate(team_names):
            if "crop" in n.lower():
                p_idx=i
                break
    steps=data["steps"]
    rewards=data.get("rewards",[])
    final_money=int(rewards[p_idx]) if rewards else int(steps[-1][p_idx]["observation"]["farms"][p_idx]["money"])
    # land timeline
    land=[]
    prev_unlocked=set(steps[0][p_idx]["observation"]["farms"][p_idx].get("unlocked_quadrants",[]))
    for s in steps:
        obs=s[p_idx]["observation"]
        farm=obs["farms"][p_idx]
        cur=set(farm.get("unlocked_quadrants",[]))
        new=cur-prev_unlocked
        if new:
            for q in new:
                land.append({"quad": q, "day": obs["day"], "hour": obs["hour"], "money_before": farm["money"], "cost": 1000 if q=="NE" else 2000 if q=="SW" else 4000})
            prev_unlocked=cur
        # also detect via action
        act=s[p_idx].get("action",{}).get("market",[])
        # not needed
    # crop/animal dist at mid-season (day15) + final
    def _quad_dist_at(day_target):
        obs_mid=None
        for s in steps:
            if s[p_idx]["observation"]["day"]==day_target and s[p_idx]["observation"]["hour"]==0:
                obs_mid=s[p_idx]["observation"]
                break
        if not obs_mid:
            obs_mid=steps[min(15*24, len(steps)-1)][p_idx]["observation"]
        tiles_mid=obs_mid["farms"][p_idx]["tiles"]
        qc=defaultdict(Counter)
        for y,row in enumerate(tiles_mid):
            for x,t in enumerate(row):
                if isinstance(t, dict) and t.get("kind")=="PLANT":
                    qc[quadrant_of(x,y)][t.get("crop","")] +=1
        dist={}
        for q in ["NW","NE","SW"]:
            cnt=qc[q]
            tot=sum(cnt.values())
            dist[q]={k: round(v/tot*100,1) if tot else 0 for k,v in cnt.items()}
            dist[q]["_total"]=tot
        return dist, obs_mid["day"]
    crop_dist_mid, mid_day = _quad_dist_at(15)
    # final for reference
    final_obs=steps[-1][p_idx]["observation"]
    tiles=final_obs["farms"][p_idx]["tiles"]
    quad_crops=mid_crops=crop_dist_mid  # use mid-season as primary
    crop_dist=crop_dist_mid
    # animal dist at final (mid similar)
    quad_animals=defaultdict(Counter)
    for y,row in enumerate(tiles):
        for x,t in enumerate(row):
            if isinstance(t, dict) and "animal" in t and t.get("animal"):
                quad_animals[quadrant_of(x,y)][t["animal"]]+=1
    animal_dist={q: dict(cnt) for q,cnt in quad_animals.items()}
    # day1 plants
    day1_obs=None
    for s in steps:
        if s[p_idx]["observation"]["day"]==1 and s[p_idx]["observation"]["hour"]==0:
            day1_obs=s[p_idx]["observation"]
            break
    day1_plants=0
    if day1_obs:
        tiles1=day1_obs["farms"][p_idx]["tiles"]
        day1_plants=sum(1 for row in tiles1 for t in row if isinstance(t, dict) and t.get("kind")=="PLANT")
    # weeds/escapes
    weeds=sum(1 for row in tiles for t in row if isinstance(t, dict) and t.get("kind")=="WEED")
    # estimate escapes by max animals vs final (simplified)
    escapes=0  # would need history
    # sell pattern
    sells=[]
    for s in steps:
        for o in s[p_idx].get("action",{}).get("market",[]):
            if o and o[0]=="SELL":
                obs=s[p_idx]["observation"]
                sells.append({"day": obs["day"], "product": o[1], "qty": o[2], "price": obs["market"]["prices"].get(o[1],0)})
    return PlayerReplayMetrics(
        player=team_names[p_idx] if p_idx < len(team_names) else f"p{p_idx}",
        episode_id=info.get("EpisodeId",0),
        seed=info.get("seed",0),
        opponent=team_names[1-p_idx] if len(team_names)>1 else "",
        final_money=final_money,
        land_timeline=land,
        crop_dist=crop_dist,
        animal_dist=animal_dist,
        efficiency={"day1_plants": day1_plants, "weeds_total": weeds, "weed_cause": {"neglect": 0, "spawn": 0, "unknown": weeds}, "escapes": escapes},
        sell_pattern=sells[:10],
        raw={"steps": len(steps)}
    )

def suggest_experiments(gaps: List[OpportunityGap]) -> List[Experiment]:
    exps=[]
    for i,g in enumerate([x for x in gaps if x.priority=="gap_high"]):
        if g.metric=="day1_plants":
            exps.append(Experiment(f"جرب توسيع FIXED_NW_20 لـ NE في day0-1 (5 خانات إضافية)", g.metric, "+3-5 نباتات → +2-4k", "low", "python -m src.evaluation --seeds 8", None, i+1))
        elif g.metric=="weeds":
            exps.append(Experiment(f"ارفع WATER prio عند weeds>5", g.metric, "-2 حشائش", "low", "python -m src.evaluation --seeds 8", None, i+1))
        elif "land" in g.metric:
            exps.append(Experiment(f"قدّم NE day6→4", g.metric, "+1.5k", "low", "python -m src.evaluation --seeds 8", None, i+1))
        else:
            exps.append(Experiment(f"اختبر تحسين {g.metric}", g.metric, "غير محدد", "med", "python -m src.evaluation --seeds 32", None, i+1))
    return sorted(exps, key=lambda x: x.priority)

if __name__=="__main__":
    import argparse, json
    p=argparse.ArgumentParser()
    p.add_argument("--replay", type=str, help="path to single replay")
    p.add_argument("--player", type=str, default="Crop Dusta")
    args=p.parse_args()
    if args.replay:
        m=extract_metrics(args.replay, args.player)
        print(json.dumps(asdict(m), indent=2, ensure_ascii=False))
