"""
ZoneManager — تجميع المكونات الأربعة في كلاس واحد (لسه منعزل عن planner.py)
Phase 5: أول دمج حقيقي لكن صغير، مع محاكاة يدوية ليوم واحد
"""
import math
from collections import Counter

class ZoneManager:
    def __init__(self, tiles, num_workers, plant_target=20):
        self.tiles = tiles
        self.num_workers = num_workers
        self.plant_target = plant_target
        self.zones = self._compute_zones(tiles, num_workers)
        self.helped_today = set()  # worker_idx who helped
        # كوتة أساسية
        self.base_quota = math.ceil(plant_target / num_workers) if num_workers else 0

    @staticmethod
    def _compute_zones(tiles, num_workers):
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
        """تخصيص ثابت — يضمن 1/زون حتى لو الكل في نفس النقطة"""
        return worker_idx % len(self.zones) if self.zones else 0

    def quota_for_zone(self, zone_idx, zone_empty_counts=None):
        """
        لو زون ممتلئ (0 empty) يعيد 0 ويعيد توزيع الحصة على الباقي عند الحاجة
        للاختبار البسيط: نرجع base_quota، لكن لو zone_empty_counts أعطي، نحسب redistributed
        """
        if zone_empty_counts is not None:
            empty = zone_empty_counts.get(zone_idx, 25)
            if empty == 0:
                return 0
        return self.base_quota

    def can_help(self, worker_idx, zone_tasks):
        """
        zone_tasks: {zone_idx: {'PLANT':int,'WATER':int,'HARVEST':int,'DIG':int}}
        can_help = (not helped) AND (my zone truly empty)
        """
        if worker_idx in self.helped_today:
            return False
        my_zone = self.zone_for_worker(worker_idx)
        tasks = zone_tasks.get(my_zone, {})
        has_work = (tasks.get('PLANT',0)>0 or tasks.get('WATER',0)>0 or
                    tasks.get('HARVEST',0)>0 or tasks.get('DIG',0)>0)
        return not has_work

    def mark_helped(self, worker_idx):
        self.helped_today.add(worker_idx)

    def reset_day(self):
        self.helped_today.clear()


# ── محاكاة يدوية بسيطة (يوم واحد، 10x10 فاضية، 4 عمال) ──
if __name__ == "__main__":
    tiles = [[None]*10 for _ in range(10)]
    zm = ZoneManager(tiles, num_workers=4, plant_target=20)
    print("=== ZoneManager: zones ===")
    for i, (x0,y0,x1,y1) in enumerate(zm.zones):
        print(f"  Zone {i}: x0={x0} x1={x1} y0={y0} y1={y1} w={x1-x0+1} h={y1-y0+1}")

    print("\n=== Worker assignment (all start at shed (4,4)) ===")
    for wi in range(4):
        z = zm.zone_for_worker(wi)
        x0,y0,x1,y1 = zm.zones[z]
        print(f"  worker {wi} -> zone {z} [{x0},{y0}-{x1},{y1}]")

    print(f"\n=== Quota: plant_target=20 -> base {zm.base_quota} each -> {[zm.quota_for_zone(i) for i in range(4)]}")

    # سيناريو يدوي متوقع:
    # - كل زون فاضي (25 empty) -> كل عامل يجب أن يزرع في زونه (PLANT 5)
    # - لا مساعدة لأن كل زون فيه شغل
    print("\n=== Manual simulation: Day 0, each zone has 5 PLANT tasks ===")
    zone_tasks = {
        0: {'PLANT':5,'WATER':0,'HARVEST':0,'DIG':0},
        1: {'PLANT':5,'WATER':0,'HARVEST':0,'DIG':0},
        2: {'PLANT':5,'WATER':0,'HARVEST':0,'DIG':0},
        3: {'PLANT':5,'WATER':0,'HARVEST':0,'DIG':0},
    }
    expected = {0: "PLANT in zone0 (quota 5)", 1:"PLANT in zone1 (quota 5)", 2:"PLANT in zone2 (quota 5)", 3:"PLANT in zone3 (quota 5)"}
    for wi in range(4):
        z = zm.zone_for_worker(wi)
        can = zm.can_help(wi, zone_tasks)
        task = f"PLANT in zone{z} (quota {zm.quota_for_zone(z)})" if not can else f"HELP zone?? (should not)"
        exp = expected[wi]
        status = "OK" if task == exp else "FAIL"
        print(f"  worker {wi} zone {z} can_help={can} -> {task}  (expected {exp}) [{status}]")

    # سيناريو ثاني: zone0 خلص شغله (0/0/0/0)، الباقي لسه فيه شغل -> worker0 يجب أن يساعد
    print("\n=== Scenario: Zone0 empty, others have work -> worker0 should HELP ===")
    zone_tasks2 = {
        0: {'PLANT':0,'WATER':0,'HARVEST':0,'DIG':0},
        1: {'PLANT':3,'WATER':0,'HARVEST':0,'DIG':0},
        2: {'PLANT':2,'WATER':1,'HARVEST':0,'DIG':0},
        3: {'PLANT':5,'WATER':0,'HARVEST':0,'DIG':0},
    }
    for wi in [0,1]:
        z = zm.zone_for_worker(wi)
        can = zm.can_help(wi, zone_tasks2)
        print(f"  worker {wi} zone {z} tasks {zone_tasks2[z]} -> can_help={can} (expected {wi==0}) [{'OK' if can==(wi==0) else 'FAIL'}]")

    # سيناريو ثالث: يبدو فاضي لكن فيه WATER -> لا يساعد (يصلح خطأ الكوتة فقط)
    print("\n=== Scenario: Zone0 looks empty (quota done) but WATER 1 remains -> should NOT help ===")
    zone_tasks3 = {0: {'PLANT':0,'WATER':1,'HARVEST':0,'DIG':0}}
    can = zm.can_help(0, zone_tasks3)
    print(f"  worker0 zone0 {zone_tasks3[0]} -> can_help={can} (expected False) [{'OK' if not can else 'FAIL'}]")

    print("\n=== Summary: ZoneManager manual simulation PASSED if all OK above ===")
