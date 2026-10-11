"use strict";

/* Word study: level lists (A1–C1), learning cards and quizzes (meaning, listen & write,
   fill the gap, own sentence). Words being learned are notebook words with spaced repetition,
   so answers here move their next review date like the notebook's flashcards. */

const wordsUi = {
  el: {
    levels: $("#words-levels"), summary: $("#words-summary"), study: $("#words-study"),
    list: $("#words-list"), search: $("#words-search"), filter: $("#words-filter"),
    learn: $("#words-learn"), review: $("#words-review"),
  },
  overview: null,
  level: store.get("wordsLevel"),
  lists: {},        // level → words (with status)
  shown: 60,        // list rows shown (more on request)
  session: null,
};

const STATUS_TR = { new: "yeni", learning: "öğreniliyor", learned: "öğrenildi ✓" };
const LEARN_BATCH = 10;
const FREQ_LIST = "TOP3000";  // the most frequent words (backend/words.py FREQ_ID), shown next to the levels
const isFreqList = (level) => level === FREQ_LIST;

/* ------------------------------------------------------------------ page */

async function loadWordsPage() {
  try {
    wordsUi.overview = await api("/api/words");
  } catch (err) {
    wordsUi.el.list.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted"));
    return;
  }
  const o = wordsUi.overview;
  if (!o.levels.some((l) => l.level === wordsUi.level && l.total)) {
    wordsUi.level = o.levels.some((l) => l.level === o.my_level && l.total) ? o.my_level
      : o.levels.find((l) => l.total)?.level;
  }
  renderWordLevels();
  Text.render(wordsUi.el.review, o.due ? `🔁 Tekrar et (${o.due})` : "🔁 Tekrar et");
  wordsUi.el.review.disabled = !o.due;
  await loadWordList();
}

function renderWordLevels() {
  const box = wordsUi.el.levels;
  box.replaceChildren();
  for (const l of wordsUi.overview.levels) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(l.level === wordsUi.level));
    b.disabled = !l.total;
    Text.render(b, `${l.label || l.level} · ${l.learned}/${l.total}`);
    b.title = `${l.total} kelime: ${l.learning} öğreniliyor, ${l.learned} öğrenildi`;
    b.addEventListener("click", () => {
      wordsUi.level = l.level;
      store.set("wordsLevel", l.level);
      wordsUi.shown = 60;
      renderWordLevels();
      loadWordList();
    });
    box.append(b);
  }
  const cur = wordsUi.overview.levels.find((l) => l.level === wordsUi.level);
  Text.render(wordsUi.el.summary, !cur ? ""
    : isFreqList(cur.level)
      ? `İngilizcede en sık kullanılan ${cur.total} kelime, sıklık sırasıyla · ${cur.learning} öğreniliyor · `
        + `${cur.learned} öğrenildi. Yeni kelimeler en sıktan başlar; ➕ ile istediğini aktif kelimelerine ekle `
        + "(defterinde olan bir kelime ikinci kez eklenmez)."
      : `${cur.level} seviyesinde ${cur.total} kelime · ${cur.learning} öğreniliyor · ${cur.learned} öğrenildi`
        + (wordsUi.level === wordsUi.overview.my_level ? " (senin seviyen)" : ""));
}

async function loadWordList(force = false) {
  const level = wordsUi.level;
  if (!level) return;
  if (force || !wordsUi.lists[level]) {
    wordsUi.el.list.replaceChildren(Text.create("p", "Yükleniyor…", "muted"));
    try {
      wordsUi.lists[level] = (await api(`/api/words/level/${level}`)).words;
    } catch (err) {
      wordsUi.el.list.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted"));
      return;
    }
  }
  renderWordList();
}

function renderWordList() {
  const all = wordsUi.lists[wordsUi.level] || [];
  const q = wordsUi.el.search.value.trim().toLowerCase();
  const filter = wordsUi.el.filter.value;
  const items = all.filter((w) => (filter === "all" || w.status === filter)
    && (!q || w.w.toLowerCase().includes(q) || w.tr.toLowerCase().includes(q)));
  const box = wordsUi.el.list;
  box.replaceChildren();
  if (!items.length) {
    box.append(Text.create("p", "Bu filtreyle kelime yok.", "muted"));
    return;
  }
  for (const w of items.slice(0, wordsUi.shown)) box.append(wordRow(w));
  if (items.length > wordsUi.shown) {
    const more = Text.create("button", `Daha fazla göster (${items.length - wordsUi.shown} kelime daha)`, "ghost small");
    more.type = "button";
    more.addEventListener("click", () => { wordsUi.shown += 120; renderWordList(); });
    box.append(more);
  }
}

