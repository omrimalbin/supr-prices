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
  function matchAll(it, groups) { return groups.every(g => wordIn(it.aw || it.words, g)); }
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

  // מארז שהגודל שלו נרשם כגודל של יחידה אחת ("500 מ"ל מארז 12 יח'", "שישייה 1.5 ליטר") – מתקנים לגודל כל המארז,
  // כדי שהמחיר לליטר/לק"ג יהיה נכון
  const PACKW = [[/שישי(?:י)?(?:ה|ת)/, 6], [/רביעי(?:י)?(?:ה|ת)/, 4], [/שלישי(?:י)?(?:ה|ת)/, 3], [/תריסר/, 12]];
  const usz = it => it[4] / (it.pc || 1);   // גודל של יחידה אחת (במארז: חלקי מספר היחידות)
  function packCount(nm) {
    if (/\d\s*[*xX×]\s*\d/.test(nm) || /\d\s*-\s*\d+\s*(?:יח|ק"?ג)/.test(nm)) return [0, false];   // "6*750" כבר חושב; "9-10 יח'" / "12-17 ק"ג" – לא מארז
    for (const [re, c] of PACKW) if (re.test(nm)) return [c, true];
    let m = nm.match(/מארז\s*(?:של\s*)?(\d{1,2})(?!\d)/);
    if (m && +m[1] > 1) return [+m[1], true];
    m = nm.match(/(\d{1,2})\s*(?:יח'|יחידות|יח)(?![א-ת])/);          // "5 יח' 200 גרם" – לא ברור אם 200 ליחידה או לכולן
    return m && +m[1] > 1 ? [+m[1], false] : [0, false];
  }
  const minPrice = it => Math.min(...it[3].map(e => e[1]));
  // שני שלבים: מחיר לליטר/ק"ג "רגיל" לכל סוג מוצר (לפי המילה הראשונה), ואז לכל מארז בוחרים –
  // הגודל בשם הוא של יחידה (מכפילים) או של כל המארז – מה שקרוב יותר למחיר הרגיל של הסוג
  function packFixAll(items) {
    const pend = [], per = {};
    // מספר היחידות במארז – לכל מוצר (גם בלי גודל: "מים עין גדי שישייה 2")
    for (const it of items) if (!it.pc && it[5] !== "u") { const [n, strong] = packCount(it[1].replace(/[״]/g, '"').replace(/[׳`]/g, "'")); if (n > 1 && strong) it.pc = n; }
    for (const it of items) {
      if (it._pf || !(it[4] > 0) || (it[5] !== "g" && it[5] !== "ml") || !it[3].length) continue;
      it._pf = true;
      const nm = it[1].replace(/[״]/g, '"').replace(/[׳`]/g, "'");
      const [n, strong] = packCount(nm), up = minPrice(it) / it[4], k = it.words[0] + "|" + it[5];
      if (n) { const q = parseLine(nm); if (q.size && q.unit === it[5] && Math.abs(q.size - it[4]) < 1) pend.push([it, n, k, strong]); }
      else (per[k] = per[k] || []).push(up);
    }
    for (const [it, n, k, strong] of pend) {
      const arr = per[k];
      let mult = strong;
      if (arr && arr.length >= 3) {
        const s = arr.slice().sort((a, b) => a - b), med = s[s.length >> 1], up = minPrice(it) / it[4];
        mult = Math.abs(Math.log(up / n / med)) < Math.abs(Math.log(up / med));
      }
      if (mult) it[4] = it[4] * n;
      it.pc = n;                         // כך או כך זה מארז של n יחידות
    }
    // "6*750" / "750*6": מספר היחידות = המספר הקטן (עד 24)
    for (const it of items) if (!it.pc && it[4] > 0) {
      const mm = it[1].match(/(\d+(?:\.\d+)?)\s*[*xX×]\s*(\d+(?:\.\d+)?)/);
      if (mm) { const a = +mm[1], b = +mm[2], c = Math.min(a, b); if (Number.isInteger(c) && c >= 2 && c <= 24 && Math.max(a, b) > 24) it.pc = c; }
    }
  }
  // "שם של אוכל" במוצר: מילה שהיא המילה הראשונה בשמות של הרבה מוצרים בקטלוג (זיתים, טונה, חלב, מים...).
  // נלמד מהנתונים – כך גם בשם ארוך ("מארז רביעיית נתחי טונה בשמן פילטונה") יודעים שזה טונה.
  let HEADS = null, HEADS_OF = null, MANU = new Set();
  function headStats(items) {
    if (HEADS_OF === items) return HEADS;
    const cnt = new Map();
    const lead = ws => { let i = 0; while (i < ws.length - 1 && (LEAD.has(ws[i]) || /^\d/.test(ws[i]))) i++; return ws[i]; };
    for (const it of items) {
      const hs = new Set([lead(it.words), ...(it.heads || [])]);
      for (const h of hs) if (h && h.length >= 2 && !/^\d/.test(h)) { const k = stem(h); cnt.set(k, (cnt.get(k) || 0) + 1); }
    }
    MANU = new Set();   // מילים משמות יצרנים (תנובה, מולר, אסם...) – הן לא "שם האוכל"
    for (const it of items) if (it[2]) for (const w of norm(it[2]).split(" ")) if (w.length >= 2) MANU.add(w);
    HEADS = cnt; HEADS_OF = items; return cnt;
  }
  // המילה הכי "אוכלית" בשם: זו שהכי הרבה מוצרים מתחילים בה (לא מילת אריזה ולא שם יצרן)
  const PACKAGING = new Set(["נתחי", "מי", "פרוסות", "פרוס", "פרוסה", "קופסת", "בקבוק", "פחית", "מגש", "שקית", "סלסלת", "ארוז", "טרי", "קפוא"]);
  function foodIndex(toks, items) {
    const H = headStats(items); let bi = -1, bv = 5;
    for (let i = 0; i < toks.length; i++) { const t = toks[i];
      if (LEAD.has(t) || STOP.has(t) || PACKAGING.has(t) || t.length < 2) continue;
      const v = (H.get(stem(t)) || 0) * (MANU.has(t) ? 0.25 : 1); if (v > bv) { bv = v; bi = i; } }
    return bi;
  }
  // שאילתות חלופה לפי שם האוכל: "שם האוכל + המילה שאחריו", ואז "שם האוכל" לבד
  function foodQueries(text, items, brand) {
    const toks = norm(text).split(" ").filter(t => t && !STOP.has(t) && !/^\d/.test(t));
    const i = foodIndex(toks, items); if (i < 0) return [];
    const next = toks.slice(i + 1).find(t => !(brand && brand.has(t)) && !MANU.has(t) && !LEAD.has(t) && !PACKAGING.has(t) && t.length >= 2);
    return [...new Set([next ? toks[i] + " " + next : null, toks[i]].filter(Boolean))];
  }
  function prep(items) {           // מחשב פעם אחת מילים מנורמלות לכל מוצר
    if (!EXCL) EXCL = EXCLUDE.map(norm);
    let fresh = false;
    for (const it of items) if (!it.words) {
      it.words = norm(it[1]).split(" "); fresh = true;
      // שמות של אותו מוצר ברשתות אחרות (נלמד מהנתונים): כל המילים שלהם + המילה הראשונה של כל שם
      if (it[6]) { const vs = it[6].split(" | ").map(v => norm(v).split(" ")); it.aw = [...new Set(it.words.concat(...vs))]; it.heads = vs.map(v => v[0]); }
    }
    if (fresh) packFixAll(items);
    return items;
  }

  // כל המוצרים שמתאימים לשורה (בלי קשר לסניף), מסוננים לסוג הנכון
  function candidates(items, q) {
    // מילות קישור לא מחייבות התאמה ("קורנפלקס של אלופים")
    const toks = q.text.split(" ").filter(t => t && !STOP.has(t));
    if (!toks.length) return [];
    const groups = groupsOf(toks), allT = groups.flat();
    let wide = null;
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
    const head = res.filter(it => groups[0].some(t => wordMatches(firstReal(it.words), t) || wordMatches(it.words[0], t) || (it.heads || []).some(h => wordMatches(h, t))));
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
      wide = res.slice();   // כל הגדלים (גם מארזים) – לבחירה ידנית
      // מסננים אריזות קטנטנות/ענקיות: נשארים בטווח של הגודל הנפוץ
      const sizes = res.filter(it => it[4] > 0 && it[5] !== "kg").map(usz).sort((a, b) => a - b);
      if (sizes.length >= 4) {
        const med = sizes[Math.floor(sizes.length / 2)];
        res = res.filter(it => !(it[4] > 0) || it[5] === "kg" || (usz(it) >= med * 0.45 && usz(it) <= med * 2.6));
      }
    }
    // הגודל הנפוץ (למשל 12 ביצים, 1 ליטר חלב) – כדי שכל הסניפים יושוו על אותה אריזה
    const cnt = {};
    for (const it of res) if (it[4] > 0 && it[5] !== "kg") cnt[usz(it)] = (cnt[usz(it)] || 0) + 1;   // כמה מוצרים שונים בכל גודל
    const top2 = Object.keys(cnt).sort((a, b) => (cnt[b] - cnt[a]) || (a - b))[0];
    res.target = q.size || (top2 ? +top2 : 0);
    // שורה כללית במילה אחת ("מים"): כל הגדלים מתאימים – בוחרים לפי המחיר לליטר/לק"ג
    // שורה כללית במילה אחת של משקה ("מים", "קולה"): כל הגדלים מתאימים (בקבוק קטן או גדול) – לפי המחיר לליטר
    if (!q.size && toks.length === 1 && top === "ml") { res.allSizes = true; if (wide) { const w2 = wide; res.length = 0; res.push(...w2); } }
    res.tunit = top;
    res.wide = wide || res;
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
  // grams: מספר = גרמים שביקשו במפורש ("500 גרם"); או אובייקט {v, u} = כמות כוללת שצריך
  // (למשל מים × 6 -> 9 ליטר): אז כל הגדלים נכנסים – 6 בקבוקים בודדים או שישייה אחת – והזול לאותה כמות נבחר
  function bestIn(cands, store, qty = 1, deals = {}, grams = 0) {
    const W = grams && typeof grams === "object" ? grams : grams ? { v: grams * qty, u: "g", explicit: true } : null;
    if (cands.target && !W && !cands.allSizes) {   // קודם אריזות בגודל הנפוץ; אם אין בסניף – כל הגדלים
      const t = cands.target;
      const near = cands.filter(it => !(it[4] > 0) || it[5] === "kg" || (usz(it) >= t * 0.7 && usz(it) <= t * 1.5));
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
      if (W && it[5] !== "kg") {
        if (it[5] !== W.u || !(it[4] > 0)) continue;
        if (!W.explicit && it[4] > W.v * 1.5) continue;          // לא אריזה גדולה בהרבה ממה שצריך
        packs = Math.max(1, Math.ceil(W.v / it[4] - 0.15));
        if (packs > 12) continue;
      }
      if (W && it[5] === "kg" && W.u !== "g") continue;
      // מארז של כמה יחידות (שישייה): כמות 6 -> שישייה אחת או 6 בודדים; מארז גדול מהכמות – לא
      const pc = it.pc || 1;
      if (cands.allSizes && cands.target && it[4] > 0 && (usz(it) > Math.max(cands.target * 3.2, 2000) || usz(it) < cands.target / 3.2)) continue;
      let mpacks = 0;
      if (!W && pc > 1) { if (pc > qty * 1.25) continue; mpacks = Math.ceil(qty / pc - 1e-9); if (mpacks * pc > qty * 1.5) continue; }
      const amt = it[5] === "kg" ? Math.round(W ? W.v : qty * 1000) / 1000 : packs ? packs : mpacks || qty;
      const opts = [{ cost: amt * price, used: amt, promo: null }];
      for (const o of (e[2] || [])) {
        const [mq, bundle] = o;
        if (mq <= amt + 1e-9) {
          const n = Math.floor(amt / mq + 1e-9);
          opts.push({ cost: n * bundle + (amt - n * mq) * price, used: amt, promo: o });
        } else if (!W && deals[dealKey(it, o)] !== false) {
          const k = normKey(it, bundle / mq);
          if (!pending || k < pending.key) pending = { it, offer: o, key: k, price, mq, bundle, unit: bundle / mq };
        }
      }
      for (const op of opts) {
        // עם משקל: ההשוואה היא על אותה כמות בדיוק בכל סופר –
        // מחיר לגרם של האריזה × הגרמים שביקשו. מה שקונים בפועל (אריזות שלמות) נשמר בנפרד.
        let o2 = op;
        if (packs) {
          const adj = (op.cost / op.used) * (W.v / it[4]);
          o2 = { ...op, cost: adj, actual: op.cost, actualG: op.used * it[4], adjusted: Math.abs(op.used * it[4] - W.v) > 1, want: W };
        }
        const key = W ? o2.cost : normKey(it, op.cost / op.used);
        if (!best || key < best.key - 1e-9) best = { it, price, unitPrice: unitPrice(it, op.cost / op.used), key, weighed: it[5] === "kg", packs, pc, ...o2 };
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
      // סוג המוצר שנלמד מהשמות ברשתות אחרות: "מי עדן" נקרא גם "מים מינרליים מי עדן" -> מחפשים "מים ..."
      const heads = new Map();
      for (const it of p.cands.slice(0, 6)) for (const h of (it.heads || [])) if (h && h.length >= 2 && !wordMatches(h, toks[0]) && !STOP.has(h)) heads.set(h, (heads.get(h) || 0) + 1);
      for (const h of [...heads.keys()].sort((a, b) => heads.get(b) - heads.get(a)).slice(0, 2)) {
        queries.push([h, ...toks.slice(1).filter(t => !brand.has(t))].join(" "), h);
      }
      // שורה ארוכה (3+ מילים, למשל "זיתים ירוקים שלמים בטעם שום"): שתי המילים הראשונות – סוג המוצר ותיאור עיקרי
      // שם האוכל בשורה (או בשם המוצר שנמצא) – למשל "זיתים" מתוך "זיתים ירוקים שלמים בטעם שום בית השיטה"
      queries.push(...foodQueries(p.q.text, data.items, brand));
      if (p.cands[0]) queries.push(...foodQueries(p.cands[0][1], data.items, brand));
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
      const a = bestIn(altCands(p), si, p.q.qty, deals, gramsOf(p)) || bestIn(altCands(p), si, p.q.qty, deals, 0);
      if (a) { a.alt = true; delete a.offer; }
      return a;
    };
    // כמות כוללת: "500 גרם" במפורש, או – לשורה בלי גודל – הגודל הנפוץ × הכמות (מים × 6 = 9 ליטר)
    const gramsOf = p => {
      if (p.q.unit === "g" && p.q.size) return p.q.size;
      // מוצרים שנספרים ביחידות (ביצים): הכמות הנפוצה × הכמות שביקשו – 2 תבניות של 6 = 12 ביצים
      const c = p.cands;
      if (!p.q.size && c.tunit === "u" && c.target > 1) return { v: c.target * p.q.qty, u: "u" };
      return 0;
    };
    const bestPick = (p, si) => {
      const W = gramsOf(p);
      const bestIn_ = (c, s, q, d) => bestIn(c, s, q, d, W);
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
    const loose = g => it => (it.aw || it.words).some(w => g.some(t => t.length >= 3 && w.includes(t)));
    const res = items.filter(it => groups.every(g => wordIn(it.aw || it.words, g) || loose(g)(it) || (it[2] && norm(it[2]).includes(g[0]))));
    // רלוונטיות: מילים שלמות לפני חלקי מילה, ושם שמתחיל במילה הראשונה – קודם
    for (const it of res) it._rel = groups.reduce((a, g) => a + (wordIn(it.words, g) ? 2 : wordIn(it.aw || it.words, g) ? 1 : 0), 0)
      + (g0 => g0.some(t => wordMatches(it.words[0], t)) ? 1 : 0)(groups[0]);
    return res.sort((a, b) => b._rel - a._rel);
  }
  const api = { foodQueries, search, norm, parseLine, candidates, bestIn, unitPrice, priceIn, entryIn, dealKey, dealsFor, compareBasket, prep };
  if (typeof module !== "undefined") module.exports = api; else root.Match = api;
})(this);
