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


def slug(city):
    return hashlib.md5(city.encode("utf-8")).hexdigest()[:10]


DEFAULT_RADIUS = 0


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
    stores, idx, items = [], {}, {}
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
        it = items.get(r["barcode"])
        if it is None:
            size, unit = parse_size(r)
            it = items[r["barcode"]] = [r["barcode"], r["name"], r["manu"], [], size, unit]
        if not it[1]:
            it[1] = r["name"]
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
    return {"stores": stores, "items": list(items.values()), "promos": descs,
            "n_city_stores": len(area), "n_promo": npromo}


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
