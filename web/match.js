// מנוע התאמה: שורה ברשימת קניות -> המוצר המתאים והזול ביותר בכל סניף.
// פריט בנתונים: [ברקוד, שם, יצרן, [[סניף, מחיר], ...], גודל, יחידה]   יחידה: g | ml | kg (שקיל) | u | ''
(function (root) {
  // מילים שהופכות מוצר לסוג אחר ("חלב שוקולד", "אורז פריך"). לא חלות אם הן מופיעות בשורה עצמה.
  const EXCLUDE = ("שוקולד שוקו בטעם טעם ממרח רוטב חטיף חטיפי סויה שקדים שקד שיבולת קוקוס משקה מעדן מעדני פודינג קרם " +
    "עוגה עוגת עוגיות עוגייה גלידה ופל וופל קרקר קרקרים פריכיות פריך פתיתים קורנפלקס הפתעה קינדר מרוכז אבקת אבקה ממתק סוכריות " +
    "מסטיק ארטיק שייק לתינוקות תמל מטרנה סימילאק לחתול לכלב חתולים כלבים קפה קקאו וניל תות בננה מוקה לאטה קפוצינו מוס " +
    "דייסה ניחוח בישום סבון שמפו מרכך קרמבו ביסקוויט ריזוטו תבשיל מוכן מוכנה מתובל תערובת מיקס סלט חמוץ חמוצים כבוש " +
    "פירה קציצות שניצל פשטידה מאפה בורקס פיצה ספריי מרסס תרסיס מגבונים קישוט סירופ ליקר בירה יין וודקה " +
    "מרוסק מקולפ חתוכ מיובש רסק קצוצ שימור במלח בחומץ ציפס צ'יפס מטוגנ ניוקי בוטנים בוטן שומשום כבושים פתיתי " +
    "פריכונים בייגלה שקדי ממולא ממולאים צנצנת בצנצנת נודלס אטריות אטריה פסטה בצק לזניה ספגטי").split(" ");
  // מילים קצרות שמחריגות רק בהתאמה מלאה ("נייר טואלט לח", "קפה קר")
  const EXACT = ["לח", "לחים", "לחות", "קר", "קרה"];
  const STOP = new Set(["של", "עם", "את", "או", "גם", "מ", "ה", "ב", "ל", "ו"]);
  // מילים שמופיעות בתחילת שם מוצר לפני הסוג עצמו
  const LEAD = new Set(["דגני", "בוקר", "מארז", "שישיית", "שישייה", "רביעיית", "רביעייה", "זוג", "מגש", "שקית", "חבילת",
    "טרי", "טריה", "טריים", "מהדרין", "מבחר", "יטבתה", "תנובה", "שטראוס", "טרה", "אסם", "עלית", "תלמה", "מותג", "חדש", "מבצע"]);
  // מילים נרדפות / חלופות (אחרי נרמול: ם->מ, בלי גרשיים). כל מילה בשורה מתאימה גם לחלופות שלה.
  const SYN = {
    "אוטס": ["שיבולת"], "שיבולת": ["אוטס"], "טבעוני": ["טבעונית", "צמחי", "צמחית"], "טבעונית": ["טבעוני", "צמחי", "צמחית"],
    "צמחי": ["טבעוני", "טבעונית", "צמחית"], "צמחית": ["טבעוני", "טבעונית", "צמחי"],
    "חיתולימ": ["טיטולימ"], "טיטולימ": ["חיתולימ"], "כלור": ["אקונומיקה"], "אקונומיקה": ["כלור"],
    "סודה": ["מוגזימ", "מוגז"], "נוזל": ["סבונ"], "שמפו": ["שמפו"], "טונה": ["טונה"],
    "לחמניות": ["לחמניה", "לחמנייה"], "פיתות": ["פיתה", "פיתה"], "קטשופ": ["קטשופ", "קאטשופ"], "קאטשופ": ["קטשופ"],
    "צ׳יפס": ["ציפס"], "קוטג": ["קוטג"], "ספגטי": ["ספגטי"], "פרגיות": ["פרגית"], "שניצל": ["שניצלונימ"],
  };
  // "חלב סויה" נקרא בחנות "משקה סויה": מוצרים מהצומח שמחליפים מוצרי חלב
  const PLANT = ["סויה", "שקדימ", "שקד", "שיבולת", "אוטס", "אורז", "קוקוס", "קשיו", "אגוזימ", "אפונה", "טבעוני", "טבעונית", "צמחי", "צמחית", "שועל"];
  const PLANT_SYN = { "חלב": ["משקה"], "יוגורט": ["מעדנ", "יוגורט"], "גבינה": ["גבינה"], "שמנת": ["תחליפ"] };
  // צורות שנראות כמו המילה אבל הן מוצר אחר
  const NOT_FORM = { "חלב": ["חלבה"], "שמנת": ["שמנ"] };
  function alts(t, toks) {
    const a = [t, ...(SYN[t] || [])];
    if (PLANT_SYN[t] && toks.some(x => PLANT.includes(x))) a.push(...PLANT_SYN[t]);
    return a;
  }
  // התאמת מילה לשם מוצר (כל המילים, בכל סדר, כולל חלופות)
  function groupsOf(toks) { return toks.map(t => alts(t, toks)); }
  function wordIn(ws, g) { return ws.some(w => g.some(t => wordMatches(w, t) && !(NOT_FORM[t] || []).includes(w))); }
  function matchAll(it, groups) { return groups.every(g => wordIn(it.words, g)); }
  // מותגים -> סוג המוצר הכללי (לחיפוש חלופה כשהמותג לא נמכר בסניף)
  const BRAND_GENERIC = [
    [/ (?:מי )?(?:עדנ|נביעות|עינ גדי|מעיינות|אקווה נובה|סנ בנדטו|נרה) /, "מימ"],
    [/ (?:קוקה )?קולה|פפסי /, "קולה"],
  ];
  const SUF = ["", "ה", "ת", "ות", "ימ", "י", "ית", "יות", "יימ", "ייה", "יה"];   // אחרי נרמול: ם -> מ

  const UNIT_RE = [
    [/(\d+(?:\.\d+)?)\s*(?:ק"?ג|קילו(?:גרם)?)/, "g", 1000],
    [/(\d+(?:\.\d+)?)\s*(?:גרם|גר|ג)(?![א-ת])/, "g", 1],
    [/(\d+(?:\.\d+)?)\s*(?:מ"?ל|מיליליטר)/, "ml", 1],
    [/(\d+(?:\.\d+)?)\s*(?:ליטר|ל)(?![א-ת])/, "ml", 1000],
    [/(?:^|\s)(חצי)\s*(?:ק"?ג|קילו(?:גרם)?)(?![א-ת])/, "g", 500],
    [/(?:^|\s)(?:1\s*)?(קילו|ק"ג)(?![א-ת])/, "g", 1000],
  ];

  let EXCL = null;
  function norm(s) {
    return String(s || "").toLowerCase()
      .replace(/[׳'`"״]/g, "")
      .replace(/[ךםןףץ]/g, c => ({ "ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ" })[c])
      .replace(/[^\w֐-׿%.]+/g, " ")
      .replace(/\s+/g, " ").trim();
  }

  // "חלב x2" / "2 חלב" / "אורז פרסי 1 קג" -> {text, qty, size, unit}
  function parseLine(line) {
    let t = String(line || "").trim(), qty = 1, size = 0, unit = "";
    const raw = t.replace(/[׳'`"״]/g, m => (m === "״" || m === '"') ? '"' : "");
    for (const [re, u, mul] of UNIT_RE) {
      const m = raw.match(re);
      if (m) { size = (/^\d/.test(m[1]) ? parseFloat(m[1]) : 1) * mul; unit = u; t = raw.replace(m[0], " "); break; }
    }
    let m = t.match(/(?:^|\s)[x×*]\s*(\d+)\s*$/i) || t.match(/\s(\d{1,2})\s*$/) || t.match(/^\s*(\d{1,2})\s+(?=\D)/);
    if (m) { qty = parseInt(m[1], 10) || 1; t = t.replace(m[0], " "); }
    return { text: norm(t), qty, size, unit };
  }

  const okRest = r => SUF.includes(r) || /^[\d%.]/.test(r);
  function stem(t) {
    for (const e of ["יות", "ייה", "ות", "ימ", "יה", "ה", "ת", "י"])
      if (t.length - e.length >= 2 && t.endsWith(e)) return t.slice(0, -e.length);
    return t;
  }
  function wordMatches(w, t) {
    if (!w) return false;
    if (w === t || (w.startsWith(t) && okRest(w.slice(t.length)))) return true;
    const b = stem(t);
    if (b !== t && w.startsWith(b) && okRest(w.slice(b.length))) return true;   // ביצים <-> ביצה, עגבניות <-> עגבנייה
    if ("הוב".includes(w[0]) && w.length > 2) return wordMatches(w.slice(1), t);  // "החלב"
    return false;
  }

  function prep(items) {           // מחשב פעם אחת מילים מנורמלות לכל מוצר
    if (!EXCL) EXCL = EXCLUDE.map(norm);
    for (const it of items) if (!it.words) it.words = norm(it[1]).split(" ");
    return items;
  }

  // כל המוצרים שמתאימים לשורה (בלי קשר לסניף), מסוננים לסוג הנכון
  function candidates(items, q) {
    // מילות קישור לא מחייבות התאמה ("קורנפלקס של אלופים")
    const toks = q.text.split(" ").filter(t => t && !STOP.has(t));
    if (!toks.length) return [];
    const groups = groupsOf(toks), allT = groups.flat();
    let res = items.filter(it => {
      const ws = it.words;
      if (!matchAll(it, groups)) return false;
      for (const w of ws) {
        for (const ex of EXCL) if (w.startsWith(ex) && !allT.some(t => t.startsWith(ex))) return false;
        if (EXACT.includes(w) && !toks.includes(w)) return false;
      }
      return true;
    });
    // "חלב קוקוס" – לא מי קוקוס
    if (toks.includes("חלב") && toks.some(x => PLANT.includes(x))) res = res.filter(it => !it.words.includes("מי"));
    // מעדיפים מוצרים ששמם מתחיל במילה הראשונה ("חלב 3%" ולא "קפה עם חלב")
    // (מדלגים על מילות פתיחה כלליות: "דגני בוקר קורנפלקס", "מארז במבה", "חלב טרי")
    const firstReal = ws => { let i = 0; while (i < ws.length - 1 && LEAD.has(ws[i])) i++; return ws[i]; };
    const head = res.filter(it => groups[0].some(t => wordMatches(firstReal(it.words), t) || wordMatches(it.words[0], t)));
    if (head.length) res = head;
    // מוצרים שקילים (מחיר לק"ג): רק לירקות/פירות/בשר בסיסיים (שם קצר), או כשאין חלופה ארוזה
    if (res.some(it => it[5] !== "kg")) res = res.filter(it => it[5] !== "kg" || it.words.length <= 4);
    // משווים באותה יחידת מידה (משקל / נפח / יחידות) – הנפוצה בין המועמדים
    const fam = it => it[5] === "kg" ? "g" : it[5];
    const fams = {};
    res.forEach(it => { if (it[4] > 0 && fam(it)) fams[fam(it)] = (fams[fam(it)] || 0) + 1; });
    const top = q.unit || Object.keys(fams).sort((a, b) => fams[b] - fams[a])[0];
    if (top) res = res.filter(it => !(it[4] > 0) || fam(it) === top);
    // גודל שביקשו במפורש
    if (q.size) {
      // במשקל (גרם): כל המותגים נכנסים – שקילים, וארוזים במשקל עד פי 2.5 מהכמות (כמה אריזות שצריך)
      const sized = q.unit === "g"
        ? res.filter(it => it[5] === "kg" || (it[5] === "g" && it[4] > 0 && it[4] <= q.size * 2.5))
        : res.filter(it => it[5] === q.unit && Math.abs(it[4] - q.size) <= q.size * 0.15);
      if (sized.length) res = sized;
    } else {
      // מסננים אריזות קטנטנות/ענקיות: נשארים בטווח של הגודל הנפוץ
      const sizes = res.filter(it => it[4] > 0 && it[5] !== "kg").map(it => it[4]).sort((a, b) => a - b);
      if (sizes.length >= 4) {
        const med = sizes[Math.floor(sizes.length / 2)];
        res = res.filter(it => !(it[4] > 0) || it[5] === "kg" || (it[4] >= med * 0.45 && it[4] <= med * 2.6));
      }
    }
    // הגודל הנפוץ (למשל 12 ביצים, 1 ליטר חלב) – כדי שכל הסניפים יושוו על אותה אריזה
    const cnt = {};
    for (const it of res) if (it[4] > 0 && it[5] !== "kg") cnt[it[4]] = (cnt[it[4]] || 0) + 1;   // כמה מוצרים שונים בכל גודל
    const top2 = Object.keys(cnt).sort((a, b) => (cnt[b] - cnt[a]) || (a - b))[0];
    res.target = q.size || (top2 ? +top2 : 0);
    return res;
  }

  function unitPrice(it, price) {   // מחיר לליטר/ק"ג (או ליחידה)
    if (it[5] === "kg") return price;
    if (it[4] > 0 && (it[5] === "g" || it[5] === "ml")) return price / it[4] * 1000;
    if (it[4] > 0 && it[5] === "u") return price / it[4];
    return null;
  }

  function entryIn(it, store) {
    for (const e of it[3]) if (e[0] === store) return e;
    return null;
  }
  function priceIn(it, store) { const e = entryIn(it, store); return e ? e[1] : null; }
  const normKey = (it, eff) => { const u = unitPrice(it, eff); return u != null ? u : eff * 1000; };
  const dealKey = (it, o) => it[0] + "|" + o[0] + "|" + o[1];

  // המוצר הכי משתלם בסניף לכמות qty, כולל מבצעים.
  // deals[key] = false – מבצע כמות שהמשתמש דחה (לא להציע שוב). מימוש = הגדלת הכמות בשורה.
  // grams – משקל שביקשו (למוצרים שקילים: המחיר לק"ג מוכפל במשקל). בלי משקל – ק"ג אחד.
  function bestIn(cands, store, qty = 1, deals = {}, grams = 0) {
    if (cands.target && !grams) {   // קודם אריזות בגודל הנפוץ; אם אין בסניף – כל הגדלים
      const t = cands.target;
      const near = cands.filter(it => !(it[4] > 0) || it[5] === "kg" || (it[4] >= t * 0.7 && it[4] <= t * 1.5));
      if (near.length < cands.length) {
        const b = bestIn(near, store, qty, deals, grams);
        if (b) return b;
      }
    }
    let best = null, pending = null;
    for (const it of cands) {
      const e = entryIn(it, store);
      if (!e) continue;
      const price = e[1];
      // כמות במשקל: שקיל – ק"ג בפועל; ארוז במשקל – מספר האריזות שמכסות את הכמות (עד 15% פחות נחשב מספיק)
      let packs = 0;
      if (grams && it[5] !== "kg") {
        if (it[5] !== "g" || !(it[4] > 0)) continue;
        packs = Math.max(1, Math.ceil(grams / it[4] - 0.15));
        if (packs > 12) continue;
      }
      const amt = it[5] === "kg" ? Math.round(qty * (grams || 1000)) / 1000 : packs ? qty * packs : qty;
      const opts = [{ cost: amt * price, used: amt, promo: null }];
      for (const o of (e[2] || [])) {
        const [mq, bundle] = o;
        if (mq <= amt + 1e-9) {
          const n = Math.floor(amt / mq + 1e-9);
          opts.push({ cost: n * bundle + (amt - n * mq) * price, used: amt, promo: o });
        } else if (!grams && deals[dealKey(it, o)] !== false) {
          const k = normKey(it, bundle / mq);
          if (!pending || k < pending.key) pending = { it, offer: o, key: k, price, mq, bundle, unit: bundle / mq };
        }
      }
      for (const op of opts) {
        // עם משקל: ההשוואה היא על אותה כמות בדיוק בכל סופר –
        // מחיר לגרם של האריזה × הגרמים שביקשו. מה שקונים בפועל (אריזות שלמות) נשמר בנפרד.
        let o2 = op;
        if (packs) {
          const adj = (op.cost / op.used) * (grams / it[4]) * qty;
          o2 = { ...op, cost: adj, actual: op.cost, actualG: op.used * it[4], adjusted: Math.abs(op.used * it[4] - grams * qty) > 1 };
        }
        const key = grams ? o2.cost : normKey(it, op.cost / op.used);
        if (!best || key < best.key - 1e-9) best = { it, price, unitPrice: unitPrice(it, op.cost / op.used), key, weighed: it[5] === "kg", packs, ...o2 };
      }
    }
    if (best && pending && pending.key < best.key * 0.98) best.offer = pending;   // מבצע כמות שמשתלם יותר – לשאול
    return best;
  }

  // השוואת סל: lines = [{line, pick?: ברקוד נעול}]
  function compareBasket(data, lines, deals = {}) {
    prep(data.items);
    const byCode = new Map(data.items.map(it => [it[0], it]));
    // l.pick = מוצר קבוע (📌, בכל הסניפים); l.tmp = {סניף: ברקוד} – החלפה ידנית בסניף מסוים בלבד
    const parsed = lines.map(l => {
      const q = parseLine(l.line);
      if (l.qty) q.qty = Math.max(q.qty, l.qty);   // כמות שהוגדלה בעקבות מבצע
      return { ...l, q, cands: candidates(data.items, q), pinned: l.pick && byCode.get(l.pick), tmp: l.tmp || {} };
    });
    // חלופה לסניף שלא מוכר את המוצר המבוקש: מותג -> סוג כללי (מי עדן -> מים), או בלי מילה (בדרך כלל המותג)
    const altCands = p => {
      if (p._alt) return p._alt;
      const toks = norm(p.q.text).split(" ").filter(t => t && !STOP.has(t)), seen = new Set(p.cands.map(it => it[0])), out = [];
      const queries = [];
      const txt = " " + toks.join(" ") + " ";
      for (const [re, gen] of BRAND_GENERIC) if (re.test(txt)) queries.push(txt.replace(re, " " + gen + " ").trim());
      // מורידים רק מילים שהן שם יצרן/מותג (לפי שדה היצרן של המוצרים המתאימים) – לא "לבנה", "מתוקה", "סויה"
      const brand = new Set();
      for (const it of p.cands) for (const w of norm(it[2] || "").split(" ")) if (w.length >= 2) brand.add(w);
      const drop = toks.filter((t, j) => j >= 1 && brand.has(t));
      if (drop.length) queries.push(toks.filter(t => !drop.includes(t)).join(" "));
      for (const qt of queries) {
        for (const it of candidates(data.items, { ...p.q, text: qt })) if (!seen.has(it[0])) { seen.add(it[0]); out.push(it); }
        if (out.length >= 40) break;
      }
      return (p._alt = out);
    };
    parsed.forEach(p => { p.altFn = () => altCands(p); });   // לבחירה ידנית (החלפה)
    const pick = (p, si) => {
      const b = bestPick(p, si);
      if (b || p.tmp[si]) return b;
      const a = bestIn(altCands(p), si, p.q.qty, deals, gramsOf(p));
      if (a) { a.alt = true; delete a.offer; }
      return a;
    };
    const gramsOf = p => (p.q.unit === "g" ? p.q.size : 0);
    const bestPick = (p, si) => {
      const bestIn_ = (c, s, q, d) => bestIn(c, s, q, d, gramsOf(p));
      const t = p.tmp[si] && byCode.get(p.tmp[si]);
      if (t) { const b = bestIn_([t], si, p.q.qty, deals); if (b) { b.manual = true; return b; } }
      if (p.pinned) {
        const b = bestIn_([p.pinned], si, p.q.qty, deals);
        if (b) { b.pinned = true; return b; }
        const f = bestIn_(p.cands, si, p.q.qty, deals);   // הקבוע לא נמכר כאן – הזול ביותר בסניף
        if (f) { f.fallback = true; delete f.offer; }   // בלי הצעות מבצע על מוצר דומה
        return f;
      }
      return bestIn_(p.cands, si, p.q.qty, deals);         // ברירת מחדל: הזול ביותר בסניף
    };
    const stores = data.stores.map((st, si) => {
      let total = 0, found = 0, offers = 0;
      const rows = parsed.map(p => {
        const b = pick(p, si);
        if (!b) return null;
        found++;
        total += b.cost;
        if (b.offer) offers++;
        return b;
      });
      return { si, name: st[0] + " – " + st[1], total, found, offers, rows };
    });
    stores.sort((a, b) => (b.found - a.found) || (a.total - b.total));
    const mixed = parsed.map(p => {
      let best = null;
      data.stores.forEach((_, si) => {
        const b = pick(p, si);
        if (!b) return;
        // סל משולב: המוצר שבחרת (איפה שנמכר) קודם לתחליף
        if (!best || (best.fallback && !b.fallback) || (best.fallback === !!b.fallback && b.key < best.key)) best = { ...b, si };
      });
      return best;
    });
    return { parsed, stores, mixed };
  }


  // כל מבצעי הכמות על מוצרים שמתאימים לשורה, בסניף מסוים (מהמשתלם ביותר)
  function dealsFor(cands, store) {
    const out = [], seen = new Set();
    for (const it of cands) {
      const e = entryIn(it, store);
      if (!e || !e[2]) continue;
      for (const o of e[2]) {
        const k = dealKey(it, o);
        if (seen.has(k)) continue;
        seen.add(k);
        out.push({ it, offer: o, price: e[1], mq: o[0], bundle: o[1], unit: o[1] / o[0], key: k, rank: normKey(it, o[1] / o[0]) });
      }
    }
    return out.sort((a, b) => a.rank - b.rank);
  }

  // חיפוש חופשי בלשונית המוצרים: כל המילים בכל סדר, עם צורות (יחיד/רבים) וחלופות
  function search(items, text) {
    prep(items);
    const toks = norm(text).split(" ").filter(t => t && !STOP.has(t));
    if (!toks.length) return items.slice();
    const groups = groupsOf(toks);
    const loose = g => it => it.words.some(w => g.some(t => t.length >= 3 && w.includes(t)));
    const res = items.filter(it => groups.every(g => wordIn(it.words, g) || loose(g)(it) || (it[2] && norm(it[2]).includes(g[0]))));
    // רלוונטיות: מילים שלמות לפני חלקי מילה, ושם שמתחיל במילה הראשונה – קודם
    for (const it of res) it._rel = groups.reduce((a, g) => a + (wordIn(it.words, g) ? 2 : 0), 0)
      + (g0 => g0.some(t => wordMatches(it.words[0], t)) ? 1 : 0)(groups[0]);
    return res.sort((a, b) => b._rel - a._rel);
  }
  const api = { search, norm, parseLine, candidates, bestIn, unitPrice, priceIn, entryIn, dealKey, dealsFor, compareBasket, prep };
  if (typeof module !== "undefined") module.exports = api; else root.Match = api;
})(this);
