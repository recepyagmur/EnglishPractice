"use strict";

/* Writing practice: task, topic, editor, review (streamed), history. */

const writingUi = {
  types: [],
  type: store.get("writingType") || "email",
  el: {
    types: $("#writing-types"),
    topic: $("#writing-topic"),
    topicTr: $("#writing-topic-tr"),
    text: $("#writing-text"),
    count: $("#writing-count"),
    timerBtn: $("#writing-timer"),
    reviewBtn: $("#writing-review"),
    suggestBtn: $("#writing-suggest"),
    feedback: $("#writing-feedback"),
    history: $("#writing-history"),
  },
  timer: { start: 0, handle: 0 },
  recentTopics: [],
  busy: false,
};

const SCORE_LABELS = {
  grammar: "Dilbilgisi",
  vocabulary: "Kelime çeşitliliği",
  coherence: "Akıcılık / bağlantı",
  task_achievement: "Göreve uygunluk",
};

/* ---------------------------------------------------------------- page load */

async function loadWritingPage() {
  if (!writingUi.types.length) {
    try {
      writingUi.types = await api("/api/writing/types");
    } catch {
      return;
    }
    renderWritingTypes();
    const w = writingUi.el;
    w.text.value = store.get("writingDraft") || "";
    w.topic.value = store.get("writingTopic") || "";
    updateWordCount();
  }
  loadWritingHistory();
}

function currentType() {
  return writingUi.types.find((t) => t.id === writingUi.type) || writingUi.types[0];
}

function renderWritingTypes() {
  const box = writingUi.el.types;
  box.innerHTML = "";
  for (const t of writingUi.types) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.setAttribute("role", "radio");
    chip.setAttribute("aria-checked", String(t.id === writingUi.type));
    Text.render(chip, t.label_tr);
    chip.addEventListener("click", () => {
      writingUi.type = t.id;
      store.set("writingType", t.id);
      renderWritingTypes();
      updateWordCount();
      resetTimer();
    });
    box.append(chip);
  }
}

/* ------------------------------------------------------- editor, counter, timer */

