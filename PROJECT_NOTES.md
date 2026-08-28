# PROJECT_NOTES — DeepSim Kaggriculture

> ملف تتبع مركزي للمشاكل المكتشفة والمرفوضة — بدل الاعتماد على الذاكرة فقط.
> آخر تحديث: 2026-08-28 — main `a6da650` + right-sized `967e7d3` → `v25`/`v26`

## 1) التحسينات المدمجة في `main` (الستة + no-4th + no-waste + right-sized)

| # | الفرع / الكوميت | الوصف | الأثر المُقاس `Simulator 32` vs `pass` | الحالة |
|---|---|---|---|---|
| 1 | `a711815` `v20: merge early-warning + cap6` | مؤشر مبكر `milk_history <150` + سقف 6 بقرات (15→6) | `78%` local winrate، `cap6` قلب 5W-3L→3W-5L في `crash` | **مدمج** `fc63fc8` |
| 2 | `5dde44f` `market-aware-sell` | `CAPS` حسب `above_target` `MELON25 WOOL30 MILK40 STRAW50 WHEAT150` `src/economy.py:233` | `worst +704` `mean -89` `stdev -238` | **مدمج** `01fa4bd` |
| 3 | `6b1cc26` `weed-priority` | `DIG 3→1` عند `weeds≥15` `src/planner.py:170` | `weeds 32.1→11.9 (-63%)` `worst +2.6k` `mean +456` | **مدمج** `01fa4bd` |
| 4 | `7bcb1aa` `no-4th-land` | إيقاف الأرض الرابعة `if unlocked < len(LAND_COSTS)` `src/economy.py:511` | `+2.1k~+3.3k` `tiles 33→29` `quadrants 4→3` | **مدمج** `9391312` |
| 5 | `49efc80` `no-waste-buying` | `WHEAT 28→27` `STRAW 22→19` `MELON 13 keeps` `COW<=21 SHEEP<=23` `src/economy.py:524,537` | `+70` مجاني `weeds 32.1→32.8` لا ضرر | **مدمج** `cb45531` |
| 6 | `4da9199` `right-sized-plan` | `PLAN STRAW 45→20` `src/economy.py:30` (قريب من `plant_target 11` + هامش) | `+2.4k` `worst +2.5k` `plants 11.2=11.2` | **مدمج** `967e7d3` → `v25 701.0` |
| 7 | `134ccd5` `wheat-right-sized` | `PLAN WHEAT 30→15` `src/economy.py:30` (avg plants 0.25 vs 30 waste) | `worst +6-8k` `stdev -35%` `mean -0.3%` | **مدمج** `a6da650` → `v26` |

> `main` الحالي `a6da650` = الستة + `no-4th` + `no-waste` + `right-sized` (ST20 + W15) — `v26` `55837644` `PENDING`

## 2) المشاكل المكتشفة وغير المحلولة

### A) هروب الحيوانات المتأخر `escape ~2k` — 71.9% من المباريات
- **الكشف:** `Simulator 32` على `main a6da650` `escapes 23/32 (71.9%)` `avg 1.17` حيوان/مباراة هاربة (0:9, 1:19, 2:4) — ليس قطيع كامل.
- **التوقيت:** ليس مبكرًا يوم0 (`history 0-5` `placed 4→5` بلا هبوط) بل **متأخر `day 10-20`** بعد اكتمال القطيع `9` وتراكم `WATER54` + `FEED8/CARE8`.
- **التأثير:** `money escape 89669` vs `no-escape 91645` → **فرق `1976$` (~2k)** — أصغر من العشب (`+8k worst`) لكنه حقيقي وليس side effect بسيط.
- **الحالة:** غير محلول — `dedicated-feeder` (1 و 2 feeders) زاد الهروب لـ `28-32/32` فرفض فورًا. يحتاج تصميمًا معماريًا أكبر (hand مخصص ديناميكي `ceil(animals/4)`) — مسجل للمرحلة الجاية.

### B) تأخر زراعة اليوم الأول `day0 plant delay` — 5 vs 22
- **الكشف:** `101918050` أول `PLANT` نحن `turn12` vs خصم `turn6` vs `Crop Dusta` `turn8` — نهاية يوم0 `5 vs 13 vs 22` نبات.
- **السبب الحقيقي:** `collect_jobs` `FEED0 > CARE1 > PLANT2` + `BUILD_PASTURE2` + `tie-break` قرب الشيد `planner.py:390` يفضل `PASTURE (3,3)` مسافة1 على `PLANT (0,0)` مسافة8 عندما كل العمال عند الشيد `(4,4)` — فيُبنى حظيرتان قبل أول زراعة (6 turns تأخير). `Crop Dusta` يوزع: عامل يُطعم وآخر يزرع بنفس الساعة.
- **المحاولات الفاشلة (4):** `delay` يوم0→1 (`11` نبات لكن `escapes 30/32`), `FEED2` (`7` نبات `29/32`), `dedicated-feeder` 1 hand (`6` نبات `32/32`), `2 feeders` (`5` نبات `31/32`), `nearest-to-worker` (توثيقي فقط، `_prefer_tie` كان صحيح أصلاً) → `5` نبات `26/32` — كلها زادت الهروب.
- **الحالة:** **مشكلة معمارية كبيرة غير محلولة** — `docs/ARCH_ISSUE_DAY0.md` — تحتاج جلسة تحليل منفصلة، ليست تجربة سريعة. موقوفة حاليًا.

### C) أرقام ثابتة قديمة تحتاج اختبار (نفس نمط `PLAN45` و `4th land`)
- `RESERVE 15` `src/economy.py:90` — يمنع شراء حتى لو `money-pending≥15` — لم يُختبر
- `SHED 80%` `src/economy.py:207` `SHED_CAPACITY100/DUMP_AT80` — متوسط الثقة
- `PLANT_TARGET_FULL 55` `src/strategy.py:37` — `actual 11.2` vs `55` waste، جُرب `55→20` فخسر `-18k` (يثبت 55 مناسب)
- `MELON cap 28` `src/planner.py:189` — لم يُختبر
- **الحالة:** مرشحون للمرحلة الجاية — واحد واحد كما في `WHEAT` و `STRAWBERRY`، ليس دفعة واحدة.

## 3) الفروع التجريبية الحالية
- `weed-priority 058f525` — مدمج
- `market-aware-sell 5dde44f` — مدمج
- `combined-weed-market 6b1cc26` — مدمج
- `no-4th-land 7bcb1aa` — مدمج
- `no-waste-buying 49efc80` — مدمج
- `right-sized-plan 4da9199` — مدمج
- `wheat-right-sized 134ccd5` — مدمج → `main a6da650`
- `plant-target-right-sized 7131011` — **مرفوض** (55→20 خسر -18k)
- `day0-plant-priority / dedicated-feeder / dynamic-feeder / nearest-to-worker` — **مرفوضة** (تزيد الهروب)
- `docs/ARCH_ISSUE_DAY0.md` — توثيق الفجوة 5 vs 22

> أي عودة للمشروع تبدأ من هذا الملف، ليس الذاكرة.
