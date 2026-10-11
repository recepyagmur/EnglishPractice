"use strict";

/* Click-a-word popup, the vocabulary notebook and flashcard reviews. */

const vocabUi = {
  popup: null,
  review: { queue: [], done: 0, total: 0, current: null, flipped: false },
  el: {
    due: $("#vocab-due"), total: $("#vocab-total"), learned: $("#vocab-learned"),
    start: $("#vocab-start"), card: $("#flashcard"), list: $("#vocab-list"),
    search: $("#vocab-search"), add: $("#vocab-add"), dictNote: $("#vocab-dict-note"),
    reviewCount: $("#vocab-review-count"), quizCount: $("#vocab-quiz-count"),
  },
};

/* ------------------------------------------------------------- how many words */

const VOCAB_COUNT_STEPS = [5, 10, 15, 20, 30, 50];

/** Fill a "how many words" select: the steps below `available`, then "Hepsi (N)". The learner's last
 *  choice (localStorage `key`) is kept when it is still on offer; otherwise `fallback` (a number or "all"). */
function fillVocabCount(select, available, key, fallback) {
  const options = VOCAB_COUNT_STEPS.filter((n) => n < available).map((n) => [String(n), `${n} kelime`]);
  options.push(["all", available ? `Hepsi (${available} kelime)` : "Kelime yok"]);
  const wanted = store.get(key) ?? String(fallback);
  select.replaceChildren(...options.map(([value, label]) => {
    const o = Text.create("option", label);
    o.value = value;
    return o;
  }));
  select.value = options.some(([v]) => v === wanted) ? wanted : "all";
  select.disabled = !available;
  select.onchange = () => store.set(key, select.value);
}

/** The chosen count of a "how many words" select (Infinity for "Hepsi"). */
function vocabCount(select) {
  return select.value === "all" ? Infinity : Number(select.value);
}

/* ---------------------------------------------------------------- notebook API */

async function addToVocab(entry) {
  const saved = await api("/api/vocab", { method: "POST", body: entry });
  refreshVocabBadge();
  return saved;
}

async function refreshVocabBadge() {
  try {
    const s = await api("/api/vocab/stats");
    const link = document.querySelector('#nav a[data-page="vocab"]');
    if (!link) return s;
    let badge = link.querySelector(".nav-badge");
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "nav-badge";
      link.append(badge);
    }
    badge.hidden = !s.due;
    badge.textContent = s.due;
    badge.title = `Bugün tekrar edilecek ${s.due} kelime`;
    return s;
  } catch {
    return null;
  }
}

function sourceOf(el) {
  if (el.closest(".report-card")) return "report";
  if (el.closest("#page-writing")) return "writing";
  if (el.closest(".msg")) return "chat";
  return "other";
}

/** Notebook entry from a dictionary lookup result. */
function entryFromLookup(result, context) {
  const e = result.entries[0];
  return {
    word: result.lemma || result.query,
    meaning_tr: e ? e.translations.slice(0, 3).map((t) => t.word).join(", ") : "",
    definition: e?.definitions[0] || "",
    example: e?.example || "",
    ipa: e?.ipa || "",
    context,
  };
}

/* ------------------------------------------------------------------- popup */

document.addEventListener("click", (e) => {
  const word = e.target.closest(".w");
  if (word) {
    e.preventDefault();
    openWordPopup(word);
    return;
  }
  if (vocabUi.popup && !e.target.closest(".word-popup")) closeWordPopup();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeWordPopup();
});

function closeWordPopup() {
  vocabUi.popup?.remove();
  vocabUi.popup = null;
  document.querySelector(".w.active")?.classList.remove("active");
}

