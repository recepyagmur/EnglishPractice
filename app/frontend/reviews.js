"use strict";

/* Reviewing finished lessons (backend/reviews.py): the list on the lessons page, the number in the menu, the
   summary card (also "📌 Özet" on the lesson page) and the review itself: the card, then a short quiz of the
   lesson's own exercises; the result sets the next review date. */

const reviewUi = { shownId: null, el: { list: $("#lessons-reviews"), view: $("#review-view") } };

/** A number next to a menu entry (hidden when 0). */
function setNavBadge(page, count, title) {
  const link = document.querySelector(`#nav a[data-page="${page}"]`);
  if (!link) return;
  let badge = link.querySelector(".nav-badge");
  if (!badge) {
    badge = document.createElement("span");
    badge.className = "nav-badge";
    link.append(badge);
  }
  badge.hidden = !count;
  badge.textContent = count;
  badge.title = title;
}

async function refreshReviewBadge() {
  try {
    const r = await api("/api/reviews/count");
    setNavBadge("lessons", r.due, `Bugün tekrar zamanı gelen ${r.due} ders`);
  } catch { /* the badge is a hint only */ }
}

const reviewDay = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString("tr-TR", { day: "numeric", month: "long" });

function daysAgo(iso) {
  if (!iso) return "";
  const days = Math.round((Date.now() - new Date(iso).getTime()) / 86400000);
  return days < 1 ? "bugün" : `${days} gün önce`;
}

/* ------------------------------------------------------ list (lessons page) */

function renderReviewList(r) {
  const box = reviewUi.el.list;
  box.replaceChildren();
  if (!r || (!r.due.length && !r.soon.length)) return;
  const row = (item) => {
    const meta = item.reason
      || (item.review_count ? `${item.review_count + 1}. tekrar · son: ${daysAgo(item.last_reviewed_at)}` : "ilk tekrar");
    const go = Text.create("a", "Tekrar et", "button-link small");
    go.href = `#/review/${encodeURIComponent(item.lesson_id)}`;
    return lnode("div", "review-row",
      Text.create("span", item.level, "level-badge"),
      Text.create("span", item.title_tr, "review-title"),
      Text.create("span", meta, `small ${item.pulled ? "warn-text" : "muted"}`), go);
  };
  box.append(Text.create("h3", r.due.length ? `🗓 Bugün tekrar zamanı gelenler (${r.due.length})` : "🗓 Tekrar takvimi"));
  if (r.due.length) box.append(lnode("div", "review-list", r.due.map(row)));
  else if (r.soon.length) {
    const next = r.soon[0];
    box.append(Text.create("p", `Bugün tekrar yok. Sıradaki: ${next.title_tr} · ${reviewDay(next.due_date)}`, "muted small"));
  }
  if (r.weak.length) {
    box.append(Text.create("p", `Son 14 günde sık hata yaptığın konular: ${r.weak.map((w) => `${w.label} (${w.count})`).join(", ")}. `
      + "Bu konuların bitirdiğin dersleri tekrara öne alınır; henüz açmadığın ilgili dersler 🎯 Sana önerilen'de.", "muted small"));
  }
}

/* --------------------------------------------------------- summary card */

function reviewTable(table) {
  const t = document.createElement("table");
  t.className = "lesson-table";
  const head = document.createElement("tr");
  for (const h of table.head) head.append(Text.create("th", h));
  t.append(head);
  for (const row of table.rows) {
    const tr = document.createElement("tr");
    for (const cell of row) tr.append(Text.create("td", cell));
    t.append(tr);
  }
  return lnode("div", "table-scroll", t);
}

function renderReviewCard(card) {
  return lnode("div", "review-card",
    Text.create("div", "Ana kurallar", "review-label"),
    lnode("ul", "review-rules", card.rules_tr.map((r) => Text.create("li", r))),
    card.table && Text.create("div", "Kalıp", "review-label"),
    card.table && reviewTable(card.table),
    Text.create("div", "Dikkat: sık yapılan hatalar", "review-label"),
    lnode("ul", "lesson-mistakes", card.mistakes.map((m) => lnode("li", "",
      lnode("div", "corr-change", Text.create("span", m.wrong, "wrong"), " → ", Text.create("span", m.right, "right", { words: true })),
      Text.create("div", m.note_tr, "expl")))),
    lnode("div", "review-remember", "💡 Aklında kalsın: ", Text.create("span", card.remember_tr)));
}

