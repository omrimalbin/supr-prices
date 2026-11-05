#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
רץ על המחשב בבית (בישראל) דרך GitHub Actions: שואב רק את הרשתות שחוסמות גישה מחו"ל
לערים שב-cities.txt, וכותב israel/israel.json. ה-workflow הראשי ממזג את זה לאפליקציה.
"""
import json
import os
import time
from pathlib import Path

import prices_app as A
os.environ.setdefault("ONLY_CHAINS", ",".join(A.ISRAEL_CHAINS))

import build  # noqa: E402  (אחרי ההגדרה של ONLY_CHAINS)

OUT = Path(__file__).resolve().parent / "israel"


def main():
    OUT.mkdir(exist_ok=True)
    cities = build.read_cities()
    A.update_stores()
    result = {}
    for c, radius in cities.items():
        try:
            data = build.make_city(c, radius)
            result[c] = data
            print(f"{c}: {len(data['stores'])} סניפים, {len(data['items'])} מוצרים")
        except Exception as e:  # noqa
            print(f"{c}: לא נמצאו סניפים של הרשתות האלה ({e})")
    (OUT / "israel.json").write_text(json.dumps({"updated": time.time(), "cities": result},
                                                ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("נשמר:", OUT / "israel.json")


if __name__ == "__main__":
    main()
