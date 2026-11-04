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

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
CITIES_FILE = ROOT / "cities.txt"


def slug(city):
    return hashlib.md5(city.encode("utf-8")).hexdigest()[:10]


def read_cities():
    out = []
    for line in CITIES_FILE.read_text(encoding="utf-8").splitlines():
        c = A.norm_city(line)
        if c and not c.startswith("#") and c not in out:
            out.append(c)
    return out


def main():
    cities = read_cities()
    new = A.norm_city(os.environ.get("NEW_CITY", ""))
    if new and new not in cities:
        cities.append(new)
        with open(CITIES_FILE, "a", encoding="utf-8") as f:
            f.write(new + "\n")

    A.update_stores()
    if os.environ.get("DIAG"):
        from collections import Counter, defaultdict
        st = A.load_stores()
        print("DIAG total", len(st))
        per = defaultdict(Counter)
        for s in st:
            per[s["chain"]][s["city"]] += 1
        for ch, cnt in per.items():
            print("DIAG chain", ch, len(sum(cnt.values() and [cnt], Counter())), list(cnt.most_common(6)))
        for s in st:
            blob = " ".join([s["city"], s["sname"], s["address"]])
            if "ציונ" in blob or "ness" in blob.lower():
                print("DIAG match", s)
    all_cities = A.city_names()

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "data").mkdir(parents=True)
    shutil.copy(ROOT / "web" / "index.html", SITE / "index.html")

    meta = []
    for c in cities:
        entry = {"name": c, "slug": slug(c)}
        try:
            A.fetch_city(c)
            d = A.city_data(c)
            stores, idx, items = [], {}, {}
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
                    stores.append([r["chain"], r["sname"] or "סניף " + r["store"]])
                it = items.setdefault(r["barcode"], [r["barcode"], r["name"], r["manu"], []])
                if not it[1]:
                    it[1] = r["name"]
                it[3].append([idx[k], round(pr, 2)])
            for it in items.values():
                it[3].sort(key=lambda x: x[1])
            (SITE / "data" / f"{entry['slug']}.json").write_text(
                json.dumps({"stores": stores, "items": list(items.values())}, ensure_ascii=False,
                           separators=(",", ":")), encoding="utf-8")
            entry.update(stores=len(A.city_stores(c)), with_prices=len(stores), items=len(items))
        except Exception as e:  # noqa
            entry["error"] = str(e)
            entry["suggestions"] = difflib.get_close_matches(c, list(all_cities), n=5, cutoff=0.5)
        meta.append(entry)

    (SITE / "data" / "cities.json").write_text(json.dumps({
        "updated": time.time(),
        "repo": os.environ.get("GITHUB_REPOSITORY", ""),
        "cities": meta,
        "all_cities": sorted(all_cities.items()),
    }, ensure_ascii=False), encoding="utf-8")
    print("האתר נבנה:", [(m["name"], m.get("items", m.get("error"))) for m in meta])


if __name__ == "__main__":
    main()