/** "📌 Özet" on the lesson page (closed until opened). */
function lessonSummary(l) {
  if (!l.review_card) return null;
  const d = document.createElement("details");
  d.className = "lesson-summary";
  d.append(Text.create("summary", "📌 Özet: bu dersin ana kuralları (tekrar için)"), renderReviewCard(l.review_card));
  return d;
}

/* --------------------------------------------------------------- review */

async function loadReview(id) {
  const view = reviewUi.el.view;
  if (reviewUi.shownId === id && view.querySelector(".review-card")) return;  // back to the same review: as it was
  reviewUi.shownId = null;
  view.replaceChildren(Text.create("p", "Yükleniyor…", "muted"));
  let r;
  try {
    r = await api(`/api/reviews/${encodeURIComponent(id)}`);
  } catch (err) {
    view.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted"));
    return;
  }
  reviewUi.shownId = id;
  const lessonLink = Object.assign(Text.create("a", "📘 Dersi aç", "ghost small button-link"),
    { href: `#/lesson/${encodeURIComponent(id)}` });
  const quiz = lnode("section", "lesson-section exercises");
  const start = Text.create("button", `✏️ Mini teste başla (${r.items.length} soru)`, "primary");
  start.type = "button";
  start.addEventListener("click", () => {
    start.remove();
    runReviewQuiz(r, quiz);
  });
  const step = r.state?.review_count ? `${r.state.review_count + 1}. tekrar` : "ilk tekrar";
  view.replaceChildren(
    lnode("div", "lesson-head", Text.create("span", `${r.level} · ${LEVEL_NAMES[r.level] || ""}`, "level-badge"),
      Text.create("span", step, "tag")),
    Text.create("h2", `📌 ${r.title_tr}`),
    Text.create("p", "Önce kurallara bir göz at, sonra kısa testle ne kadarını hatırladığına bak. Sonuca göre bir "
      + "sonraki tekrarın tarihi belirlenir: iyi hatırladıkça aralık uzar.", "muted small"),
    r.card ? renderReviewCard(r.card) : Text.create("p", "Bu dersin özeti henüz hazır değil; dersi açıp göz atabilirsin.", "muted"),
    lnode("div", "review-actions", start, lessonLink),
    quiz);
}

function runReviewQuiz(r, box) {
  const list = lnode("ol", "exercise-list");
  const result = lnode("div", "exercise-result");
  const wrong = [];
  let answered = 0;
  box.replaceChildren(Text.create("h3", "✏️ Mini test"), list, result);
  r.exercises.forEach((ex, k) => {
    list.append(renderExercise(ex, (ok) => {
      if (!ok) wrong.push(r.items[k]);
      answered += 1;
      if (answered === r.items.length) finishReview(r, wrong, result);
    }));
  });
  list.scrollIntoView({ behavior: "smooth", block: "start" });
}

const REVIEW_ADVICE = {
  good: "🎉 İyi hatırlıyorsun; bir sonraki tekrar daha ileride.",
  again: "Fena değil. Yanlışlarına bak; bu aralıkla bir kez daha tekrar edeceğiz.",
  relearn: "Bu konu biraz unutulmuş. Dersi baştan gözden geçirmeni öneririm; tekrar yarın yine gelecek.",
};

async function finishReview(r, wrong, box) {
  let s;
  try {
    s = await api(`/api/reviews/${encodeURIComponent(r.lesson_id)}`, { method: "POST", body: { items: r.items, wrong } });
  } catch (err) {
    box.replaceChildren(Text.create("span", `⚠️ Sonuç kaydedilemedi (${err.message}). Biraz sonra tekrar dene.`, "muted"));
    return;
  }
  refreshReviewBadge();
  const back = Object.assign(Text.create("a", "← Derslere dön", "ghost small button-link"), { href: "#/lessons" });
  const lesson = Object.assign(Text.create("a", "📘 Dersi aç", `${s.advice === "relearn" ? "primary" : "ghost"} small button-link`),
    { href: `#/lesson/${encodeURIComponent(r.lesson_id)}` });
  box.replaceChildren(
    Text.create("strong", `Sonuç: ${s.correct} / ${s.total} doğru · Sonraki tekrar: ${s.days} gün sonra (${reviewDay(s.due_date)})`),
    Text.create("p", REVIEW_ADVICE[s.advice], s.advice === "good" ? "ok-text" : "muted"),
    lnode("div", "review-actions", lesson, back));
}
