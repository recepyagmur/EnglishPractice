"use strict";

/* Level exams (#/exam/<LEVEL>, results: #/exam/result-<id>). Four parts — grammar, listening
   (TTS, limited plays), speaking (microphone → Whisper) and writing — graded on the server
   when the exam is handed in. No feedback before the end, like a real exam. */

const examUi = {
  exam: null,       // the running attempt (from /start)
  answers: null,    // { grammar: {id: value}, listening: {id: value}, speaking: {id: {text, typed}}, writing }
  step: 0,
  plays: {},        // audio id → times played
  order: {},        // word-order question id → { built: [tile index…], pool: [tile index…] }
  result: null,     // the last graded result (shown without another request)
  el: { view: $("#exam-view") },
};

const EXAM_STEPS = [
  { id: "grammar", title: "Dilbilgisi" },
  { id: "listening", title: "Dinleme" },
  { id: "speaking", title: "Konuşma" },
  { id: "writing", title: "Yazma" },
];
const MAX_PLAYS = 3;

function examButton(label, className, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = className;
  Text.render(b, label);
  b.addEventListener("click", onClick);
  return b;
}

/* ------------------------------------------------------------- lessons page */

/** The exam card under a level's lessons (Dersler page). */
function examCard(st) {
  if (!st?.available) {
    return lnode("div", "exam-card muted", Text.create("strong", `🎓 ${lessonsUi.level} Seviye Sınavı`),
      Text.create("span", "Bu seviyenin sınavı dersleriyle birlikte eklenecek.", "small"));
  }
  const status = st.passed ? `✓ Geçtin · en iyi sonucun %${Math.round(st.best_score * 100)}`
    : st.unlocked ? "Tüm dersleri bitirdin — sınava hazırsın!"
    : `Seviyenin tüm dersleri bitince açılır (${st.lessons_done}/${st.lessons_total} ders).`;
  const go = () => { location.hash = `#/exam/${st.level}`; };
  return lnode("div", `exam-card ${st.passed ? "passed" : st.unlocked ? "ready" : ""}`,
    lnode("div", "exam-card-text", Text.create("strong", `🎓 ${st.title_tr}`),
      Text.create("span", status, "small"),
      Text.create("span", "Dilbilgisi · dinleme · konuşma · yazma — yaklaşık 20–25 dakika.", "muted small")),
    lnode("div", "actions",
      st.last && Object.assign(Text.create("a", `Son sonuç: %${Math.round(st.last.score * 100)}`, "small"),
        { href: `#/exam/result-${st.last.id}` }),
      examButton(st.unlocked || st.passed ? "Sınava gir" : "Yine de gir", st.unlocked ? "primary" : "ghost small", go)));
}

/* -------------------------------------------------------------------- route */

async function loadExam(arg) {
  const view = examUi.el.view;
  $("#page-exam").scrollTop = 0;
  if (arg.startsWith("result-")) {
    const id = Number(arg.slice(7));
    if (examUi.result?.attempt_id === id) return renderExamResult(examUi.result);
    view.replaceChildren(Text.create("p", "Yükleniyor…", "muted"));
    try {
      renderExamResult(await api(`/api/exams/attempts/${id}`));
    } catch (err) {
      view.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted"));
    }
    return;
  }
  if (examUi.exam?.level === arg && examUi.answers) return renderExamStep();  // back to a running exam
  const saved = await savedState.get(`exam:${arg}`);  // left half done (also before a restart)
  if (saved?.exam?.attempt_id && saved.answers) {
    Object.assign(examUi, { exam: saved.exam, answers: saved.answers, step: saved.step || 0,
      plays: saved.plays || {}, order: saved.order || {} });
    lastExamSave = JSON.stringify(examSnapshot());
    return renderExamStep();
  }
  renderExamIntro(arg);
}

/* The running exam is saved as the learner works (savedState "exam:<level>", kept until it is handed in,
   its questions are changed or it is given up): leaving the page or restarting the app continues it. */
let lastExamSave = "";