function placePopup(popup, anchor) {
  const r = anchor.getBoundingClientRect();
  const width = Math.min(320, window.innerWidth - 16);
  popup.style.width = `${width}px`;
  popup.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - width - 8)) + window.scrollX}px`;
  const below = r.bottom + 8;
  popup.style.top = `${below + window.scrollY}px`;
  // Flip above the word when there is no room below.
  requestAnimationFrame(() => {
    if (below + popup.offsetHeight > window.innerHeight && r.top > popup.offsetHeight + 8) {
      popup.style.top = `${r.top - popup.offsetHeight - 8 + window.scrollY}px`;
    }
  });
}

function iconButton(icon, title, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "icon-btn";
  b.title = title;
  b.setAttribute("aria-label", title);
  b.textContent = icon;
  b.addEventListener("click", (e) => {
    e.stopPropagation();
    onClick(b);
  });
  return b;
}

/** "📝" next to a 🔊 whose text is not on the screen (listening exercises; not in exams): shows the
 *  text under `host` (words clickable), a second click hides it again. */
function transcriptButton(text, host) {
  let shown = null;
  const b = iconButton("📝", "Yazılı göster", () => {
    if (shown) {
      shown.remove();
      shown = null;
    } else {
      shown = Text.create("div", text, "transcript", { words: true });
      host.after(shown);
    }
    b.classList.toggle("on", Boolean(shown));
    b.title = shown ? "Yazıyı gizle" : "Yazılı göster";
    b.setAttribute("aria-label", b.title);
  });
  return b;
}

async function openWordPopup(wordEl) {
  closeWordPopup();
  wordEl.classList.add("active");
  const raw = wordEl.textContent;
  // A word Whisper did not hear clearly: play the right pronunciation right away.
  const unclear = wordEl.classList.contains("unclear");
  if (unclear) speakText(raw);
  const context = Text.sentenceAround(wordEl);
  const popup = document.createElement("div");
  popup.className = "word-popup";
  popup.setAttribute("role", "dialog");
  popup.append(Text.create("div", "…", "muted"));
  document.body.append(popup);
  vocabUi.popup = popup;
  placePopup(popup, wordEl);

  let result;
  try {
    result = await api(`/api/dictionary/lookup?word=${encodeURIComponent(raw)}`);
  } catch (err) {
    popup.replaceChildren(Text.create("div", `⚠️ ${err.message}`, "muted"));
    return;
  }
  if (vocabUi.popup !== popup) return;  // another word was clicked meanwhile

  const head = document.createElement("div");
  head.className = "wp-head";
  const title = document.createElement("div");
  title.append(Text.create("strong", result.lemma || raw));
  if (result.via && result.lemma.toLowerCase() !== result.query.toLowerCase()) {
    title.append(Text.create("span", ` ← ${result.query} (${result.via})`, "muted small"));
  }
  head.append(title, iconButton("🔊", "Dinle", () => speakText(unclear ? raw : result.lemma || raw)),
    iconButton("✕", "Kapat", closeWordPopup));
  popup.replaceChildren(head);
  if (unclear) {
    popup.append(Text.create("div", "🎤 Bu kelime net anlaşılmadı. Doğru telaffuzunu dinle (🔊) ve tekrar söylemeyi dene. "
      + "(Kaba bir gösterge: isimler ve hızlı söylenen kelimeler de işaretlenebilir.)", "wp-unclear"));
  }

  const first = result.entries[0];
  if (first?.ipa) popup.append(Text.create("div", first.ipa, "wp-ipa"));
  for (const e of result.entries.slice(0, 2)) {
    const box = document.createElement("div");
    box.className = "wp-entry";
    box.append(Text.create("span", e.pos || "", "wp-pos"),
      Text.create("span", e.translations.slice(0, 5).map((t) => t.word).join(", "), "wp-tr"));
    if (e.definitions[0]) box.append(Text.create("div", e.definitions[0], "wp-def"));
    popup.append(box);
  }

  const ai = document.createElement("div");
  ai.className = "wp-ai";
  popup.append(ai);
  const actions = document.createElement("div");
  actions.className = "wp-actions";
  popup.append(actions);

  let entry = entryFromLookup(result, context);
  const explain = async () => {
    Text.render(ai, "🤖 Yapay zekaya soruluyor…");
    try {
      const x = await api("/api/dictionary/explain", { method: "POST", body: { word: raw, sentence: context } });
      ai.replaceChildren(
        Text.create("span", "🤖 Bu cümlede: ", "muted small"),
        Text.create("strong", x.meaning_tr),
        Text.create("div", x.definition, "wp-def"),
      );
      if (!result.entries.length) {
        entry = { ...entry, word: x.lemma || entry.word, meaning_tr: x.meaning_tr, definition: x.definition };
      }
    } catch (err) {
      Text.render(ai, `⚠️ ${err.message}`);
    }
  };

  if (!result.entries.length) {
    popup.insertBefore(Text.create("div", result.available ? "Sözlükte bulunamadı." : "Çevrimdışı sözlük kurulu değil.",
      "muted small"), ai);
    explain();
  } else if (context && context.split(/\s+/).length > 2) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ghost small";
    Text.render(btn, "🤖 Bu cümledeki anlamı?");
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      btn.remove();
      explain();
    });
    actions.append(btn);
  }

  if (context && context.split(/\s+/).length > 2) {
    const tr = document.createElement("button");
    tr.type = "button";
    tr.className = "ghost small";
    Text.render(tr, "🌐 Cümleyi çevir");
    tr.addEventListener("click", async (e) => {
      e.stopPropagation();
      tr.disabled = true;
      const box = Text.create("div", "🌐 Çevriliyor…", "wp-translation muted small");
      popup.insertBefore(box, actions);
      try {
        const t = await api("/api/translate", { method: "POST", body: { text: context } });
        box.className = "wp-translation";
        box.replaceChildren(Text.create("div", context, "wp-def", { words: true }), Text.create("div", `🇹🇷 ${t.translation}`));
      } catch (err) {
        Text.render(box, `⚠️ ${err.message}`);
      }
      tr.remove();
      placePopup(popup, wordEl);
    });
    actions.append(tr);
  }

  const add = document.createElement("button");
  add.type = "button";
  add.className = result.in_vocab ? "ghost small" : "primary small";
  Text.render(add, result.in_vocab ? "✓ Defterde" : "➕ Deftere ekle");
  add.disabled = result.in_vocab;
  add.addEventListener("click", async (e) => {
    e.stopPropagation();
    add.disabled = true;
    try {
      await addToVocab({ ...entry, source: sourceOf(wordEl), session_id: chat.sessionId });
      Text.render(add, "✓ Eklendi");
      add.className = "ghost small";
    } catch (err) {
      add.disabled = false;
      Text.render(add, `⚠️ ${err.message}`);
    }
  });
  actions.append(add);
  placePopup(popup, wordEl);
}

/** A ➕ button that adds a phrase (report / writing suggestions) to the notebook. */
function addPhraseButton(phrase, meaning, example, sourceEl) {
  const b = iconButton("➕", "Deftere ekle", async () => {
    b.disabled = true;
    try {
      const saved = await addToVocab({ word: phrase, meaning_tr: meaning || "", example: example || "",
        source: sourceOf(sourceEl || b), session_id: chat.sessionId });
      b.textContent = "✓";
      b.title = saved.created ? "Eklendi" : "Zaten defterde";
    } catch {
      b.disabled = false;
    }
  });
  return b;
}

/* --------------------------------------------------------------- notebook page */

async function loadVocabPage() {
  const s = await refreshVocabBadge();
  if (s) {
    Text.render(vocabUi.el.due, String(s.due));
    Text.render(vocabUi.el.total, String(s.total));
    Text.render(vocabUi.el.learned, String(s.learned));
    vocabUi.el.start.disabled = !s.due;
    $("#vocab-quiz-start").disabled = !s.total;
    fillVocabCount(vocabUi.el.reviewCount, s.due, "vocab.reviewCount", "all");
    fillVocabCount(vocabUi.el.quizCount, s.total, "vocab.quizCount", NOTEBOOK_QUIZ);
    vocabUi.el.dictNote.hidden = s.dictionary;
    Text.render(vocabUi.el.dictNote, "⚠️ Çevrimdışı sözlük kurulu değil; anlamlar yapay zekadan alınacak.");
  }
  loadVocabList();
}

function dueLabel(dueDate) {
  const days = Math.round((new Date(dueDate) - new Date(new Date().toDateString())) / 86400000);
  return days <= 0 ? "bugün" : days === 1 ? "yarın" : `${days} gün sonra`;
}

async function loadVocabList() {
  const list = vocabUi.el.list;
  const q = vocabUi.el.search.value.trim();
  let items;
  try {
    items = await api(`/api/vocab${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  } catch (err) {
    list.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted"));
    return;
  }
  list.replaceChildren();
  if (!items.length) {
    list.append(Text.create("p", q ? "Eşleşen kelime yok." : "Defterin boş. Bir kelimeye tıklayıp ekleyerek başla.", "muted"));
    return;
  }
  for (const v of items) {
    const row = document.createElement("div");
    row.className = "vocab-row";
    const main = document.createElement("div");
    main.className = "vocab-main";
    const top = document.createElement("div");
    top.append(Text.create("strong", v.word, "", { words: false }));
    if (v.ipa) top.append(Text.create("span", ` ${v.ipa}`, "muted small"));
    main.append(top, Text.create("div", v.meaning_tr || "—", "vocab-meaning"));
    if (v.context || v.example) main.append(Text.create("div", v.context || v.example, "example", { words: true }));
    const meta = Text.create("span", `tekrar: ${dueLabel(v.due_date)}`, "muted small");
    const edit = iconButton("✎", "Anlamı düzenle", async () => {
      const meaning = window.prompt(`"${v.word}" için Türkçe anlam:`, v.meaning_tr || "");
      if (meaning === null) return;
      await api(`/api/vocab/${v.id}`, { method: "PATCH", body: { meaning_tr: meaning } });
      loadVocabList();
    });
    const del = iconButton("🗑", "Sil", async () => {
      if (!window.confirm(`"${v.word}" defterden silinsin mi?`)) return;
      await api(`/api/vocab/${v.id}`, { method: "DELETE" });
      loadVocabPage();
    });
    row.append(iconButton("🔊", "Dinle", () => speakText(v.word)), main, meta, edit, del);
    list.append(row);
  }
}

