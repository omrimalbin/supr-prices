// שומר עותק של האפליקציה והנתונים האחרונים, כדי שתיפתח גם בלי אינטרנט.
// תמיד מנסה קודם את הרשת (נתונים טריים), ונופל לעותק השמור רק כשאין חיבור.
const CACHE = "prices-v31";
const DATA = "prices-data";   // נשמר בין גרסאות של האפליקציה
const SHELL = ["./", "index.html", "match.js", "manifest.webmanifest", "icon-192.png", "icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE && k !== DATA).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  const key = new URL(req.url); key.search = "";          // בלי פרמטרי עקיפת מטמון
  // קובצי מחירים עם מספר גרסה (data/<עיר>.json?<זמן עדכון>): אם הגרסה הזו כבר שמורה – מיד מהטלפון,
  // בלי להוריד שוב כמה מגה. גרסה חדשה (אחרי עדכון מחירים) יורדת פעם אחת ונשמרת.
  const u = new URL(req.url);
  if (/\/data\/(?!cities\.json)[^/]+\.json$/.test(u.pathname) && u.search) {
    e.respondWith(caches.open(DATA).then(c => c.match(req.url).then(hit => hit || fetch(req).then(res => {
      if (res.ok) {
        const copy = res.clone();
        c.keys().then(ks => Promise.all(ks.filter(k => new URL(k.url).pathname === u.pathname).map(k => c.delete(k))))
          .then(() => c.put(req.url, copy));
      }
      return res;
    }).catch(() => c.keys().then(ks => { const k = ks.find(k => new URL(k.url).pathname === u.pathname); return k ? c.match(k) : Response.error(); })))));
    return;
  }
  e.respondWith(
    fetch(req, { cache: "no-cache" }).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(key.href, copy)); }
      return res;
    }).catch(() => caches.match(key.href).then(r => r || caches.match("index.html")))
  );
});
