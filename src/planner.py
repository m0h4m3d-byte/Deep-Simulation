"""
planner.py - Farm planner ported VERBATIM from src/main.py (production baseline).

Ports Agent._collect_jobs + Agent._unit_action + Agent._go_to_shed_and_pickup
+ Agent._step + Agent._count_structs. Deliberate divergences from the frozen
monolith are documented below (Phase 3 maturity gate, Phase 4 layout); the
market side (hiring/seeds/land/sell) stays step-identical to baseline and is
pinned by tests/test_market_parity.py.

Design notes:
  * Jobs and actions keep the monolith's RAW formats (job tuples, action
    lists) - no Task wrapper - to keep the port line-for-line.
  * _step is the monolith's x-first stepper (main.py:388-395). The separate
    navigation.get_direction (axis-dominant) is intentionally NOT used here.
  * Crop readiness uses CROP_CONFIG (constants.py) whose "first_yield_day" /
    "is_ongoing" match the monolith's CROPS["fy"] / ["ongoing"] exactly.

Phase 1 & 2 experiments (all benchmarked, ALL reverted to baseline):
  * Row-by-row planting          : peak plants 49 vs 60, no score gain  -> REVERTED
  * DIG priority 1 / containment : -$14k (chasing weeds starves watering) -> REVERTED
  * Hire law 2+day/3             : hands reset daily -> -$45k           -> REVERTED
  * Worker specialization (x2)   : -$11k..-$20k (locked-in animal units,
                                   half the planting/watering)          -> REVERTED
baseline's global priority pool is the empirically best allocator.

Phase 4 (competitor-replay-driven, benchmark-gated):
  * Pasture reduction     : build buffer 4 -> 2 (PASTURE_BUFFER) and the
    baseline cap fixed (it never incremented while emitting, so all 28 pasture
    positions were built, burning ~10 tiles of permanent crop capacity).
    Peak herd measured 11-12 vs the 18-tile plan - every freed tile is
    crop capacity.
  * Center-outward emission TRIED and REVERTED: sorted plant emission
    flooded the field with melons (short season 0-13), peak plants
    59.0 -> 53.8 and avg $72,722 -> $71,767. baseline row-major + nearest-tie
    stays as the empirically best field order.
  * Hiring stays baseline (min(12, 3+day)) - already >= 5 workers by day 3 vs
    the observed competitor pattern of 5 by day 6; the 2+day/3 law crashed.

Phase 5 (leaderboard-driven efficiency, benchmark-gated):
  * Just-in-time pastures  : strict JIT (build ONLY for unplaced animals)
    was tried and REVERTED - purchase latency shrank the herd
    (wool 118 -> 69 units/game, day-15 cash $7,138 -> $438) and score fell
    $81,479 -> $74,982. Ordered + 2-buffer pens (Phase 4) is the measured
    optimum; the 2 empty-pen tiles are the only waste, and geometry proves
    the pipeline cannot stall (pens = ordered+2 > animals >= placed).
  * Dead-end task clear    : clearing stale unit_task was tried with the
    JIT run ($78,272 avg) and REVERTED - mid-approach redirection costs
    more trips than it saves; baseline's approach affinity stays.
"""

from typing import Dict, List, Optional, Set, Tuple

import os

from src.constants import (
    CROP_CONFIG, SHED_TILES, PASTURE_POS, COOP_POS,
)
from src.economy import PLAN, PASTURE_BUFFER, MarketEngine, ANIMAL_ADVISOR_ON
from src.strategy import strategy

# ============================================================
# Phase 13: Market-adaptive crop selection (DeepSim project).
# ON by default (30-seed: $86.3k vs $85.5k, worst seed +$18.7k).
# KAGG_CROP_ADVISOR=0 restores the fixed STRAWBERRY->MELON->WHEAT
# priority (bit-identical pre-Phase-13 behavior).
# Phase 20: AutonomousBrain — when KAGG_AUTONOMOUS=1 the brain decides
# crop order directly via MarketModel; the toggle above is superseded.
# ============================================================
CROP_ADVISOR_ON = os.environ.get("KAGG_CROP_ADVISOR", "1") == "1"

