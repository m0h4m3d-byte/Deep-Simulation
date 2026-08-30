"""
Phase 1 — isolated _compute_zones / _zone_for_pos
لا يعتمد على planner.py — اختبار منطق التقسيم فقط
"""

def _compute_zones(tiles, num_workers):
    """
    tiles: 10x10 list — للاختبار فاضية، لاحقًا نحترم LOCKED
    num_workers: عدد العمال
    ترجع: list of (x0, y0, x1, y1) inclusive
    المنطق المصحح: تقسيم شبكي ثنائي الأبعاد (grid) زي Crop Dusta NW/NE/SW/SE
      cols = ceil(sqrt(n)), rows = ceil(n/cols) — يضمن مربعات تقريبية لا شرائح
      والصف الأخير يتسع ليغطي كامل العرض لو العدد لا يملأ الشبكة (لا فجوات)
    """
    import math
    H = len(tiles)
    W = len(tiles[0]) if H else 0
    n = num_workers
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols) if cols else 1
    base_h, rem_h = divmod(H, rows)
    row_heights = [base_h + (1 if r < rem_h else 0) for r in range(rows)]
    row_y0 = []
    y = 0
    for h in row_heights:
        row_y0.append(y)
        y += h

    zones = []
    idx = 0
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


def _zone_for_pos(pos, zones):
    """pos: (x,y) -> index الزون، أو 0 لو خارج"""
    x, y = pos
    for idx, (x0, y0, x1, y1) in enumerate(zones):
        if x0 <= x <= x1 and y0 <= y <= y1:
            return idx
    return 0  # fallback


def _zone_for_worker_naive(worker_pos, zones):
    """الطريقة الساذجة: حسب موقع العامل الحالي — تفشل لو الكل في نفس النقطة"""
    return _zone_for_pos(worker_pos, zones)


def _zone_for_worker_fixed(worker_idx, zones):
    """الطريقة المصححة: تخصيص ثابت حسب index العامل — يضمن توزيع 1/زون"""
    return worker_idx % len(zones)


def _plant_quota(plant_target, num_zones):
    """كوتة أساسية = ceil(target / zones)"""
    import math
    return math.ceil(plant_target / num_zones) if num_zones else 0


def _quotas_with_full_zone(plant_target, num_zones, full_zone_idx=0):
    """
    سيناريو: زون واحد ممتلئ (لا مكان زراعة)
    - Naïve: يبقى 5 لكل زون المتبقي (مجموع 15 < 20 → نقص)
    - Redistributed: يوزع target كامل على الباقي ceil(20/3)=7 لكل زون
    """
    import math
    base = _plant_quota(plant_target, num_zones)
    naive = [base]*num_zones
    # المحاكاة: الزون الممتلئ لا يمكنه الزراعة، فالـ 5 بتاعته تضيع
    naive_effective = sum(naive[i] for i in range(num_zones) if i != full_zone_idx)

    remaining_zones = num_zones - 1
    redistributed_quota = math.ceil(plant_target / remaining_zones) if remaining_zones else 0
    redistributed = []
    total_redist = 0
    for i in range(num_zones):
        if i == full_zone_idx:
            redistributed.append(0)  # ممتلئ
        else:
            redistributed.append(redistributed_quota)
            total_redist += redistributed_quota
    return base, naive_effective, redistributed_quota, total_redist, naive, redistributed


# --- Phase 4: Triple safeguard for helping neighbor ---
def _zone_has_work(zone_idx, zone_tasks):
    """
    zone_tasks: dict {zone_idx: {'PLANT':int,'WATER':int,'HARVEST':int,'DIG':int}}
    ترجع True لو فيه أي شغل متبقي في الزون (PLANT/WATER/HARVEST/DIG >0)
    """
    t = zone_tasks.get(zone_idx, {})
    return (t.get('PLANT', 0) > 0) or (t.get('WATER', 0) > 0) or (t.get('HARVEST', 0) > 0) or (t.get('DIG', 0) > 0)


