"use strict";

/* 🧩 Kalıplar: fixed expressions by level and category (app/content/patterns), learning cards and quizzes
   (meaning both ways, listen & write, fill the gap, put the sentence in order, own sentence). Progress has its
   own spaced-repetition table (backend/patterns.py), separate from the vocabulary notebook.
   Shares helpers with words.js (shuffle, wordAnswerInput, sameWord, iconButton, speakText, lnode). */

const patternsUi = {
  el: {
    levels: $("#patterns-levels"), cats: $("#patterns-cats"), summary: $("#patterns-summary"),
    study: $("#patterns-study"), list: $("#patterns-list"), search: $("#patterns-search"),
    filter: $("#patterns-filter"), learn: $("#patterns-learn"), review: $("#patterns-review"),
    sources: $("#patterns-sources"),
  },
  overview: null,
  level: store.get("patternsLevel"),
  cat: store.get("patternsCat") || "all",
  lists: {},        // level → patterns (with status)
  shown: 60,
  session: null,
};

const PATTERN_BATCH = 5;
const PATTERN_QUIZ_TITLES = { learn: "Test", review: "Tekrar" };

/* ------------------------------------------------------------------ page */

async function loadPatternsPage() {
  try {
    patternsUi.overview = await api("/api/patterns");
  } catch (err) {
    patternsUi.el.list.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted"));
    return;
  }
  const o = patternsUi.overview;
  if (!o.levels.some((l) => l.level === patternsUi.level && l.total)) {
    patternsUi.level = o.levels.some((l) => l.level === o.my_level && l.total) ? o.my_level
      : o.levels.find((l) => l.total)?.level;
  }
  renderPatternLevels();
  renderPatternCats();
  Text.render(patternsUi.el.review, o.due ? `🔁 Tekrar et (${o.due})` : "🔁 Tekrar et");
  patternsUi.el.review.disabled = !o.due;
  await loadPatternList();
}

async function refreshPatterns() {
  patternsUi.overview = await api("/api/patterns");
  renderPatternLevels();
  Text.render(patternsUi.el.review, patternsUi.overview.due ? `🔁 Tekrar et (${patternsUi.overview.due})` : "🔁 Tekrar et");
  patternsUi.el.review.disabled = !patternsUi.overview.due;
  await loadPatternList(true);
}

function renderPatternLevels() {
  const box = patternsUi.el.levels;
  box.replaceChildren();
  for (const l of patternsUi.overview.levels) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(l.level === patternsUi.level));
    b.disabled = !l.total;
    Text.render(b, l.total ? `${l.level} · ${l.learned}/${l.total}` : `${l.level} · yakında`);
    b.title = `${l.total} kalıp: ${l.learning} öğreniliyor, ${l.learned} öğrenildi`;
    b.addEventListener("click", () => {
      patternsUi.level = l.level;
      store.set("patternsLevel", l.level);
      patternsUi.shown = 60;
      renderPatternLevels();
      loadPatternList();
    });
    box.append(b);
  }
  const cur = patternsUi.overview.levels.find((l) => l.level === patternsUi.level);
  Text.render(patternsUi.el.summary, cur
    ? `${cur.level} seviyesinde ${cur.total} kalıp · ${cur.learning} öğreniliyor · ${cur.learned} öğrenildi`
    + (patternsUi.level === patternsUi.overview.my_level ? " (senin seviyen)" : "")
    : "");
}

function renderPatternCats() {
  const box = patternsUi.el.cats;
  box.replaceChildren();
  const cats = { all: "Hepsi", ...patternsUi.overview.cats };
  for (const [key, label] of Object.entries(cats)) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip small";
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(key === patternsUi.cat));
    Text.render(b, label);
    b.addEventListener("click", () => {
      patternsUi.cat = key;
      store.set("patternsCat", key);
      patternsUi.shown = 60;
      renderPatternCats();
      renderPatternList();
    });
    box.append(b);
  }
}