function examSnapshot() {
  const { exam, answers, step, plays, order } = examUi;
  return { exam, answers, step, plays, order };
}

function saveExam(now = false) {
  if (!examUi.exam || !examUi.answers) return;
  const json = JSON.stringify(examSnapshot());
  if (json === lastExamSave) return;
  lastExamSave = json;
  const key = `exam:${examUi.exam.level}`;
  savedState.set(key, JSON.parse(json), 0);
  if (now) savedState.flush(key, true);
}
setInterval(saveExam, 2000);
window.addEventListener("pagehide", () => saveExam(true));

function beginExam(exam) {
  Object.assign(examUi, { exam, answers: { grammar: {}, listening: {}, speaking: {}, writing: "" },
    step: 0, plays: {}, order: {} });
  saveExam();
  renderExamStep();
}

/** New questions for the running exam: a new attempt replaces it (its answers are dropped). */
async function changeExamQuestions(btn) {
  if (!window.confirm("Bu sınavın tüm soruları yenilensin mi? Şimdiye kadarki cevapların silinir.")) return;
  if (examRecorder.media) examRecorder.media.stop();
  btn.disabled = true;
  const old = examUi.exam;
  try {
    const exam = await api(`/api/exams/${old.level}/start`, { method: "POST" });
    await api(`/api/exams/attempts/${old.attempt_id}`, { method: "DELETE" }).catch(() => {});
    beginExam(exam);
  } catch (err) {
    window.alert(`Sorular değiştirilemedi: ${err.message}`);
    btn.disabled = false;
  }
}

async function abandonExam() {
  if (examRecorder.media) examRecorder.media.stop();
  const { level, attempt_id } = examUi.exam;
  await api(`/api/exams/attempts/${attempt_id}`, { method: "DELETE" }).catch(() => {});
  await savedState.del(`exam:${level}`);
  examUi.exam = examUi.answers = null;
  lastExamSave = "";
  renderExamIntro(level);
}

async function renderExamIntro(level) {
  const view = examUi.el.view;
  view.replaceChildren(Text.create("p", "Yükleniyor…", "muted"));
  let st;
  try {
    st = (await api("/api/exams")).find((e) => e.level === level);
  } catch (err) {
    view.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted"));
    return;
  }
  if (!st?.available) {
    view.replaceChildren(Text.create("p", "Bu seviyenin sınavı henüz yok.", "muted"));
    return;
  }
  const start = examButton("▶ Sınavı başlat", "primary", async () => {
    start.disabled = true;
    try {
      beginExam(await api(`/api/exams/${level}/start`, { method: "POST" }));
    } catch (err) {
      window.alert(err.message);
      start.disabled = false;
    }
  });
  view.replaceChildren(
    Text.create("h2", `🎓 ${st.title_tr}`),
    !st.unlocked && Text.create("p", `Bu seviyenin derslerinin ${st.lessons_done}/${st.lessons_total} kadarını bitirdin. `
      + "Sınav tüm konuları kapsar; hazır hissediyorsan yine de girebilirsin.", "exam-warn"),
    lnode("ol", "exam-parts",
      Text.create("li", "Dilbilgisi (%40): seviyenin tüm konularından sorular — seçme, boşluk doldurma, "
        + "düzeltme, dönüştürme ve kelime sıralama."),
      Text.create("li", `Dinleme (%20): duyduğunu yaz ve kısa metinleri dinleyip soruları cevapla. Her ses en fazla ${MAX_PLAYS} kez çalınır.`),
      Text.create("li", "Konuşma (%20): sorulara mikrofona konuşarak cevap ver (birkaç cümle)."),
      Text.create("li", "Yazma (%20): kısa bir mesaj yaz.")),
    Text.create("p", `Geçmek için toplamda en az %70, her bölümde en az %50 gerekir. Cevaplar sınav bitince `
      + "değerlendirilir; bölümler arasında geri dönüp cevaplarını değiştirebilirsin. Her girişte sorular "
      + "geniş bir havuzdan yeniden seçilir.", "muted"),
    Text.create("p", "🎧 Kulaklık önerilir. 🎤 Konuşma bölümü için mikrofon izni istenecek.", "muted small"),
    start,
  );
}

