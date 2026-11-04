#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
מחירי סופר לפי עיר
-------------------
בוחרים עיר ולוחצים "שאיבת מחירים": האפליקציה שואבת את קובצי המחירים שהרשתות
מפרסמות לפי חוק המזון (הרשימה שבאתר gov.il), מאתרת את הסניפים שבעיר ומציגה
טבלת מוצרים עם השוואת מחירים בין הסניפים.

הפעלה:  py prices_app.py
דרוש:   py -m pip install il-supermarket-scraper   (קובץ start_prices.bat עושה זאת)
"""

import csv
import gzip
import io
import json
import re
import socket
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
import xml.etree.ElementTree as ET
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DUMPS = BASE_DIR / "dumps"

CHAIN_HE = {  # שמות בעברית לתצוגה (אם בקובץ אין שם רשת)
    "BAREKET": "ברקת", "YAYNO_BITAN_AND_CARREFOUR": "יינות ביתן / קרפור", "CITY_MARKET_KIRYATGAT": "סיטי מרקט",
    "CITY_MARKET_SHOPS": "סיטי מרקט", "DOR_ALON": "דור אלון", "GOOD_PHARM": "גוד פארם", "HAZI_HINAM": "חצי חינם",
    "HET_COHEN_NEW_SOURCE": "ח. כהן", "KESHET": "קשת טעמים", "KING_STORE": "קינג סטור", "MAAYAN_2000": "מעיין 2000",
    "MAHSANI_ASHUK_NEW_SOURCE": "מחסני השוק", "MAHSANI_ASHUK": "מחסני השוק", "NETIV_HASED": "נתיב החסד",
    "MESHMAT_YOSEF_1": "משנת יוסף", "MESHMAT_YOSEF_2": "משנת יוסף", "OSHER_AD": "אושר עד", "POLIZER": "פוליצר",
    "RAMI_LEVY": "רמי לוי", "SALACH_DABACH": "סאלח דבאח", "SHEFA_BARCART_ASHEM": "שפע ברכת השם",
    "SHUFERSAL": "שופרסל", "SHUK_AHIR": "שוק העיר", "STOP_MARKET": "סטופ מרקט", "SUPER_PHARM": "סופר-פארם",
    "SUPER_YUDA": "סופר יודה", "SUPER_SAPIR": "סופר ספיר", "FRESH_MARKET_AND_SUPER_DOSH": "פרשמרקט / סופר דוש",
    "TIV_TAAM": "טיב טעם", "VICTORY": "ויקטורי", "VICTORY_NEW_SOURCE": "ויקטורי", "YELLOW": "יילו",
    "YOHANANOF": "יוחננוף", "ZOL_VEBEGADOL": "זול ובגדול", "WOLT": "וולט מרקט", "MEGA": "מגה",
}


# ================================================================ הספרייה
def lib():
    """טוען את ספריית השאיבה (il-supermarket-scraper)."""
    from il_supermarket_scarper import ScarpingTask, ScraperFactory  # noqa
    from il_supermarket_scarper.utils import DumpFolderNames  # noqa
    return ScarpingTask, ScraperFactory, DumpFolderNames


def lib_status():
    try:
        lib()
        return None
    except Exception as e:  # noqa
        return f"{type(e).__name__}: {e}"


def folder_to_scraper():
    _, SF, DFN = lib()
    names = set(SF.all_scrapers_name())
    return {d.value: d.name for d in DFN if d.name in names}


def run_scrape(scrapers, file_type, regex=None):
    ScarpingTask, _, _ = lib()
    task = ScarpingTask(
        enabled_scrapers=list(scrapers),
        files_types=[file_type],
        file_name_regex=regex,
        multiprocessing=max(1, min(5, len(scrapers))),
        output_configuration={"output_mode": "disk", "base_storage_path": str(DUMPS)},
        status_configuration={"database_type": "json", "base_path": str(DUMPS / "status")},
        timeout_in_seconds=60 * 20,
    )
    task.start()
    task.join()


# ================================================================ משימת רקע
JOB = {"running": False, "steps": [], "error": None, "done_at": None, "kind": None}
job_lock = threading.Lock()


def log(msg):
    JOB["steps"].append(time.strftime("%H:%M:%S ") + msg)
    print(msg, flush=True)


def start_job(kind, fn):
    with job_lock:
        if JOB["running"]:
            return False
        JOB.update(running=True, steps=[], error=None, done_at=None, kind=kind)

    def run():
        try:
            fn()
        except Exception as e:  # noqa
            traceback.print_exc()
            JOB["error"] = str(e)
        finally:
            JOB["running"] = False
            JOB["done_at"] = time.time()
    threading.Thread(target=run, daemon=True).start()
    return True


# ================================================================ קריאת קבצים
def read_xml(p):
    raw = p.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    elif raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            raw = z.read(z.namelist()[0])
    return ET.fromstring(raw)


def tag(el):
    return el.tag.split("}")[-1].lower()


def norm_id(s):
    s = (s or "").strip()
    return str(int(s)) if s.isdigit() else s


def norm_city(s):
    return re.sub(r"\s+", " ", (s or "").strip().strip("\"'").replace("־", "-"))


def first(kids, *names):
    for n in names:
        if kids.get(n):
            return kids[n]
    return ""


def newest(files):
    return max(files, key=lambda p: (p.name.lower(), p.stat().st_mtime)) if files else None


_stores_cache = {"key": None, "stores": []}


def load_stores():
    """רשימת כל הסניפים מכל הרשתות, מקובצי הסניפים העדכניים ביותר."""
    if not DUMPS.exists():
        return []
    try:
        f2s = folder_to_scraper()
    except Exception:  # noqa
        f2s = {}
    picks = []
    for folder in DUMPS.iterdir():
        if folder.is_dir() and folder.name != "status":
            n = newest([p for p in folder.iterdir() if p.is_file() and p.name.lower().startswith("store")])
            if n:
                picks.append((folder.name, n))
    key = tuple((f, p.name, p.stat().st_mtime) for f, p in picks)
    if key == _stores_cache["key"]:
        return _stores_cache["stores"]
    stores = []
    for folder, p in picks:
        scraper = f2s.get(folder, "")
        try:
            root = read_xml(p)
        except Exception:  # noqa
            continue
        chain_name = ""
        for el in root.iter():
            if tag(el) == "chainname" and (el.text or "").strip():
                chain_name = el.text.strip()
                break
        seen = set()
        for el in root.iter():
            kids = {tag(c): (c.text or "").strip() for c in el if len(c) == 0}
            sid = first(kids, "storeid", "storeidentifier")
            if not sid or not ("city" in kids or "storename" in kids or "storenm" in kids):
                continue
            sid = norm_id(sid)
            if sid in seen:
                continue
            seen.add(sid)
            stores.append({
                "folder": folder, "scraper": scraper,
                "chain": CHAIN_HE.get(scraper) or chain_name or folder,
                "store": sid,
                "sname": first(kids, "storename", "storenm"),
                "city": norm_city(first(kids, "city")),
                "address": first(kids, "address"),
            })
    _stores_cache.update(key=key, stores=stores)
    return stores


def city_stores(city):
    c = norm_city(city)
    return [s for s in load_stores() if s["city"] == c]


def price_file_for(folder, store):
    d = DUMPS / folder
    if not d.exists():
        return None
    pat = re.compile(r"^pricefull\d*-0*" + re.escape(store) + r"-", re.I)
    return newest([p for p in d.iterdir() if p.is_file() and pat.match(p.name)])


FIELDS = [
    ("barcode", ["itemcode", "itembarcode", "barcode"]),
    ("name", ["itemname", "itemnm", "manufactureritemdescription"]),
    ("price", ["itemprice", "price"]),
    ("manu", ["manufacturername"]),
    ("qty", ["quantity"]),
    ("unit", ["unitofmeasure", "unitqty"]),
    ("upd", ["priceupdatedate"]),
]


def parse_prices(p):
    rows = []
    for el in read_xml(p).iter():
        kids = {tag(c): (c.text or "").strip() for c in el if len(c) == 0}
        if not any(t in kids for t in FIELDS[0][1]):
            continue
        rows.append({k: first(kids, *tags) for k, tags in FIELDS})
    return rows


_city_cache = {}


def city_data(city):
    """כל המוצרים בסניפי העיר + השוואה לפי ברקוד."""
    stores = city_stores(city)
    files = [(s, price_file_for(s["folder"], s["store"])) for s in stores]
    files = [(s, f) for s, f in files if f]
    key = tuple((f.name, f.stat().st_mtime) for _, f in files)
    if _city_cache.get(city, {}).get("key") == key:
        return _city_cache[city]
    full, items = [], {}
    for s, f in files:
        try:
            rows = parse_prices(f)
        except Exception:  # noqa
            continue
        where = f'{s["chain"]} – {s["sname"] or "סניף " + s["store"]}'
        for r in rows:
            r = dict(r, chain=s["chain"], store=s["store"], sname=s["sname"], file_date=f.name)
            full.append(r)
            try:
                pr = float(r["price"])
            except ValueError:
                continue
            if pr <= 0 or not r["barcode"]:
                continue
            it = items.setdefault(r["barcode"], {"barcode": r["barcode"], "name": "", "manu": "",
                                                 "min": pr, "max": pr, "n": 0, "where": where})
            it["name"] = it["name"] or r["name"]
            it["manu"] = it["manu"] or r["manu"]
            it["n"] += 1
            if pr < it["min"]:
                it["min"], it["where"] = pr, where
            it["max"] = max(it["max"], pr)
    data = {"key": key, "full": full, "items": list(items.values()), "stores_with_prices": len(files),
            "stores": len(stores)}
    _city_cache[city] = data
    return data


# ================================================================ הגדרות ותזמון
SETTINGS_FILE = BASE_DIR / "settings.json"
settings_lock = threading.Lock()


def load_settings():
    s = {"cities": [], "interval_hours": 6, "city_updated": {}, "stores_updated": 0}
    try:
        s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:  # noqa
        pass
    return s


def save_settings(s):
    with settings_lock:
        SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def scheduler():
    """רץ ברקע: מעדכן אוטומטית את הערים במעקב ואת רשימת הסניפים."""
    time.sleep(5)
    while True:
        try:
            if not JOB["running"] and lib_status() is None:
                s = load_settings()
                now = time.time()
                if s["cities"] and now - s.get("stores_updated", 0) > 7 * 86400:
                    start_job("stores", update_stores)
                else:
                    iv = float(s.get("interval_hours") or 0) * 3600
                    for c in s["cities"]:
                        if iv and now - s["city_updated"].get(c, 0) > iv:
                            start_job("city", lambda c=c: fetch_city(c, auto=True))
                            break
        except Exception:  # noqa
            traceback.print_exc()
        time.sleep(60)


# ================================================================ פעולות
def update_stores():
    _, SF, _ = lib()
    names = SF.all_scrapers_name()
    log(f"מוריד את רשימות הסניפים מ-{len(names)} רשתות (זה לוקח כמה דקות)...")
    run_scrape(names, "STORE_FILE")
    st = load_stores()
    log(f"נמצאו {len(st):,} סניפים מ-{len(set(s['folder'] for s in st))} רשתות")
    s = load_settings()
    s["stores_updated"] = time.time()
    save_settings(s)


def fetch_city(city, auto=False):
    JOB["city"] = city
    if auto:
        log(f"עדכון אוטומטי של {city}")
    if not load_stores():
        update_stores()
    stores = city_stores(city)
    if not stores:
        raise RuntimeError(f'לא נמצאו סניפים בעיר "{city}". נסו לעדכן את רשימת הסניפים או לבחור שם אחר מהרשימה.')
    by_scraper = {}
    for s in stores:
        if s["scraper"]:
            by_scraper.setdefault(s["scraper"], set()).add(s["store"])
    log(f"נמצאו {len(stores)} סניפים ב{city} של {len(by_scraper)} רשתות")
    for i, (scraper, ids) in enumerate(sorted(by_scraper.items()), 1):
        log(f"({i}/{len(by_scraper)}) שואב מחירים מ{CHAIN_HE.get(scraper, scraper)} – {len(ids)} סניפים")
        regex = r"(?i)pricefull\d*-0*(" + "|".join(sorted(map(re.escape, ids))) + r")-"
        try:
            run_scrape([scraper], "PRICE_FULL_FILE", regex)
        except Exception as e:  # noqa
            log(f"   נכשל: {e}")
    d = city_data(city)
    log(f"מוכן: {len(d['items']):,} מוצרים מ-{d['stores_with_prices']} סניפים")
    s = load_settings()
    if city not in s["cities"]:
        s["cities"].append(city)
    s["city_updated"][city] = time.time()
    save_settings(s)


# ================================================================ שרת
def to_csv(rows, cols):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([l for _, l in cols])
    for r in rows:
        w.writerow([f'="{r[k]}"' if k == "barcode" and r.get(k) else r.get(k, "") for k, _ in cols])
    return ("﻿" + buf.getvalue()).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def send(self, body, ctype="application/json; charset=utf-8", status=200, extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        city = norm_city(q.get("city", ""))
        try:
            if u.path == "/":
                return self.send(PAGE, "text/html; charset=utf-8")
            if u.path == "/api/info":
                st = load_stores()
                cities = {}
                for s in st:
                    if s["city"]:
                        cities[s["city"]] = cities.get(s["city"], 0) + 1
                return self.send({"lib_error": lib_status(), "stores": len(st),
                                  "chains": len(set(s["folder"] for s in st)),
                                  "cities": sorted(cities.items(), key=lambda x: x[0])})
            if u.path == "/api/job":
                return self.send(JOB)
            if u.path == "/api/settings":
                s = load_settings()
                if "interval" in q:
                    s["interval_hours"] = float(q["interval"])
                if q.get("remove"):
                    s["cities"] = [c for c in s["cities"] if c != norm_city(q["remove"])]
                if "interval" in q or "remove" in q:
                    save_settings(s)
                return self.send(s)
            if u.path == "/api/update-stores":
                ok = start_job("stores", update_stores)
                return self.send({"started": ok})
            if u.path == "/api/fetch-city":
                if not city:
                    return self.send({"error": "לא נבחרה עיר"}, status=400)
                ok = start_job("city", lambda: fetch_city(city))
                return self.send({"started": ok})
            if u.path == "/api/city":
                st = city_stores(city)
                d = city_data(city)
                return self.send({"stores": st, "items": d["items"], "with_prices": d["stores_with_prices"]})
            if u.path == "/api/item":
                d = city_data(city)
                rows = [r for r in d["full"] if r["barcode"] == q.get("barcode")]
                return self.send(sorted(rows, key=lambda r: float(r["price"] or 0)))
            if u.path == "/api/csv":
                d = city_data(city)
                if q.get("mode") == "compare":
                    cols = [("barcode", "ברקוד"), ("name", "שם המוצר"), ("manu", "יצרן"), ("min", "מחיר זול ביותר"),
                            ("max", "מחיר יקר ביותר"), ("n", "מספר סניפים"), ("where", "איפה הכי זול")]
                    body, fname = to_csv(d["items"], cols), "compare.csv"
                else:
                    cols = [("chain", "רשת"), ("store", "מס' סניף"), ("sname", "סניף"), ("barcode", "ברקוד"),
                            ("name", "שם המוצר"), ("price", "מחיר"), ("manu", "יצרן"), ("qty", "כמות"),
                            ("unit", "יחידת מידה"), ("upd", "עדכון מחיר")]
                    body, fname = to_csv(d["full"], cols), "all_prices.csv"
                return self.send(body, "text/csv; charset=utf-8", extra={
                    "Content-Disposition": f"attachment; filename=\"{fname}\"; filename*=UTF-8''"
                                           + urllib.parse.quote(f"{city}_{fname}")})
            if u.path == "/api/open-folder":
                import os, subprocess
                DUMPS.mkdir(exist_ok=True)
                if sys.platform.startswith("win"):
                    os.startfile(str(DUMPS))  # noqa
                else:
                    subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(DUMPS)])
                return self.send({"ok": True})
            self.send({"error": "not found"}, status=404)
        except Exception as ex:  # noqa
            traceback.print_exc()
            self.send({"error": str(ex)}, status=500)

    def log_message(self, *a):
        pass


PORT = 8790
URL = f"http://127.0.0.1:{PORT}/"


def already_running():
    import urllib.request
    try:
        with urllib.request.urlopen(URL + "api/job", timeout=2) as r:
            return r.status == 200
    except Exception:  # noqa
        return False


def install():
    """יוצר קיצור דרך בשולחן העבודה והפעלה אוטומטית עם הדלקת המחשב (Windows)."""
    import base64
    import subprocess
    pyw = Path(sys.executable).with_name("pythonw.exe")
    if not pyw.exists():
        pyw = Path(sys.executable)
    app = Path(__file__).resolve()

    def ps_quote(s):
        return "'" + str(s).replace("'", "''") + "'"

    script = f"""