async function loadPatternList(force = false) {
  const level = patternsUi.level;
  if (!level) return;
  if (force || !patternsUi.lists[level]) {
    patternsUi.el.list.replaceChildren(Text.create("p", "Yükleniyor…", "muted"));
    try {
      patternsUi.lists[level] = (await api(`/api/patterns/level/${level}`)).patterns;
    } catch (err) {
      patternsUi.el.list.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted"));
      return;
    }
  }
  renderPatternList();
}

/** The level's patterns in the chosen category (the learn button and the list use this). */
function visiblePatterns() {
  const all = patternsUi.lists[patternsUi.level] || [];
  return patternsUi.cat === "all" ? all : all.filter((x) => x.cat === patternsUi.cat);
}

function renderPatternList() {
  const q = patternsUi.el.search.value.trim().toLowerCase();
  const filter = patternsUi.el.filter.value;
  const items = visiblePatterns().filter((x) => (filter === "all" || x.status === filter)
    && (!q || x.p.toLowerCase().includes(q) || x.tr.toLowerCase().includes(q)
      || x.examples.some((ex) => ex.en.toLowerCase().includes(q))));
  const box = patternsUi.el.list;
  box.replaceChildren();
  if (!items.length) {
    box.append(Text.create("p", "Bu filtreyle kalıp yok.", "muted"));
    return;
  }
  for (const x of items.slice(0, patternsUi.shown)) box.append(patternRow(x));
  if (items.length > patternsUi.shown) {
    const more = Text.create("button", `Daha fazla göster (${items.length - patternsUi.shown} kalıp daha)`, "ghost small");
    more.type = "button";
    more.addEventListener("click", () => { patternsUi.shown += 120; renderPatternList(); });
    box.append(more);
  }
}

function patternRow(x) {
  const row = document.createElement("div");
  row.className = `vocab-row word-row status-${x.status}`;
  const main = document.createElement("div");
  main.className = "vocab-main";
  main.append(Text.create("strong", x.p), " ", Text.create("span", `${x.cat_tr} · ${x.topic_tr} · ${x.register_tr}`, "muted small"),
    Text.create("div", x.tr, "vocab-meaning"));
  row.append(iconButton("🔊", "Dinle", () => speakText(patternSpeech(x))), main,
    Text.create("span", STATUS_TR[x.status], `word-status ${x.status}`));
  row.addEventListener("click", () => openPatternCard(x));
  row.title = "Kartı aç: anlam, kullanım notu, örnekler";
  return row;
}

/** The pattern read aloud: the slot is skipped ("Could you, please?" is odd, so the first example is read). */
function patternSpeech(x) {
  return x.p.includes("___") ? x.examples[0].en : x.p;
}

/* ------------------------------------------------------------------ card */

/** A full card for one pattern: pattern, meaning, usage note, the two examples. */
function patternCardView(x, { onAdd = null } = {}) {
  const card = document.createElement("div");
  card.className = "flashcard word-card";
  const front = lnode("div", "fc-front", Text.create("div", x.p, "fc-word pattern-word"),
    iconButton("🔊", "Dinle", () => speakText(patternSpeech(x))));
  card.append(front, Text.create("div", `${x.cat_tr} · ${x.topic_tr} · ${x.register_tr}`, "muted"),
    Text.create("div", x.tr, "fc-meaning"), Text.create("div", x.note_tr, "pattern-note"));
  const exBox = document.createElement("div");
  exBox.className = "word-examples";
  for (const ex of x.examples) exBox.append(wordExampleRow(ex));
  card.append(exBox);
  if (onAdd) card.append(onAdd);
  return card;
}

