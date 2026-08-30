# PROJECT_NOTES — DeepSim Kaggriculture

> ملف تتبع مركزي للمشاكل المكتشفة والمرفوضة — بدل الاعتماد على الذاكرة فقط.
> آخر تحديث: 2026-08-30 — zone-based-v2 **مدمج في main** `f95bacd` — أساس `90225/69897/26-32/5` → zone+DROP `101973/77129/8-32/14` (+12.9k) | هدر 10.1%→5.0%

> **مبدأ توجيهي عام:** الوقت (`turns` الـ 720) هو المورد الوحيد غير القابل للتعويض في اللعبة — الفلوس، البذور، الحيوانات كلها قابلة للتصحيح لاحقًا (بيع، شراء، إعادة زراعة)، لكن `turn` ضايع في حركة (`65%` من الـ turns حركة `src/planner.py:390` `4224/6500`) أو انتظار (`PASS` `392` turn للـ `farmer`) مش هيرجع. أي تصميم مستقبلي لازم يعامل استهلاك الوقت (خصوصًا المسافة/الحركة `max_dist 5-6` في `far cases 0.3-1.5%`) كتكلفة صريحة `score = f(priority, distance, remaining, urgency)`، مش تأثير جانبي لـ `sort`.
> **مبدأ تشخيصي:** المشاكل ممكن يكون عرضها الظاهر في ملف، وسببها الحقيقي في ملف تاني تمامًا — زي ما اكتشفنا إن مشكلة `BUILD/PLANT` في `planner.py` كان سببها الحقيقي توقيت الشراء في `economy.py` (`day0 hour<12 skip`). أي تشخيص جديد لازم يتحقق من كل الملفات المترابطة (`planner.py`, `economy.py`, `strategy.py`, `main.py`, `constants.py`) قبل ما نفترض إن الحل محصور في أول ملف بيبان فيه العرض.

## 1) المدمج والمرفوع — كل حاجة شغالة على السيرفر دلوقتي

| # | الفرع / الكوميت | الوصف | الأثر المُقاس `Simulator 32` vs `pass` | الحالة |
|---|---|---|---|---|
| 1 | `a711815` `v20: merge early-warning + cap6` | مؤشر مبكر `milk_history <150` + سقف 6 بقرات (15→6) | `78%` local winrate، `cap6` قلب 5W-3L→3W-5L في `crash` | **مدمج** `fc63fc8` |
| 2 | `5dde44f` `market-aware-sell` | `CAPS` حسب `above_target` `MELON25 WOOL30 MILK40 STRAW50 WHEAT150` `src/economy.py:233` | `worst +704` `mean -89` `stdev -238` | **مدمج** `01fa4bd` |
| 3 | `6b1cc26` `weed-priority` | `DIG 3→1` عند `weeds≥15` `src/planner.py:170` | `weeds 32.1→11.9 (-63%)` `worst +2.6k` `mean +456` | **مدمج** `01fa4bd` |
| 4 | `7bcb1aa` `no-4th-land` | إيقاف الأرض الرابعة `if unlocked < len(LAND_COSTS)` `src/economy.py:511` | `+2.1k~+3.3k` `tiles 33→29` `quadrants 4→3` | **مدمج** `9391312` |
| 5 | `49efc80` `no-waste-buying` | `WHEAT 28→27` `STRAW 22→19` `MELON 13 keeps` `COW<=21 SHEEP<=23` `src/economy.py:524,537` | `+70` مجاني `weeds 32.1→32.8` لا ضرر | **مدمج** `cb45531` |
| 6 | `4da9199` `right-sized-plan` | `PLAN STRAW 45→20` `src/economy.py:30` (قريب من `plant_target 11` + هامش) | `+2.4k` `worst +2.5k` `plants 11.2=11.2` | **مدمج** `967e7d3` |
| 7 | `134ccd5` `wheat-right-sized` | `PLAN WHEAT 30→15` `src/economy.py:30` (avg plants 0.25 vs 30 waste 29.4) | `worst +6-8k` `stdev -35%` `mean -0.3%` | **مدمج** `a6da650` |
| 8 | `f95bacd` `zone-based-v2 + end-season DROP` | `planner.py ZoneManager 2×2 + main.py hour + DROP last10 + seed 27/19→24/14` `src/planner.py:267` `src/economy.py:306` | `day1 5→14` `mean 90225→101973 (+12.9k)` `worst 69897→77129` `escapes 26→8/32` `waste 10.1%→5.0%` | **مدمج في main** `f95bacd` |