def _can_help(worker_idx, helped_today_set, worker_zone, zone_tasks):
    """
    الضابط الثلاثي: can_help = (لم يساعد اليوم) AND (زونه فاضي فعليًا 100%)
    - helped_today_set: set of worker_idx who already helped
    - zone_tasks: كما فوق
    """
    if worker_idx in helped_today_set:
        return False
    if _zone_has_work(worker_zone, zone_tasks):
        return False
    return True


# ── Unit test بسيط ──
if __name__ == "__main__":
    tiles = [[None]*10 for _ in range(10)]  # فاضية بالكامل 10x10
    zones = _compute_zones(tiles, num_workers=4)
    print("=== _compute_zones(tiles=10x10 empty, num_workers=4) ===")
    for i, (x0, y0, x1, y1) in enumerate(zones):
        w = x1 - x0 + 1
        h = y1 - y0 + 1
        print(f"  Zone {i}: x0={x0} y0={y0} x1={x1} y1={y1}  (w={w} h={h} area={w*h})")
    print(f"  Total zones: {len(zones)}  Coverage check: sum areas = {sum((x1-x0+1)*(y1-y0+1) for x0,y0,x1,y1 in zones)} / 100")

    print("\n=== _zone_for_pos (2x2 grid NW/NE/SW/SE) ===")
    # للـ 2x2: 0=NW [0-4,0-4], 1=NE [5-9,0-4], 2=SW [0-4,5-9], 3=SE [5-9,5-9]
    tests = {
        (0, 0): 0,   # NW corner
        (4, 4): 0,   # آخر خلية NW
        (5, 0): 1,   # NE top edge
        (9, 4): 1,   # NE corner
        (0, 5): 2,   # SW
        (4, 9): 2,   # SW corner
        (9, 9): 3,   # SE
        (5, 5): 3,   # SE start
    }
    for pos, expected in tests.items():
        got = _zone_for_pos(pos, zones)
        status = "OK" if got == expected else "FAIL"
        print(f"  pos {pos} -> zone {got}  (expected {expected})  [{status}]")

    from collections import Counter
    c = Counter(_zone_for_pos((x, y), zones) for y in range(10) for x in range(10))
    print(f"\n  Cells per zone: {dict(c)}  (should sum 100, each ~25)")

    # ── المرحلة 2: تخصيص العمال ──
    print("\n=== Phase 2: zone_for_worker (4 workers starting at shed (4,4)) ===")
    workers = [(4, 4), (4, 4), (4, 4), (4, 4)]  # الواقع: كل العمال يبدأوا من الشيد نفس النقطة
    print("  Naïve (_zone_for_pos from pos):")
    naive_counts = Counter(_zone_for_worker_naive(pos, zones) for pos in workers)
    for i, pos in enumerate(workers):
        z = _zone_for_worker_naive(pos, zones)
        print(f"    worker {i} at {pos} -> zone {z}")
    print(f"    Result counts per zone: {dict(sorted(naive_counts.items()))}  (expected 1 per zone, got {dict(naive_counts)})")
    crowded = len(naive_counts) == 1 and naive_counts[0] == 4
    print(f"    => {'CROWDED FAIL: all 4 in same zone!' if crowded else 'OK'}")

    print("\n  Fixed (worker_idx % num_zones):")
    fixed_counts = Counter(_zone_for_worker_fixed(i, zones) for i in range(4))
    for i in range(4):
        z = _zone_for_worker_fixed(i, zones)
        print(f"    worker {i} -> zone {z}")
    print(f"    Result counts per zone: {dict(sorted(fixed_counts.items()))}  (expected {{0:1,1:1,2:1,3:1}})")
    print(f"    => {'OK: equal 1/zone' if fixed_counts == Counter({0:1,1:1,2:1,3:1}) else 'FAIL'}")

    # ── المرحلة 3: كوتة الزراعة ──
    print("\n=== Phase 3: plant_quota (plant_target=20, num_zones=4) ===")
    base, naive_eff, redis_q, total_redis, naive_list, redis_list = _quotas_with_full_zone(20, 4, full_zone_idx=0)
    print(f"  Base quota_per_zone = ceil(20/4) = {base}  -> {naive_list} total={sum(naive_list)} (expected 5 each)")
    print(f"  Scenario: Zone 0 full (25 tiles occupied, 0 empty)")
    print(f"    Naive fixed quota: each remaining zone keeps 5 -> effective total {naive_eff} (zones 1-3) < target 20 => SHORT by {20 - naive_eff} plants")
    print(f"    Redistributed: target 20 on 3 remaining zones -> ceil(20/3)={redis_q} each -> {redis_list} total={total_redis} (>=20, covers shortfall)")
    print(f"    => Redistributed compensates the lost quota from full zone")

    # ── المرحلة 4: الضابط الثلاثي لمساعدة الجار ──
    print("\n=== Phase 4: Triple safeguard (can_help) ===")
    # zone_tasks يحاكي حالة كل زون: 0=فاضي تمامًا، 1=يبدو فاضي لكن فيه WATER
    scenarios = {
        "A: Zone truly empty (PLANT0 WATER0 HARVEST0 DIG0, not helped)": (0, {0: {'PLANT':0,'WATER':0,'HARVEST':0,'DIG':0}}, set(), True),
        "B: Looks empty (quota done) but WATER 2 remains": (0, {0: {'PLANT':0,'WATER':2,'HARVEST':0,'DIG':0}}, set(), False),
        "C: Truly empty but already helped today": (0, {0: {'PLANT':0,'WATER':0,'HARVEST':0,'DIG':0}}, {0}, False),
        "D: Has DIG 1 remaining": (0, {0: {'PLANT':0,'WATER':0,'HARVEST':0,'DIG':1}}, set(), False),
        "E: Has HARVEST 1 remaining": (0, {0: {'PLANT':0,'WATER':0,'HARVEST':1,'DIG':0}}, set(), False),
        "F: Different zone has work, but my zone empty -> can help": (1, {1: {'PLANT':0,'WATER':0,'HARVEST':0,'DIG':0}, 0: {'PLANT':1}}, set(), True),
    }
    for name, (worker_zone, tasks, helped, expected) in scenarios.items():
        got = _can_help(0, helped, worker_zone, tasks)
        # worker_idx=0 for simplicity; for F we test worker in zone1
        if "F:" in name:
            got = _can_help(1, helped, 1, tasks)
        status = "OK" if got == expected else "FAIL"
        detail = f"zone {worker_zone} tasks {tasks.get(worker_zone,{})}, helped={helped}"
        print(f"  {name}")
        print(f"    -> can_help={got} (expected {expected}) [{status}]  {detail}")

    print("\n  Key check B: quota done but WATER remains -> correctly BLOCKED (not helping)")
    print("  This was the exact bug in old design: checking quota only, not WATER/HARVEST/DIG")

    # اختبار إضافي: 7 و 12 عامل — يوضح تعميم الشبكة
    for n in [7, 12]:
        z = _compute_zones(tiles, n)
        import math
        cols = math.ceil(math.sqrt(n)); rows = math.ceil(n/cols)
        print(f"\n  n={n} -> grid {cols}x{rows} = {cols*rows} cells, using {n}:")
        for i, (x0, y0, x1, y1) in enumerate(z):
            w, h = x1-x0+1, y1-y0+1
            print(f"    Zone {i}: x0={x0} x1={x1} y0={y0} y1={y1} w={w} h={h} area={w*h}")
        cc = Counter(_zone_for_pos((x, y), z) for y in range(10) for x in range(10))
        print(f"    Cells per zone (grid): {dict(sorted(cc.items()))} sum={sum(cc.values())}")
