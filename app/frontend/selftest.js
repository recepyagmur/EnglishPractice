"use strict";

/* 🎯 Kendini Test Et: timed self-tests. One category for now — YDS-style questions (backend/selftest.py):
   a set of one question type, or a 40-question mini exam in YDS proportions. Answers are saved on the server
   as you go and the deadline lives there too, so leaving the page or restarting loses nothing. During the test
   there is no help (no word popups, no transcript); answers and explanations come only with the result. */

const selftestUi = {
  el: { cats: $("#selftest-cats"), view: $("#selftest-view") },
  cat: "yds",
  overview: null,
  qtype: store.get("selftestType") || "grammar",
  attempt: null,     // the running attempt (questions without answers)
  answers: {},
  current: 0,
  timer: 0,          // setInterval id
  deadline: 0,       // ms, 0 = no limit
  saveTimer: 0,
};

const SELFTEST_CATS = [{ id: "yds", label: "📝 YDS tarzı sınav" }];
const LETTERS = ["A", "B", "C", "D", "E"];
const ROMAN = ["I", "II", "III", "IV", "V"];
const TIMING_TR = { standard: "YDS standardı (2,25 dk/soru)", relaxed: "Rahat (1,5×)", none: "Süresiz" };

function stButton(label, className, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = className;
  Text.render(b, label);
  b.addEventListener("click", onClick);
  return b;
}

const fmtTime = (s) => {
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return (h ? `${h}:${String(m).padStart(2, "0")}` : String(m)) + `:${String(sec).padStart(2, "0")}`;
};
const fmtMinutes = (s) => (s % 60 ? `${Math.floor(s / 60)} dk ${s % 60} sn` : `${s / 60} dk`);
const fmtDate = (iso) => new Date(iso).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });

/* ------------------------------------------------------------------ page */

async function loadSelftestPage() {
  const cats = selftestUi.el.cats;
  cats.replaceChildren();
  for (const c of SELFTEST_CATS) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(c.id === selftestUi.cat));
    Text.render(b, c.label);
    cats.append(b);
  }
  if (selftestUi.attempt) return renderTest();  // still solving: the page keeps its state
  await renderSelftestIntro();
}

