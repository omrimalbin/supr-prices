// שומר עותק של האפליקציה והנתונים האחרונים, כדי שתיפתח גם בלי אינטרנט.
// תמיד מנסה קודם את הרשת (נתונים טריים), ונופל לעותק השמור רק כשאין חיבור.
const CACHE = "prices-v12";
const SHELL = ["./", "index.html", "match.js", "manifest.webmanifest", "icon-192.png", "icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  const key = new URL(req.url); key.search = "";          // בלי פרמטרי עקיפת מטמון
  e.respondWith(
    fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(key.href, copy)); }
      return res;
    }).catch(() => caches.match(key.href).then(r => r || caches.match("index.html")))
  );
});