let vocabSearchTimer = 0;
vocabUi.el.search.addEventListener("input", () => {
  clearTimeout(vocabSearchTimer);
  vocabSearchTimer = setTimeout(loadVocabList, 250);
});

vocabUi.el.add.addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = e.target.word;
  const word = input.value.trim();
  if (!word) return;
  input.disabled = true;
  try {
    let entry = { word, source: "manual" };
    const single = !/\s/.test(word);
    const result = single ? await api(`/api/dictionary/lookup?word=${encodeURIComponent(word)}`) : null;
    if (result?.entries.length) {
      entry = { ...entryFromLookup(result, ""), source: "manual" };
    } else if (result?.available && !window.confirm(
      `"${word}" sözlükte bulunamadı — yazımı yanlış olabilir. Yine de eklensin mi?`)) {
      return;
    } else {
      const x = await api("/api/dictionary/explain", { method: "POST", body: { word, sentence: word } }).catch(() => null);
      if (x) entry = { ...entry, meaning_tr: x.meaning_tr, definition: x.definition };
    }
    await addToVocab(entry);
    input.value = "";
    loadVocabPage();
  } catch (err) {
    window.alert(err.message);
  } finally {
    input.disabled = false;
    input.focus();
  }
});

/* ------------------------------------------------------------------ flashcards */