> **آخر commit على `main`:** `f95bacd` `zone-based-v2: end-season waste fix` على `955a121` — مدمج رسمياً (32 `mean 101973` `worst 77129` `escapes 8/32` `day1 14`)
> **آخر نسخة مرفوعة:** `v26` `55837644` `v26_wheat15.tar.gz` `2026-08-28 07:27:52` `main a6da650` — `COMPLETE 683.5` (31 PUBLIC +1 VALIDATION =32) — التالي `v27` سيكون zone+DROP

## 2) اتجرب وفشل — عشان محدش يكررهم من غير داعي

- `plant-target-right-sized` `7131011` `PLANT_TARGET 55→20` `src/strategy.py:37` — **خسارة -18k** `32 mean 71850` vs `90499` `worst 51303` — الرقم `55` مناسب فعلًا (actual 11.2 لكن 55 يسمح بذروة 30 منتصف الموسم) — **مرفوض**
- `day0-plant-priority` `5591e11`/`ac450d3` `delay day0→1` أو `FEED 0→2` `src/economy.py:540` `src/planner.py:200` — `day1 11/7` vs `5` لكن `escapes 30/32` و `29/32` (90%+) vs `26/32` — **خطر هروب 90%+ مرفوض فورًا**
- `dedicated-feeder` / `dynamic-feeder` `774e73a`/`e73880f`/`8097ac9` `src/planner.py:334` بكل نسخه `1 feeder` `6 نبات 32/32`، `2 feeders` `5 نبات 31/32`، `ceil(animals/4)` `6 نبات 28/32` — **كلهم زودوا الهروب** (vs `23/32` الأساس) — **مرفوض**
- `nearest-to-worker` `df2c522` `src/planner.py:390` `_prefer_tie` من `pos` — **محايد** (الكود كان already صح من مكان العامل، ليس من الشيد) `day1 5` `escapes 26/32` = `main`
- `zone-based-v2` `economy.py:616 + planner.py:ZoneManager` `BUILD/PLANT` زوني ثنائي الأبعاد `2×2` + `quota` + `can_help` + `day0 hour<12 skip` — `day1 11` vs `5` (+6) `PASS 0/4` لكن `32 mean 83390 vs 90225 (-6835)` `worst 66236 vs 69897 (-3661)` `escapes 21/32 0.84 vs 26/32 1.16` — **مكسب يوم0 يُعوَّض بخسارة حيوانية/نقدية mid-game → مرفوض كتحسين عام (يبقى فرع تجريبي فقط)`
- `zone-based-v2 REBUILT 2026-08-30` على `config.py` النضيف + `main.py hour` + `planner.py ZoneManager` (2×2، worker_idx%4، quota, triple guard relaxed) — `day1 14` vs `5` (+9) `PASS 0/4` `32 mean 94487 vs 90225 (+4262)` `worst 71953 vs 69897 (+2056)` `best 111604 vs 105901` `escapes 9/32 0.28 vs 26/32 1.16` — vs kshitiz 19/13 2W-0L (+7233/+9565 أساس → +5955/+6982 zones) vs DevilQ `715809590` W 87707-80244 و Simon `749389386` W 75342-61286 — **تم دمجه في main `f95bacd` مع تحسين نهاية الموسم `+DROP` → `mean 101973`**
- `zone end-season DROP` `planner.py:267` `DROP last10` + `economy.py:306` `seed 27/19→24/14` — `mean 94487→101973 (+2.6k)` `waste 12.4%→5.0%` `inv 6365→52` `seeds 2990→382` — **مدمج**

## 3) مشاكل مكتشفة لسه مفتوحة — بالأولوية

- **أولوية قصوى — محلولة جزئياً:** فجوة اليوم الأول `5→14` نبات عبر `zone-based-v2` (`f95bacd`، `PASS 0/4`، `2×2` + `DROP`) — لا تزال فجوة مقابل `Crop Dusta` (`101985106` turn8: 13) وخصم قوي (22) لكن تحسن كبير محقق (+9, +180%) — لسه فيه فرق 14 مقابل 22 يستحق جلسة لاحقة، لكن الحالة لم تعد "موقوفة"
- **متوسطة:** هروب حيوان متأخر `~2k` تكلفة (`23/32 71.9%` `avg 1.17` `1:19 2:4`) — `money 89669` vs `91645` `diff 1976` — مرتبطة بنفس مشكلة الفجوة فوق (نفس جذر التوزيع)
- **منخفضة (لسه معملناش حاجة):** `RESERVE 15` `src/economy.py:90`, `SHED capacity 80%` `src/economy.py:207`, `MELON cap 28` `src/planner.py:189` — أرقام ثابتة قديمة لسه محتاجة اختبار واحد واحد (مثل `WHEAT`/`STRAW`)

## 4) حالة النسخ على السيرفر — آخر تقييم معروف

| النسخة | `ref` | التاريخ | `publicScore` | الحلقات | الحالة |
|---|---|---|---|---|---|
| `v23` `combined 4x` | `55835000` | `2026-08-28 05:33` | `631.9` | 1 VAL + ~20 PUBLIC | COMPLETE |
| `v24` `no-4th-land` | `55835652` | `2026-08-28 06:03` | `707.5` | 1 VAL + ~24 PUBLIC | COMPLETE — الأعلى حتى الآن |
| `v25` `right-sized STRAW20` | `55836983` | `2026-08-28 07:01` | `651.1` | 1 VAL +28 PUBLIC =29 | COMPLETE (كان 701 عند 5 حلقات → 651 بعد 28 → تذبذب عينة صغيرة) |
| `v26` `wheat15` | `55837644` | `2026-08-28 07:27` | `683.5` | 1 VAL +32 PUBLIC =33 | COMPLETE (2W-1L في أول 3، 50% متوقع بعد 30) |

> `v24` لا يزال الأعلى `707.5`، `v26 683.5` تحسن `+32` عن `v25` لكن لم يتجاوز `v24` بعد — يحتاج 20-30 حلقة إضافية للاستقرار.

> أي عودة للمشروع تبدأ من هذا الملف، ليس الذاكرة.

## 5) البنية — ملفات غير متصلة عمدًا (مقصودة)

- `src/opponent_model.py` **غير مستورد في `main.py`/`planner.py` عمدًا** — يُستخدم فقط في `tests/vs_ghosts.py` و `src/replay_tool.py` لمحاكاة خصوم Ghost من `episode-*-replay.json` (تقييم `Simulator` خارج الإنتاج) — إبقاؤه لا يؤثر على السلوك التنافسي (`grepped: لا استيراد في src/planner.py|main.py|economy.py`).
- المحذوف نهائيًا `2026-08-29`: `src/navigation.py` + `src/task.py` (كلاهما من `b465369 Initial commit`، لا استيراد لهما في أي ملف `src/*.py` أو `tests/*.py`، لا خطة استخدام قريبة — حُذفا كـ `src/brain/` بالظبط) + `src/brain/` سابقًا — تأكيد إضافي أن مشكلة `zone-based-planner (escapes 32/32)` كانت في `planner.py` نفسه لا في ملفات خارجية.

## 6) فرص مستقبلية — DROP كأداة تحكم استراتيجي (لم يُختبر بعد)

> `DROP` (يفرغ كل أنواع المخزون من إيد العامل مرة واحدة، بعكس `PLACE` اللي بيتطلب فعل منفصل لكل نوع) مش بس أداة كفاءة لنهاية الموسم - هي أداة تحكم استراتيجي محتملة في توقيت البيع: ممكن نجمع منتجات في إيد العمال عمدًا (تأخير `DROP`) لحد ما يوصل توقيت مثالي (سعر مرتفع)، أو نستخدم `DROP` الفوري لتسريع دخول الشيد وقت الحاجة. ده مرتبط مباشرة بحساسية الأسعار (`above_target`) اللي اكتشفناها في `overview.txt` - يفتح باب لتحكم أدق في الإغراق/التعطيش. لم يُختبر بعد، يحتاج جلسة تصميم منفصلة.
