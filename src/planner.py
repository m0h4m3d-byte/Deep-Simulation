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

from src.constants import (
    CROP_CONFIG, SHED_TILES, COOP_POS,
)
from src.economy import PLAN, PASTURE_BUFFER, MarketEngine, ANIMAL_ADVISOR_ON
from src.config import (
    CROP_ADVISOR_ON,
    MELON_LAST_DAY, STRAWBERRY_LAST_DAY,
    PLANT_TARGET_FULL, PLANT_TARGET_LATE,
    STRAW_LEAD_THRESHOLD, ADVISOR_MIN_DAY,
    LAST_PLAYABLE_DAY,
    PASTURE_LOCATIONS,
)

# --- Day gates (were src/strategy.py — logic lives here, numbers live in config.py) ---
def is_melon_season(day: int) -> bool:
    return day <= MELON_LAST_DAY

def is_strawberry_season(day: int) -> bool:
    return day <= STRAWBERRY_LAST_DAY

def plant_target(day: int) -> int:
    return PLANT_TARGET_FULL if day <= STRAWBERRY_LAST_DAY else PLANT_TARGET_LATE


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
    try:
        from src.decision_engine import project_harvest_prices
        proj = project_harvest_prices(market_ctx)
    except Exception:
        proj = {}

    straw_active = is_strawberry_season(day)
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


def _crop_season_active(crop, day):
    if crop == "STRAWBERRY":
        return is_strawberry_season(day)
    if crop == "MELON":
        return is_melon_season(day)
    return True

# ============================================================
# Phase 3: Maturity Tracker
# ============================================================
# The season is 30 days (obs day 0..29). A crop planted on day d can first
# be harvested from day d + first_yield_day, so any planting with
# d + first_yield_day > LAST_PLAYABLE_DAY can never yield (baseline wasted seeds,
# tiles and labor: wheat planted day 28, strawberry planted days 20-22).
# LAST_PLAYABLE_DAY lives in config.py (imported above).


def expected_ready_day(crop: str, planted_day: int) -> int:
    """Maturity Tracker: the day a crop first becomes harvestable."""
    return planted_day + CROP_CONFIG[crop]["first_yield_day"]


# ============================================================
# ZoneManager — rebuilt from scratch (zone-based-v2)
# 4 components: 2×2 grid, fair worker_idx % num_zones, dynamic quota, triple help guard
# ============================================================
import math as _zm_math