const countWords = (text) => (text.match(/[A-Za-z0-9'’-]+/g) || []).length;

function updateWordCount() {
  const n = countWords(writingUi.el.text.value);
  const t = currentType();
  const target = t?.words ? ` · hedef ${t.words[0]}–${t.words[1]}` : "";
  const el = writingUi.el.count;
  Text.render(el, `${n} kelime${target}`);
  el.classList.toggle("ok", Boolean(t?.words && n >= t.words[0] && n <= t.words[1]));
  el.classList.toggle("over", Boolean(t?.words && n > t.words[1] * 1.3));
}

writingUi.el.text.addEventListener("input", () => {
  updateWordCount();
  store.set("writingDraft", writingUi.el.text.value);  // keeps the draft across reloads
});
writingUi.el.topic.addEventListener("input", () => store.set("writingTopic", writingUi.el.topic.value));

function formatClock(seconds) {
  const s = Math.abs(Math.round(seconds));
  return `${seconds < 0 ? "-" : ""}${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function resetTimer() {
  clearInterval(writingUi.timer.handle);
  writingUi.timer.handle = 0;
  const minutes = currentType()?.minutes;
  writingUi.el.timerBtn.classList.remove("running", "late");
  Text.render(writingUi.el.timerBtn, minutes ? `⏱ ${minutes} dk başlat` : "⏱ Süre başlat");
}

writingUi.el.timerBtn.addEventListener("click", () => {
  if (writingUi.timer.handle) return resetTimer();
  const minutes = currentType()?.minutes;  // IELTS counts down, the others count up
  writingUi.timer.start = Date.now();
  const btn = writingUi.el.timerBtn;
  btn.classList.add("running");
  const tick = () => {
    const elapsed = (Date.now() - writingUi.timer.start) / 1000;
    const shown = minutes ? minutes * 60 - elapsed : elapsed;
    btn.classList.toggle("late", Boolean(minutes) && shown < 0);
    Text.render(btn, `⏱ ${formatClock(shown)} (durdur)`);
  };
  tick();
  writingUi.timer.handle = setInterval(tick, 1000);
});

/* ------------------------------------------------------------- topic suggestion */

writingUi.el.suggestBtn.addEventListener("click", async () => {
  const btn = writingUi.el.suggestBtn;
  btn.disabled = true;
  Text.render(btn, "🎲 Düşünüyorum…");
  try {
    const params = new URLSearchParams({ type: writingUi.type });
    for (const t of writingUi.recentTopics.slice(-5)) params.append("avoid", t);
    const topic = await api(`/api/writing/prompt?${params}`);
    writingUi.el.topic.value = topic.prompt;
    Text.render(writingUi.el.topicTr, topic.prompt_tr ? `🇹🇷 ${topic.prompt_tr}` : "");
    writingUi.recentTopics.push(topic.prompt);
    store.set("writingTopic", topic.prompt);
  } catch (err) {
    Text.render(writingUi.el.topicTr, `⚠️ ${err.message}`);
  } finally {
    btn.disabled = false;
    Text.render(btn, "🎲 Konu öner");
  }
});

/* ------------------------------------------------------------------- review */

/** Parse a fetch() response body as Server-Sent Events. */
async function* readSSE(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = "message", data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      yield { event, data: data ? JSON.parse(data) : null };
    }
  }
}

writingUi.el.reviewBtn.addEventListener("click", reviewWriting);

async function reviewWriting() {
  const text = writingUi.el.text.value.trim();
  if (writingUi.busy || !text) return;
  if (countWords(text) < 3) {
    showWritingError("Değerlendirmek için biraz daha yaz.");
    return;
  }
  writingUi.busy = true;
  writingUi.el.reviewBtn.disabled = true;
  if (writingUi.timer.handle) clearInterval(writingUi.timer.handle);

  const view = createReviewView(text);
  const state = { sentences: [], total: 0 };
  try {
    const res = await fetch("/api/writing/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_type: writingUi.type, prompt: writingUi.el.topic.value.trim(), text }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    for await (const { event, data } of readSSE(res)) {
      if (event === "saved") {
        state.total = data.sentences;
        view.setProgress(0, state.total);
      } else if (event === "sentence") {
        state.sentences.push(data);
        view.setProgress(state.sentences.length, state.total);
        view.annotate(state.sentences);
      } else if (event === "assessment") {
        view.setProgress(null);
        view.showAssessment(data);
      } else if (event === "improved_delta") {
        view.appendImproved(data.text);
      } else if (event === "done") {
        view.finish(data.review);
        store.set("writingDraft", null);
        loadWritingHistory();
      } else if (event === "error") {
        throw new Error(data.message);
      }
    }
  } catch (err) {
    view.setProgress(null);
    showWritingError(err.message);
  } finally {
    writingUi.busy = false;
    writingUi.el.reviewBtn.disabled = false;
  }
}

function showWritingError(message) {
  const fb = writingUi.el.feedback;
  fb.hidden = false;
  fb.prepend(Text.create("div", `⚠️ ${message}`, "msg error"));
}

/* ------------------------------------------------------------- review view */

/** Builds the feedback area; returns updaters used while the review streams in. */
function createReviewView(text) {
  const fb = writingUi.el.feedback;
  fb.hidden = false;
  fb.innerHTML = "";

  const progress = document.createElement("div");
  progress.className = "writing-progress";
  const bar = document.createElement("div");
  bar.className = "bar";
  const label = Text.create("span", "Hazırlanıyor…", "muted small");
  progress.append(label, bar);

  const annotated = document.createElement("div");
  annotated.className = "annotated";
  const errorList = document.createElement("div");
  errorList.className = "writing-errors";
  const assessment = document.createElement("div");
  assessment.className = "writing-assessment";
  const compare = document.createElement("div");
  compare.className = "compare";
  const improved = Text.create("div", "", "compare-text pending");
  const phrases = document.createElement("div");

  fb.append(
    progress,
    Text.create("h4", "📝 Metnin"), annotated, errorList,
    assessment, compare, phrases,
  );
  renderAnnotated(annotated, text, []);
  fb.scrollIntoView({ behavior: "smooth", block: "start" });

  return {
    setProgress(done, total) {
      if (done === null) {
        progress.remove();
        return;
      }
      Text.render(label, total ? `Cümleler kontrol ediliyor: ${done}/${total}` : "Hazırlanıyor…");
      bar.style.setProperty("--p", total ? done / total : 0);
    },
    annotate(sentences) {
      const errs = sentences.flatMap((s) => s.errors);
      renderAnnotated(annotated, text, errs);
      renderErrorList(errorList, errs, annotated);
    },
    showAssessment(a) {
      renderAssessment(assessment, a);
      compare.innerHTML = "";
      const left = document.createElement("div");
      left.append(Text.create("h4", "Senin metnin"), Text.create("div", text, "compare-text"));
      const right = document.createElement("div");
      const head = document.createElement("h4");
      const listen = document.createElement("button");
      listen.className = "replay inline";
      listen.title = "Dinle";
      listen.textContent = "🔊";
      listen.addEventListener("click", () => speakText(Text.get(improved)));
      head.append(Text.create("span", "✨ Daha doğal versiyon "), listen);
      right.append(head, improved);
      compare.append(left, right);
      renderPhrases(phrases, a.suggested_phrases);
    },
    appendImproved(chunk) {
      Text.append(improved, chunk);
    },
    finish(review) {
      Text.render(improved, review.improved_version, { words: true });
      improved.classList.remove("pending");
    },
  };
}

/** Show a saved review (history). */
function showSavedReview(w) {
  writingUi.el.text.value = w.text;
  writingUi.el.topic.value = w.prompt || "";
  updateWordCount();
  const view = createReviewView(w.text);
  view.setProgress(null);
  view.annotate(w.review.sentences);
  view.showAssessment(w.review.assessment);
  view.finish(w.review);
}

/** The learner's text with errors underlined; click an error for the fix. */
function renderAnnotated(container, text, errs) {
  container.innerHTML = "";
  const marks = errs
    .filter((e) => e.start !== null && e.start !== undefined)
    .sort((a, b) => a.start - b.start);
  let pos = 0;
  marks.forEach((e, i) => {
    if (e.start < pos) return;  // overlapping: keep the first
    if (e.start > pos) container.append(Text.create("span", text.slice(pos, e.start)));
    const mark = Text.create("mark", text.slice(e.start, e.end), `err cat-${e.category}`);
    mark.tabIndex = 0;
    mark.dataset.errorIndex = i;
    mark.title = `${e.wrong} → ${e.right}`;
    const tip = document.createElement("span");
    tip.className = "err-tip";
    tip.append(
      Text.create("span", categoryLabel(e.category), "tag"),
      Text.create("span", e.right, "right"),
      Text.create("span", e.explanation || "", "expl"),
    );
    mark.append(tip);
    container.append(mark);
    pos = e.end;
  });
  if (pos < text.length) container.append(Text.create("span", text.slice(pos)));
}

function renderErrorList(container, errs, annotated) {
  container.innerHTML = "";
  if (!errs.length) return;
  container.append(Text.create("h4", `Hatalar (${errs.length})`));
  const ul = document.createElement("ul");
  ul.className = "corr-errors";
  for (const e of errs) {
    const li = document.createElement("li");
    const head = document.createElement("div");
    head.className = "corr-change";
    head.append(
      Text.create("span", categoryLabel(e.category), `tag cat-${e.category}`),
      Text.create("span", e.wrong, "wrong"), " → ", Text.create("span", e.right, "right"),
    );
    li.append(head);
    if (e.explanation) li.append(Text.create("div", e.explanation, "expl"));
    li.addEventListener("click", () => {
      const mark = [...annotated.querySelectorAll("mark.err")].find((m) => m.title === `${e.wrong} → ${e.right}`);
      if (!mark) return;
      mark.scrollIntoView({ behavior: "smooth", block: "center" });
      mark.focus();
    });
    ul.append(li);
  }
  container.append(ul);
}

function renderAssessment(container, a) {
  container.innerHTML = "";
  const head = document.createElement("div");
  head.className = "assessment-head";
  if (a.estimated_cefr) {
    const badge = Text.create("div", a.estimated_cefr, "cefr-badge");
    badge.title = "Tahmini CEFR seviyesi";
    head.append(badge);
  }
  head.append(Text.create("div", a.summary, "summary"));
  container.append(Text.create("h4", "📊 Değerlendirme"), head);

  const scores = document.createElement("div");
  scores.className = "scores";
  for (const [key, label] of Object.entries(SCORE_LABELS)) {
    const value = a.scores?.[key];
    if (!value) continue;
    const row = document.createElement("div");
    row.className = "score";
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.style.setProperty("--p", value / 10);
    row.append(Text.create("span", label), bar, Text.create("strong", `${value}/10`));
    scores.append(row);
  }
  container.append(scores);
  container.append(Text.create("div", `${a.words} kelime · ${a.error_count} hata`, "muted small"));
}

function renderPhrases(container, phrases) {
  container.innerHTML = "";
  if (!phrases?.length) return;
  const box = document.createElement("div");
  box.className = "report-phrases";
  for (const p of phrases) {
    const row = document.createElement("div");
    row.className = "report-phrase";
    const listen = document.createElement("button");
    listen.className = "replay inline";
    listen.title = "Dinle";
    listen.textContent = "🔊";
    listen.addEventListener("click", () => speakText(p.example || p.phrase));
    const text = document.createElement("div");
    text.append(Text.create("strong", p.phrase, "", { words: true }),
      Text.create("div", p.example, "example", { words: true }));
    row.append(listen, text, addPhraseButton(p.phrase, "", p.example, container));
    box.append(row);
  }
  container.append(Text.create("h4", "📚 Kullanabileceğin ifadeler"), box);
}

/* ------------------------------------------------------------------ history */

async function loadWritingHistory() {
  const list = writingUi.el.history;
  try {
    const items = await api("/api/writings");
    list.innerHTML = "";
    if (!items.length) {
      list.append(Text.create("p", "Henüz değerlendirilmiş yazı yok.", "muted"));
      return;
    }
    const labels = Object.fromEntries(writingUi.types.map((t) => [t.id, t.label_tr]));
    for (const w of items) {
      const a = document.createElement("a");
      a.className = "session-item";
      a.href = "#/writing";
      const left = document.createElement("span");
      left.append(Text.create("strong", labels[w.task_type] || w.task_type), " ",
        Text.create("span", `· ${w.preview}…`, "muted"));
      const right = Text.create("span",
        `${formatDate(w.created_at)} · ${w.words} kelime · ${w.error_count} hata${w.estimated_cefr ? ` · ${w.estimated_cefr}` : ""}`,
        "muted");
      a.append(left, right, deleteButton("Bu yazı (değerlendirmesi ve hataları) silinsin mi? Geri alınamaz.", async () => {
        await api(`/api/writings/${w.id}`, { method: "DELETE" });
        loadWritingHistory();
      }));
      a.addEventListener("click", async (e) => {
        e.preventDefault();
        try {
          showSavedReview(await api(`/api/writings/${w.id}`));
        } catch (err) {
          showWritingError(err.message);
        }
      });
      list.append(a);
    }
  } catch (err) {
    list.innerHTML = "";
    list.append(Text.create("p", `⚠️ ${err.message}`, "muted"));
  }
}
