"use strict";

/* Lessons (A1–C1). List: recommendations + level tabs. Lesson page: the hand-written
   explanation, typical mistakes, instant-check exercises, "build your own sentences"
   (AI questions, answers checked by the correction engine) and conversation practice. */

const lessonsUi = {
  level: store.get("lessonsLevel"),  // the level tab the learner last looked at
  data: null,
  shownId: null,  // the lesson on the lesson page (kept as it is when the learner comes back to it)
  el: {
    level: $("#lessons-level"), recommended: $("#lessons-recommended"), levels: $("#lessons-levels"),
    grid: $("#lessons-grid"), view: $("#lesson-view"),
  },
};

const LEVEL_NAMES = { A1: "Başlangıç", A2: "Temel", B1: "Orta", B2: "Orta üstü", C1: "İleri" };

/** Small element helper for this page: class + children (strings go through Text). */
function lnode(tag, className = "", ...children) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    e.append(typeof c === "string" ? Text.create("span", c) : c);
  }
  return e;
}

const percent = (x) => `%${Math.round(x * 100)}`;

function lessonStatus(l) {
  if (l.status === "done") return Text.create("span", `✓ Tamamlandı · ${percent(l.best_score)}`, "lesson-status done");
  if (l.status === "started") {
    return Text.create("span", l.best_score != null ? `Son en iyi: ${percent(l.best_score)}` : "Başlandı",
      "lesson-status started");
  }
  return Text.create("span", "Yeni", "lesson-status");
}

/* ------------------------------------------------------------------- list */

async function loadLessonsPage() {
  try {
    [lessonsUi.data, lessonsUi.exams] = await Promise.all([api("/api/lessons"), api("/api/exams").catch(() => [])]);
  } catch (err) {
    lessonsUi.el.grid.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted"));
    return;
  }
  const d = lessonsUi.data;
  if (!d.levels.some((lv) => lv.id === lessonsUi.level)) lessonsUi.level = null;
  if (!lessonsUi.level) {
    // The learner's level; if it has no lessons yet, the nearest level below that has some.
    const upTo = d.levels.slice(0, d.levels.findIndex((lv) => lv.id === d.level) + 1);
    lessonsUi.level = [...upTo].reverse().find((lv) => lv.count)?.id || d.level;
  }
  Text.render(lessonsUi.el.level, `Seviyen: ${d.level} — ${LEVEL_NAMES[d.level] || ""}. Seviyeni Ayarlar'dan değiştirebilirsin; `
    + "alt seviyelerin dersleri de her zaman açık.");
  renderRecommended(d.recommended);
  renderLevels();
}

function lessonCard(l, reason = "") {
  const a = document.createElement("a");
  a.className = `lesson-card ${l.status}`;
  a.href = `#/lesson/${encodeURIComponent(l.id)}`;
  a.append(
    lnode("div", "lesson-card-head",
      lnode("span", "", Text.create("span", l.level, "level-badge"), (l.tags || []).includes("work") && Text.create("span", "💼 İş", "work-badge")),
      lessonStatus(l)),
    Text.create("strong", l.title_tr),
    Text.create("span", l.title_en, "muted small"),
    reason && Text.create("span", `🎯 ${reason}`, "lesson-reason small"),
  );
  return a;
}

function renderRecommended(items) {
  const box = lessonsUi.el.recommended;
  box.replaceChildren();
  if (!items.length) return;
  box.append(Text.create("h3", "🎯 Sana önerilen"),
    lnode("div", "lesson-grid", items.map((l) => lessonCard(l, l.reason))));
}

function renderLevels() {
  const d = lessonsUi.data;
  lessonsUi.el.levels.replaceChildren(...d.levels.map((lv) => {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(lv.id === lessonsUi.level));
    Text.render(b, lv.count ? `${lv.id} (${lv.done}/${lv.count})` : lv.id);
    b.title = LEVEL_NAMES[lv.id];
    b.addEventListener("click", () => {
      lessonsUi.level = lv.id;
      store.set("lessonsLevel", lv.id);
      renderLevels();
    });
    return b;
  }));
  const list = d.lessons.filter((l) => l.level === lessonsUi.level);
  lessonsUi.el.grid.replaceChildren(...(list.length ? list.map((l) => lessonCard(l))
    : [Text.create("p", `${lessonsUi.level} seviyesinin dersleri yakında eklenecek.`, "muted")]));
  // The level exam, after the level's lessons.
  lessonsUi.el.grid.append(examCard((lessonsUi.exams || []).find((e) => e.level === lessonsUi.level)));
}

