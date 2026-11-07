#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
רץ ב-GitHub Actions: שואב מחירים לערים שב-cities.txt ובונה אתר סטטי בתיקייה site/
שמוצג ב-GitHub Pages (מותאם לטלפון).
"""
import difflib
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

import prices_app as A
import geo

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
CITIES_FILE = ROOT / "cities.txt"


import re

_U = [  # (ביטוי, יחידה בסיסית, מכפיל)
    (r'ק"ג|ק״ג|קג|קילוגרם|קילוגרמים|קילו|ק\'ג', "g", 1000),
    (r'גרם|גרמים|גר\'|גר|ג\'|ג', "g", 1),
    (r'מ"ל|מ״ל|מל|מיליליטר|מיליליטרים|מ\'ל', "ml", 1),
    (r'ליטר|ליטרים|ל\'|ל', "ml", 1000),
]
_NUM = r"(\d+(?:[.,]\d+)?)"


def _unit_of(text):
    t = (text or "").strip().replace("׳", "'").replace("״", '"')
    for pat, base, mul in _U:
        if re.fullmatch(r"(?:" + pat + r")\.?", t):
            return base, mul
    return None


def parse_size(r):
    """גודל אריזה בגרם/מ"ל (או מוצר שקל = מחיר לק"ג)."""
    if (r.get("w") or "").strip() in ("1", "true", "True"):
        return 1000, "kg"
    name = (r.get("name") or "").replace("׳", "'").replace("״", '"')
    # מהשם: "6*1.5 ליטר", "1.5 ליטר", "500 גרם", "1ק"ג"
    for pat, base, mul in _U:
        m = re.search(r"(\d+)\s*[*xX×]\s*" + _NUM + r"\s*(?:" + pat + r")(?![א-ת])", name)
        if m:
            return round(int(m.group(1)) * float(m.group(2).replace(",", ".")) * mul), base
    for pat, base, mul in _U:
        m = re.search(_NUM + r"\s*(?:" + pat + r")(?![א-ת])", name)
        if m:
            v = float(m.group(1).replace(",", ".")) * mul
            if v > 0:
                return round(v), base
    # מהשדות: Quantity + UnitQty
    try:
        q = float((r.get("qty") or "0").replace(",", "."))
    except ValueError:
        q = 0
    u = _unit_of(r.get("uq")) or _unit_of(r.get("unit"))
    if q > 0 and u:
        return round(q * u[1]), u[0]
    m = re.search(r"(\d+)\s*(?:יח'|יחידות|יח)(?![א-ת])", name)
    if m:
        return int(m.group(1)), "u"
    return 0, ""


# מילים שמסמנות מארז של כמה יחידות (שם בלי "6*750")
_PACK_WORDS = [(r"שישי(?:י)?(?:ה|ת)", 6), (r"רביעי(?:י)?(?:ה|ת)", 4), (r"שלישי(?:י)?(?:ה|ת)", 3),
               (r"תריסר", 12), (r"זוג(?:ות)?", 2)]


def size_info(r):
    """גודל + כמה אמינים הנתונים: 2 = מארז מפורש (6*750 / שישייה + גודל), 1 = גודל מהשם, 0 = מהשדות/כלום."""
    size, unit = parse_size(r)
    if unit == "kg":
        return size, unit, 1
    name = (r.get("name") or "").replace("׳", "'").replace("״", '"')
    if re.search(r"\d+\s*[*xX×]\s*\d", name) and size:
        return size, unit, 2
    n = 0
    for pat, cnt in _PACK_WORDS:
        if re.search(pat, name):
            n = cnt
            break
    m = re.search(r"מארז\s*(?:של\s*)?(\d{1,2})(?!\d)", name) or re.search(r"(\d{1,2})\s*(?:יח'|יחידות|יח)(?![א-ת])", name)
    if not n and m and unit and unit != "u":
        n = int(m.group(1))
    if n > 1 and size and unit in ("g", "ml"):
        # לא מכפילים כאן: לפעמים הגודל בשם הוא של כל המארז ("פילטונה רביעייה 632 גרם").
        # האפליקציה מחליטה לפי המחיר לק"ג/ליטר של מוצרים דומים.
        return size, unit, 1
    return size, unit, 1 if size else 0


def best_name(names):
    """השם הכי מלא מבין הרשתות (שופרסל, למשל, חותכת שמות ל-20 תווים)."""
    names = [re.sub(r"\s+", " ", n.replace("\u202b", "").replace("\u202a", "")).strip() for n in names if n and n.strip()]
    return max(names, key=lambda n: (len(n), n)) if names else ""


def slug(city):
    return hashlib.md5(city.encode("utf-8")).hexdigest()[:10]


DEFAULT_RADIUS = 0
MAX_NEAR = 70


def parse_city_line(line):
    """"נס ציונה | 10" -> ("נס ציונה", 10)"""
    name, _, r = (line or "").partition("|")
    try:
        radius = max(0, min(30, float(r.strip()))) if r.strip() else DEFAULT_RADIUS
    except ValueError:
        radius = DEFAULT_RADIUS
    return A.norm_city(name), radius


def read_cities():
    out = {}
    for line in CITIES_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        c, r = parse_city_line(line)
        if c:
            out[c] = r
    return out


def write_cities(cities):
    lines = ["# ערים למעקב – עיר בכל שורה. אפשר להוסיף רדיוס בק\"מ: נס ציונה | 10"]
    lines += [f"{c} | {r:g}" if r else c for c, r in cities.items()]
    CITIES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_city(c, radius=0):
    """שואב עיר (+ סניפים ביישובים סמוכים עד radius ק"מ) ומחזיר: סניפים, מוצרים ומבצעים."""
    if not A.load_stores():
        A.update_stores()
    own = A.city_stores(c)
    near = geo.nearby_stores(c, radius, exclude=own) if radius else []
    if len(near) > MAX_NEAR:                       # רדיוס גדול: הסניפים הקרובים ביותר בלבד, כדי שהנתונים יישארו קלים לטלפון
        print(f"{c}: {len(near)} סניפים באזור – נשמרים {MAX_NEAR} הקרובים")
        near = near[:MAX_NEAR]
    area = own + [s for s, _ in near]
    if not area:
        raise RuntimeError(f'לא נמצאו סניפים בעיר "{c}"')
    by_key = {(s["chain"], s["store"]): s for s in area}
    dist = {(s["chain"], s["store"]): 0 for s in own}
    dist.update({(s["chain"], s["store"]): d for s, d in near})
    print(f"{c}: {len(own)} סניפים בעיר + {len(near)} באזור (עד {radius:g} ק\"מ)")
    A.fetch_city(c, stores=area)
    d = A.city_data(c, area)
    now = round(time.time())
    stores, idx, items, info = [], {}, {}, {}
    promo_by_store, descs, desc_idx = {}, [], {}
    npromo = 0
    for st in area:
        pf = A.price_file_for(st["folder"], st["store"], "promofull")
        if pf:
            try:
                promo_by_store[(st["chain"], st["store"])] = A.parse_promos(pf)
            except Exception as e:  # noqa
                print("promo parse failed", pf.name, e)
    for r in d["full"]:
        try:
            pr = float(r["price"])
        except ValueError:
            continue
        if pr <= 0 or not r["barcode"]:
            continue
        k = (r["chain"], r["store"])
        if k not in idx:
            idx[k] = len(stores)
            so = by_key.get(k, {})
            addr = re.sub(r",?\s*Israel\s*$", "", (so.get("address") or "").strip(), flags=re.I)
            stores.append([r["chain"], r["sname"] or "סניף " + r["store"], now, dist.get(k, 0),
                           addr, geo.store_city(so) if so else ""])
        size, unit, ev = size_info(r)
        ik = item_key(r, unit)
        it = items.get(ik)
        if it is None:
            it = items[ik] = [ik, r["name"], r["manu"], [], size, unit]
            info[ik] = {"names": set(), "size": (ev, size, unit)}
        inf = info[ik]
        if r["name"]:
            inf["names"].add(r["name"])
        if not it[2] and r["manu"]:
            it[2] = r["manu"]
        if ev > inf["size"][0]:
            inf["size"] = (ev, size, unit)
        dup = next((x for x in it[3] if x[0] == idx[k]), None)
        if dup is not None:                   # אותו מוצר פנימי פעמיים באותו סניף – נשאר הזול
            if pr >= dup[1]:
                continue
            it[3].remove(dup)
        pe = [idx[k], round(pr, 2)]
        offers = {}
        for mq, bundle, rate, desc in promo_by_store.get(k, {}).get(r["barcode"], []):
            if bundle is None:
                bundle = mq * pr * (1 - rate / 100)
            unit = bundle / mq
            if not (0.15 * pr <= unit < pr * 0.995):
                continue                      # לא הגיוני / לא באמת הנחה
            key = round(mq, 3)
            if key not in offers or bundle < offers[key][1]:
                if desc not in desc_idx:
                    desc_idx[desc] = len(descs)
                    descs.append(desc)
                offers[key] = [key, round(bundle, 2), desc_idx[desc]]
        if offers:
            pe.append(sorted(offers.values())[:3])
            npromo += 1
        it[3].append(pe)
    # שם מלא מכל הרשתות + גודל מהמקור הכי אמין (מארז מפורש > גודל מהשם > שדות)
    for ik, it in items.items():
        inf = info[ik]
        nm = best_name(inf["names"])
        if nm:
            it[1] = nm
        ev, size, unit = inf["size"]
        if it[5] != "kg" and ev > 0:
            s2, u2, ev2 = size_info({"name": it[1]})
            it[4], it[5] = (s2, u2) if ev2 >= ev and s2 else (size, unit)
    return {"stores": stores, "items": list(items.values()), "promos": descs,
            "n_city_stores": len(area), "n_promo": npromo}


def internal_code(r):
    """קוד פנימי של הרשת (ירקות, פירות, מעדנייה, שקילים) – לא ברקוד אמיתי.
    אותו מספר מסמן מוצרים שונים ברשתות שונות (למשל 7290000000091 = פלפל אדום בשופרסל
    ומוצר אחר ברמי לוי), ואותו מוצר מקבל מספר אחר בכל רשת."""
    code = r["barcode"]
    return len(code) < 8 or code.startswith("7290000000") or (r.get("itype") == "0" and len(code) < 13)


def item_key(r, unit):
    """מפתח המוצר: ברקוד אמיתי – הברקוד. קוד פנימי – השם המנורמל + יחידת המידה,
    כך שפלפל צהוב משופרסל, רמי לוי ויוחננוף נאחד למוצר אחד, ושני מוצרים שונים עם אותו קוד לא יתערבבו."""
    if not internal_code(r):
        return r["barcode"]
    nm = re.sub(r"\*?מבצע\*?", " ", r["name"] or "")
    nm = re.sub(r"[^\w%]+", " ", nm).strip()
    nm = re.sub(r"\s+", " ", nm)
    if not nm:
        return f'~{r.get("chain", "")}:{r["barcode"]}'
    return f"~{nm}|{unit}"


def merge(base, extra):
    """מוסיף לעיר סניפים ממקור נוסף (המחשב בבית). base יכול להיות None."""
    if not base:
        base = {"stores": [], "items": [], "promos": [], "n_city_stores": 0, "n_promo": 0}
    have = {(s[0], s[1]) for s in base["stores"]}
    s_off, p_off = len(base["stores"]), len(base["promos"])
    keep = [i for i, s in enumerate(extra["stores"]) if (s[0], s[1]) not in have]
    remap = {old: s_off + n for n, old in enumerate(keep)}
    base["stores"] += [extra["stores"][i] for i in keep]
    base["promos"] += extra["promos"]
    by_code = {it[0]: it for it in base["items"]}
    for it in extra["items"]:
        prices = []
        for pe in it[3]:
            if pe[0] not in remap:
                continue
            pe = [remap[pe[0]], pe[1]] + ([[[o[0], o[1], o[2] + p_off] for o in pe[2]]] if len(pe) > 2 else [])
            prices.append(pe)
        if not prices:
            continue
        cur = by_code.get(it[0])
        if cur is None:
            cur = by_code[it[0]] = [it[0], it[1], it[2], [], it[4], it[5]]
        elif cur[5] != "kg":
            # שם מלא יותר / מארז מפורש מהרשתות של המחשב בבית
            if len(it[1] or "") > len(cur[1] or ""):
                cur[1] = it[1]
            a, b = size_info({"name": cur[1]}), size_info({"name": it[1] or ""})
            best = max([a, b], key=lambda x: x[2])
            if best[0] and best[2] >= 1:
                cur[4], cur[5] = best[0], best[1]
            base["items"].append(cur)
        cur[3] += prices
        cur[3].sort(key=lambda x: x[1])
    base["n_city_stores"] += len(keep)
    base["n_promo"] += extra.get("n_promo", 0)
    return base


def load_israel():
    """נתונים מהמחשב בבית (אם הורדו לתיקייה israel/ ע"י ה-workflow), עד 14 יום אחורה."""
    f = ROOT / "israel" / "israel.json"
    if not f.exists():
        return {}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa
        return {}
    if time.time() - d.get("updated", 0) > 14 * 86400:
        print("נתוני הבית ישנים מדי – לא נכללים")
        return {}
    print("נתוני הבית מ-", time.strftime("%Y-%m-%d %H:%M", time.gmtime(d["updated"])), "UTC:",
          {c: len(v["stores"]) for c, v in d["cities"].items()})
    return d["cities"]


def main():
    cities = read_cities()
    new = os.environ.get("NEW_CITY", "").strip()
    only = None
    if new:
        c, r = parse_city_line(new)
        if c:
            cities[c] = r
            write_cities(cities)
            if os.environ.get("ONLY_NEW"):
                only = c                      # שאיבה של העיר החדשה בלבד; השאר נשארים מהעדכון הקודם

    A.update_stores()
    israel = load_israel()
    prev = Path(os.environ.get("PREV", "prev"))
    prev_meta = {}
    if only and (prev / "data" / "cities.json").exists():
        prev_meta = {m["name"]: m for m in json.loads((prev / "data" / "cities.json").read_text(encoding="utf-8"))["cities"]}

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "data").mkdir(parents=True)
    for f in (ROOT / "web").iterdir():   # הדף + קובצי האפליקציה (אייקונים, manifest, sw.js)
        shutil.copy(f, SITE / f.name)

    all_cities = {}
    for s_ in A.load_stores():
        n = geo.store_city(s_)
        if n:
            all_cities[n] = all_cities.get(n, 0) + 1
    # קואורדינטות לכל יישוב שיש בו סניפים – לאפליקציה (מציאת היישוב הקרוב למיקום הנוכחי)
    locs = {}
    for n in all_cities:
        xy = geo.coords(n)
        if xy:
            locs[n] = xy
    geo.save()
    (SITE / "data" / "localities.json").write_text(json.dumps(locs, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"מיקומים: {len(locs)} יישובים")

    meta = []
    for c, radius in cities.items():
        entry = {"name": c, "slug": slug(c), "radius": radius}
        if only and c != only and c in prev_meta:          # עיר קיימת – מעתיקים כמו שהיא
            pf = prev / "data" / f"{entry['slug']}.json"
            if pf.exists():
                shutil.copy(pf, SITE / "data" / pf.name)
                meta.append(prev_meta[c])
                continue
        data, err = None, None
        try:
            data = make_city(c, radius)
        except Exception as e:  # noqa
            err = str(e)
        if c in israel:
            data = merge(data, israel[c])
        if data and data["stores"]:
            out = {k: data[k] for k in ("stores", "items", "promos")}
            (SITE / "data" / f"{entry['slug']}.json").write_text(
                json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            entry.update(stores=data["n_city_stores"], with_prices=len(data["stores"]),
                         items=len(data["items"]), promos=data["n_promo"], updated=time.time())
            print(f"{c}: {len(data['items'])} מוצרים מ-{len(data['stores'])} סניפים, {data['n_promo']} מחירים עם מבצע")
        else:
            entry["error"] = err or "לא נמצאו מחירים"
            entry["suggestions"] = difflib.get_close_matches(c, list(all_cities), n=5, cutoff=0.5)
        meta.append(entry)
    geo.save()

    # שמות לפי ברקוד מכל הערים – כדי שסריקת מוצר שלא נמכר בעיר שנבחרה תציג מה הוא ותציע מוצרים דומים
    names = {}
    for m in meta:
        f = SITE / "data" / f"{m['slug']}.json"
        if not f.exists():
            continue
        for it in json.loads(f.read_text(encoding="utf-8"))["items"]:
            if it[0] and it[0][0] != "~" and it[1]:
                names.setdefault(it[0], it[1])
    (SITE / "data" / "names.json").write_text(json.dumps(names, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    (SITE / "data" / "stores.json").write_text(json.dumps(
        [[s["chain"], s["store"], s["sname"], s["city"], s["address"]] for s in A.load_stores()],
        ensure_ascii=False), encoding="utf-8")
    (SITE / "data" / "cities.json").write_text(json.dumps({
        "updated": time.time(),
        "repo": os.environ.get("GITHUB_REPOSITORY", ""),
        "cities": meta,
        "all_cities": sorted(all_cities.items()),
    }, ensure_ascii=False), encoding="utf-8")
    print("האתר נבנה:", [(m["name"], m.get("items", m.get("error"))) for m in meta])


if __name__ == "__main__":
    main()