/* -------------------------------------------------------------------- steps */

function renderExamStep() {
  const ex = examUi.exam;
  const step = EXAM_STEPS[examUi.step];
  const change = examButton("🔀 Soruları değiştir", "ghost small", () => changeExamQuestions(change));
  change.title = "Bu sınavın tüm sorularını yenile (cevaplar silinir)";
  const head = lnode("div", "exam-head",
    Text.create("strong", ex.title_tr),
    lnode("ol", "exam-steps", EXAM_STEPS.map((s, i) => Text.create("li", `${i + 1}. ${s.title}`,
      i === examUi.step ? "current" : i < examUi.step ? "done" : ""))),
    lnode("div", "actions exam-head-actions", change,
      deleteButton("Sınav bırakılsın mı? Cevapların silinir; istediğin zaman yeniden başlayabilirsin.", abandonExam,
        "🗑 Sınavı bırak")));
  const body = { grammar: renderGrammarPart, listening: renderListeningPart, speaking: renderSpeakingPart,
    writing: renderWritingPart }[step.id]();
  const last = examUi.step === EXAM_STEPS.length - 1;
  const nav = lnode("div", "exam-nav",
    examUi.step > 0 && examButton("← Önceki bölüm", "ghost", () => { examUi.step -= 1; renderExamStep(); }),
    lnode("span", "spacer"),
    last ? examButton("✓ Sınavı bitir", "primary", submitExam)
      : examButton("Sonraki bölüm →", "primary", () => { examUi.step += 1; renderExamStep(); }));
  examUi.el.view.replaceChildren(head, Text.create("h3", `${examUi.step + 1}. ${step.title}`), body, nav);
  $("#page-exam").scrollTop = 0;
}

function choiceChips(options, selected, onPick) {
  const box = lnode("div", "exercise-options");
  options.forEach((opt, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.setAttribute("aria-pressed", String(selected === i));
    Text.render(b, opt);
    b.addEventListener("click", () => {
      for (const other of box.children) other.setAttribute("aria-pressed", "false");
      b.setAttribute("aria-pressed", "true");
      onPick(i);
    });
    box.append(b);
  });
  return box;
}

function answerInput(value, placeholder, onInput) {
  const input = document.createElement("input");
  input.className = "exam-input";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.placeholder = placeholder;
  input.value = value ?? "";
  input.addEventListener("input", () => onInput(input.value));
  return input;
}

/** The question line of a grammar item (exam page and results). */
function grammarQuestion(q) {
  if (q.type === "transform") {
    return lnode("div", "exercise-q", Text.create("strong", `${q.instruction_tr}: `), Text.create("span", q.q));
  }
  if (q.type === "order") return Text.create("div", q.q || "Kelimeleri doğru sıraya koy:", "exercise-q");
  return Text.create("div", q.type === "fix" ? `Düzelt: ${q.q}` : q.q, "exercise-q");
}

const GRAMMAR_PLACEHOLDER = { fix: "Doğru cümleyi yaz", transform: "Yeni cümleyi yaz" };

function renderGrammarPart() {
  const a = examUi.answers.grammar;
  return lnode("ol", "exercise-list exam-list", examUi.exam.grammar.map((q) => lnode("li", "exercise",
    grammarQuestion(q),
    q.type === "choice" ? choiceChips(q.options, a[q.id], (i) => { a[q.id] = i; })
      : q.type === "order" ? orderTiles(q, (v) => { a[q.id] = v; })
      : answerInput(a[q.id], GRAMMAR_PLACEHOLDER[q.type] || "Boşluğa gelen kelime(ler)", (v) => { a[q.id] = v; }))));
}

/** Word tiles: click one to add it to the sentence, click it there to take it back. The arrangement is
 *  kept in examUi.order so it survives moving between parts; the answer is the built sentence. */