async function renderSelftestIntro() {
  const view = selftestUi.el.view;
  view.replaceChildren(Text.create("p", "Yükleniyor…", "muted"));
  let o;
  try {
    o = selftestUi.overview = await api("/api/selftest");
  } catch (err) {
    view.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted"));
    return;
  }
  const box = lnode("div", "st-intro");
  box.append(Text.create("p", "ÖSYM'nin YDS / e-YDS / YÖKDİL formatında özgün sorular; süre YDS'deki gibi soru başına 2,25 dakika. "
    + "Sınav sırasında yardım yok; cevaplar ve açıklamalar sonuçta görünür. Çözmediğin sorular önce gelir.", "muted"));
  if (o.running) {
    const a = o.running;
    const n = Object.keys(a.answers).length;
    box.append(lnode("div", "st-running",
      Text.create("span", `⏳ Yarım kalan test: ${a.kind === "mini" ? "Mini deneme" : a.qtype_tr} · ${n} / ${a.questions.length} cevaplandı`
        + (a.remaining_s != null ? ` · kalan süre ${fmtTime(a.remaining_s)}` : "")),
      stButton("▶ Devam et", "primary small", () => beginAttempt(a)),
      stButton("🗑 Bırak", "ghost small", async () => {
        if (!window.confirm("Yarım kalan test silinsin mi? Cevapların kaybolur.")) return;
        await api(`/api/selftest/attempts/${a.id}`, { method: "DELETE" });
        renderSelftestIntro();
      })));
  }

  // --- a set of one question type
  box.append(Text.create("h3", "Soru türüne göre"));
  const grid = lnode("div", "st-types");
  grid.setAttribute("role", "radiogroup");
  if (!o.types.some((t) => t.type === selftestUi.qtype && t.pool)) selftestUi.qtype = o.types.find((t) => t.pool)?.type;
  const controls = lnode("div", "st-controls");
  const countSel = document.createElement("select");
  const timingSel = document.createElement("select");
  const timeNote = Text.create("span", "", "muted small");
  const drawControls = () => {
    const t = o.types.find((x) => x.type === selftestUi.qtype);
    countSel.replaceChildren(...(t?.counts || []).map((c) => Object.assign(Text.create("option", `${c} soru`), { value: String(c) })));
    const wanted = store.get("selftestCount");
    if ([...countSel.options].some((x) => x.value === wanted)) countSel.value = wanted;
    updateNote();
  };
  const updateNote = () => {
    const n = Number(countSel.value || 0);
    const f = { standard: 1, relaxed: 1.5, none: 0 }[timingSel.value];
    Text.render(timeNote, f ? `süre: ${fmtMinutes(Math.round(n * o.seconds_per_question * f))}` : "süre yok");
  };
  for (const t of o.types) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "st-type";
    card.setAttribute("role", "radio");
    card.setAttribute("aria-checked", String(t.type === selftestUi.qtype));
    card.disabled = !t.pool;
    const acc = t.seen ? ` · doğruluk %${Math.round(100 * t.right / t.seen)}` : "";
    card.append(Text.create("strong", t.tr), Text.create("span", t.pool ? `${t.pool} soru · ${t.seen} çözüldü${acc}` : "yakında", "muted"));
    card.addEventListener("click", () => {
      selftestUi.qtype = t.type;
      store.set("selftestType", t.type);
      grid.querySelectorAll(".st-type").forEach((c) => c.setAttribute("aria-checked", "false"));
      card.setAttribute("aria-checked", "true");
      drawControls();
    });
    grid.append(card);
  }
  for (const [k, label] of Object.entries(TIMING_TR)) timingSel.append(Object.assign(Text.create("option", label), { value: k }));
  timingSel.value = store.get("selftestTiming") || "standard";
  countSel.addEventListener("change", () => { store.set("selftestCount", countSel.value); updateNote(); });
  timingSel.addEventListener("change", () => { store.set("selftestTiming", timingSel.value); updateNote(); });
  drawControls();
  controls.append(lnode("label", "", "Soru sayısı:", countSel), lnode("label", "", "Süre:", timingSel), timeNote,
    stButton("▶ Başla", "primary", (e) => startSelftest({ kind: "type", qtype: selftestUi.qtype, count: Number(countSel.value),
      timing: timingSel.value }, e.target)));
  box.append(grid, controls);

  // --- mini exam
  box.append(Text.create("h3", "Mini deneme"));
  const miniTiming = document.createElement("select");
  for (const [k, label] of Object.entries(TIMING_TR)) miniTiming.append(Object.assign(Text.create("option", label), { value: k }));
  miniTiming.value = store.get("selftestTiming") || "standard";
  miniTiming.addEventListener("change", () => store.set("selftestTiming", miniTiming.value));
  const miniNote = Text.create("span", `${o.mini_total} soru, YDS oranında ve sırasında · standart süre ${fmtMinutes(o.mini_total * o.seconds_per_question)}`, "muted small");
  box.append(lnode("div", "st-controls", miniNote, lnode("label", "", "Süre:", miniTiming),
    stButton("▶ Mini denemeye başla", "primary", (e) => startSelftest({ kind: "mini", timing: miniTiming.value }, e.target))));

  // --- history
  if (o.history.length) {
    box.append(Text.create("h3", "Geçmiş"));
    const list = lnode("div", "st-history");
    for (const h of o.history) {
      const row = lnode("div", "vocab-row");
      const main = lnode("div", "vocab-main",
        Text.create("strong", h.kind === "mini" ? "Mini deneme" : h.qtype_tr),
        Text.create("div", `${fmtDate(h.finished_at)} · ${h.correct} / ${h.total} doğru (%${Math.round(100 * h.correct / h.total)})`
          + (h.time_used_s != null ? ` · ${fmtTime(h.time_used_s)}${h.time_limit_s ? ` / ${fmtTime(h.time_limit_s)}` : ""}` : ""), "muted small"));
      row.append(main, deleteButton("Bu test sonucu silinsin mi?", async () => {
        await api(`/api/selftest/attempts/${h.id}`, { method: "DELETE" });
        renderSelftestIntro();
      }));
      row.addEventListener("click", () => openSelftestResult(h.id));
      list.append(row);
    }
    box.append(list);
  }
  box.append(Text.create("p", "Sorular ÖSYM formatında özgün olarak yazılmış ve bağımsız denetimden geçmiştir; gerçek ÖSYM soruları değildir. "
    + "Biçim ve kaynaklar: app/content/yds/README.md", "muted small"));
  view.replaceChildren(box);
}

async function startSelftest(body, btn) {
  if (selftestUi.overview?.running && !window.confirm("Yarım kalan test kapatılacak (puanlanmaz). Yeni test başlasın mı?")) return;
  btn.disabled = true;
  try {
    const a = await api("/api/selftest/start", { method: "POST", body });
    beginAttempt(a);
  } catch (err) {
    btn.disabled = false;
    window.alert(err.message);
  }
}