/* ----------------------------------------------------------------- lesson */

async function loadLessonDetail(id, { force = false } = {}) {
  const view = lessonsUi.el.view;
  // Back to the lesson on the screen: keep it as it is (answers, typed text, results).
  if (!force && lessonsUi.shownId === id && view.querySelector(".exercises")) return;
  lessonsUi.shownId = null;
  view.replaceChildren(Text.create("p", "Yükleniyor…", "muted"));
  $("#page-lesson").scrollTop = 0;
  let l, saved;
  try {
    [l, saved] = await Promise.all([api(`/api/lessons/${encodeURIComponent(id)}`), savedState.get(`lesson:${id}`)]);
  } catch (err) {
    view.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted"));
    return;
  }
  // The learner's work on this page, kept until they delete it: answered exercises, unsent text, own sentences.
  const work = { exercises: {}, drafts: {}, result: null, sentences: [], ...(saved || {}) };
  work.save = () => {
    const { save, ...value } = work;
    savedState.set(`lesson:${l.id}`, value);
  };
  lessonsUi.shownId = id;
  view.replaceChildren(
    lnode("div", "lesson-head", Text.create("span", `${l.level} · ${LEVEL_NAMES[l.level] || ""}`, "level-badge"),
      ...l.category_labels.map((c) => Text.create("span", c, "tag")),
      l.status !== "new" && l.best_score != null && deleteButton(
        "Bu dersin ilerlemesi (puan ve tamamlandı bilgisi) sıfırlansın mı?", async () => {
          await api(`/api/lessons/${encodeURIComponent(l.id)}/progress`, { method: "DELETE" });
          loadLessonDetail(l.id, { force: true });
        }, "↺ İlerlemeyi sıfırla")),
    Text.create("h2", l.title_tr),
    Text.create("p", l.title_en, "muted lesson-title-en"),
    Text.create("p", l.intro_tr, "lesson-intro"),
    askTeacherButton(l),
    ...l.sections.map(renderSection),
    renderMistakes(l.mistakes),
    renderExercises(l, work),
    renderSentenceBuilder(l, work),
    renderConversationPractice(l),
    renderSources(l.sources),
    l.next && lnode("div", "lesson-next", Text.create("span", "Sıradaki ders: ", "muted"),
      Object.assign(Text.create("a", `${l.next.title_tr} →`), { href: `#/lesson/${encodeURIComponent(l.next.id)}` })),
  );
}

function askTeacherButton(l) {
  const b = Text.create("button", "🧑‍🏫 Öğretmene sor", "ghost small ask-teacher");
  b.type = "button";
  b.title = "Bu dersle ilgili sorunu öğretmene Türkçe sor";
  b.addEventListener("click", () => Teacher.open({ type: "lesson", lesson_id: l.id, title: `📘 ${l.title_tr} (${l.level})` }));
  return b;
}

function exampleRow(ex) {
  return lnode("li", "lesson-example",
    iconButton("🔊", "Dinle", () => speakText(ex.en)),
    lnode("div", "", Text.create("div", ex.en, "en", { words: true }), Text.create("div", ex.tr, "muted small")));
}

function renderSection(s) {
  const box = lnode("section", `lesson-section ${s.work ? "work-section" : ""}`, Text.create("h3", s.title_tr));
  for (const para of s.text_tr.split(/\n\n+/)) box.append(Text.create("p", para));
  if (s.table) {
    const table = document.createElement("table");
    table.className = "lesson-table";
    const head = document.createElement("tr");
    for (const h of s.table.head) head.append(Text.create("th", h));
    table.append(head);
    for (const row of s.table.rows) {
      const tr = document.createElement("tr");
      for (const cell of row) tr.append(Text.create("td", cell));
      table.append(tr);
    }
    box.append(lnode("div", "table-scroll", table));
  }
  if (s.examples?.length) box.append(lnode("ul", "lesson-examples", s.examples.map(exampleRow)));
  return box;
}