function orderTiles(q, onChange) {
  if (!examUi.order[q.id]) {
    let pool = shuffled(q.words.map((_, i) => i));
    if (pool.every((x, i) => x === i) && pool.length > 1) pool = [...pool.slice(1), pool[0]];  // never pre-solved
    examUi.order[q.id] = { built: [], pool };
  }
  const state = examUi.order[q.id];
  const built = lnode("div", "order-built");
  const pool = lnode("div", "order-pool");
  const draw = () => {
    const tile = (i, from, to) => {
      const b = Text.create("button", q.words[i], "chip order-tile");
      b.type = "button";
      b.addEventListener("click", () => {
        from.splice(from.indexOf(i), 1);
        to.push(i);
        draw();
      });
      return b;
    };
    built.replaceChildren(...state.built.map((i) => tile(i, state.built, state.pool)));
    pool.replaceChildren(...state.pool.map((i) => tile(i, state.pool, state.built)));
    onChange(state.built.map((i) => q.words[i]).join(" "));
  };
  draw();
  return lnode("div", "", built, pool);
}

/** ▶ that plays `text` with TTS, at most MAX_PLAYS times (null = unlimited). */
function playButton(key, text, limit = MAX_PLAYS) {
  const used = () => examUi.plays[key] || 0;
  const label = () => (limit ? `▶ Dinle (${limit - used()} hak)` : "▶ Dinle");
  const b = examButton(label(), "ghost small", async () => {
    if (limit && used() >= limit) return;
    examUi.plays[key] = used() + 1;
    Text.render(b, label());
    b.disabled = true;
    try {
      const res = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, speed: examUi.exam.tts_speed }) });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
      stopSpeaking();
      await player.enqueue(await res.arrayBuffer());
    } catch (err) {
      window.alert(`Ses çalınamadı: ${err.message}`);
      examUi.plays[key] = used() - 1;  // a failed play does not count
      Text.render(b, label());
    } finally {
      b.disabled = Boolean(limit && used() >= limit);
    }
  });
  b.disabled = Boolean(limit && used() >= limit);
  return b;
}

function renderListeningPart() {
  const l = examUi.exam.listening;
  const a = examUi.answers.listening;
  return lnode("div", "exam-list",
    Text.create("h4", "A) Duyduğunu yaz"),
    Text.create("p", "Her cümleyi dinle ve aynen yaz.", "muted small"),
    lnode("ol", "exercise-list", l.dictation.map((d) => lnode("li", "exercise",
      playButton(d.id, d.text), answerInput(a[d.id], "Duyduğun cümle…", (v) => { a[d.id] = v; })))),
    Text.create("h4", "B) Dinle ve cevapla"),
    ...l.comprehension.map((c, n) => lnode("div", "exam-block",
      lnode("div", "q-row", Text.create("strong", `Metin ${n + 1}`), playButton(c.id, c.text)),
      lnode("ol", "exercise-list", c.questions.map((q) => lnode("li", "exercise",
        Text.create("div", q.q_tr, "exercise-q"), choiceChips(q.options, a[q.id], (i) => { a[q.id] = i; })))))));
}

/* --------------------------------------------------------------- speaking */

// done: resolves when the last recording has been turned into text (or failed).
const examRecorder = { media: null, stream: null, chunks: [], done: Promise.resolve() };