class ZoneManager:
    def __init__(self, tiles, num_workers, plant_target=20):
        self.tiles = tiles
        self.num_workers = num_workers
        self.plant_target = plant_target
        self.zones = self._compute_zones(tiles, num_workers)
        self.helped_today = set()
        self.base_quota = _zm_math.ceil(plant_target / num_workers) if num_workers else 0

    @staticmethod
    def _compute_zones(tiles, num_workers):
        H = len(tiles)
        W = len(tiles[0]) if H else 0
        n = num_workers
        cols = _zm_math.ceil(_zm_math.sqrt(n))
        rows = _zm_math.ceil(n / cols) if cols else 1
        base_h, rem_h = divmod(H, rows)
        row_heights = [base_h + (1 if r < rem_h else 0) for r in range(rows)]
        row_y0 = []
        y = 0
        for h in row_heights:
            row_y0.append(y)
            y += h
        zones = []
        for r in range(rows):
            remaining = n - len(zones)
            cols_this_row = cols if r < rows - 1 else remaining
            if cols_this_row <= 0:
                break
            base_w, rem_w = divmod(W, cols_this_row)
            col_widths = [base_w + (1 if c < rem_w else 0) for c in range(cols_this_row)]
            col_x0 = []
            x = 0
            for w in col_widths:
                col_x0.append(x)
                x += w
            for c in range(cols_this_row):
                x0 = col_x0[c]
                x1 = x0 + col_widths[c] - 1
                y0 = row_y0[r]
                y1 = y0 + row_heights[r] - 1
                zones.append((x0, y0, x1, y1))
                if len(zones) >= n:
                    break
        return zones

    @staticmethod
    def _zone_for_pos(pos, zones):
        x, y = pos
        for idx, (x0, y0, x1, y1) in enumerate(zones):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return idx
        return 0

    def zone_for_worker(self, worker_idx):
        return worker_idx % len(self.zones) if self.zones else 0

    def quota_for_zone(self, zone_idx, zone_empty_counts=None):
        if zone_empty_counts is not None:
            empty = zone_empty_counts.get(zone_idx, 25)
            if empty == 0:
                return 0
        return self.base_quota

    def can_help(self, worker_idx, zone_tasks):
        if worker_idx in self.helped_today:
            return False
        my_zone = self.zone_for_worker(worker_idx)
        tasks = zone_tasks.get(my_zone, {})
        has_work = (tasks.get('PLANT', 0) > 0 or tasks.get('WATER', 0) > 0 or
                    tasks.get('HARVEST', 0) > 0 or tasks.get('DIG', 0) > 0)
        return not has_work

    def mark_helped(self, worker_idx):
        self.helped_today.add(worker_idx)

    def reset_day(self):
        self.helped_today.clear()


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
        self.zones = []
        self.zone_helped = set()
        self._zone_mgr = None

    def on_day(self, day: int):
        """Roll over the day; a fresh game (day 0) resets everything."""
        if day != self.day:
            self.day = day
            self.unit_task = {}
            self.zone_helped = set()
            if self._zone_mgr:
                self._zone_mgr.reset_day()

    @staticmethod
    def _count_structs(tiles, kind: str) -> int:
        return sum(1 for row in tiles for t in row
                   if isinstance(t, dict) and t.get("kind") == kind)

    # weed-priority experiment: when weeds accumulate, DIG jumps above PLANT/WATER
    WEED_PRIORITY_THRESHOLD = 15  # j5rb 15-20 kama tlb, default 15
    WEED_PRIORITY_PRIO = 1  # foq zra3a (2) w ta7t FEED(0)

    def collect_jobs(self, day: int, tiles, shed, seeds, invs,
                     animals_ordered: Dict[str, int],
                     market_ctx: Optional[dict] = None) -> List[tuple]:
        """Build the priority-sorted job queue. Mirrors Agent._collect_jobs."""
        jobs = []
        _hour = market_ctx.get("hour", 0) if market_ctx else 0
        _is_final = (day == 29 and _hour >= 14)  # last 10 turns 710-719: deposit only
        # count weeds up front (handles dict kind==WEED and string "WEED")
        _weed_count = 0
        for _r in tiles:
            for _t in _r:
                if _t is None:
                    continue
                if isinstance(_t, str) and _t == "WEED":
                    _weed_count += 1
                elif isinstance(_t, dict) and _t.get("kind") == "WEED":
                    _weed_count += 1
        _dig_prio = self.WEED_PRIORITY_PRIO if _weed_count >= self.WEED_PRIORITY_THRESHOLD else 3
        melon_cap = 28
        melon_on_field = sum(1 for row in tiles for t in row
                             if isinstance(t, dict) and t.get("kind") == "PLANT"
                             and t.get("crop") == "MELON")
        wheat_available = shed.get("WHEAT", 0) > 0 or any(i.get("WHEAT", 0) > 0 for i in invs)
        for y in range(10):
            for x in range(10):
                if _is_final:
                    continue  # final 10 turns: skip all farm jobs, only DEPOSIT
                t = tiles[y][x]
                if isinstance(t, dict) and "animal" in t:
                    pos = (x, y)
                    if not t.get("fed_today") and wheat_available:
                        jobs.append((pos, "FEED", 0))
                    if not t.get("cared_today"):
                        jobs.append((pos, "CARE", 1))
                    if t.get("fertilizer_available"):
                        jobs.append((pos, "COLLECT_FERTILIZER", 1))
                    if t.get("yield_units", 0) > 0 and not _is_final:
                        jobs.append((pos, "HARVEST", 2))
                elif isinstance(t, dict) and t.get("kind") == "PLANT":
                    pos = (x, y)
                    cd = CROP_CONFIG[t["crop"]]
                    age = day - t["planted_day"]
                    ready = t.get("yield_units", 0) > 0 and (cd["is_ongoing"] or age >= cd["first_yield_day"])
                    if ready and not _is_final:
                        jobs.append((pos, "HARVEST", 2))
                    elif not t.get("watered_today"):
                        jobs.append((pos, "WATER", 2))
                    if t.get("fertilized_until_day", -1) < day:
                        if cd["is_ongoing"] and age >= cd["first_yield_day"]:
                            jobs.append((pos, "FERTILIZE", 5))
                elif isinstance(t, dict) and t.get("kind") == "WEED":
                    # weed-priority branch: when _weed_count >=15, DIG@1 foq zra3a
                    # (Phase 1 DIG@1 crash was with unconditional prio 1; here it's
                    # conditional threshold, so watering not starved in clean fields)
                    jobs.append(((x, y), "DIG", _dig_prio))
                elif isinstance(t, str) and t == "WEED":
                    jobs.append(((x, y), "DIG", _dig_prio))

                # Phase 5 verdict: strict JIT (build ONLY for unplaced animals) was
        # benchmarked and REVERTED - purchase-wave latency shrank the herd
        # (wool 118 -> 69 units/game) and score fell $81,479 -> $74,982.
        # Empirically best: pens = animals ORDERED + PASTURE_BUFFER (2).
        # Purchases arrive in a continuous stream, so pens are ready just
        # before animals; the 2-tile buffer is the only empty-pen waste.
        # Geometry note: total pens can never sit full while an animal is
        # unplaced (pens > placed and pens = ordered+2 > animals >= placed),
        # so the count below (existing pens of ANY occupancy) is deadlock-free.
        _hour = market_ctx.get("hour", 0) if market_ctx else 0
        FIXED_PASTURES_5 = [(4,2), (3,3), (4,3), (3,4), (4,4)]
        if day <= 2 and not _is_final:
            total_pastures = self._count_structs(tiles, "PASTURE")
            pasture_jobs = total_pastures
            for p in FIXED_PASTURES_5:
                t = tiles[p[1]][p[0]]
                if t is None and pasture_jobs < 5:
                    jobs.append((p, "BUILD_PASTURE", 2))
                    pasture_jobs += 1
                elif isinstance(t, dict) and t.get("kind") == "PASTURE" and "animal" not in t:
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
        _skip_build_day0 = (day == 0 and _hour < 12)
        if not _skip_build_day0 and not _is_final and day > 2:
            build_target = min(PLAN["COW"] + PLAN["SHEEP"],
                               sum(animals_ordered.get(k, 0) for k in ("COW", "SHEEP")) + PASTURE_BUFFER)
            total_pastures = self._count_structs(tiles, "PASTURE")
            pasture_jobs = total_pastures
            for p in PASTURE_LOCATIONS:
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

        active = {"WHEAT": True, "MELON": is_melon_season(day),
                  "STRAWBERRY": is_strawberry_season(day)}
        if CROP_ADVISOR_ON and market_ctx:
            crop_order = _advisor_crop_order(day, market_ctx)
        else:
            crop_order = list(DEFAULT_CROP_ORDER)
        shed_tiles = set(SHED_TILES)
        plant_count = sum(1 for row in tiles for t in row
                          if isinstance(t, dict) and t.get("kind") == "PLANT")
        p_target = plant_target(day)
        # Fixed NW 20+5 for high efficiency (weeds low, escapes zero) - verified 85385
        FIXED_NW_20 = [
            (0,0,"MELON"), (1,0,"MELON"), (2,0,"MELON"), (3,0,"MELON"), (4,0,"MELON"),
            (0,1,"WHEAT"), (1,1,"WHEAT"), (2,1,"WHEAT"), (3,1,"WHEAT"), (4,1,"WHEAT"),
            (0,2,"WHEAT"), (1,2,"WHEAT"), (2,2,"WHEAT"), (3,2,"WHEAT"),
            (0,3,"WHEAT"), (1,3,"WHEAT"), (2,3,"WHEAT"),
            (0,4,"STRAWBERRY"), (1,4,"STRAWBERRY"), (2,4,"WHEAT"),
        ]
        FIXED_NW_PASTURES_5 = [(4,2), (3,3), (4,3), (3,4), (4,4)]
        # Use fixed NW for days 0-2, sorted by distance to shed for minimal moves
        if day <= 2:
            all_nw = [(x,y,c) for x,y,c in FIXED_NW_20] + [(x,y,"PASTURE") for x,y in FIXED_NW_PASTURES_5]
            all_nw_sorted = sorted(all_nw, key=lambda pp: min(abs(pp[0]-sx)+abs(pp[1]-sy) for sx,sy in SHED_TILES))
            for x, y, fixed_crop in all_nw_sorted:
                if (x, y) in shed_tiles or tiles[y][x] == "LOCKED":
                    continue
                if fixed_crop == "PASTURE":
                    continue
                if tiles[y][x] is not None:
                    continue
                if plant_count >= p_target:
                    break
                crop = fixed_crop
                if not active.get(crop) or seeds.get(crop, 0) <= 0:
                    continue
                if crop == "MELON" and melon_on_field >= melon_cap:
                    continue
                if day + CROP_CONFIG[crop]["first_yield_day"] > LAST_PLAYABLE_DAY:
                    continue
                jobs.append(((x, y), "PLANT", 2, crop))
                plant_count += 1
                if crop == "MELON":
                    melon_on_field += 1
        else:
            for y in range(10):
                for x in range(10):
                    if (x, y) in shed_tiles or tiles[y][x] == "LOCKED":
                        continue
                    if tiles[y][x] is None:
                        if plant_count >= p_target:
                            break
                        for crop in crop_order:
                            if not active.get(crop) or seeds.get(crop, 0) <= 0:
                                continue
                            if crop == "MELON" and melon_on_field >= melon_cap:
                                continue
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
            # in final 10 turns, dump everything (including WHEAT reserve) in one DROP
            if _is_final and any(v > 0 for v in inv.values()):
                # use DROP priority -1 to outrank everything and empty whole inventory at once
                near = min(SHED_TILES, key=lambda s: abs(s[0]) + abs(s[1]))
                jobs.append((near, "DEPOSIT", -1, "__DROP_ALL__", u_idx))
            elif depositable:
                near = min(SHED_TILES, key=lambda s: abs(s[0]) + abs(s[1]))
                dep_prio = -1 if _is_final else 2
                jobs.append((near, "DEPOSIT", dep_prio, depositable[0], u_idx))
        # --- ZoneManager 2×2 rebuild: fixed 4 zones (NW/NE/SW/SE) ---
        try:
            self.zones = ZoneManager._compute_zones([[None]*10 for _ in range(10)], 4)
            self._zone_mgr = ZoneManager(tiles, 4, plant_target=p_target)
            self._zone_mgr.zones = self.zones
            self._zone_mgr.helped_today = self.zone_helped
        except Exception:
            self.zones = [(0, 0, 4, 4), (5, 0, 9, 4), (0, 5, 4, 9), (5, 5, 9, 9)]
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
        # --- Zone-based-v2 filtering (2×2 grid, fair allocation, triple guard) ---
        # Fix trapped worker: compute allowed jobs BEFORE has_work
        def _is_allowed_for_worker(job, w_idx):
            # Base fix: all allowed. Feeder experiment can be enabled by changing this to FEEDER_IDX logic.
            return True

        zones = getattr(self, 'zones', [])
        worker_zone = None
        can_help = True
        zone_tasks = {}
        if zones:
            worker_zone = u_idx % len(zones)
            # build per-zone task counts ONLY from allowed jobs (fix trapped worker)
            for zj in jobs:
                if zj[0] in used_jobs:
                    continue
                if zj[1] == "DEPOSIT":
                    continue
                if not _is_allowed_for_worker(zj, u_idx):
                    continue
                z = ZoneManager._zone_for_pos(zj[0], zones)
                op = zj[1]
                zone_tasks.setdefault(z, {})
                zone_tasks[z][op] = zone_tasks[z].get(op, 0) + 1
            my_tasks = zone_tasks.get(worker_zone, {})
            has_work = any(my_tasks.get(k, 0) > 0 for k in ('PLANT', 'WATER', 'HARVEST', 'DIG', 'BUILD_PASTURE', 'BUILD_COOP', 'PLACE', 'FEED', 'CARE', 'COLLECT_FERTILIZER', 'FERTILIZE'))
            can_help = not has_work
        pick = None
        pick_prio = None
        for j in jobs:
            if j[1] == "DEPOSIT" and len(j) > 4 and j[4] != u_idx:
                continue
            if j[0] in used_jobs:
                continue
            if j[1] == "FEED" and inv.get("WHEAT", 0) <= 0 and shed.get("WHEAT", 0) <= 0:
                continue
            # zone filter: stay in my zone unless triple guard allows helping
            if zones and worker_zone is not None and j[1] != "DEPOSIT":
                job_zone = ZoneManager._zone_for_pos(j[0], zones)
                in_my_zone = (job_zone == worker_zone)
                if not in_my_zone and not can_help:
                    continue
            prio = j[2]
            if j[0] == task_tile:
                prio -= 100
            if j[1] == task_op:
                prio -= 30
            # spatial WATER clustering: prefer WATER over PLANT when prio equal and distance similar (no cost to other tasks)
            prefer = False
            if pick is not None and prio == pick_prio:
                if j[1] == "WATER" and pick[1] == "PLANT":
                    prefer = True
                elif j[1] == "WATER" and pick[1] == "WATER":
                    prefer = self._prefer_tie(j, pick, pos)
                else:
                    prefer = self._prefer_tie(j, pick, pos)
                if prefer or self._prefer_tie(j, pick, pos):
                    pick = j
                    pick_prio = prio
            elif pick is None or prio < pick_prio:
                pick = j
                pick_prio = prio
        if pick is None:
            return ["PASS"]
        # mark triple-guard help
        if zones and worker_zone is not None and pick[1] != "DEPOSIT":
            try:
                _jz = ZoneManager._zone_for_pos(pick[0], zones)
                if _jz != worker_zone:
                    self.zone_helped.add(u_idx)
                    if self._zone_mgr:
                        self._zone_mgr.mark_helped(u_idx)
            except Exception:
                pass
        target, op = pick[0], pick[1]
        if op == "DEPOSIT":
            # final 10 turns: DROP empties whole inventory at once (AGENTS.md: DROP dumps entire inventory)
            if len(pick) > 3 and pick[3] == "__DROP_ALL__":
                if pos == list(target) and any(v > 0 for v in inv.values()):
                    self.unit_task.pop(u_idx, None)
                    return ["DROP"]
                if not any(v > 0 for v in inv.values()):
                    return ["PASS"]
                self.unit_task.pop(u_idx, None)
                return self._step(pos, target)
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