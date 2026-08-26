"""
opponent_model.py - Opponent modeling from Kaggle replay files.

Two layers:

1. GhostOpponent — replays the EXACT action sequence recorded in an episode.
   Most faithful possible opponent model for the opening (first ~10 days),
   where openings are scripted and state divergence is small.

2. ReplayProfile — aggregates behavioral statistics from a replay
   (crop/animal purchase mix, hiring cadence, land-expansion timing,
   sell mix, money trajectory). Used to sanity-check ghosts and later to
   build adaptive statistical opponents.

Usage:
    from src.opponent_model import GhostOpponent, load_replay, profile_summary

    ghost = GhostOpponent("replays/LEADER DATA/KAWASHIGI.json", player=0)
    res = Simulator(seed=0).run([Agent(), ghost])
"""

import json
import statistics


def load_replay(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class GhostOpponent:
    """Plays back the recorded actions of one side of an episode."""

    def __init__(self, path, player=0):
        replay = load_replay(path)
        self.path = path
        self.player = player
        self.name = path.split("/")[-1].split("\\")[-1].rsplit(".", 1)[0]
        self.rewards = replay.get("rewards")
        self.actions = []
        for step in replay["steps"]:
            raw = step[player].get("action") if player < len(step) else None
            self.actions.append(raw or {"farmer": ["PASS"], "hands": [], "market": []})

    def __call__(self, obs):
        s = obs.get("step", 0)
        if s < len(self.actions):
            return self.actions[s]
        return {"farmer": ["PASS"], "hands": [], "market": []}


class ReplayProfile:
    """Behavioral statistics extracted from one replay for one player."""

    def __init__(self, path, player=0):
        replay = load_replay(path)
        self.path = path
        self.player = player
        self.name = path.split("/")[-1].split("\\")[-1].rsplit(".", 1)[0]
        self.final_money = (replay.get("rewards") or [None])[player] if replay.get("rewards") else None

        self.seed_buys = {}          # crop -> units
        self.animal_buys = {}        # animal -> units
        self.product_buys = {}       # item -> units (BUY_PRODUCT, e.g. wheat feed)
        self.sells = {}              # product -> units sold
        self.hires_per_day = {}      # day -> hires
        self.land_buy_step = None
        self.first_animal_step = None
        self.crop_first_buy = {}     # crop -> first step bought
        self.money_curve = []        # (day, money) sampled daily

        for t, step in enumerate(replay["steps"]):
            if player >= len(step):
                continue
            action = step[player].get("action") or {}
            market = action.get("market") or []
            day = t // 24
            for order in market:
                if not isinstance(order, list) or not order:
                    continue
                op = order[0]
                if op == "BUY_SEED" and len(order) >= 3:
                    crop, n = order[1], int(order[2])
                    self.seed_buys[crop] = self.seed_buys.get(crop, 0) + n
                    self.crop_first_buy.setdefault(crop, t)
                elif op == "BUY_ANIMAL" and len(order) >= 3:
                    animal, n = order[1], int(order[2])
                    self.animal_buys[animal] = self.animal_buys.get(animal, 0) + n
                    if self.first_animal_step is None:
                        self.first_animal_step = t
                elif op == "BUY_PRODUCT" and len(order) >= 3:
                    self.product_buys[order[1]] = self.product_buys.get(order[1], 0) + int(order[2])
                elif op == "SELL" and len(order) >= 3:
                    self.sells[order[1]] = self.sells.get(order[1], 0) + int(order[2])
                elif op == "HIRE":
                    self.hires_per_day[day] = self.hires_per_day.get(day, 0) + 1
                elif op == "BUY_LAND" and self.land_buy_step is None:
                    self.land_buy_step = t
            obs = step[player].get("observation") or {}
            farms = obs.get("farms")
            hour = obs.get("hour", t % 24)
            if farms and hour == 23:
                self.money_curve.append((day, float(farms[player]["money"])))


def profile_summary(profile):
    lines = [f"--- {profile.name} (player {profile.player}) ---"]
    lines.append(f"final money : ${profile.final_money:,.0f}" if profile.final_money else "final money : ?")
    if profile.land_buy_step is not None:
        lines.append(f"land expand : step {profile.land_buy_step} (day {profile.land_buy_step // 24})")
    if profile.first_animal_step is not None:
        lines.append(f"first animal: step {profile.first_animal_step} (day {profile.first_animal_step // 24})")
    total_hires = sum(profile.hires_per_day.values())
    active_days = max(1, len(profile.hires_per_day))
    lines.append(f"hiring      : {total_hires} hires over {active_days} days "
                 f"(avg {total_hires / active_days:.1f}/day)")
    lines.append(f"seed buys   : {profile.seed_buys}")
    lines.append(f"animal buys : {profile.animal_buys}")
    lines.append(f"product buys: {profile.product_buys}")
    lines.append(f"sold        : {profile.sells}")
    return "\n".join(lines)


def compare_profiles(paths_players):
    """Aggregate table across several (path, player) pairs."""
    profiles = [ReplayProfile(p, pl) for p, pl in paths_players]
    for prof in profiles:
        print(profile_summary(prof))
    return profiles


# Well-known local replay files.
LEADERS = {
    "KAWASHIGI": r"replays\LEADER DATA\KAWASHIGI.json",
    "Ryo Hasegawa": r"replays\LEADER DATA\Ryo Hasegawa-8-22-2026.json",
    "Arman Tuganbaev": r"replays\LEADER DATA\Arman Tuganbaev.json",
    "tetsuya": r"replays\LEADER DATA\tetsuya.json",
}


def leader_ghost(name, player=0):
    return GhostOpponent(LEADERS[name], player=player)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    import os
    os.chdir(root)

    parser = argparse.ArgumentParser(description="Analyze opponent replays")
    parser.add_argument("--names", nargs="*", default=list(LEADERS))
    parser.add_argument("--player", type=int, default=0)
    args = parser.parse_args()

    for name in args.names:
        print(profile_summary(ReplayProfile(LEADERS[name], args.player)))
        print()