/* ------------------------------------------------------------------ solving */

function beginAttempt(a) {
  stopSelftestTimer();
  selftestUi.attempt = a;
  selftestUi.answers = { ...a.answers };
  const firstOpen = a.questions.findIndex((q) => !(q.id in selftestUi.answers));
  selftestUi.current = firstOpen < 0 ? 0 : firstOpen;
  selftestUi.deadline = a.remaining_s != null ? Date.now() + a.remaining_s * 1000 : 0;
  renderTest();
  if (selftestUi.deadline) selftestUi.timer = setInterval(tickSelftest, 1000);
  window.scrollTo({ top: 0 });
}

function stopSelftestTimer() {
  clearInterval(selftestUi.timer);
  selftestUi.timer = 0;
}

function tickSelftest() {
  const left = (selftestUi.deadline - Date.now()) / 1000;
  const el = $("#st-timer");
  if (el) {
    Text.render(el, fmtTime(left));
    el.classList.toggle("low", left < 120);
  }
  if (left <= 0) {
    stopSelftestTimer();
    finishSelftest(true);
  }
}

const answeredCount = () => selftestUi.attempt.questions.filter((q) => q.id in selftestUi.answers).length;

function renderTest() {
  const a = selftestUi.attempt;
  const view = selftestUi.el.view;
  const title = a.kind === "mini" ? "Mini deneme" : a.qtype_tr;
  const timer = Text.create("span", a.remaining_s != null ? fmtTime((selftestUi.deadline - Date.now()) / 1000) : "⏱ süresiz", "st-timer");
  timer.id = "st-timer";
  if (a.remaining_s != null && (selftestUi.deadline - Date.now()) / 1000 < 120) timer.classList.add("low");
  const count = Text.create("span", "", "muted small");
  count.id = "st-count";
  const head = lnode("div", "st-head",
    lnode("div", "", Text.create("strong", `📝 ${title}`), " ", count),
    lnode("div", "actions", timer, stButton("Bitir", "primary small", () => finishSelftest(false))));
  const nav = lnode("div", "st-nav");
  nav.id = "st-nav";
  const qbox = lnode("div", "");
  qbox.id = "st-qbox";
  view.replaceChildren(head, nav, qbox);
  drawSelftestNav();
  drawSelftestQuestion();
}

function drawSelftestNav() {
  const a = selftestUi.attempt;
  const nav = $("#st-nav");
  if (!nav) return;
  nav.replaceChildren();
  a.questions.forEach((q, i) => {
    const b = stButton(String(i + 1), (q.id in selftestUi.answers ? "answered" : "") + (i === selftestUi.current ? " current" : ""),
      () => { selftestUi.current = i; drawSelftestNav(); drawSelftestQuestion(); });
    b.title = a.types[q.type];
    nav.append(b);
  });
  const c = $("#st-count");
  if (c) Text.render(c, `${answeredCount()} / ${a.questions.length} cevaplandı`);
}

/** The passage with the current cloze blank marked, or any `----` kept as is. */
function passageNode(text, markBlank = null) {
  const box = lnode("div", "st-passage");
  if (markBlank == null) {
    box.append(Text.create("span", text));
    return box;
  }
  const marker = `(${markBlank})----`;
  const at = text.indexOf(marker);
  if (at < 0) {
    box.append(Text.create("span", text));
    return box;
  }
  box.append(Text.create("span", text.slice(0, at)), Text.create("mark", marker), Text.create("span", text.slice(at + marker.length)));
  return box;
}

/** The question body (shared by solving and review): passage, stem, dialogue lines or numbered sentences. */
function questionBody(q, a, { review = false } = {}) {
  const parts = [];
  const words = review ? { words: true } : {};
  if (q.passage_id && a.passages[q.passage_id]) {
    const p = a.passages[q.passage_id];
    if (q.type === "cloze") {
      parts.push(passageNode(p.passage, q.n));
      parts.push(Text.create("div", `(${q.n}) numaralı boşluğa uygun olanı seç:`, "st-stem"));
    } else {
      const node = lnode("div", "st-passage");
      Text.render(node, p.passage, words);
      parts.push(node, Text.create("div", q.q, "st-stem"));
    }
  } else if (q.type === "dialogue") {
    const d = lnode("div", "st-dialogue");
    for (const l of q.lines) d.append(lnode("div", "", Text.create("span", `${l.speaker}:`, "speaker"), Text.create("span", l.text)));
    parts.push(Text.create("div", "Boş bırakılan yere uygun olanı seç:", "muted small"), d);
  } else if (q.type === "irrelevant") {
    const s = lnode("div", "st-sentences");
    for (const line of q.sentences) s.append(Text.create("div", line));
    parts.push(Text.create("div", "Anlam bütünlüğünü bozan cümleyi seç:", "muted small"), s);
  } else if (q.type === "paragraph") {
    parts.push(Text.create("div", "Paragrafta boş bırakılan yere uygun olanı seç:", "muted small"), passageNode(q.passage));
  } else {
    const hint = { vocab: "Boşluğa uygun olanı seç:", grammar: "Boşluğa uygun olanı seç:", sentence: "Cümleyi uygun şekilde tamamlayanı seç:",
      paraphrase: "Verilen cümleye anlamca en yakın olanı seç:",
      translation: q.direction === "en-tr" ? "Türkçe çevirisi en doğru olanı seç:" : "İngilizce çevirisi en doğru olanı seç:" }[q.type];
    parts.push(Text.create("div", hint, "muted small"), Text.create("div", q.q, "st-stem"));
  }
  return parts;
}