function openPatternCard(x) {
  endPatternSession();
  const box = patternsUi.el.study;
  box.hidden = false;
  let add = null;
  if (x.status === "new") {
    add = Text.create("button", "➕ Öğrenmeye başla", "primary small");
    add.type = "button";
    add.addEventListener("click", async () => {
      add.disabled = true;
      await api("/api/patterns/learn", { method: "POST", body: { ids: [x.id] } });
      await refreshPatterns();
      endPatternSession();
    });
  } else {
    add = Text.create("button", "🗑 Öğrenme listesinden çıkar", "ghost small");
    add.type = "button";
    add.addEventListener("click", async () => {
      if (!window.confirm(`"${x.p}" öğrenme listesinden çıkarılsın mı? (tekrar takvimi silinir)`)) return;
      await api(`/api/patterns/${x.id}/progress`, { method: "DELETE" });
      await refreshPatterns();
      endPatternSession();
    });
  }
  const close = Text.create("button", "Kapat", "ghost small");
  close.type = "button";
  close.addEventListener("click", endPatternSession);
  box.replaceChildren(patternCardView(x, { onAdd: add }), close);
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* --------------------------------------------------------------- sessions */

function endPatternSession() {
  patternsUi.session = null;
  patternsUi.el.study.hidden = true;
  patternsUi.el.study.replaceChildren();
}

function patternSessionExit() {
  const b = Text.create("button", "✕ Çalışmayı bitir", "ghost small");
  b.type = "button";
  b.addEventListener("click", async () => {
    endPatternSession();
    await refreshPatterns();
  });
  return b;
}

/** Learn: cards for new patterns of the level (and category), then a quiz on them. */
async function startPatternLearning() {
  const fresh = shuffle(visiblePatterns().filter((x) => x.status === "new")).slice(0, PATTERN_BATCH);
  if (!fresh.length) {
    window.alert("Bu seviye ve kategorideki bütün kalıplar öğrenme listende. Tekrar et ya da başka bir seviye/kategori seç.");
    return;
  }
  await api("/api/patterns/learn", { method: "POST", body: { ids: fresh.map((x) => x.id) } });
  patternsUi.session = { kind: "learn", items: fresh, i: 0 };
  showPatternLearnCard();
}

function showPatternLearnCard() {
  const s = patternsUi.session;
  const box = patternsUi.el.study;
  box.hidden = false;
  const x = s.items[s.i];
  const card = document.createElement("div");
  card.className = "flashcard word-card";
  card.append(Text.create("div", `Yeni kalıp ${s.i + 1} / ${s.items.length}`, "fc-progress muted small"));
  card.append(lnode("div", "fc-front", Text.create("div", x.p, "fc-word pattern-word"),
    iconButton("🔊", "Dinle", () => speakText(patternSpeech(x)))),
    Text.create("div", `${x.cat_tr} · ${x.topic_tr} · ${x.register_tr}`, "muted"));
  speakText(patternSpeech(x));
  const reveal = Text.create("button", "Anlamını göster (Boşluk)", "primary");
  reveal.type = "button";
  const next = () => {
    s.i += 1;
    if (s.i < s.items.length) showPatternLearnCard();
    else startPatternQuiz(s.items, "learn");
  };
  reveal.addEventListener("click", () => {
    reveal.remove();
    card.append(Text.create("div", x.tr, "fc-meaning"), Text.create("div", x.note_tr, "pattern-note"));
    const exBox = document.createElement("div");
    exBox.className = "word-examples";
    for (const ex of x.examples) exBox.append(wordExampleRow(ex));
    card.append(exBox);
    const btn = Text.create("button", s.i + 1 < s.items.length ? "Sonraki kalıp →" : "Teste geç →", "primary");
    btn.type = "button";
    btn.addEventListener("click", next);
    card.append(btn);
    btn.focus();
  });
  card.append(reveal);
  box.replaceChildren(card, patternSessionExit());
  reveal.focus();
}

/** Review: patterns that are due today, asked in mixed ways. */
async function startPatternReview() {
  const due = await api("/api/patterns/due");
  if (!due.length) {
    window.alert("Bugün tekrar edilecek kalıp yok.");
    return;
  }
  startPatternQuiz(due.slice(0, 20), "review");
}

/* ------------------------------------------------------------------ quiz */

function patternModesFor(x, ownLeft) {
  const m = ["mc_en", "mc_tr", "listen", "fill", "order"];
  if (ownLeft > 0) m.push("own");
  return m;
}

function startPatternQuiz(items, kind) {
  let ownLeft = 2;  // own sentences take longer: at most two per session
  const questions = shuffle(items.slice()).map((x) => {
    const modes = patternModesFor(x, ownLeft);
    const mode = modes[Math.floor(Math.random() * modes.length)];
    if (mode === "own") ownLeft -= 1;
    return { x, mode, retried: false };
  });
  patternsUi.session = { kind, queue: questions, done: 0, total: questions.length, right: 0, wrong: [] };
  nextPatternQuestion();
}

function nextPatternQuestion() {
  const s = patternsUi.session;
  if (!s) return;
  const q = s.queue.shift();
  if (!q) return finishPatternQuiz();
  const box = patternsUi.el.study;
  box.hidden = false;
  const card = document.createElement("div");
  card.className = "flashcard word-card quiz";
  card.append(Text.create("div", `${PATTERN_QUIZ_TITLES[s.kind]} · ${s.done + 1} / ${s.total}`, "fc-progress muted small"));
  box.replaceChildren(card, patternSessionExit());
  ({ mc_en: askPatternChoice, mc_tr: askPatternChoice, listen: askPatternListen, fill: askPatternFill,
    order: askPatternOrder, own: askPatternOwn })[q.mode](card, q);
}

/** Record the answer (spaced repetition) and show the verdict with a "next" button. */
async function patternAnswered(card, q, grade, verdictText, cls) {
  const s = patternsUi.session;
  card.append(Text.create("div", verdictText, `verdict ${cls}`));
  if (grade) {  // grade null: the answer could not be checked, nothing is recorded
    try {
      await api(`/api/patterns/${q.x.id}/review`, { method: "POST", body: { grade } });
    } catch (err) {
      card.append(Text.create("div", `⚠️ Kaydedilemedi: ${err.message}`, "muted small"));
    }
  }
  if (grade === "good") s.right += 1;
  else if (!grade) s.total -= 1;  // not counted
  else if (!q.retried) {
    s.wrong.push(q.x);
    s.queue.push({ ...q, retried: true, mode: q.mode === "own" ? "mc_en" : q.mode });  // once more at the end
    s.total += 1;
  }
  if (grade) s.done += 1;
  const next = Text.create("button", "Devam →", "primary");
  next.type = "button";
  next.addEventListener("click", nextPatternQuestion);
  card.append(next);
  next.focus();
}

/** Wrong options for meaning questions: other patterns, the same category first. */
function patternPool(target) {
  const all = Object.values(patternsUi.lists).flat();
  const others = all.filter((y) => y.id !== target.id && y.tr !== target.tr && y.p !== target.p);
  return shuffle(others.filter((y) => y.cat === target.cat)).concat(shuffle(others.filter((y) => y.cat !== target.cat)));
}

function askPatternChoice(card, q) {
  const x = q.x;
  const toTr = q.mode === "mc_en";
  const distractors = [];
  for (const o of patternPool(x)) {
    const label = toTr ? o.tr : o.p;
    if (!distractors.includes(label)) distractors.push(label);
    if (distractors.length === 3) break;
  }
  const right = toTr ? x.tr : x.p;
  const options = shuffle([right, ...distractors]);
  card.append(Text.create("div", toTr ? "Bu kalıbın anlamı hangisi?" : "Bu anlama gelen kalıp hangisi?", "muted"),
    toTr ? lnode("div", "fc-front", Text.create("div", x.p, "fc-word pattern-word"),
      iconButton("🔊", "Dinle", () => speakText(patternSpeech(x))))
      : Text.create("div", x.tr, "fc-meaning"));
  const opts = document.createElement("div");
  opts.className = "quiz-options";
  for (const label of options) {
    const b = Text.create("button", label, "quiz-option");
    b.type = "button";
    b.addEventListener("click", () => {
      opts.querySelectorAll("button").forEach((y) => {
        y.disabled = true;
        if (y._text === right) y.classList.add("correct");
      });
      const ok = label === right;
      if (!ok) b.classList.add("wrong");
      patternAnswered(card, q, ok ? "good" : "again", ok ? "Doğru ✓" : `Yanlış — doğrusu: ${right}`, ok ? "ok" : "wrong");
    });
    opts.append(b);
  }
  card.append(opts);
}

/** Listen & write: one of the examples (a whole sentence with the pattern in it). */
function askPatternListen(card, q) {
  const x = q.x;
  const ex = x.examples[Math.floor(Math.random() * x.examples.length)];
  const front = lnode("div", "fc-front", iconButton("🔊", "Tekrar dinle", () => speakText(ex.en)));
  front.append(transcriptButton(ex.en, front));
  card.append(Text.create("div", "Dinle ve cümleyi yaz:", "muted"), front,
    Text.create("div", `ipucu: ${x.tr}`, "muted small"));
  speakText(ex.en);
  wordAnswerInput(card, "Duyduğun cümle…", (text) => {
    const ok = answerMatches([ex.en], text);
    patternAnswered(card, q, ok ? "good" : "again", ok ? `Doğru ✓ — ${ex.en}` : `Yanlış — doğrusu: ${ex.en}`,
      ok ? "ok" : "wrong");
    if (!ok) card.append(Text.create("div", ex.tr, "muted small"));
  });
}

/** The example with the pattern's fixed parts blanked out: {text, answer}. */
function blankPattern(sentence, p) {
  // The fixed parts without their punctuation: "Could you ___, please?" → "Could you", "please"
  const parts = p.split("___").map((s) => s.replace(/^[\s,.;:!?…]+|[\s,.;:!?…]+$/g, "")).filter(Boolean);
  let text = sentence, at = 0;
  const answers = [];
  for (const part of parts) {
    const i = text.toLowerCase().replace(/’/g, "'").indexOf(part.toLowerCase().replace(/’/g, "'"), at);
    if (i < 0) return null;
    answers.push(text.slice(i, i + part.length));
    text = `${text.slice(0, i)}_____${text.slice(i + part.length)}`;
    at = i + 5;
  }
  return { text, answer: answers.join(" … ") };
}

function askPatternFill(card, q) {
  const x = q.x;
  const options = x.examples.map((ex) => ({ ex, gap: blankPattern(ex.en, x.p) })).filter((o) => o.gap);
  if (!options.length) return askPatternChoice(card, { ...q, mode: "mc_en" });
  const { ex, gap } = options[Math.floor(Math.random() * options.length)];
  const several = gap.answer.includes(" … ");
  card.append(Text.create("div", several ? "Boşluklara uygun kalıbı yaz (parçaları “…” ile ayır):" : "Boşluğa uygun kalıbı yaz:", "muted"),
    Text.create("div", gap.text, "quiz-sentence"),
    Text.create("div", `${ex.tr}  ·  ipucu: ${x.tr}`, "muted small"));
  wordAnswerInput(card, several ? "parça 1 … parça 2" : "Eksik kalıp…", (text) => {
    const given = text.split(/\s*(?:…|\.\.\.)\s*/).map((s) => s.trim()).filter(Boolean).join(" … ");
    const ok = sameWord(given, gap.answer) || sameWord(given.replace(/ … /g, " "), gap.answer.replace(/ … /g, " "));
    patternAnswered(card, q, ok ? "good" : "again", ok ? `Doğru ✓ — ${ex.en}` : `Yanlış — doğrusu: ${gap.answer}`,
      ok ? "ok" : "wrong");
    if (!ok) card.append(Text.create("div", ex.en, "en"));
  });
}

/** Put the example's words in order (tiles, as in the lessons' "order" exercise). */
function askPatternOrder(card, q) {
  const x = q.x;
  const ex = x.examples[Math.floor(Math.random() * x.examples.length)];
  const words = ex.en.split(/\s+/);
  card.append(Text.create("div", "Kelimeleri sıralayıp cümleyi kur:", "muted"),
    Text.create("div", ex.tr, "muted"), Text.create("div", `ipucu: ${x.p}`, "muted small"));
  const built = lnode("div", "order-built");
  const pool = lnode("div", "order-pool");
  let tiles = shuffled(words);
  if (tiles.join(" ") === words.join(" ") && tiles.length > 1) tiles = [...tiles.slice(1), tiles[0]];
  const tile = (text, from, to) => {
    const b = Text.create("button", text, "chip order-tile");
    b.type = "button";
    b.addEventListener("click", () => to.append(tile(text, to, from)) || b.remove());
    return b;
  };
  for (const t of tiles) pool.append(tile(t, pool, built));
  const check = Text.create("button", "Kontrol et", "primary");
  check.type = "button";
  check.addEventListener("click", () => {
    const sentence = [...built.children].map((b) => Text.get(b)).join(" ");
    if (!sentence) return;
    [...card.querySelectorAll("button.order-tile")].forEach((b) => (b.disabled = true));
    check.disabled = true;
    const ok = answerMatches([ex.en], sentence);
    speakText(ex.en);
    patternAnswered(card, q, ok ? "good" : "again", ok ? `Doğru ✓ — ${ex.en}` : `Yanlış — doğrusu: ${ex.en}`, ok ? "ok" : "wrong");
  });
  card.append(built, pool, check);
}

function askPatternOwn(card, q) {
  const x = q.x;
  card.append(Text.create("div", "Bu kalıpla kendi cümleni kur:", "muted"),
    lnode("div", "fc-front", Text.create("div", x.p, "fc-word pattern-word"), iconButton("🔊", "Dinle", () => speakText(patternSpeech(x)))),
    Text.create("div", x.tr, "muted"), Text.create("div", `örnek: ${x.examples[0].en}`, "muted small"));
  wordAnswerInput(card, "İngilizce bir cümle yaz…", async (text) => {
    const wait = Text.create("div", "⏳ Kontrol ediliyor…", "muted small");
    card.append(wait);
    let r;
    try {
      r = await api("/api/patterns/check", { method: "POST", body: { id: x.id, text } });
    } catch (err) {
      wait.remove();
      card.append(Text.create("div", `⚠️ ${err.message}`, "muted"));
      return patternAnswered(card, q, null, "Kontrol edilemedi; bu soru sayılmadı.", "warn");
    }
    wait.remove();
    if (r.correction?.has_errors) card.append(correctionCard(r.correction));
    patternAnswered(card, q, r.verdict === "ok" ? "good" : r.verdict === "warn" ? "hard" : "again", r.message_tr,
      r.verdict === "ok" ? "ok" : r.verdict === "warn" ? "warn" : "wrong");
  });
}

async function finishPatternQuiz() {
  const s = patternsUi.session;
  const box = patternsUi.el.study;
  const card = document.createElement("div");
  card.className = "flashcard word-card";
  const first = s.total - s.wrong.length;  // questions answered right the first time
  card.append(Text.create("div", s.kind === "learn" ? "🎉 Yeni kalıplar tamam!" : "🎉 Tekrar tamam!", "fc-message"),
    Text.create("div", `İlk denemede doğru: ${first} / ${s.total}`, "muted"));
  if (s.wrong.length) {
    card.append(Text.create("div", "Zorlandığın kalıplar (yakında tekrar sorulacak):", "muted small"));
    for (const x of s.wrong) card.append(Text.create("div", `${x.p} — ${x.tr}`, "small"));
  }
  const again = Text.create("button", s.kind === "learn" ? `🆕 ${PATTERN_BATCH} yeni kalıp daha` : "Kalıp listesine dön", "primary");
  again.type = "button";
  again.addEventListener("click", async () => {
    if (s.kind === "learn") { await refreshPatterns(); startPatternLearning(); }
    else endPatternSession();
  });
  patternsUi.session = null;
  box.replaceChildren(card, again);
  await refreshPatterns();
}

/* ----------------------------------------------------------------- events */

patternsUi.el.learn.addEventListener("click", () => startPatternLearning().catch((err) => window.alert(err.message)));
patternsUi.el.review.addEventListener("click", () => startPatternReview().catch((err) => window.alert(err.message)));
patternsUi.el.filter.addEventListener("change", renderPatternList);
let patternsSearchTimer = 0;
patternsUi.el.search.addEventListener("input", () => {
  clearTimeout(patternsSearchTimer);
  patternsSearchTimer = setTimeout(renderPatternList, 200);
});
document.addEventListener("keydown", (e) => {
  if (!$("#page-patterns").classList.contains("active") || e.code !== "Space" || isTyping(e.target)) return;
  const reveal = patternsUi.el.study.querySelector(".word-card button.primary");
  if (reveal && patternsUi.session?.kind === "learn" && reveal.textContent.startsWith("Anlamını")) {
    e.preventDefault();
    reveal.click();
  }
});
