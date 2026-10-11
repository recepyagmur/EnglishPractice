"use strict";

/* Correction panel: one card per learner message, a ✓ / ⚠ badge on the message. */

const corrections = {
  layout: document.querySelector(".conv-layout"),
  tab: document.querySelector("#corrections-tab"),
  count: document.querySelector("#corrections-count"),
  panel: document.querySelector("#corrections-panel"),
  list: document.querySelector("#corrections"),
  note: document.querySelector("#corrections-note"),
  categories: {},  // id → { name, tr } from /api/error-categories (the one fixed list)
};

async function loadErrorCategories() {
  try {
    const data = await api("/api/error-categories");
    corrections.categories = Object.fromEntries(data.categories.map((c) => [c.id, c]));
  } catch {}
}

function categoryLabel(id) {
  const c = corrections.categories[id];
  if (!c) return id;
  return appSettings.explanation_language === "en" ? c.name : c.tr;
}

function updateCorrectionsNote() {
  const mode = appSettings.correction_mode;
  const n = corrections.list.querySelectorAll(".corr-card").length;
  corrections.note.textContent =
    mode === "off" ? "Düzeltmeler kapalı (Ayarlar'dan açabilirsin)."
    : mode === "end" ? "Düzeltmeler oturum sonunda gösterilecek."
    : !n ? "Sadece hatalı cümlelerin burada listelenir. Hatasız cümleler mesajında ✓ ile işaretlenir." : "";
  corrections.count.hidden = !n;
  corrections.count.textContent = n;
}

/* ---------------------------------------------------- open / close the panel */

// Wide screens: the panel sits next to the chat and can be folded away (remembered).
// Narrow screens: it is a slide-over, opened from the tab or a message badge.
const narrowScreen = () => window.matchMedia("(max-width: 1000px)").matches;

function setCorrectionsOpen(open) {
  if (narrowScreen()) {
    corrections.panel.classList.toggle("open", open);
  } else {
    corrections.layout.classList.toggle("corr-collapsed", !open);
    store.set("correctionsCollapsed", open ? "0" : "1");
  }
}

corrections.layout.classList.toggle("corr-collapsed", store.get("correctionsCollapsed") === "1");
document.querySelector("#corrections-collapse").addEventListener("click", () => setCorrectionsOpen(false));
corrections.tab.addEventListener("click", () => setCorrectionsOpen(true));

function clearCorrections() {
  corrections.list.innerHTML = "";
  updateCorrectionsNote();
}

/* ---------------------------------------------------------------- diff */