function wordRow(w) {
  const row = document.createElement("div");
  row.className = `vocab-row word-row status-${w.status}`;
  const main = document.createElement("div");
  main.className = "vocab-main";
  if (w.rank) main.append(Text.create("span", `#${w.rank}`, "word-rank"), " ");
  main.append(Text.create("strong", w.w), " ", Text.create("span", w.pos_tr, "muted small"));
  if (w.rank && w.cefr) main.append(" ", Text.create("span", w.cefr, "word-cefr"));
  main.append(Text.create("div", w.tr, "vocab-meaning"));
  row.append(iconButton("🔊", "Dinle", () => speakText(w.w)), main,
    Text.create("span", STATUS_TR[w.status], `word-status ${w.status}`));
  if (w.status === "new") row.append(addWordButton(w));
  row.addEventListener("click", () => openWordCard(w));
  row.title = "Kartı aç: anlam, okunuş, örnek cümleler";
  return row;
}

/** ➕ on a list row: the word goes to the learner's active words (the notebook, spaced repetition) without
 *  opening its card. The server never adds a word twice (backend/vocab.py word_key). */
function addWordButton(w) {
  const b = iconButton("➕", "Aktif kelimelerime ekle (tekrarlarda sorulur)", async () => {  // iconButton stops the click reaching the row (no card)
    b.disabled = true;
    try {
      await api("/api/words/learn", { method: "POST", body: { words: [w.w] } });
    } catch (err) {
      b.disabled = false;
      window.alert(err.message);
      return;
    }
    markActive(w.w);
    refreshVocabBadge();
    const ov = await api("/api/words").catch(() => null);
    if (ov) { wordsUi.overview = ov; renderWordLevels(); }
    renderWordList();
  });
  return b;
}

/** The word is now being learned: in every loaded list (a word can be in a level list and the frequency list). */
function markActive(word) {
  const key = word.toLowerCase();
  for (const list of Object.values(wordsUi.lists)) {
    for (const x of list) if (x.w.toLowerCase() === key && x.status === "new") x.status = "learning";
  }
}

/* ------------------------------------------------------------------ card */

/** A full card for one word: word, pronunciation, meaning, checked example sentences. */
function wordCardView(w, { onAdd = null } = {}) {
  const card = document.createElement("div");
  card.className = "flashcard word-card";
  const front = lnode("div", "fc-front", Text.create("div", w.w, "fc-word"), iconButton("🔊", "Dinle", () => speakText(w.w)));
  card.append(front, Text.create("div", [w.ipa, w.pos_tr].filter(Boolean).join(" · "), "muted"),
    Text.create("div", w.tr, "fc-meaning"));
  const exBox = document.createElement("div");
  exBox.className = "word-examples";
  card.append(exBox);
  renderExamples(w, exBox);
  if (onAdd) card.append(onAdd);
  return card;
}

async function renderExamples(w, box) {
  box.replaceChildren(Text.create("div", "Örnekler yükleniyor…", "muted small"));
  let list = [];
  try {
    list = (await api(`/api/words/examples?word=${encodeURIComponent(w.w)}`)).examples;
  } catch {}
  w.examples = list;
  const draw = (note = "") => {
    box.replaceChildren();
    for (const ex of list) box.append(wordExampleRow(ex));
    if (!list.length) box.append(Text.create("div", "Henüz örnek cümle yok.", "muted small"));
    if (note) box.append(Text.create("div", note, "muted small"));
    if (list.length < 6) {
      const gen = Text.create("button", list.length ? "🤖 Bir örnek daha üret" : "🤖 Örnek cümle üret", "ghost small");
      gen.type = "button";
      gen.title = "Yapay zeka örnek cümle yazar; hatasız ve kelimeyi içeren cümleler gösterilir";
      gen.addEventListener("click", async (e) => {
        e.stopPropagation();
        gen.disabled = true;
        Text.render(gen, "⏳ Hazırlanıyor ve kontrol ediliyor…");
        try {
          const r = await api("/api/words/examples", { method: "POST", body: { word: w.w } });
          list = r.examples;
          w.examples = list;
          draw(r.added ? "" : "Kontrolden geçen yeni bir cümle çıkmadı; tekrar dene.");
        } catch (err) {
          draw(`⚠️ ${err.message}`);
        }
      });
      box.append(gen);
    }
  };
  draw();
}

