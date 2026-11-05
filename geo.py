# -*- coding: utf-8 -*-
"""
מיקום סניפים: לכל סניף מוצאים את היישוב שלו (לפי סמל יישוב של הלמ"ס, שם עיר, או הכתובת)
ואת קואורדינטות היישוב (OpenStreetMap). המטמון נשמר ב-geo_cache.json כדי לא לחפש שוב.
"""
import json
import math
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import prices_app as A

CACHE_FILE = Path(__file__).resolve().parent / "geo_cache.json"
UA = "supr-prices/1.0 (github.com/omrimalbin/supr-prices)"
LOCALITIES_RESOURCE = "5c78e9fa-c2e2-4771-93ff-7f400a12f7ba"   # data.gov.il – רשימת ישובים בישראל

_cache = None


def _load():
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa
            _cache = {}
        _cache.setdefault("codes", {})
        _cache.setdefault("coords", {})
    return _cache


def save():
    if _cache is not None:
        CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")


def _get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def localities():
    """סמל יישוב -> שם (מהלמ"ס דרך data.gov.il)."""
    c = _load()
    if not c["codes"]:
        try:
            url = ("https://data.gov.il/api/3/action/datastore_search?resource_id=" + LOCALITIES_RESOURCE + "&limit=5000")
            recs = _get(url)["result"]["records"]
            for r in recs:
                code = str(r.get("סמל_ישוב") or r.get("סמל ישוב") or "").strip()
                name = A.norm_city(str(r.get("שם_ישוב") or r.get("שם ישוב") or ""))
                if code.isdigit() and name:
                    c["codes"][str(int(code))] = name
            print(f"geo: {len(c['codes'])} יישובים מהלמ\"ס")
        except Exception as e:  # noqa
            print("geo: רשימת היישובים לא זמינה:", e)
    return c["codes"]


def coords(name):
    """קואורדינטות יישוב (lat, lon) או None. OpenStreetMap, עד בקשה אחת בשנייה."""
    name = A.norm_city(name)
    if not name:
        return None
    c = _load()
    if name in c["coords"]:
        return c["coords"][name]
    res = None
    try:
        q = urllib.parse.urlencode({"q": name + ", ישראל", "format": "json", "limit": 1, "countrycodes": "il"})
        d = _get("https://nominatim.openstreetmap.org/search?" + q)
        if d:
            res = [round(float(d[0]["lat"]), 5), round(float(d[0]["lon"]), 5)]
        time.sleep(1.1)
    except Exception as e:  # noqa
        print("geo: חיפוש נכשל", name, e)
        return None
    c["coords"][name] = res
    return res


def km(a, b):
    if not a or not b:
        return None
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


_names_sorted = None


def store_city(s):
    """שם היישוב של סניף."""
    global _names_sorted
    codes = localities()
    if _names_sorted is None:
        _names_sorted = sorted(set(codes.values()), key=len, reverse=True)
    text = A._flat(s["address"] + " " + s["sname"])
    c = (s["city"] or "").strip()
    if c.isdigit() and int(c) and str(int(c)) in codes:
        return codes[str(int(c))]
    # בלי סמל: לפי הכתובת/שם הסניף (גם כשהעיר כתובה במילים, הכתובת אמינה יותר – למשל וולט)
    for n in _names_sorted:
        if len(n) >= 3 and A._flat(n) in text:
            return n
    if c and not c.isdigit() and c.lower() not in ("unknown", "none", "null"):
        return A.norm_city(c)
    return None


def nearby_stores(city, radius_km, exclude=()):
    """סניפים ביישובים אחרים עד radius_km מהעיר. מחזיר [(סניף, מרחק)]."""
    center = coords(city)
    if not center or radius_km <= 0:
        return []
    skip = {(s["folder"], s["store"]) for s in exclude}
    out = []
    for s in A.load_stores():
        if (s["folder"], s["store"]) in skip:
            continue
        name = store_city(s)
        if not name:
            continue
        d = km(center, coords(name))
        if d is not None and d <= radius_km:
            out.append((s, round(d, 1)))
    return sorted(out, key=lambda x: x[1])