const norm = (w) => w.toLowerCase().replace(/[^a-z0-9']/g, "");

/** Word-level diff: [{type: "same"|"del"|"ins", text}] (LCS; sentences are short). */
function wordDiff(a, b) {
  const x = a.split(/\s+/).filter(Boolean), y = b.split(/\s+/).filter(Boolean);
  const n = x.length, m = y.length;
  const lcs = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      lcs[i][j] = norm(x[i]) === norm(y[j]) ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  const ops = [];
  const push = (type, text) => {
    const last = ops[ops.length - 1];
    if (last && last.type === type) last.text += " " + text;
    else ops.push({ type, text });
  };
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (norm(x[i]) === norm(y[j])) { push("same", y[j]); i++; j++; }
    else if (lcs[i + 1][j] >= lcs[i][j + 1]) push("del", x[i++]);
    else push("ins", y[j++]);
  }
  while (i < n) push("del", x[i++]);
  while (j < m) push("ins", y[j++]);
  return ops;
}

function renderDiff(original, corrected) {
  const el = document.createElement("div");
  el.className = "corr-diff";
  for (const op of wordDiff(original, corrected)) {
    const tag = { same: "span", del: "del", ins: "ins" }[op.type];
    el.append(Text.create(tag, op.text), " ");
  }
  return el;
}

/* ---------------------------------------------------------------- cards */

/** ❓: the Turkish teacher explains this error using the learner's own sentence. */
function whyButton(c, e) {
  const b = Text.create("button", "❓ Neden?", "ghost small corr-why");
  b.type = "button";
  b.title = "Öğretmen bu hatayı Türkçe açıklasın";
  b.addEventListener("click", (ev) => {
    ev.stopPropagation();
    Teacher.open({ type: "error", sentence: c.original, corrected: c.corrected, wrong: e.wrong, right: e.right,
      category: e.category, explanation: e.explanation, title: `❓ ${e.wrong} → ${e.right}` });
  });
  return b;
}

/** A correction card (also used inline on the history page). */
function correctionCard(c) {
  const card = document.createElement("div");
  card.className = `corr-card ${c.not_english ? "not-english" : c.has_errors ? "has-errors" : "perfect"}`;
  card.dataset.messageId = c.message_id;

  if (c.not_english) {
    card.append(Text.create("div", "⚠ Bu İngilizce bir cümle gibi görünmüyor.", "corr-not-english"),
      Text.create("div", c.original, "corr-original"),
      Text.create("div", "Aynı şeyi İngilizce söylemeyi dene; takılırsan yapay zekaya \"How do I say …?\" diye sorabilirsin.",
        "muted small"));
  } else if (c.has_errors) {
    card.append(renderDiff(c.original, c.corrected));
    const ul = document.createElement("ul");
    ul.className = "corr-errors";
    for (const e of c.errors) {
      const li = document.createElement("li");
      const head = document.createElement("div");
      head.className = "corr-change";
      head.append(
        Text.create("span", categoryLabel(e.category), `tag cat-${e.category}`),
        Text.create("span", e.wrong, "wrong"), " → ", Text.create("span", e.right, "right"),
        whyButton(c, e),
      );
      li.append(head);
      if (e.explanation) li.append(Text.create("div", e.explanation, "expl"));
      ul.append(li);
    }
    card.append(ul);
  } else {
    card.append(Text.create("div", "Perfect! ✓", "corr-perfect"), Text.create("div", c.original, "corr-original"));
  }
  if (c.more_natural) {
    const nat = document.createElement("div");
    nat.className = "corr-natural";
    nat.append(Text.create("span", "💡 Daha doğal: ", "label"), Text.create("span", c.more_natural, "", { words: true }));
    card.append(nat);
  }
  return card;
}

function findCard(messageId) {
  return corrections.list.querySelector(`.corr-card[data-message-id="${messageId}"]`);
}

/** Newest first, so the latest feedback is always visible at the top. */
function placeCard(card) {
  const old = findCard(card.dataset.messageId);
  if (old) old.replaceWith(card);
  else corrections.list.prepend(card);
  updateCorrectionsNote();
}

function userBubble(messageId) {
  return document.querySelector(`#chat .msg.user[data-message-id="${messageId}"]`);
}

function setBadge(bubble, c) {
  if (!bubble) return;
  bubble.querySelector(".corr-badge")?.remove();
  const badge = document.createElement("button");
  const problem = c.has_errors || c.not_english;
  badge.className = `corr-badge ${problem ? "warn" : "ok"}`;
  badge.textContent = c.not_english ? "?" : c.has_errors ? `⚠ ${c.errors.length}` : "✓";
  badge.title = c.not_english ? "İngilizce değil" : c.has_errors ? "Düzeltmeyi göster" : "Hata yok";
  badge.addEventListener("click", (e) => {
    e.stopPropagation();
    showCard(c.message_id);
  });
  bubble.append(badge);
}

function showCard(messageId) {
  const card = findCard(messageId);
  if (!card) return;
  setCorrectionsOpen(true);
  card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  card.classList.remove("flash");
  void card.offsetWidth;  // restart the animation
  card.classList.add("flash");
}

/* ----------------------------------------------------- marks in the bubble */

/** The corrected sentence under the learner's message; changed words in green. */
function fixLine(original, corrected) {
  const el = document.createElement("div");
  el.className = "msg-fix";
  el.append(Text.create("span", "✓ ", "msg-fix-mark"));
  for (const op of wordDiff(original, corrected)) {
    if (op.type === "del") continue;
    el.append(Text.create(op.type === "ins" ? "strong" : "span", op.text), " ");
  }
  return el;
}

/** Mark the learner's message itself: wrong parts red, the correct sentence below it. */
function markBubble(bubble, c) {
  if (!bubble?.textEl) return;
  Text.renderAnnotated(bubble.textEl, Text.get(bubble.textEl), { words: bubble.spokenWords, errors: c.errors });
  bubble.querySelector(".msg-fix, .msg-note")?.remove();
  if (c.has_errors) bubble.textEl.after(fixLine(c.original, c.corrected));
  else if (c.not_english) bubble.textEl.after(Text.create("div", "⚠ İngilizce değil — İngilizce söylemeyi dene.", "msg-note"));
}

// A click on a red part opens its card in the panel.
document.addEventListener("click", (e) => {
  const mark = e.target.closest(".msg-err");
  const bubble = mark?.closest(".msg.user");
  if (bubble?.dataset.messageId) showCard(bubble.dataset.messageId);
});

/* --------------------------------------------------------------- events */

/** The user's message was stored (WS "meta"): show a pending card. */
function onUserMessageStored(bubble, messageId) {
  if (!bubble) return;
  bubble.dataset.messageId = messageId;
}

/** WS "correction" event (arrives a few seconds after the reply). */
function onCorrection(c) {
  // Only mistakes are listed; a correct sentence just gets ✓ on the message.
  if (c.has_errors || c.not_english) placeCard(correctionCard(c));
  else {
    findCard(c.message_id)?.remove();
    updateCorrectionsNote();
  }
  const bubble = userBubble(c.message_id);
  setBadge(bubble, c);
  markBubble(bubble, c);
}

/** Restore cards and badges for a reloaded session. */
function showSessionCorrections(byMessage) {
  clearCorrections();
  if (appSettings.correction_mode !== "every") return;
  for (const c of Object.values(byMessage || {}).sort((a, b) => a.message_id - b.message_id)) onCorrection(c);
}