async function recordAnswer(btn, onText) {
  if (examRecorder.media) {  // second click: stop
    examRecorder.media.stop();
    return;
  }
  try {
    examRecorder.stream ||= await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } });
  } catch (err) {
    window.alert(err.name === "NotAllowedError" ? "Mikrofon izni verilmedi." : `Mikrofon açılamadı: ${err.message}`);
    return;
  }
  stopSpeaking();
  const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
  const media = new MediaRecorder(examRecorder.stream, mimeType ? { mimeType } : undefined);
  examRecorder.media = media;
  examRecorder.chunks = [];
  let finished;
  examRecorder.done = new Promise((resolve) => { finished = resolve; });
  media.ondataavailable = (e) => e.data.size && examRecorder.chunks.push(e.data);
  media.onstop = async () => {
    examRecorder.media = null;
    btn.classList.remove("recording");
    Text.render(btn, "⏳ Yazıya çevriliyor…");
    btn.disabled = true;
    try {
      const blob = new Blob(examRecorder.chunks, { type: media.mimeType });
      const res = await fetch("/api/stt", { method: "POST", headers: { "Content-Type": media.mimeType || "audio/webm" }, body: blob });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      onText(data.text);
    } catch (err) {
      window.alert(`Ses yazıya çevrilemedi: ${err.message}`);
    } finally {
      btn.disabled = false;
      Text.render(btn, "🎤 Yeniden kaydet");
      finished();
    }
  };
  media.start();
  btn.classList.add("recording");
  Text.render(btn, "⏹ Bitir");
}

function renderSpeakingPart() {
  const a = examUi.answers.speaking;
  return lnode("div", "exam-list",
    Text.create("p", "Soruyu dinle, 🎤 ile kaydı başlat, cevabını birkaç cümleyle söyle ve ⏹ ile bitir. "
      + "Beğenmezsen yeniden kaydedebilirsin. Mikrofon çalışmıyorsa cevabını yazabilirsin.", "muted small"),
    ...examUi.exam.speaking.map((s, n) => {
      const said = Text.create("div", "", "exam-said");
      const show = () => {
        const ans = a[s.id];
        Text.render(said, ans?.text ? `${ans.typed ? "✍️ Yazdığın" : "🗣 Söylediğin"}: ${ans.text}` : "Henüz cevap yok.");
        said.classList.toggle("muted", !ans?.text);
      };
      show();
      const rec = examButton(a[s.id]?.text && !a[s.id].typed ? "🎤 Yeniden kaydet" : "🎤 Kaydı başlat", "primary", () =>
        recordAnswer(rec, (text) => { a[s.id] = { text, typed: false }; show(); }));
      const type = examButton("✍️ Yazarak cevapla", "ghost small", () => {
        const box = document.createElement("textarea");
        box.className = "exam-textarea";
        box.rows = 3;
        box.value = a[s.id]?.typed ? a[s.id].text : "";
        box.addEventListener("input", () => { a[s.id] = { text: box.value, typed: true }; show(); });
        type.replaceWith(box);
        box.focus();
      });
      return lnode("div", "exam-block",
        Text.create("strong", `Soru ${n + 1}`),
        Text.create("p", s.instruction_tr),
        lnode("div", "q-row", Text.create("div", s.question_en, "exercise-q", { words: true }), playButton(`q-${s.id}`, s.question_en, null)),
        lnode("div", "actions", rec, type),
        said);
    }));
}