function wordExampleRow(ex) {
  return lnode("div", "word-example",
    iconButton("🔊", "Dinle", () => speakText(ex.en)),
    lnode("div", "", Text.create("div", ex.en, "en", { words: true }), Text.create("div", ex.tr, "muted small")));
}

function openWordCard(w) {
  endWordSession();
  const box = wordsUi.el.study;
  box.hidden = false;
  let add = null;
  if (w.status === "new") {
    add = Text.create("button", "➕ Aktif kelimelerime ekle", "primary small");
    add.type = "button";
    add.addEventListener("click", async () => {
      add.disabled = true;
      await api("/api/words/learn", { method: "POST", body: { words: [w.w] } });
      Text.render(add, "✓ Öğrenme listende (tekrarlarda sorulacak)");
      refreshVocabBadge();
      await refreshWords();
    });
  }
  const close = Text.create("button", "✕ Kapat", "ghost small");
  close.type = "button";
  close.addEventListener("click", () => { box.hidden = true; box.replaceChildren(); });
  box.replaceChildren(wordCardView(w, { onAdd: add }), close);
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function refreshWords() {
  // Another list may show the same words (a level and the frequency list): load it again when it is opened.
  for (const k of Object.keys(wordsUi.lists)) if (k !== wordsUi.level) delete wordsUi.lists[k];
  wordsUi.overview = await api("/api/words");
  renderWordLevels();
  Text.render(wordsUi.el.review, wordsUi.overview.due ? `🔁 Tekrar et (${wordsUi.overview.due})` : "🔁 Tekrar et");
  wordsUi.el.review.disabled = !wordsUi.overview.due;
  await loadWordList(true);
}

/* --------------------------------------------------------------- sessions */

const shuffle = (a) => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };

/** End the running learn / quiz session (here or on the notebook page: the session knows its box). */
function endWordSession() {
  const box = wordsUi.session?.box || wordsUi.el.study;
  wordsUi.session = null;
  box.hidden = true;
  box.replaceChildren();
}

/** Learn: cards for new words of the level, then a quiz on them. */
async function startLearning() {
  const all = wordsUi.lists[wordsUi.level] || [];
  const unseen = all.filter((w) => w.status === "new");
  // The frequency list in its order (the most frequent words first); a level in random order.
  const fresh = (isFreqList(wordsUi.level) ? unseen : shuffle(unseen)).slice(0, LEARN_BATCH);
  if (!fresh.length) {
    window.alert("Bu seviyedeki bütün kelimeler öğrenme listende. Tekrar et ya da başka bir seviye seç.");
    return;
  }
  const entries = await api("/api/words/learn", { method: "POST", body: { words: fresh.map((w) => w.w) } });
  const ids = Object.fromEntries(entries.map((e) => [e.word.toLowerCase(), e.id]));
  fresh.forEach((w) => { w.vocab_id = ids[w.w.toLowerCase()]; });
  refreshVocabBadge();
  wordsUi.session = { kind: "learn", words: fresh, i: 0 };
  showLearnCard();
}