DEFAULT_CROP_ORDER = ("STRAWBERRY", "MELON", "WHEAT")


def _advisor_crop_order(day, market_ctx):
    """Strawberry leads ONLY when its harvest-day projection is healthy.

    Calibration on solo benchmarks:
      * Weak-forever worlds plateau at $160-185 through the whole
        strawberry window (seeds 11/21/22).
      * Recovering worlds are IDENTICAL until ~day 9, then jump to $200+
        when a strawberry-consuming shop unlocks (seeds 1/6/19).
    Therefore no decision before day ADVISOR_MIN_DAY carries signal: every
    world reads ~$160-170 then. Demotion is evaluated daily from day 10 on,
    inside the strawberry planting window (starts day 8, melon ends day 13).
    """
    # Autonomous brain supersedes the calibrated advisor when enabled.
    try:
        from src.autonomous import AUTONOMOUS_ON, AutonomousBrain
        if AUTONOMOUS_ON:
            brain = AutonomousBrain()
            order = brain.choose_crop_order({"day": day, "market": {"prices": market_ctx.get("prices", {}),
                                                                     "inventory": market_ctx.get("inventory", {})},
                                             "town": {"unlocked_shops": market_ctx.get("shops", [])}})
            if order:
                return [c for c in order if c in DEFAULT_CROP_ORDER]
    except Exception:
        pass
    try:
        from src.decision_engine import project_harvest_prices
        proj = project_harvest_prices(market_ctx)
    except Exception:
        proj = {}

    straw_active = strategy.is_strawberry_season(day)
    straw_ok = (straw_active and
                (day < ADVISOR_MIN_DAY or
                 proj.get("STRAWBERRY") is None or
                 proj.get("STRAWBERRY", 0) >= STRAW_LEAD_THRESHOLD))

    order = []
    if straw_ok:
        order.append("STRAWBERRY")
    for crop in DEFAULT_CROP_ORDER:
        if crop == "STRAWBERRY":
            continue
        if _crop_season_active(crop, day):
            order.append(crop)
    if straw_active and not straw_ok:
        order.append("STRAWBERRY")  # still plant some if nothing else fits
    return order or list(DEFAULT_CROP_ORDER)


# Projected strawberry price below which we stop leading with it.
# Calibration: weak-forever worlds plateau at $160-185; recovering worlds
# jump to $200+ the moment a strawberry shop unlocks. 190 sits in the gap.
STRAW_LEAD_THRESHOLD = 190
# Before this day every world projects identically (~$160-170): realized
# shop draws are too few to separate weak from recovering worlds. Day 12 is
# the calibrated optimum: recovering worlds reveal themselves by their day-12
# shop draw, so demotion never fires on false signals (30-seed: +$851 avg,
# 3W/0L/27T, worst-case seed 11 improves +$18.7k).
ADVISOR_MIN_DAY = 12


def _crop_season_active(crop, day):
    if crop == "STRAWBERRY":
        return strategy.is_strawberry_season(day)
    if crop == "MELON":
        return strategy.is_melon_season(day)
    return True

# ============================================================
# Phase 3: Maturity Tracker
# ============================================================
# The season is 30 days (obs day 0..29). A crop planted on day d can first
# be harvested from day d + first_yield_day, so any planting with
# d + first_yield_day > LAST_PLAYABLE_DAY can never yield (baseline wasted seeds,
# tiles and labor: wheat planted day 28, strawberry planted days 20-22).
LAST_PLAYABLE_DAY = 29


def expected_ready_day(crop: str, planted_day: int) -> int:
    """Maturity Tracker: the day a crop first becomes harvestable."""
    return planted_day + CROP_CONFIG[crop]["first_yield_day"]