function renderWritingPart() {
  const w = examUi.exam.writing;
  const box = document.createElement("textarea");
  box.className = "writing-text";
  box.rows = 9;
  box.spellcheck = false;
  box.value = examUi.answers.writing;
  const count = Text.create("span", "", "muted small");
  const update = () => {
    const n = (box.value.match(/[A-Za-z']+/g) || []).length;
    Text.render(count, `${n} / ${w.min_words} kelime`);
    count.classList.toggle("ok-text", n >= w.min_words);
  };
  box.addEventListener("input", () => { examUi.answers.writing = box.value; update(); });
  update();
  return lnode("div", "exam-list",
    Text.create("p", w.instruction_tr),
    Text.create("p", w.prompt_en, "exercise-q"),
    box, count);
}

/* ------------------------------------------------------------------ submit */

function unanswered() {
  const ex = examUi.exam, a = examUi.answers;
  let n = ex.grammar.filter((q) => a.grammar[q.id] === undefined || a.grammar[q.id] === "").length;
  n += ex.listening.dictation.filter((d) => !a.listening[d.id]).length;
  n += ex.listening.comprehension.flatMap((c) => c.questions).filter((q) => a.listening[q.id] === undefined).length;
  n += ex.speaking.filter((s) => !a.speaking[s.id]?.text).length;
  return n + (a.writing.trim() ? 0 : 1);
}

async function submitExam() {
  if (examRecorder.media) {  // an answer is still being recorded: keep it
    examRecorder.media.stop();
    await examRecorder.done;
  }
  const n = unanswered();
  if (!window.confirm(n ? `${n} soru cevapsız. Yine de sınavı bitirmek istiyor musun?` : "Sınav bitirilsin mi?")) return;
  const view = examUi.el.view;
  view.replaceChildren(lnode("div", "exam-grading",
    Text.create("h2", "Sınavın değerlendiriliyor…"),
    Text.create("p", "Konuşma ve yazma cevapların yapay zekayla kontrol ediliyor; bu 20–40 saniye sürebilir.", "muted")));
  try {
    const result = await api(`/api/exams/attempts/${examUi.exam.attempt_id}/submit`, {
      method: "POST", body: examUi.answers });
    examUi.result = result;
    examUi.exam = examUi.answers = null;
    lastExamSave = "";
    savedState.del(`exam:${result.level}`);  // handed in: nothing to continue
    examRecorder.stream?.getTracks().forEach((t) => t.stop());
    examRecorder.stream = null;
    location.hash = `#/exam/result-${result.attempt_id}`;
  } catch (err) {
    view.replaceChildren(Text.create("p", `⚠️ Değerlendirilemedi: ${err.message}`, "err-text"),
      examButton("↻ Tekrar dene", "primary", submitExam));
  }
}

/* ----------------------------------------------------------------- results */

// Rounded down, like the pass rule (69.6 % is shown as %69, not %70 next to "failed").
const pct = (x) => `%${Math.floor(x * 100 + 1e-9)}`;

function renderExamResult(r) {
  const view = examUi.el.view;
  const head = lnode("div", `exam-result-head ${r.passed ? "passed" : "failed"}`,
    Text.create("div", pct(r.score), "exam-score"),
    lnode("div", "",
      Text.create("h2", r.passed ? `🎉 ${r.title_tr}: Geçtin!` : `${r.title_tr}: Bu sefer olmadı`),
      Text.create("p", r.passed ? "Tebrikler, bu seviyenin konularını oturtmuşsun."
        : `Geçmek için toplamda ${pct(r.pass_score)} ve her bölümde en az ${pct(r.section_min)} gerekiyor. `
          + "Aşağıdaki derslere dönüp tekrar dene.", "muted")));
  const sections = lnode("div", "exam-sections", r.sections.map((s) => lnode("div", `exam-section ${s.ok ? "" : "low"}`,
    lnode("div", "exam-section-head", Text.create("span", `${s.name} (ağırlık ${pct(s.weight)})`), Text.create("strong", pct(s.score))),
    Object.assign(lnode("div", "bar"), { style: `--p:${s.score.toFixed(3)}` }))));

  const actions = lnode("div", "actions exam-actions");
  if (r.passed && r.next_level && lessons_levelIndex(appSettings.level) < lessons_levelIndex(r.next_level)) {
    actions.append(examButton(`⬆ Seviyemi ${r.next_level} yap`, "primary", async (e) => {
      e.target.disabled = true;
      await api("/api/settings", { method: "PUT", body: { level: r.next_level } });
      await loadAppSettings();
      Text.render(e.target, `✓ Seviyen artık ${r.next_level}`);
    }));
  }
  actions.append(examButton("↻ Sınava tekrar gir", "ghost", () => { location.hash = `#/exam/${r.level}`; }),
    examButton("📘 Derslere dön", "ghost", () => { location.hash = "#/lessons"; }),
    deleteButton("Bu sınav sonucu silinsin mi?", async () => {
      await api(`/api/exams/attempts/${r.attempt_id}`, { method: "DELETE" });
      location.hash = "#/lessons";
    }));

  const review = r.review_lessons.length && lnode("div", "exam-review",
    Text.create("h3", "📘 Tekrar etmen önerilen dersler"),
    lnode("ul", "", r.review_lessons.map((l) => lnode("li", "",
      Object.assign(Text.create("a", l.title_tr), { href: `#/lesson/${encodeURIComponent(l.id)}` }),
      Text.create("span", ` — ${l.mistakes} yanlış`, "muted")))));

  view.replaceChildren(head, sections, actions, review || "",
    resultDetails("Dilbilgisi", r.sections[0], grammarDetails(r.grammar)),
    resultDetails("Dinleme", r.sections[1], listeningDetails(r.listening)),
    resultDetails("Konuşma", r.sections[2], speakingDetails(r.speaking)),
    resultDetails("Yazma", r.sections[3], writingDetails(r.writing)));
}

function lessons_levelIndex(level) {
  return ["A1", "A2", "B1", "B2", "C1"].indexOf(level);
}

function resultDetails(title, section, body) {
  const d = document.createElement("details");
  d.className = "exam-details";
  d.open = !section.ok;
  d.append(Text.create("summary", `${title} — ${pct(section.score)} (ayrıntılar)`), body);
  return d;
}

const mark = (ok) => Text.create("span", ok ? "✓ " : "✗ ", ok ? "ok-text" : "err-text");

function grammarDetails(items) {
  const text = (i) => (i.type === "fix" ? `Düzelt: ${i.q}` : i.type === "transform" ? `${i.instruction_tr}: ${i.q}`
    : i.type === "order" ? `${i.q || "Sırala:"} ${i.words.join(" / ")}` : i.q);
  return lnode("ol", "exam-detail-list", items.map((i) => lnode("li", i.ok ? "" : "wrong",
    lnode("div", "", mark(i.ok), Text.create("span", text(i))),
    !i.ok && lnode("div", "small", Text.create("span", "Senin cevabın: ", "muted"),
      Text.create("span", i.your || "(boş)", "wrong"), Text.create("span", " · Doğrusu: ", "muted"),
      Text.create("span", i.correct, "right", { words: true })),
    !i.ok && Text.create("div", i.explain_tr, "expl"))));
}

function listeningDetails(items) {
  return lnode("ol", "exam-detail-list", items.map((i) => (i.kind === "dictation"
    ? lnode("li", i.score >= 1 ? "" : "wrong",
      lnode("div", "", mark(i.score >= 1), Text.create("span", `Dikte (${pct(i.score)}): `), Text.create("span", i.text, "right", { words: true })),
      i.score < 1 && lnode("div", "small", Text.create("span", "Senin yazdığın: ", "muted"), Text.create("span", i.your || "(boş)")))
    : lnode("li", i.ok ? "" : "wrong",
      lnode("div", "", mark(i.ok), Text.create("span", i.q_tr)),
      !i.ok && lnode("div", "small", Text.create("span", "Senin cevabın: ", "muted"), Text.create("span", i.your || "(boş)", "wrong"),
        Text.create("span", " · Doğrusu: ", "muted"), Text.create("span", i.correct, "right")),
      !i.ok && Text.create("div", `Metin: ${i.text}`, "expl", { words: true })))));
}

function speakingDetails(items) {
  return lnode("ol", "exam-detail-list", items.map((i) => {
    const said = Text.create("div", i.text || "(cevap yok)", "exam-said");
    if (i.correction?.has_errors) Text.renderAnnotated(said, i.text, { errors: i.correction.errors });
    return lnode("li", i.score >= 0.7 ? "" : "wrong",
      Text.create("div", i.question_en, "exercise-q", { words: true }),
      said,
      i.correction?.has_errors && fixLine(i.correction.original, i.correction.corrected),
      lnode("div", "small", Text.create("strong", `${pct(i.score)} `), Text.create("span", i.message_tr, "muted")));
  }));
}

function writingDetails(w) {
  return lnode("div", "exam-detail-list",
    Text.create("p", w.message_tr, "small"),
    w.text && Text.create("div", w.text, "compare-text"),
    ...(w.corrections || []).map((c) => correctionCard(c)));
}