function renderMistakes(mistakes) {
  if (!mistakes?.length) return null;
  return lnode("section", "lesson-section",
    Text.create("h3", "⚠️ Türklerin sık yaptığı hatalar"),
    lnode("ul", "lesson-mistakes", mistakes.map((m) => lnode("li", "",
      lnode("div", "corr-change", Text.create("span", m.wrong, "wrong"), " → ", Text.create("span", m.right, "right", { words: true })),
      Text.create("div", m.note_tr, "expl")))));
}

/** Further reading: the reputable free pages the explanation is based on. */
function renderSources(sources) {
  if (!sources?.length) return null;
  return lnode("section", "lesson-section lesson-sources",
    Text.create("h3", "📚 Kaynaklar ve daha fazlası"),
    Text.create("p", "Bu dersin anlatımı aşağıdaki kaynaklarla uyumludur; konuyu daha ayrıntılı okumak ve ek alıştırma "
      + "yapmak için açabilirsin (internet gerekir).", "muted small"),
    lnode("ul", "", sources.map((s) => {
      const a = Text.create("a", s.title);
      a.href = s.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      return lnode("li", "", a, Text.create("span", ` — ${s.site}`, "muted small"));
    })));
}

/* -------------------------------------------------------------- exercises */

const CONTRACTIONS = [
  [/\bcan't\b/g, "can not"], [/\bcannot\b/g, "can not"], [/\bwon't\b/g, "will not"], [/n't\b/g, " not"],
  [/'m\b/g, " am"], [/'re\b/g, " are"], [/'ve\b/g, " have"], [/'ll\b/g, " will"],
  [/\b(he|she|it|that|there|what|where|who|here)'s\b/g, "$1 is"], [/'d have\b/g, " would have"],
  // abbreviations: 2 p.m. = 2pm = 2 pm, e.g. = eg, Mr. = Mr
  [/\b([a-z])\.([a-z])\./g, "$1$2"], [/\b(mr|mrs|ms|dr)\./g, "$1"], [/(\d)\s*(am|pm)\b/g, "$1 $2"],
];

/** Compare answers leniently: case, spaces, final punctuation, commas, contractions, abbreviations.
 *  Keep in sync with exams.py normalize_answer. */
function normalizeAnswer(text) {
  let s = text.toLowerCase().replace(/[’‘]/g, "'").replace(/[“”"]/g, "").trim();
  for (const [re, rep] of CONTRACTIONS) s = s.replace(re, rep);
  return s.replace(/,/g, "").replace(/\s+/g, " ").replace(/[.!?]+$/, "").trim();
}

// A pronoun's 's is "is" — or "has" before a past participle ("She's finished" = "She has finished");
// 'd is "would" — or "had" before a participle or "better". Only there: "He's a car" must not match
// "He has a car". Keep in sync with exams.py answer_forms.
const PARTICIPLES = new Set((
  "been got gotten had done gone seen made said sent left lost met paid put read spent taken told thought "
  + "bought brought built found heard held kept known run sold written won begun come become given forgotten "
  + "chosen spoken broken eaten fallen flown grown shown thrown drawn worn sat stood understood taught caught "
  + "felt led set cut hit let shut hurt cost quit sung drunk swum rung forgiven driven ridden risen hidden "
  + "bitten beaten woken fed meant slept sold dealt lent stuck struck").split(" "));
const ADVERBS = new Set(("just already never ever not always recently finally also still only really probably "
  + "definitely certainly obviously clearly").split(" "));
const PRONOUN_S = /\b(he|she|it|that|there|what|where|who|here)'s\b/gi;
const PRONOUN_D = /\b(i|you|he|she|it|we|they|there|who|that)'d\b/gi;

function beforeParticiple(rest) {
  let words = (rest.toLowerCase().match(/[a-z']+/g) || []).slice(0, 2);
  if (words.length && ADVERBS.has(words[0])) words = words.slice(1);
  return words.length > 0 && (PARTICIPLES.has(words[0]) || words[0].endsWith("ed") || words[0].endsWith("en"));
}

function contractionReadings(text, re, plain, perfect, extra = []) {
  const perfectText = text.replace(re, (m, p, offset) => {
    const rest = text.slice(offset + m.length);
    return beforeParticiple(rest) || extra.some((w) => rest.toLowerCase().trimStart().startsWith(w))
      ? `${p} ${perfect}` : m;
  });
  return [text.replace(re, `$1 ${plain}`), perfectText.replace(re, `$1 ${plain}`)];
}

/** Every reading of an answer, normalized with `key`. */
function answerForms(text, key = normalizeAnswer) {
  const forms = contractionReadings(text.replace(/[’‘]/g, "'"), PRONOUN_S, "is", "has")
    .flatMap((f) => contractionReadings(f, PRONOUN_D, "would", "had", ["better"]));
  return new Set(forms.map(key));
}

/** Is `given` one of the accepted `answers`? */
function answerMatches(answers, given, key = normalizeAnswer) {
  const forms = answerForms(given, key);
  return answers.some((a) => [...answerForms(a, key)].some((f) => forms.has(f)));
}

/** Exercises. `work` (the lesson page's saved work) keeps each answer, the unsent text and the result until
 *  "Tekrar çöz": leaving the page or restarting the app changes nothing. */
function renderExercises(l, work) {
  const box = lnode("section", "lesson-section exercises",
    Text.create("h3", "✏️ Alıştırmalar"),
    Text.create("p", `Her soruyu cevapla; %80 ve üstü doğruyla ders tamamlanır.${l.status === "done"
      ? ` (Bu dersi tamamladın, en iyi sonucun ${percent(l.best_score)}.)` : ""}`, "muted small"));
  const list = lnode("ol", "exercise-list");
  const result = lnode("div", "exercise-result");
  box.append(list, result);

  const start = () => {
    const state = { answered: 0, correct: 0, total: l.exercises.length };
    result.replaceChildren();
    list.replaceChildren(...l.exercises.map((ex, i) => {
      const saved = work.exercises[i];
      if (saved && saved.type === ex.type) {
        state.answered += 1;
        if (saved.ok) state.correct += 1;
        return renderAnsweredExercise(ex, saved);
      }
      return renderExercise(ex, (ok, given) => {
        work.exercises[i] = { type: ex.type, ok, given: given ?? "" };
        delete work.drafts[i];
        work.save();
        state.answered += 1;
        if (ok) state.correct += 1;
        if (state.answered === state.total) finish(state);
      }, { value: work.drafts[i] || "", onInput: (v) => { work.drafts[i] = v; work.save(); } });
    }));
    if (state.answered === state.total) work.result ? showResult(work.result) : finish(state);
  };

  const finish = async (state) => {
    let saved = null, saveError = null;
    try {
      saved = await api(`/api/lessons/${encodeURIComponent(l.id)}/result`, {
        method: "POST", body: { correct: state.correct, total: state.total } });
    } catch (err) {
      saveError = err.message;
    }
    const r = { correct: state.correct, total: state.total, saveError,
      ok: state.correct / state.total >= 0.8 && !saveError, doneBefore: saved?.status === "done" };
    if (!saveError) {
      work.result = r;
      work.save();
    }
    showResult(r);
  };

  const showResult = (r) => {
    const again = document.createElement("button");
    again.type = "button";
    again.className = "ghost small";
    Text.render(again, "↻ Tekrar çöz");
    again.addEventListener("click", () => {
      work.exercises = {};
      work.drafts = {};
      work.result = null;
      work.save();
      start();
      list.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    result.replaceChildren(
      Text.create("strong", `Sonuç: ${r.correct} / ${r.total} doğru (${percent(r.correct / r.total)})`),
      r.saveError
        ? Text.create("span", ` ⚠️ Sonuç kaydedilemedi (${r.saveError}). Uygulama yeniden başlatılıyor olabilir; biraz sonra tekrar çöz.`, "muted")
        : Text.create("span", r.ok ? " 🎉 Ders tamamlandı!" : " — %80'e ulaşınca ders tamamlanır. Açıklamalara bakıp tekrar dene.",
          r.ok ? "ok-text" : "muted"),
      r.doneBefore && !r.ok ? Text.create("span", " (Bu dersi daha önce tamamlamıştın.)", "muted small") : "",
      again,
    );
  };

  start();
  return box;
}

/** The question line of an exercise (the same while answering and when shown answered). */
function exerciseQuestion(ex) {
  if (ex.type === "choice") return Text.create("div", ex.q, "exercise-q");
  if (ex.type === "order") return Text.create("div", ex.q || "Kelimeleri doğru sıraya koy:", "exercise-q");
  if (ex.type === "match") return Text.create("div", ex.q || "Eşleştir: önce İngilizceye, sonra Türkçe karşılığına tıkla.", "exercise-q");
  if (ex.type === "listen") {
    const q = lnode("div", "exercise-q", "Dinle ve duyduğun cümleyi yaz: ", iconButton("🔊", "Dinle", () => speakText(ex.text)));
    q.append(transcriptButton(ex.text, q));
    return q;
  }
  if (ex.type === "transform") {
    return lnode("div", "exercise-q", Text.create("strong", `${ex.instruction_tr}: `), Text.create("span", ex.q));
  }
  return Text.create("div", ex.type === "fix" ? `Düzelt: ${ex.q}` : ex.q, "exercise-q");
}

function correctAnswerText(ex) {
  if (ex.type === "choice") return ex.options[ex.answer];
  if (ex.type === "match") return ex.pairs.map(([e, t]) => `${e} = ${t}`).join(" · ");
  return ex.answer[0];
}

function fillFeedback(el, ex, ok, correctText) {
  el.replaceChildren(
    Text.create("strong", ok ? "✓ Doğru!" : "✗ Yanlış.", ok ? "ok-text" : "err-text"),
    !ok && correctText ? lnode("span", "", " Doğrusu: ", Text.create("span", correctText, "right", { words: true })) : "",
    Text.create("div", ex.explain_tr, "expl"));
}

/** An exercise answered earlier (saved): the question, the learner's answer and the feedback. */
function renderAnsweredExercise(ex, saved) {
  const li = lnode("li", `exercise ${saved.ok ? "right" : "wrong"}`, exerciseQuestion(ex));
  if (ex.type === "choice") {
    li.append(lnode("div", "exercise-options", ex.options.map((opt, i) => {
      const b = Text.create("button", opt, `chip${i === ex.answer ? " correct" : ""}${!saved.ok && opt === saved.given ? " chosen-wrong" : ""}`);
      b.type = "button";
      b.disabled = true;
      return b;
    })));
  } else if (saved.given) {
    li.append(lnode("div", "exercise-given", Text.create("span", "Cevabın: ", "muted"),
      Text.create("span", saved.given, saved.ok ? "" : "wrong")));
  }
  const feedback = lnode("div", "exercise-feedback");
  fillFeedback(feedback, ex, saved.ok, correctAnswerText(ex));
  li.append(feedback);
  return li;
}

/** An exercise to answer. `draft`: typed text kept while unsent ({value, onInput}). */
function renderExercise(ex, onAnswered, draft = null) {
  const li = lnode("li", "exercise");
  const feedback = lnode("div", "exercise-feedback");
  const answered = (ok, correctText, given) => {
    li.classList.add(ok ? "right" : "wrong");
    fillFeedback(feedback, ex, ok, correctText);
    onAnswered(ok, given);
  };

  if (ex.type === "choice") {
    li.append(exerciseQuestion(ex));
    const options = lnode("div", "exercise-options");
    ex.options.forEach((opt, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      Text.render(b, opt);
      b.addEventListener("click", () => {
        for (const other of options.children) other.disabled = true;
        options.children[ex.answer].classList.add("correct");
        if (i !== ex.answer) b.classList.add("chosen-wrong");
        answered(i === ex.answer, ex.options[ex.answer], opt);
      });
      options.append(b);
    });
    li.append(options);
  } else if (ex.type === "order") {
    renderOrder(li, ex, answered);
  } else if (ex.type === "match") {
    renderMatch(li, ex, answered);
  } else {
    li.append(exerciseQuestion(ex));
    const form = document.createElement("form");
    form.className = "exercise-form";
    const input = document.createElement("input");
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = { fix: "Doğru cümleyi yaz", transform: "Yeni cümleyi yaz", listen: "Duyduğun cümle" }[ex.type]
      || "Boşluğa gelen kelime(ler)";
    const check = document.createElement("button");
    check.type = "submit";
    check.className = "ghost small";
    Text.render(check, "Kontrol");
    form.append(input, check);
    if (draft) {
      input.value = draft.value;
      input.addEventListener("input", () => draft.onInput(input.value));
    }
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      if (!input.value.trim()) return;
      input.disabled = check.disabled = true;
      const ok = answerMatches(ex.answer, input.value);
      answered(ok, ex.answer[0], input.value.trim());
    });
    li.append(form);
  }
  li.append(feedback);
  return li;
}

const shuffled = (list) => {
  const a = list.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
};

/** "order": put the word tiles in order (click a tile to move it; click it again to take it back). */
function renderOrder(li, ex, answered) {
  li.append(exerciseQuestion(ex));
  const built = lnode("div", "order-built");
  const pool = lnode("div", "order-pool");
  let tiles = shuffled(ex.words);
  if (tiles.join(" ") === ex.words.join(" ") && tiles.length > 1) tiles = [...tiles.slice(1), tiles[0]];
  const tile = (text, from, to) => {
    const b = Text.create("button", text, "chip order-tile");
    b.type = "button";
    b.addEventListener("click", () => to.append(tile(text, to, from)) || b.remove());
    return b;
  };
  for (const t of tiles) pool.append(tile(t, pool, built));
  const check = Text.create("button", "Kontrol", "ghost small");
  check.type = "button";
  check.addEventListener("click", () => {
    const sentence = [...built.children].map((b) => Text.get(b)).join(" ");
    if (!sentence) return;
    [...li.querySelectorAll("button")].forEach((b) => (b.disabled = true));
    // A tile may carry the sentence's final mark ("today."); another correct order puts it inside.
    const bare = (s) => normalizeAnswer(s.replace(/[.?!]/g, " "));
    answered(answerMatches(ex.answer, sentence, bare), ex.answer[0], sentence);
  });
  li.append(built, pool, check);
}

/** "match": click an English word, then its Turkish meaning. Correct when every pair is found without a mistake. */
function renderMatch(li, ex, answered) {
  li.append(exerciseQuestion(ex));
  const left = lnode("div", "match-col"), right = lnode("div", "match-col");
  let picked = null, mistakes = 0, found = 0;
  const pairs = ex.pairs;
  for (const [en] of pairs) {
    const b = Text.create("button", en, "chip match-item");
    b.type = "button";
    b.addEventListener("click", () => {
      left.querySelectorAll(".picked").forEach((x) => x.classList.remove("picked"));
      picked = en;
      b.classList.add("picked");
    });
    left.append(b);
  }
  for (const [, tr] of shuffled(pairs)) {
    const b = Text.create("button", tr, "chip match-item");
    b.type = "button";
    b.addEventListener("click", () => {
      if (!picked) return;
      const enBtn = [...left.children].find((x) => Text.get(x) === picked);
      if (pairs.some(([e, t]) => e === picked && t === tr)) {
        enBtn.disabled = b.disabled = true;
        enBtn.classList.replace("picked", "correct");
        b.classList.add("correct");
        found += 1;
        if (found === pairs.length) {
          answered(mistakes === 0, mistakes ? correctAnswerText(ex) : "", mistakes ? `${mistakes} yanlış eşleştirme` : "");
        }
      } else {
        mistakes += 1;
        b.classList.add("chosen-wrong");
        setTimeout(() => b.classList.remove("chosen-wrong"), 600);
      }
      picked = null;
      left.querySelectorAll(".picked").forEach((x) => x.classList.remove("picked"));
    });
    right.append(b);
  }
  li.append(lnode("div", "match-grid", left, right));
}

/* ------------------------------------------------- build your own sentences */

/** Questions from the AI, answered one sentence each. Kept (questions, answers, checks) until the learner
 *  deletes them; new questions come on top. */
function renderSentenceBuilder(l, work) {
  const list = lnode("div", "sentence-list");
  const status = lnode("div", "");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "primary small";
  const clear = deleteButton("Bu dersteki tüm sorular ve cevapların silinsin mi?", async () => {
    work.sentences = [];
    work.save();
    draw();
  }, "🗑 Tümünü sil");
  const draw = () => {
    Text.render(btn, work.sentences.length ? "➕ Yeni sorular" : "Soruları getir");
    clear.hidden = !work.sentences.length;
    clear.disabled = false;  // deleteButton keeps it disabled after a delete; this one is used again
    list.replaceChildren(...work.sentences.map((item) => sentenceItem(l.id, item, work, () => {
      work.sentences = work.sentences.filter((s) => s !== item);
      work.save();
      draw();
    })));
  };
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    status.replaceChildren(Text.create("p", "🤖 Sorular hazırlanıyor…", "muted"));
    try {
      const { items } = await api(`/api/lessons/${encodeURIComponent(l.id)}/prompts`, { method: "POST" });
      work.sentences = [...items.map((question) => ({ question, answer: "", result: null })), ...work.sentences];
      work.save();
      status.replaceChildren();
      draw();
    } catch (err) {
      status.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted"));
    } finally {
      btn.disabled = false;
    }
  });
  draw();
  return lnode("section", "lesson-section",
    Text.create("h3", "✍️ Kendi cümlelerini kur"),
    Text.create("p", "Yapay zeka bu konuyu kullanman gereken sorular sorar; her birine tek bir cümleyle cevap ver. "
      + "Cevabın üç açıdan kontrol edilir: soruya uygun mu, dersin konusunu kullanıyor mu, dilbilgisi doğru mu. "
      + "Soruların ve cevapların sen silene kadar burada kalır.", "muted small"),
    lnode("div", "actions", btn, clear), status, list);
}

function showSentenceResult(out, r) {
  const icon = { ok: "✓", warn: "⚠", wrong: "✗" }[r.verdict];
  out.replaceChildren(Text.create("div", `${icon} ${r.message_tr}`, `verdict ${r.verdict}`));
  // Grammar mistakes: the wrong words in red, the correct sentence in green.
  if (r.correction?.has_errors) out.append(correctionCard(r.correction));
}

/** One question: `item` = {question, answer (also while typing), result} in the lesson's saved work. */
function sentenceItem(lessonId, item, work, onDelete) {
  const out = lnode("div", "sentence-result");
  const form = document.createElement("form");
  form.className = "exercise-form";
  const input = document.createElement("input");
  input.autocomplete = "off";
  input.placeholder = "Cevabını İngilizce yaz…";
  input.value = item.answer || "";
  input.addEventListener("input", () => {
    item.answer = input.value;
    work.save();
  });
  const check = document.createElement("button");
  check.type = "submit";
  check.className = "ghost small";
  Text.render(check, "Kontrol et");
  form.append(input, check);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    check.disabled = true;
    out.replaceChildren(Text.create("span", "Kontrol ediliyor…", "muted small"));
    try {
      const r = await api(`/api/lessons/${encodeURIComponent(lessonId)}/check`, {
        method: "POST", body: { question: item.question, answer: text } });
      item.answer = text;
      item.result = { verdict: r.verdict, message_tr: r.message_tr, correction: r.correction || null, checked: text };
      work.save();
      showSentenceResult(out, item.result);
    } catch (err) {
      out.replaceChildren(Text.create("span", `⚠️ ${err.message}`, "muted small"));
    } finally {
      check.disabled = false;
    }
  });
  if (item.result) showSentenceResult(out, item.result);
  const row = lnode("div", "q-row", Text.create("div", item.question, "exercise-q", { words: true }));
  row.append(translateButton(() => item.question, () => row),  // the Turkish appears under the question
    deleteButton("Bu soru ve cevabın silinsin mi?", async () => onDelete()));
  return lnode("div", "sentence-item", row, form, out);
}

/* ---------------------------------------------------- conversation practice */

function renderConversationPractice(l) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "primary";
  Text.render(btn, "🗣 Konuşarak pratik yap");
  btn.addEventListener("click", () => startScenario({ lesson: l.id }));
  return lnode("section", "lesson-section",
    Text.create("h3", "🗣 Konuşarak pratik"),
    Text.create("p", "Yapay zeka seninle bu konuyu kullandıran bir sohbet başlatır. Hataların sağdaki panelde düzeltilir; "
      + "bitince 🏁 Oturumu bitir ile raporunu alırsın.", "muted small"),
    lnode("ul", "lesson-tasks", l.practice.tasks.map((t) => Text.create("li", t[0]))),
    btn);
}