function optionLabels(q) {
  return q.type === "irrelevant" ? ROMAN.map((r) => `${r}. cümle`) : q.options;
}

function drawSelftestQuestion() {
  const a = selftestUi.attempt;
  const i = selftestUi.current;
  const q = a.questions[i];
  const box = $("#st-qbox");
  if (!box || !q) return;
  const card = lnode("div", "st-question", Text.create("div", `Soru ${i + 1} / ${a.questions.length} · ${a.types[q.type]}`, "muted small"),
    ...questionBody(q, a));
  const opts = lnode("div", "st-options");
  const labels = optionLabels(q);
  const letters = q.type === "irrelevant" ? ROMAN : LETTERS;
  labels.forEach((label, k) => {
    const b = lnode("button", "st-option", Text.create("span", letters[k], "letter"), Text.create("span", label));
    b.type = "button";
    b.setAttribute("aria-pressed", String(selftestUi.answers[q.id] === k));
    b.addEventListener("click", () => {
      if (selftestUi.answers[q.id] === k) delete selftestUi.answers[q.id];
      else selftestUi.answers[q.id] = k;
      opts.querySelectorAll(".st-option").forEach((x, j) => x.setAttribute("aria-pressed", String(selftestUi.answers[q.id] === j)));
      drawSelftestNav();
      queueSelftestSave();
    });
    opts.append(b);
  });
  const foot = lnode("div", "st-foot",
    stButton("← Önceki", "ghost small", () => { if (i > 0) { selftestUi.current = i - 1; drawSelftestNav(); drawSelftestQuestion(); } }),
    i + 1 < a.questions.length
      ? stButton("Sonraki →", "ghost small", () => { selftestUi.current = i + 1; drawSelftestNav(); drawSelftestQuestion(); })
      : stButton("✓ Bitir", "primary small", () => finishSelftest(false)));
  foot.firstChild.disabled = i === 0;
  card.append(opts, foot);
  box.replaceChildren(card);
}

function queueSelftestSave() {
  clearTimeout(selftestUi.saveTimer);
  selftestUi.saveTimer = setTimeout(saveSelftestAnswers, 1500);
}

async function saveSelftestAnswers() {
  clearTimeout(selftestUi.saveTimer);
  const a = selftestUi.attempt;
  if (!a) return;
  try {
    await api(`/api/selftest/attempts/${a.id}/answers`, { method: "PUT", body: { answers: selftestUi.answers } });
  } catch {}  // the next change retries; finishing sends everything again
}

async function finishSelftest(auto) {
  const a = selftestUi.attempt;
  if (!a) return;
  if (!auto) {
    const open = a.questions.length - answeredCount();
    if (!window.confirm(open ? `${open} soru cevapsız (yanlış sayılır). Testi bitirmek istiyor musun?` : "Test bitirilsin mi?")) return;
  }
  stopSelftestTimer();
  clearTimeout(selftestUi.saveTimer);
  let r;
  try {
    r = await api(`/api/selftest/attempts/${a.id}/finish`, { method: "POST", body: { answers: selftestUi.answers } });
  } catch (err) {
    window.alert(`Teslim edilemedi: ${err.message}. Tekrar dene.`);
    if (selftestUi.deadline) selftestUi.timer = setInterval(tickSelftest, 1000);
    return;
  }
  selftestUi.attempt = null;
  selftestUi.answers = {};
  if (auto) window.alert("Süre doldu — test teslim edildi.");
  renderSelftestResult(r);
}

/* ------------------------------------------------------------------ result */