vocabUi.el.start.addEventListener("click", () => {
  if (wordsUi.session?.kind === "notebook") endWordSession();  // one study area at a time (words.js)
  startReview();
});

async function startReview() {
  const count = vocabCount(vocabUi.el.reviewCount);  // the most overdue first
  const due = await api(`/api/vocab/due?limit=${count === Infinity ? 10000 : count}`);
  const r = vocabUi.review;
  r.queue = due;
  r.done = 0;
  r.total = due.length;
  if (!due.length) {
    showCardMessage("Bugün tekrar edilecek kelime yok 🎉");
    return;
  }
  nextCard();
}

function showCardMessage(text) {
  const card = vocabUi.el.card;
  card.hidden = false;
  card.replaceChildren(Text.create("div", text, "fc-message"));
}

function nextCard() {
  const r = vocabUi.review;
  r.current = r.queue.shift();
  r.flipped = false;
  if (!r.current) {
    showCardMessage(`Bitti! ${r.total} kelimeyi tekrar ettin. 👏`);
    loadVocabPage();
    return;
  }
  renderCard();
  speakText(r.current.word);
}

function renderCard() {
  const r = vocabUi.review;
  const v = r.current;
  const card = vocabUi.el.card;
  card.hidden = false;
  card.replaceChildren();
  card.append(Text.create("div", `${r.done + 1} / ${r.total}`, "fc-progress muted small"));
  const front = document.createElement("div");
  front.className = "fc-front";
  front.append(Text.create("div", v.word, "fc-word"), iconButton("🔊", "Dinle", () => speakText(v.word)));
  card.append(front);

  if (!r.flipped) {
    const show = document.createElement("button");
    show.className = "primary";
    Text.render(show, "Göster (Boşluk)");
    show.addEventListener("click", flipCard);
    card.append(show);
    return;
  }
  const back = document.createElement("div");
  back.className = "fc-back";
  if (v.ipa) back.append(Text.create("div", v.ipa, "muted"));
  back.append(Text.create("div", v.meaning_tr || "—", "fc-meaning"));
  if (v.definition) back.append(Text.create("div", v.definition, "wp-def"));
  if (v.context || v.example) back.append(Text.create("div", v.context || v.example, "example"));
  card.append(back);

  const grades = document.createElement("div");
  grades.className = "fc-grades";
  for (const [grade, label, cls] of [["again", "1 · Bilemedim", "again"], ["hard", "2 · Zorlandım", "hard"],
    ["good", "3 · Bildim", "good"]]) {
    const b = document.createElement("button");
    b.className = `grade ${cls}`;
    Text.render(b, label);
    b.addEventListener("click", () => gradeCard(grade));
    grades.append(b);
  }
  card.append(grades);
}

function flipCard() {
  vocabUi.review.flipped = true;
  renderCard();
}

async function gradeCard(grade) {
  const r = vocabUi.review;
  const v = r.current;
  if (!v) return;
  r.current = null;
  try {
    await api(`/api/vocab/${v.id}/review`, { method: "POST", body: { grade } });
  } catch (err) {
    // Not saved: the card comes back in this session instead of counting as done.
    r.current = v;
    r.flipped = true;
    renderCard();
    window.alert(`Kaydedilemedi: ${err.message}. Tekrar dene.`);
    return;
  }
  if (grade === "again") r.queue.push(v);  // once more in this session
  else r.done += 1;
  nextCard();
}

document.addEventListener("keydown", (e) => {
  if (!$("#page-vocab").classList.contains("active") || vocabUi.el.card.hidden || !vocabUi.review.current) return;
  if (e.target.closest?.("input, textarea")) return;
  if (e.code === "Space" && !vocabUi.review.flipped) {
    e.preventDefault();
    flipCard();
  } else if (vocabUi.review.flipped && ["1", "2", "3"].includes(e.key)) {
    gradeCard({ 1: "again", 2: "hard", 3: "good" }[e.key]);
  }
});