class FarmPlanner:
    """
    Builds the farm job queue and resolves each unit's next action.

    State kept here mirrors the monolith's Agent attributes:
        unit_task: per-unit in-flight task (pos + op), reset each day.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.day = 0
        self.unit_task = {}

    def on_day(self, day: int):
        """Roll over the day; a fresh game (day 0) resets everything."""
        if day != self.day:
            self.day = day
            self.unit_task = {}

    @staticmethod
    def _count_structs(tiles, kind: str) -> int:
        return sum(1 for row in tiles for t in row
                   if isinstance(t, dict) and t.get("kind") == kind)

    def collect_jobs(self, day: int, tiles, shed, seeds, invs,
                     animals_ordered: Dict[str, int],
                     market_ctx: Optional[dict] = None) -> List[tuple]:
        """Build the priority-sorted job queue. Mirrors Agent._collect_jobs."""
        jobs = []
        melon_cap = 28
        melon_on_field = sum(1 for row in tiles for t in row
                             if isinstance(t, dict) and t.get("kind") == "PLANT"
                             and t.get("crop") == "MELON")
        wheat_available = shed.get("WHEAT", 0) > 0 or any(i.get("WHEAT", 0) > 0 for i in invs)
        for y in range(10):
            for x in range(10):
                t = tiles[y][x]
                if isinstance(t, dict) and "animal" in t:
                    pos = (x, y)
                    if not t.get("fed_today") and wheat_available:
                        jobs.append((pos, "FEED", 0))
                    if not t.get("cared_today"):
                        jobs.append((pos, "CARE", 1))
                    if t.get("fertilizer_available"):
                        jobs.append((pos, "COLLECT_FERTILIZER", 1))
                    if t.get("yield_units", 0) > 0:
                        jobs.append((pos, "HARVEST", 2))
                elif isinstance(t, dict) and t.get("kind") == "PLANT":
                    pos = (x, y)
                    cd = CROP_CONFIG[t["crop"]]
                    age = day - t["planted_day"]
                    ready = t.get("yield_units", 0) > 0 and (cd["is_ongoing"] or age >= cd["first_yield_day"])
                    if ready:
                        jobs.append((pos, "HARVEST", 2))
                    elif not t.get("watered_today"):
                        jobs.append((pos, "WATER", 2))
                    if t.get("fertilized_until_day", -1) < day:
                        if cd["is_ongoing"] and age >= cd["first_yield_day"]:
                            jobs.append((pos, "FERTILIZE", 5))
                elif isinstance(t, dict) and t.get("kind") == "WEED":
                    # Phase 1 experiments (DIG@1, early containment @<=12)
                    # BOTH crashed score ($57k vs $71k): chasing weeds starves
                    # watering/planting. baseline's prio 3 (ignoring weeds) wins.
                    # Restored to baseline parity.
                    jobs.append(((x, y), "DIG", 3))

                # Phase 5 verdict: strict JIT (build ONLY for unplaced animals) was
        # benchmarked and REVERTED - purchase-wave latency shrank the herd
        # (wool 118 -> 69 units/game) and score fell $81,479 -> $74,982.
        # Empirically best: pens = animals ORDERED + PASTURE_BUFFER (2).
        # Purchases arrive in a continuous stream, so pens are ready just
        # before animals; the 2-tile buffer is the only empty-pen waste.
        # Geometry note: total pens can never sit full while an animal is
        # unplaced (pens > placed and pens = ordered+2 > animals >= placed),
        # so the count below (existing pens of ANY occupancy) is deadlock-free.
        build_target = min(PLAN["COW"] + PLAN["SHEEP"],
                           sum(animals_ordered.get(k, 0) for k in ("COW", "SHEEP")) + PASTURE_BUFFER)
        total_pastures = self._count_structs(tiles, "PASTURE")
        # Phase 4 fix: baseline's cap counted only EXISTING pastures and never
        # incremented while emitting, so every PASTURE_POS got a build job
        # (up to 28 pastures!) - ~10 tiles of permanent crop capacity burned.
        # pasture_jobs = existing + queued builds, so the cap actually binds.
        pasture_jobs = total_pastures
        for p in PASTURE_POS:
            t = tiles[p[1]][p[0]]
            if t is None and pasture_jobs < build_target:
                jobs.append((p, "BUILD_PASTURE", 2))
                pasture_jobs += 1
            elif isinstance(t, dict) and t.get("kind") == "PASTURE" and "animal" not in t:
                # Phase 18: sheep-placement priority ONLY while the milk
                # crash pivot is active (v18 ep99844808: 4 sheep shelved
                # 12+ days beside 4-6 EMPTY pens because COW always won the
                # slot). In healthy worlds the baseline COW-first rule is
                # kept bit-for-bit — cows are the better producer there.
                un_cow = MarketEngine._unplaced_animal(invs, shed, "COW")
                un_sheep = MarketEngine._unplaced_animal(invs, shed, "SHEEP")
                crash = bool(market_ctx and market_ctx.get("milk_crash"))
                if ANIMAL_ADVISOR_ON and crash and un_sheep > un_cow and un_sheep > 0:
                    jobs.append((p, "PLACE", 2, "SHEEP"))
                else:
                    for a in ("COW", "SHEEP"):
                        if MarketEngine._unplaced_animal(invs, shed, a) > 0:
                            jobs.append((p, "PLACE", 2, a))
                            break

        coop_target = 1 if animals_ordered.get("GOOSE", 0) > 0 else 0
        if self._count_structs(tiles, "COOP") < coop_target:
            for p in COOP_POS:
                if tiles[p[1]][p[0]] is None:
                    jobs.append((p, "BUILD_COOP", 2))
        for p in COOP_POS:
            t = tiles[p[1]][p[0]]
            if isinstance(t, dict) and t.get("kind") == "COOP" and "animal" not in t:
                if MarketEngine._unplaced_animal(invs, shed, "GOOSE") > 0:
                    jobs.append((p, "PLACE", 2, "GOOSE"))

        active = {"WHEAT": True, "MELON": strategy.is_melon_season(day),
                  "STRAWBERRY": strategy.is_strawberry_season(day)}
        if CROP_ADVISOR_ON and market_ctx:
            crop_order = _advisor_crop_order(day, market_ctx)
        else:
            crop_order = list(DEFAULT_CROP_ORDER)
        shed_tiles = set(SHED_TILES)
        plant_count = sum(1 for row in tiles for t in row
                          if isinstance(t, dict) and t.get("kind") == "PLANT")
        plant_target = strategy.plant_target(day)
        for y in range(10):
            for x in range(10):
                if (x, y) in shed_tiles or tiles[y][x] == "LOCKED":
                    continue
                if tiles[y][x] is None:
                    if plant_count >= plant_target:
                        break
                    for crop in crop_order:
                            if not active.get(crop) or seeds.get(crop, 0) <= 0:
                                continue
                            if crop == "MELON" and melon_on_field >= melon_cap:
                                continue
                            # Maturity Tracker: skip crops whose first yield lands
                            # after the last playable day (day 29) - e.g. wheat
                            # planted on day 28 or strawberry planted after day 19
                            # can never be harvested, wasting seeds, tiles and labor.
                            if day + CROP_CONFIG[crop]["first_yield_day"] > LAST_PLAYABLE_DAY:
                                continue
                            jobs.append(((x, y), "PLANT", 2, crop))
                            plant_count += 1
                            if crop == "MELON":
                                melon_on_field += 1
                            break

        for u_idx, inv in enumerate(invs):
            depositable = [k for k, v in inv.items() if v > 0 and k not in ("WHEAT", "COW", "SHEEP", "GOOSE")]
            if inv.get("WHEAT", 0) > 6:
                depositable.append("WHEAT")
            if depositable:
                near = min(SHED_TILES, key=lambda s: abs(s[0]) + abs(s[1]))
                jobs.append((near, "DEPOSIT", 2, depositable[0], u_idx))
        jobs.sort(key=lambda j: j[2])
        return jobs

    def unit_action(self, pos, u_idx: int, jobs, used_jobs: Set, inv, shed) -> List[str]:
        """Pick a job for one unit and return its action list. Mirrors
        Agent._unit_action, including unit_task bookkeeping."""
        # Phase 5 verdict: clearing stale unit_task the moment its tile
        # stops emitting was benchmarked and REVERTED with the strict JIT
        # run (avg $78,272 vs the $81,479 Phase-4 baseline): redirecting a
        # worker mid-approach costs more trips than it saves (it abandons
        # near-complete walks for far jobs). baseline's approach affinity stays.
        task = self.unit_task.get(u_idx)
        task_tile = (task[0], task[1]) if task else None
        task_op = task[2] if task else None
        pick = None
        pick_prio = None
        for j in jobs:
            if j[1] == "DEPOSIT" and len(j) > 4 and j[4] != u_idx:
                continue
            if j[0] in used_jobs:
                continue
            if j[1] == "FEED" and inv.get("WHEAT", 0) <= 0 and shed.get("WHEAT", 0) <= 0:
                continue
            prio = j[2]
            if j[0] == task_tile:
                prio -= 100
            if j[1] == task_op:
                prio -= 30
            if pick is None or prio < pick_prio or (prio == pick_prio and self._prefer_tie(j, pick, pos)):
                pick = j
                pick_prio = prio
        if pick is None:
            return ["PASS"]
        target, op = pick[0], pick[1]
        if op == "DEPOSIT":
            if pos == list(target) and inv.get(pick[3], 0) > 0:
                self.unit_task.pop(u_idx, None)
                return ["PLACE", pick[3], inv[pick[3]]]
            if inv.get(pick[3], 0) <= 0:
                return ["PASS"]
            self.unit_task.pop(u_idx, None)
            return self._step(pos, target)
        if op == "FEED" and inv.get("WHEAT", 0) <= 0:
            if shed.get("WHEAT", 0) > 0:
                return self._go_to_shed_and_pickup(pos, "WHEAT", min(6, shed.get("WHEAT", 0)))
            return ["PASS"]
        if op == "FERTILIZE" and inv.get("FERTILIZER", 0) <= 0:
            if shed.get("FERTILIZER", 0) > 0:
                return self._go_to_shed_and_pickup(pos, "FERTILIZER", min(6, shed.get("FERTILIZER", 0)))
            return ["PASS"]
        if op == "PLACE" and inv.get(pick[3], 0) <= 0:
            if shed.get(pick[3], 0) > 0:
                return self._go_to_shed_and_pickup(pos, pick[3], 1)
            return ["PASS"]
        if pos != list(target):
            if op in ("FEED", "CARE", "COLLECT_FERTILIZER", "HARVEST"):
                self.unit_task[u_idx] = tuple(target) + (op,)
            else:
                self.unit_task.pop(u_idx, None)
            used_jobs.add(pick[0])
            return self._step(pos, target)
        if op in ("FEED", "CARE", "COLLECT_FERTILIZER", "HARVEST"):
            self.unit_task[u_idx] = tuple(target) + (op,)
        else:
            self.unit_task.pop(u_idx, None)
        used_jobs.add(pick[0])
        if op == "PLACE":
            return ["PLACE", pick[3]]
        if op == "PLANT":
            return ["PLANT", pick[3]]
        return [op]

    def _prefer_tie(self, j, pick, pos) -> bool:
        """baseline tie-break between two equal-priority jobs: nearest distance."""
        return (abs(j[0][0] - pos[0]) + abs(j[0][1] - pos[1]) <
                abs(pick[0][0] - pos[0]) + abs(pick[0][1] - pos[1]))

    def _go_to_shed_and_pickup(self, pos, item: str, n: int) -> List[str]:
        near = min(SHED_TILES, key=lambda s: abs(s[0] - pos[0]) + abs(s[1] - pos[1]))
        if pos == list(near):
            return ["PICKUP", item, n]
        return self._step(pos, near)

    def _step(self, pos, target) -> List[str]:
        tx, ty = target
        fx, fy = pos
        if fx != tx:
            return ["EAST" if tx > fx else "WEST"]
        if fy != ty:
            return ["SOUTH" if ty > fy else "NORTH"]
        return ["PASS"]


# Global instance
planner = FarmPlanner()