async function openSelftestResult(id) {
  try {
    renderSelftestResult(await api(`/api/selftest/attempts/${id}/result`));
  } catch (err) {
    window.alert(err.message);
  }
}

function renderSelftestResult(r) {
  const view = selftestUi.el.view;
  const good = r.score >= 60;
  const title = r.kind === "mini" ? "Mini deneme" : r.qtype_tr;
  const head = lnode("div", `exam-result-head ${good ? "passed" : "failed"}`,
    Text.create("div", `${r.correct} / ${r.total}`, "exam-score"),
    lnode("div", "", Text.create("h2", `${title} · %${Math.round(r.score)}`),
      Text.create("p", `${fmtDate(r.finished_at)} · süre ${fmtTime(r.time_used_s)}${r.time_limit_s ? ` / ${fmtTime(r.time_limit_s)}` : ""}`
        + (r.blank ? ` · ${r.blank} boş` : "") + (r.kind === "mini" ? ` · YDS karşılığı ≈ ${Math.round(r.score)} puan` : ""), "muted")));
  const table = document.createElement("table");
  table.className = "st-result-types";
  table.append(lnode("tr", "", Text.create("th", "Soru türü"), Text.create("th", "Doğru"), Text.create("th", "Boş"), Text.create("th", "Başarı")));
  for (const t of r.per_type) {
    const p = Math.round(100 * t.correct / t.total);
    table.append(lnode("tr", "", Text.create("td", t.tr), Text.create("td", `${t.correct} / ${t.total}`), Text.create("td", String(t.blank)),
      Object.assign(Text.create("td", `%${p}`), { className: p < 50 ? "low" : "" })));
  }
  const actions = lnode("div", "actions",
    stButton("🎯 Yeni test", "primary", () => renderSelftestIntro()),
    deleteButton("Bu test sonucu silinsin mi?", async () => {
      await api(`/api/selftest/attempts/${r.id}`, { method: "DELETE" });
      renderSelftestIntro();
    }, "🗑 Sonucu sil"));

  // review: every question with the given and the correct answer, and the explanation
  const byId = Object.fromEntries(r.items.map((it) => [it.id, it]));
  const review = lnode("div", "st-intro", Text.create("h3", "Soruların incelemesi"));
  const nav = lnode("div", "st-nav");
  r.questions.forEach((q, i) => {
    const it = byId[q.id];
    const b = stButton(String(i + 1), it.ok ? "right" : "wrong", () => document.getElementById(`st-r-${i}`)?.scrollIntoView({ behavior: "smooth", block: "start" }));
    b.title = it.ok ? "doğru" : it.given == null ? "boş" : "yanlış";
    nav.append(b);
  });
  review.append(nav);
  r.questions.forEach((q, i) => {
    const it = byId[q.id];
    const card = lnode("div", "st-question",
      Text.create("div", `Soru ${i + 1} · ${r.types[q.type]} · ${it.ok ? "✓ doğru" : it.given == null ? "— boş" : "✗ yanlış"}`,
        `muted small ${it.ok ? "ok-text" : "err-text"}`),
      ...questionBody(q, r, { review: true }));
    card.id = `st-r-${i}`;
    const opts = lnode("div", "st-options");
    const letters = q.type === "irrelevant" ? ROMAN : LETTERS;
    optionLabels(q).forEach((label, k) => {
      const b = lnode("button", "st-option", Text.create("span", letters[k], "letter"), Text.create("span", label));
      b.type = "button";
      b.disabled = true;
      if (k === it.answer) b.classList.add("correct");
      else if (k === it.given) b.classList.add("wrong");
      opts.append(b);
    });
    const ex = lnode("div", "st-explain");
    Text.render(ex, it.explain_tr);
    card.append(opts, ex);
    review.append(card);
  });
  view.replaceChildren(head, table, actions, review);
  window.scrollTo({ top: 0 });
}

/* ----------------------------------------------------------------- events */

document.addEventListener("keydown", (e) => {
  if (!$("#page-selftest").classList.contains("active") || !selftestUi.attempt || isTyping(e.target)) return;
  const a = selftestUi.attempt;
  if (e.key === "ArrowRight" && selftestUi.current + 1 < a.questions.length) {
    selftestUi.current += 1; drawSelftestNav(); drawSelftestQuestion();
  } else if (e.key === "ArrowLeft" && selftestUi.current > 0) {
    selftestUi.current -= 1; drawSelftestNav(); drawSelftestQuestion();
  } else if (/^[1-5]$/.test(e.key)) {
    $("#st-qbox")?.querySelectorAll(".st-option")[Number(e.key) - 1]?.click();
  }
});