function showLearnCard() {
  const s = wordsUi.session;
  const box = wordsUi.el.study;
  box.hidden = false;
  const w = s.words[s.i];
  const card = document.createElement("div");
  card.className = "flashcard word-card";
  card.append(Text.create("div", `Yeni kelime ${s.i + 1} / ${s.words.length}`, "fc-progress muted small"));
  const front = lnode("div", "fc-front", Text.create("div", w.w, "fc-word"), iconButton("🔊", "Dinle", () => speakText(w.w)));
  card.append(front, Text.create("div", [w.ipa, w.pos_tr].filter(Boolean).join(" · "), "muted"));
  speakText(w.w);
  const reveal = Text.create("button", "Anlamını göster (Boşluk)", "primary");
  reveal.type = "button";
  const next = () => {
    s.i += 1;
    if (s.i < s.words.length) showLearnCard();
    else startQuiz(s.words, "learn");
  };
  reveal.addEventListener("click", () => {
    reveal.remove();
    card.append(Text.create("div", w.tr, "fc-meaning"));
    const exBox = document.createElement("div");
    exBox.className = "word-examples";
    card.append(exBox);
    renderExamples(w, exBox);
    const btn = Text.create("button", s.i + 1 < s.words.length ? "Sonraki kelime →" : "Teste geç →", "primary");
    btn.type = "button";
    btn.addEventListener("click", next);
    card.append(btn);
    btn.focus();
  });
  card.append(reveal);
  box.replaceChildren(card, sessionExit());
  reveal.focus();
}

function sessionExit() {
  const b = Text.create("button", "✕ Çalışmayı bitir", "ghost small");
  b.type = "button";
  b.addEventListener("click", async () => {
    const notebook = wordsUi.session?.kind === "notebook";
    endWordSession();
    await (notebook ? loadVocabPage() : refreshWords());
  });
  return b;
}

/** A notebook entry as a quiz word (its level-list entry gives the part of speech when it has one). */
function quizWord(v) {
  const listed = (wordsUi.lists[v.level] || []).find((x) => x.w.toLowerCase() === v.word.toLowerCase());
  return { w: v.word, tr: v.meaning_tr || listed?.tr || "", ipa: v.ipa || listed?.ipa || "",
    pos_tr: listed?.pos_tr || "", vocab_id: v.id, level: v.level };
}

async function loadLevelLists(levels) {
  for (const level of new Set(levels.filter(Boolean))) {
    if (!wordsUi.lists[level]) {
      try { wordsUi.lists[level] = (await api(`/api/words/level/${level}`)).words; } catch {}
    }
  }
}

const NOTEBOOK_QUIZ = 15;  // the default of the notebook's "how many words" choice (vocab.js)

/** Kelime Defteri → 🧪 Test et: the same quiz as here, on the notebook's words (due ones first, then
 *  random ones), as many as the learner chose next to the button. Answers move their review dates like
 *  the flashcards do. */
async function startNotebookQuiz(box) {
  const all = await api("/api/vocab");
  if (!all.length) {
    window.alert("Defterde henüz kelime yok. Sohbette bir kelimeye tıklayıp ekleyebilir ya da yukarıdan yazabilirsin.");
    return;
  }
  const today = new Date().toLocaleDateString("sv");  // YYYY-MM-DD, local
  const due = shuffle(all.filter((v) => v.due_date <= today));
  const rest = shuffle(all.filter((v) => v.due_date > today));
  const count = vocabCount(vocabUi.el.quizCount);
  const chosen = [...due, ...rest].slice(0, count === Infinity ? all.length : count);
  // Wrong options: the other notebook words, then the learner's level list.
  await loadLevelLists([...chosen.map((v) => v.level), appSettings.level]);
  endWordSession();
  const extra = all.filter((v) => v.meaning_tr).map((v) => ({ w: v.word, tr: v.meaning_tr, pos_tr: "" }));
  await startQuiz(chosen.map(quizWord), "notebook", box, extra);
}

/** Review: notebook words that are due today, asked in mixed ways. */
async function startWordReview() {
  const due = await api("/api/vocab/due");
  if (!due.length) {
    window.alert("Bugün tekrar edilecek kelime yok.");
    return;
  }
  // A word from a level list: its list entry (Turkish part of speech, meaning); the list must be loaded.
  await loadLevelLists(due.map((v) => v.level));
  startQuiz(due.slice(0, 20).map(quizWord), "review");
}

/* ------------------------------------------------------------------ quiz */

const QUIZ_MODES = ["mc_en", "mc_tr", "listen", "fill", "own"];

/** Which kinds of question a word can get (fill needs a checked example sentence). */
function modesFor(w, ownLeft) {
  const m = ["listen"];
  if (w.tr) m.push("mc_en", "mc_tr");
  if (w.examples?.some((ex) => blankOut(ex.en, w.w))) m.push("fill");
  if (ownLeft > 0) m.push("own");
  return m;
}