$s = New-Object -ComObject WScript.Shell
$startup = [Environment]::GetFolderPath('Startup')
$desktop = [Environment]::GetFolderPath('Desktop')
$l = $s.CreateShortcut((Join-Path $startup 'PricesApp.lnk'))
$l.TargetPath = {ps_quote(pyw)}
$l.Arguments = '"' + {ps_quote(app)} + '" --no-browser'
$l.WorkingDirectory = {ps_quote(BASE_DIR)}
$l.Save()
$d = $s.CreateShortcut((Join-Path $desktop 'מחירי סופר.lnk'))
$d.TargetPath = {ps_quote(pyw)}
$d.Arguments = '"' + {ps_quote(app)} + '"'
$d.WorkingDirectory = {ps_quote(BASE_DIR)}
$d.IconLocation = 'shell32.dll,165'
$d.Save()
"""
    enc = base64.b64encode(script.encode("utf-16-le")).decode()
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc], check=True)
    print("נוצרו: קיצור דרך בשולחן העבודה + הפעלה אוטומטית עם הדלקת המחשב")
    # הפעלת האפליקציה ברקע ופתיחת הדפדפן
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(pyw), str(app)], cwd=str(BASE_DIR), creationflags=flags)


def main():
    if sys.stdout is None or sys.stderr is None:  # הרצה ברקע (pythonw) - פלט לקובץ
        f = open(BASE_DIR / "log.txt", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = f
    if "--install" in sys.argv:
        return install()
    no_browser = "--no-browser" in sys.argv
    if already_running():
        if not no_browser:
            webbrowser.open(URL)
        return
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"האפליקציה פועלת בכתובת {URL}")
    threading.Thread(target=scheduler, daemon=True).start()
    if not no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(URL)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


# ================================================================ ממשק
PAGE = r"""<!DOCTYPE html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>מחירי סופר לפי עיר</title>
<style>
:root{--bg:#f6f4ef;--card:#fff;--ink:#1d1d1b;--muted:#6b6a65;--line:#e3e0d8;--accent:#1f6f5c;--soft:#e3f1ec;--err:#b3261e;--good:#1f6f5c}
@media (prefers-color-scheme:dark){:root{--bg:#151513;--card:#1e1e1b;--ink:#ecebe6;--muted:#9b9a93;--line:#33322e;--accent:#5cc3a6;--soft:#1d3a32;--err:#f2b8b5;--good:#5cc3a6}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:"Segoe UI",Heebo,Arial,sans-serif;line-height:1.5}
main{max-width:1150px;margin:0 auto;padding:28px 20px 60px}h1{margin:0;font-size:26px}.sub{color:var(--muted);margin:2px 0 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin-top:16px}
h2{font-size:17px;margin:0 0 10px}
.row{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.row.sp{justify-content:space-between}
input,select{font:inherit;font-size:15px;padding:8px 12px;border:1px solid var(--line);border-radius:9px;background:var(--bg);color:var(--ink)}
button,a.btn{font:inherit;font-size:14px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:9px;padding:8px 14px;cursor:pointer;text-decoration:none;display:inline-block}
button:hover,a.btn:hover{border-color:var(--accent)}
.primary{background:var(--accent)!important;color:#fff!important;border-color:var(--accent)!important;font-weight:600}
button:disabled{opacity:.55;cursor:default}
.muted{color:var(--muted);font-size:14px}.err{color:var(--err)}
.log{font-family:Consolas,monospace;font-size:13px;background:var(--bg);border:1px solid var(--line);border-radius:9px;padding:10px;margin-top:10px;max-height:160px;overflow:auto;white-space:pre-wrap}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.chip{background:var(--soft);border-radius:20px;padding:2px 10px;font-size:13px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:right;padding:7px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:500;position:sticky;top:0;background:var(--card);cursor:pointer;white-space:nowrap}
td.bc{font-family:Consolas,monospace;font-size:13px;unicode-bidi:plaintext}
td.num{white-space:nowrap}.cheap{color:var(--good);font-weight:600}
tr.item{cursor:pointer}tr.item:hover td{background:var(--soft)}
tr.detail td{background:var(--bg);padding:6px 14px}
.scroll{overflow:auto;max-height:640px}
.spin{display:inline-block;width:14px;height:14px;border:2px solid var(--line);border-top-color:var(--accent);border-radius:50%;animation:s .8s linear infinite;vertical-align:-2px;margin-left:6px}
@keyframes s{to{transform:rotate(360deg)}}
</style></head><body><main>
<h1>מחירי סופר לפי עיר</h1>
<p class="sub">שואב את קובצי המחירים שהרשתות מפרסמות לפי חוק המזון (הרשימה באתר gov.il) ומשווה בין הסניפים בעיר שבחרתם.</p>

<div class="card err" id="libErr" hidden></div>

<div class="card">
  <div class="row">
    <input id="city" list="cities" placeholder="בחרו עיר, למשל ירושלים" style="flex:1;min-width:220px" autocomplete="off">
    <datalist id="cities"></datalist>
    <button class="primary" id="fetchBtn">שאיבת מחירים לעיר</button>
  </div>
  <div class="muted" id="info" style="margin-top:8px"></div>
  <div class="chips" id="storeChips"></div>
  <div id="jobBox" hidden><div class="muted" id="jobTitle"></div><div class="log" id="jobLog"></div></div>
  <div class="row" style="margin-top:10px"><button id="storesBtn">עדכון רשימת הסניפים</button><button id="folderBtn">פתיחת תיקיית הקבצים</button></div>
</div>

<div class="card">
  <div class="row sp"><h2>עדכון אוטומטי</h2>
    <label class="muted">תדירות&nbsp;<select id="interval">
      <option value="1">כל שעה</option><option value="3">כל 3 שעות</option><option value="6">כל 6 שעות</option>
      <option value="12">כל 12 שעות</option><option value="24">פעם ביום</option><option value="0">כבוי</option></select></label></div>
  <div class="muted">ערים שכבר שאבתם מתעדכנות לבד ברקע, גם כשהחלון סגור (כל עוד המחשב דלוק).</div>
  <div class="chips" id="tracked"></div>
</div>

<div class="card" id="tableCard" hidden>
  <div class="row sp"><h2 id="tTitle"></h2>
    <div class="row"><a class="btn" id="csvCmp">הורדת ההשוואה לאקסל</a><a class="btn" id="csvAll">כל המחירים בכל הסניפים (CSV)</a></div></div>
  <div class="row" style="margin-bottom:6px"><input id="q" type="search" placeholder="חיפוש מוצר לפי שם, ברקוד או יצרן…" style="flex:1;min-width:220px"></div>
  <div class="muted" id="cnt"></div>
  <div class="scroll"><table><thead><tr id="ph"></tr></thead><tbody id="rows"></tbody></table></div>
  <div class="muted" style="margin-top:6px">לחיצה על מוצר מציגה את המחיר שלו בכל סניף.</div>
</div>
</main>
<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const LS={get(k,d){try{return localStorage.getItem(k)??d}catch(e){return d}},set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
const money=v=>v===''||v==null||isNaN(v)?esc(v):'₪'+Number(v).toFixed(2);
async function api(p){const r=await fetch(p);const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);return j;}
let items=[],sortKey='name',dir=1,curCity='',polling=null,cityCounts={};

async function loadInfo(){
  const i=await api('/api/info');
  if(i.lib_error){$('#libErr').hidden=false;$('#libErr').innerHTML='ספריית השאיבה לא מותקנת. הפעילו את <b>start_prices.bat</b> (הוא מתקין אותה), או הריצו: <code>py -m pip install il-supermarket-scraper</code><br><span class="muted">'+esc(i.lib_error)+'</span>';}
  cityCounts=Object.fromEntries(i.cities);
  $('#cities').innerHTML=i.cities.map(([c,n])=>`<option value="${esc(c)}">${n} סניפים</option>`).join('');
  $('#info').textContent=i.stores?`ברשימה: ${i.stores.toLocaleString('he-IL')} סניפים מ-${i.chains} רשתות ב-${i.cities.length} ערים`:'רשימת הסניפים עוד לא הורדה – היא תורד אוטומטית בשאיבה הראשונה (כמה דקות).';
}

function showJob(j){
  $('#jobBox').hidden=false;
  $('#jobTitle').innerHTML=j.running?'עובד…<span class="spin"></span>':(j.error?'<span class="err">שגיאה: '+esc(j.error)+'</span>':'הסתיים ✓');
  $('#jobLog').textContent=j.steps.join('\n');$('#jobLog').scrollTop=1e9;
  $('#fetchBtn').disabled=$('#storesBtn').disabled=j.running;
}
function poll(after){
  clearInterval(polling);
  polling=setInterval(async()=>{const j=await api('/api/job');showJob(j);
    if(!j.running){clearInterval(polling);polling=null;wasRunning=false;lastDone=j.done_at;await loadInfo();await loadSettings();if(after&&!j.error)after();}},1000);
}
$('#fetchBtn').onclick=async()=>{
  const c=$('#city').value.trim(); if(!c){$('#city').focus();return;}
  LS.set('city',c);
  const r=await api('/api/fetch-city?city='+encodeURIComponent(c));
  if(!r.started){alert('כבר רצה שאיבה – חכו שתסתיים');}
  poll(()=>showCity(c));
};
$('#storesBtn').onclick=async()=>{await api('/api/update-stores');poll();};
$('#folderBtn').onclick=()=>fetch('/api/open-folder');
$('#city').addEventListener('change',()=>{const c=$('#city').value.trim();if(cityCounts[c])showCity(c);});

async function showCity(c){
  curCity=c;
  const d=await api('/api/city?city='+encodeURIComponent(c));
  $('#storeChips').innerHTML=d.stores.map(s=>`<span class="chip">${esc(s.chain)} – ${esc(s.sname||'סניף '+s.store)}</span>`).join('');
  items=d.items;
  if(!items.length){$('#tableCard').hidden=true;return;}
  $('#tableCard').hidden=false;
  $('#tTitle').textContent=`${c} · ${d.with_prices} סניפים עם מחירים`;
  $('#csvCmp').href='/api/csv?mode=compare&city='+encodeURIComponent(c);
  $('#csvAll').href='/api/csv?city='+encodeURIComponent(c);
  draw();
}
const COLS=[['barcode','ברקוד'],['name','שם המוצר'],['manu','יצרן'],['min','הכי זול',1],['max','הכי יקר',1],['n','סניפים',1],['where','איפה הכי זול']];
function filtered(){
  let r=items;const q=$('#q').value.trim().toLowerCase();
  if(q)r=r.filter(x=>x.name.toLowerCase().includes(q)||x.barcode.includes(q)||(x.manu||'').toLowerCase().includes(q));
  const num=(COLS.find(c=>c[0]===sortKey)||[])[2];
  return [...r].sort((a,b)=>dir*(num?a[sortKey]-b[sortKey]:String(a[sortKey]).localeCompare(String(b[sortKey]),'he',{numeric:true})));
}
function draw(){
  const r=filtered(),MAX=1500;
  $('#ph').innerHTML=COLS.map(c=>`<th data-k="${c[0]}">${c[1]} ${sortKey===c[0]?(dir>0?'▲':'▼'):''}</th>`).join('');
  document.querySelectorAll('#ph th').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(sortKey===k)dir=-dir;else{sortKey=k;dir=1;}draw();});
  $('#cnt').textContent=`${r.length.toLocaleString('he-IL')} מוצרים`+(r.length>MAX?` · מוצגים ${MAX.toLocaleString('he-IL')} הראשונים – השתמשו בחיפוש`:'');
  $('#rows').innerHTML=r.slice(0,MAX).map(x=>`<tr class="item" data-b="${esc(x.barcode)}"><td class="bc">${esc(x.barcode)}</td><td>${esc(x.name)}</td><td>${esc(x.manu)}</td>
    <td class="num cheap">${money(x.min)}</td><td class="num">${money(x.max)}</td><td>${x.n}</td><td>${esc(x.where)}</td></tr>`).join('');
  document.querySelectorAll('tr.item').forEach(tr=>tr.onclick=()=>toggle(tr));
}
async function toggle(tr){
  const nx=tr.nextElementSibling; if(nx&&nx.classList.contains('detail')){nx.remove();return;}
  const rows=await api(`/api/item?city=${encodeURIComponent(curCity)}&barcode=${encodeURIComponent(tr.dataset.b)}`);
  const d=document.createElement('tr');d.className='detail';
  d.innerHTML=`<td colspan="7"><table>${rows.map((r,i)=>`<tr><td>${esc(r.chain)} – ${esc(r.sname||'סניף '+r.store)}</td><td class="num ${i==0?'cheap':''}">${money(r.price)}</td><td class="muted">${esc(r.upd)}</td></tr>`).join('')}</table></td>`;
  tr.after(d);
}
$('#q').oninput=draw;

function ago(t){if(!t)return 'טרם עודכן';const m=Math.round((Date.now()/1000-t)/60);
  return m<1?'עודכן עכשיו':m<60?`עודכן לפני ${m} דק'`:m<1440?`עודכן לפני ${Math.round(m/60)} שע'`:`עודכן לפני ${Math.round(m/1440)} ימים`;}
async function loadSettings(q=''){
  const s=await api('/api/settings'+q);
  $('#interval').value=String(+s.interval_hours);
  $('#tracked').innerHTML=s.cities.length?s.cities.map(c=>`<span class="chip"><a href="#" data-c="${esc(c)}" style="color:inherit">${esc(c)}</a> · ${ago(s.city_updated[c])} <a href="#" data-rm="${esc(c)}" title="הפסקת מעקב" style="color:var(--muted);text-decoration:none">✕</a></span>`).join('')
    :'<span class="muted">עדיין אין ערים במעקב – שאבו עיר והיא תתווסף לכאן.</span>';
  document.querySelectorAll('[data-c]').forEach(a=>a.onclick=e=>{e.preventDefault();$('#city').value=a.dataset.c;LS.set('city',a.dataset.c);showCity(a.dataset.c);});
  document.querySelectorAll('[data-rm]').forEach(a=>a.onclick=e=>{e.preventDefault();loadSettings('?remove='+encodeURIComponent(a.dataset.rm));});
}
$('#interval').onchange=()=>loadSettings('?interval='+$('#interval').value);

// מעקב קבוע אחרי עבודות רקע (כולל עדכונים אוטומטיים) ורענון הטבלה בסיומן
let wasRunning=false,lastDone=null;
setInterval(async()=>{
  if(polling)return;
  try{const j=await api('/api/job');
    if(j.running){showJob(j);wasRunning=true;}
    else if(wasRunning||(j.done_at&&j.done_at!==lastDone)){wasRunning=false;lastDone=j.done_at;showJob(j);await loadInfo();await loadSettings();if(curCity)showCity(curCity);}
  }catch(e){}
},3000);

(async()=>{
  await loadInfo(); await loadSettings();
  const j=await api('/api/job'); lastDone=j.done_at; if(j.running){showJob(j);wasRunning=true;}
  const c=LS.get('city','');if(c){$('#city').value=c;if(cityCounts[c])showCity(c);}
})();
</script></body></html>"""

if __name__ == "__main__":
    main()
