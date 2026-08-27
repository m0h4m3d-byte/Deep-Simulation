"""Dynamic budget — ties PLAN to recent ladder replays (last 5-10 games)."""

import glob
import json
from pathlib import Path


def recommend_plan(replays_dir="replays/LIVE/v18_all", lookback=10) -> dict:
    """Analyze last `lookback` replays, return {COW,SHEEP,WHEAT,STRAWBERRY}."""
    # Fallback to current defaults if no replays
    default = {"COW": 15, "SHEEP": 3, "WHEAT": 30, "STRAWBERRY": 45}
    files = sorted(glob.glob(f"{replays_dir}/*.json"), key=lambda p: Path(p).stat().st_mtime)[-lookback:]
    if len(files) < 5:
        return default
    crash = 0
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
            # Find our player index
            names = (d.get("info") or {}).get("TeamNames") or []
            oi = 0
            for i, n in enumerate(names):
                if "m0h4m3d" in str(n).lower():
                    oi = i
            # Milk crash = min price < 80
            mmin = min(
                (p.get("MILK") for t, step in enumerate(d["steps"])
                 for p in [((step[oi].get("observation") or {}).get("market", {}).get("prices") or {})]
                 if p.get("MILK")),
                default=160,
            )
            if mmin < 80:
                crash += 1
        except Exception:
            continue
    crash_rate = crash / len(files)
    # Top players' wheat is 60 vs our old 192 — we already cut to 30.
    # Further cut to 15-19 if crash_rate high (wheat is safe in crashes, but
    # we want more sheep to hedge milk).
    wheat = 30 if crash_rate < 0.3 else 19 if crash_rate > 0.5 else 25
    # Herd: more crashes → fewer cows, more sheep
    if crash_rate > 0.4:
        cow, sheep = 8, 7
    elif crash_rate > 0.25:
        cow, sheep = 11, 5
    else:
        cow, sheep = 15, 3
    return {"COW": cow, "SHEEP": sheep, "WHEAT": wheat, "STRAWBERRY": 45}