/** `box`: where the cards go (this page's study area, or the notebook's); `extra`: more words for the
 *  wrong options of meaning questions. */
async function startQuiz(words, kind, box = wordsUi.el.study, extra = []) {
  // Example sentences already made for these words (fill-the-gap needs one).
  await Promise.all(words.map(async (w) => {
    if (w.examples) return;
    try { w.examples = (await api(`/api/words/examples?word=${encodeURIComponent(w.w)}`)).examples; } catch { w.examples = []; }
  }));
  let ownLeft = 2;  // own sentences take longer: at most two per session
  const questions = shuffle(words.slice()).map((w) => {
    const modes = modesFor(w, ownLeft);
    const mode = modes[Math.floor(Math.random() * modes.length)];
    if (mode === "own") ownLeft -= 1;
    return { w, mode, retried: false };
  });
  wordsUi.session = { kind, box, extra, queue: questions, done: 0, total: questions.length, right: 0, wrong: [] };
  nextQuestion();
}

const QUIZ_TITLES = { learn: "Test", review: "Tekrar", notebook: "Defter testi" };

function nextQuestion() {
  const s = wordsUi.session;
  if (!s) return;
  const q = s.queue.shift();
  if (!q) return finishQuiz();
  const box = s.box;
  box.hidden = false;
  const card = document.createElement("div");
  card.className = "flashcard word-card quiz";
  card.append(Text.create("div", `${QUIZ_TITLES[s.kind]} · ${s.done + 1} / ${s.total}`, "fc-progress muted small"));
  box.replaceChildren(card, sessionExit());
  ({ mc_en: askChoice, mc_tr: askChoice, listen: askListen, fill: askFill, own: askOwn })[q.mode](card, q);
}

/** Record the answer (spaced repetition) and show the verdict with a "next" button. */
async function answered(card, q, grade, verdictText, cls) {
  const s = wordsUi.session;
  card.append(Text.create("div", verdictText, `verdict ${cls}`));
  if (q.w.vocab_id && grade) {  // grade null: the answer could not be checked, nothing is recorded
    try {
      await api(`/api/vocab/${q.w.vocab_id}/review`, { method: "POST", body: { grade } });
    } catch (err) {
      card.append(Text.create("div", `⚠️ Kaydedilemedi: ${err.message}`, "muted small"));
    }
  }
  if (grade === "good") s.right += 1;
  else if (!grade) s.total -= 1;  // not counted
  else if (!q.retried) {
    s.wrong.push(q.w);
    s.queue.push({ ...q, retried: true, mode: q.mode === "own" ? "mc_en" : q.mode });  // once more at the end
    s.total += 1;
  }
  if (grade) s.done += 1;
  const next = Text.create("button", "Devam →", "primary");
  next.type = "button";
  next.addEventListener("click", nextQuestion);
  card.append(next);
  next.focus();
}

function pool(target) {
  const lists = [...(wordsUi.session?.extra || []), ...Object.values(wordsUi.lists).flat()];
  return lists.filter((x) => x.w.toLowerCase() !== target.w.toLowerCase() && x.tr);
}

function askChoice(card, q) {
  const w = q.w;
  const toTr = q.mode === "mc_en";
  const others = shuffle(pool(w).filter((x) => !w.pos_tr || x.pos_tr === w.pos_tr || Math.random() < 0.3));
  const distractors = [];
  for (const o of others) {
    const label = toTr ? o.tr : o.w;
    if (label !== (toTr ? w.tr : w.w) && !distractors.includes(label)) distractors.push(label);
    if (distractors.length === 3) break;
  }
  const right = toTr ? w.tr : w.w;
  const options = shuffle([right, ...distractors]);
  card.append(Text.create("div", toTr ? "Bu kelimenin anlamı hangisi?" : "Bu anlama gelen kelime hangisi?", "muted"),
    toTr ? lnode("div", "fc-front", Text.create("div", w.w, "fc-word"), iconButton("🔊", "Dinle", () => speakText(w.w)))
      : Text.create("div", w.tr, "fc-meaning"));
  const opts = document.createElement("div");
  opts.className = "quiz-options";
  for (const label of options) {
    const b = Text.create("button", label, "quiz-option");
    b.type = "button";
    b.addEventListener("click", () => {
      opts.querySelectorAll("button").forEach((x) => {
        x.disabled = true;
        if (x._text === right) x.classList.add("correct");
      });
      const ok = label === right;
      if (!ok) b.classList.add("wrong");
      if (!toTr) speakText(w.w);
      answered(card, q, ok ? "good" : "again", ok ? "Doğru ✓" : `Yanlış — doğrusu: ${right}`, ok ? "ok" : "wrong");
    });
    opts.append(b);
  }
  card.append(opts);
}

/** A typed answer: Enter submits. */
function wordAnswerInput(card, placeholder, onSubmit) {
  const form = document.createElement("form");
  form.className = "quiz-input";
  const input = document.createElement("input");
  input.placeholder = placeholder;
  input.autocomplete = "off";
  input.spellcheck = false;
  const btn = Text.create("button", "Kontrol et", "primary");
  btn.type = "submit";
  form.append(input, btn);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!input.value.trim() || input.disabled) return;
    input.disabled = btn.disabled = true;
    onSubmit(input.value.trim());
  });
  card.append(form);
  setTimeout(() => input.focus(), 50);
}

const sameWord = (a, b) => a.toLowerCase().replace(/[’']/g, "'").replace(/\s+/g, " ").trim()
  === b.toLowerCase().replace(/[’']/g, "'").replace(/\s+/g, " ").trim();

function askListen(card, q) {
  const w = q.w;
  const front = lnode("div", "fc-front", iconButton("🔊", "Tekrar dinle", () => speakText(w.w)));
  front.append(transcriptButton(w.w, front));
  card.append(Text.create("div", "Dinle ve kelimeyi yaz:", "muted"), front);
  speakText(w.w);
  wordAnswerInput(card, "Duyduğun kelime…", (text) => {
    const ok = sameWord(text, w.w);
    answered(card, q, ok ? "good" : "again", ok ? `Doğru ✓ — ${w.w}: ${w.tr}` : `Yanlış — doğrusu: ${w.w} (${w.tr})`,
      ok ? "ok" : "wrong");
  });
}

/** The sentence with the word (or its form) replaced by a gap: {text, answer} or null. */
function blankOut(sentence, word) {
  const parts = sentence.split(/([A-Za-z]+(?:['’][A-Za-z]+)?)/);
  const base = word.toLowerCase();
  if (word.includes(" ")) {
    const at = sentence.toLowerCase().indexOf(base);
    return at < 0 ? null : { text: `${sentence.slice(0, at)}_____${sentence.slice(at + word.length)}`, answer: sentence.slice(at, at + word.length) };
  }
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i].toLowerCase();
    // the word itself or a form of it that starts like it (stop → stopped, study → studies)
    if (p === base || (p.length > base.length && p.startsWith(base.slice(0, Math.max(3, base.length - 1)))
        && p.length - base.length <= 4)) {
      return { text: parts.map((x, j) => (j === i ? "_____" : x)).join(""), answer: parts[i] };
    }
  }
  return null;
}

function askFill(card, q) {
  const w = q.w;
  const options = w.examples.map((ex) => ({ ex, gap: blankOut(ex.en, w.w) })).filter((x) => x.gap);
  const { ex, gap } = options[Math.floor(Math.random() * options.length)];
  card.append(Text.create("div", "Boşluğa uygun kelimeyi yaz:", "muted"),
    Text.create("div", gap.text, "quiz-sentence"),
    Text.create("div", `${ex.tr}  ·  ipucu: ${w.tr}`, "muted small"));
  wordAnswerInput(card, "Eksik kelime…", (text) => {
    const ok = sameWord(text, gap.answer);
    const base = !ok && sameWord(text, w.w);  // the right word, wrong form (stop vs stopped)
    answered(card, q, ok ? "good" : base ? "hard" : "again",
      ok ? `Doğru ✓ — ${ex.en}` : base ? `Kelime doğru, biçimi farklı: cümlede “${gap.answer}” olmalı.` : `Yanlış — doğrusu: ${gap.answer}`,
      ok ? "ok" : base ? "warn" : "wrong");
    if (!ok) card.append(Text.create("div", ex.en, "en"));
  });
}

function askOwn(card, q) {
  const w = q.w;
  card.append(Text.create("div", "Bu kelimeyle kendi cümleni kur:", "muted"),
    lnode("div", "fc-front", Text.create("div", w.w, "fc-word"), iconButton("🔊", "Dinle", () => speakText(w.w))),
    Text.create("div", w.tr, "muted"));
  wordAnswerInput(card, "İngilizce bir cümle yaz…", async (text) => {
    const wait = Text.create("div", "⏳ Kontrol ediliyor…", "muted small");
    card.append(wait);
    let r;
    try {
      r = await api("/api/words/check", { method: "POST", body: { word: w.w, text } });
    } catch (err) {
      wait.remove();
      card.append(Text.create("div", `⚠️ ${err.message}`, "muted"));
      return answered(card, q, null, "Kontrol edilemedi; bu soru sayılmadı.", "warn");
    }
    wait.remove();
    if (r.correction?.has_errors) card.append(correctionCard(r.correction));
    answered(card, q, r.verdict === "ok" ? "good" : r.verdict === "warn" ? "hard" : "again", r.message_tr,
      r.verdict === "ok" ? "ok" : r.verdict === "warn" ? "warn" : "wrong");
  });
}

async function finishQuiz() {
  const s = wordsUi.session;
  const box = s.box;
  const card = document.createElement("div");
  card.className = "flashcard word-card";
  const first = s.total - s.wrong.length;  // questions answered right the first time
  card.append(Text.create("div", { learn: "🎉 Yeni kelimeler tamam!", review: "🎉 Tekrar tamam!",
    notebook: "🎉 Defter testi tamam!" }[s.kind], "fc-message"),
    Text.create("div", `İlk denemede doğru: ${first} / ${s.total}`, "muted"));
  if (s.wrong.length) {
    card.append(Text.create("div", "Zorlandığın kelimeler (yakında tekrar sorulacak):", "muted small"));
    for (const w of s.wrong) card.append(Text.create("div", `${w.w} — ${w.tr}`, "small"));
  }
  const again = Text.create("button", { learn: `🆕 ${LEARN_BATCH} yeni kelime daha`, review: "Kelime listesine dön",
    notebook: "🧪 Yeniden test et" }[s.kind], "primary");
  again.type = "button";
  again.addEventListener("click", async () => {
    if (s.kind === "learn") { await refreshWords(); startLearning(); }
    else if (s.kind === "notebook") startNotebookQuiz(box).catch((err) => window.alert(err.message));
    else endWordSession();
  });
  const close = s.kind === "notebook" && Text.create("button", "Kapat", "ghost small");
  if (close) {
    close.type = "button";
    close.addEventListener("click", () => { box.hidden = true; box.replaceChildren(); });
  }
  wordsUi.session = null;
  box.replaceChildren(card, again, close || "");
  await (s.kind === "notebook" ? loadVocabPage() : refreshWords());
}

/* ----------------------------------------------------------------- events */

wordsUi.el.learn.addEventListener("click", () => startLearning().catch((err) => window.alert(err.message)));
$("#vocab-quiz-start").addEventListener("click", () => {
  $("#flashcard").hidden = true;  // one study area at a time on the notebook page
  startNotebookQuiz($("#vocab-quiz")).catch((err) => window.alert(err.message));
});
wordsUi.el.review.addEventListener("click", () => startWordReview().catch((err) => window.alert(err.message)));
wordsUi.el.search.addEventListener("input", () => { wordsUi.shown = 60; renderWordList(); });
wordsUi.el.filter.addEventListener("change", () => { wordsUi.shown = 60; renderWordList(); });
document.addEventListener("keydown", (e) => {
  if (!$("#page-words").classList.contains("active") || e.code !== "Space" || isTyping(e.target)) return;
  const reveal = wordsUi.el.study.querySelector(".word-card button.primary");
  if (reveal && wordsUi.session?.kind === "learn" && reveal.textContent.startsWith("Anlamını")) {
    e.preventDefault();
    reveal.click();
  }
});
