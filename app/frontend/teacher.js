"use strict";

/* The Turkish-speaking teacher: a typed chat in Turkish. English example lines get 🔊 and
   clickable words; English the learner writes is checked (red/green) by the server.
   Other pages open it with a context: Teacher.open({type: "lesson" | "error" | "practice", …}). */

const teacherUi = {
  el: {
    chat: $("#teacher-chat"), input: $("#teacher-input"), form: $("#teacher-form"), send: $("#teacher-send"),
    banner: $("#teacher-context"), suggest: $("#teacher-suggest"), history: $("#teacher-history"),
    historyCount: $("#teacher-history-count"), del: $("#teacher-delete"),
  },
  sessionId: Number(store.get("teacherSessionId")) || null,
  context: null,       // context of a session that has no message yet (sent with the first one)
  pending: null,       // set by Teacher.open() before navigating here
  busy: false,
  shownSessionId: undefined,
};

const TEACHER_SUGGESTIONS = {
  none: ["Present perfect ile past simple arasındaki fark ne?", "İş e-postalarında kullanabileceğim kibar kalıplar neler?",
    "Zayıf noktalarıma göre neye çalışmalıyım?", "make ile do ne zaman kullanılır?"],
  lesson: ["Bu konuyu kısaca özetler misin?", "İş hayatından birkaç örnek daha verir misin?",
    "Türkler bu konuda en çok neyi yanlış yapıyor?", "Bu konuda bana alıştırma yaptırır mısın?"],
};

const Teacher = {
  /** Open the teacher with a new conversation about `context` (from a lesson, correction, weak point). */
  open(context) {
    teacherUi.pending = context;
    if (location.hash === "#/teacher") loadTeacherPage();
    else location.hash = "#/teacher";
  },
};

/* ------------------------------------------------------------ rendering */

const TURKISH_LETTERS = /[çğıöşüÇĞİÖŞÜ]/;

/** Text with **bold** parts. */
function richLine(tag, text, className = "") {
  const el = document.createElement(tag);
  if (className) el.className = className;
  text.split(/\*\*(.+?)\*\*/).forEach((part, i) => {
    if (part) el.append(Text.create(i % 2 ? "strong" : "span", part));
  });
  return el;
}

/** An English example line with 🔊 and clickable words:
 *  "I have worked here. (Burada çalıştım.) - optional Turkish note". */
function exampleLine(text) {
  const m = text.replace(/\*\*/g, "").match(/^(.*?)\s*\(([^()]*)\)\s*(?:[-–—:]\s*)?(.*)$/);
  const en = (m ? m[1] : text.replace(/\*\*/g, "")).replace(/^["“]|["”]$/g, "").trim();
  if (!en || TURKISH_LETTERS.test(en)) return null;  // a Turkish bullet point, not an example
  const row = document.createElement("div");
  row.className = "teacher-example";
  row.append(iconButton("🔊", "Dinle", () => teacherSpeak(en)));
  const body = document.createElement("div");
  body.append(Text.create("div", en, "en", { words: true }));
  if (m) body.append(Text.create("div", m[2], "muted small"));
  if (m?.[3]) body.append(richLine("div", m[3], "small"));
  row.append(body);
  return row;
}

/** The teacher's reply: paragraphs, example lines, the exercise (> …) and the tip. */
function renderTeacherReply(el, text) {
  el.replaceChildren();
  el._text = text;
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    const exercise = line.match(/^>\s*(.*)$/);
    if (bullet) el.append(exampleLine(bullet[1]) || richLine("div", `• ${bullet[1]}`, "teacher-bullet"));
    else if (exercise) el.append(richLine("div", `✏️ ${exercise[1]}`, "teacher-exercise"));
    else if (/^(💡\s*)?İpucu:/.test(line)) el.append(richLine("div", line.startsWith("💡") ? line : `💡 ${line}`, "teacher-tip"));
    else el.append(richLine("p", line));
  }
}

async function teacherSpeak(text) {
  stopSpeaking();
  try {
    const res = await fetch("/api/tts", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    await player.enqueue(await res.arrayBuffer());
  } catch (err) {
    teacherMessage("error", `⚠️ Ses çalınamadı: ${err.message}`);
  }
}

/* ------------------------------------------------------- reading aloud */

// The reply read aloud: Turkish by the Turkish voice (/api/tts/tr), English examples and words by the
// English voice (/api/tts, the conversation's) — the server splits it (backend/teacher_speech.py).
const teacherVoice = { readingBtn: null };

const teacherAutoRead = () => store.get("teacherVoice") !== "0";

async function teacherReadAloud(text, btn) {
  if (teacherVoice.readingBtn === btn && player.playing) {  // second click: stop
    stopSpeaking();
    return;
  }
  stopSpeaking();
  player.unlock();
  const epoch = player.epoch;
  teacherVoice.readingBtn = btn;
  btn.classList.add("on");
  try {
    const { segments } = await api("/api/teacher/speech", { method: "POST", body: { text } });
    for (const seg of segments) {
      if (player.epoch !== epoch) return;  // stopped
      const res = await fetch(seg.lang === "tr" ? "/api/tts/tr" : "/api/tts", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: seg.text }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
      if (player.epoch !== epoch) return;
      player.enqueue(await res.arrayBuffer());
    }
    await player.chain;
    while (player.playing && player.epoch === epoch) await new Promise((r) => setTimeout(r, 200));
  } catch (err) {
    teacherMessage("error", `⚠️ Sesli okunamadı: ${err.message}`);
  } finally {
    btn.classList.remove("on");
    if (teacherVoice.readingBtn === btn) teacherVoice.readingBtn = null;
  }
}

function addReadButton(bubble, getText) {
  if (bubble.querySelector(".replay")) return;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "replay";
  btn.title = "Sesli oku (Türkçe öğretmen sesi, İngilizce örnekler İngilizce sesle)";
  btn.setAttribute("aria-label", "Sesli oku");
  btn.textContent = "🔊";
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    teacherReadAloud(getText(), btn);
  });
  bubble.append(btn);
  return btn;
}

function teacherMessage(role, text) {
  const chatEl = teacherUi.el.chat;
  chatEl.querySelector(".empty-hint")?.remove();
  const el = document.createElement("div");
  el.className = `msg ${role}${role === "assistant" ? " teacher-msg" : ""}`;
  el.textEl = role === "assistant" ? document.createElement("div") : Text.create("span", text, "text");
  el.textEl.classList.add("text");
  if (role === "assistant") {
    el.textEl.dataset.textHost = "";
    if (text) renderTeacherReply(el.textEl, text);
  }
  el.append(el.textEl);
  if (role === "assistant" && text) addReadButton(el, () => el.textEl._text);
  chatEl.append(el);
  chatEl.scrollTop = chatEl.scrollHeight;
  return el;
}

function showTeacherBanner(context) {
  const b = teacherUi.el.banner;
  b.hidden = !context?.title;
  if (context?.title) b.replaceChildren(Text.create("span", context.title, "scenario-head"));
}

function showSuggestions(kind) {
  const box = teacherUi.el.suggest;
  box.replaceChildren();
  for (const q of TEACHER_SUGGESTIONS[kind] || []) {
    const chip = Text.create("button", q, "chip");
    chip.type = "button";
    chip.addEventListener("click", () => sendTeacher(q));
    box.append(chip);
  }
  box.hidden = !box.children.length;
}

function resetTeacherChat(context = null) {
  teacherUi.sessionId = null;
  teacherUi.shownSessionId = null;
  teacherUi.context = context;
  store.set("teacherSessionId", null);
  teacherUi.el.chat.replaceChildren(Text.create("div",
    context?.type === "lesson"
      ? "Bu dersle ilgili aklına takılanı Türkçe sor. 👇"
      : "Merhaba! 👋 İngilizceyle ilgili her şeyi Türkçe sorabilirsin: dilbilgisi, bir cümlenin doğru olup olmadığı, "
        + "iş e-postası kalıpları… Seviyeni ve son hatalarını biliyorum.",
    "empty-hint"));
  showTeacherBanner(context);
  showSuggestions(context ? context.type : "none");
  teacherUi.el.del.hidden = true;
}

/* -------------------------------------------------------------- talking */

async function sendTeacher(text) {
  text = (text || "").trim();
  if (teacherUi.busy) return;
  const isNew = !teacherUi.sessionId;
  if (!text && !(isNew && teacherUi.context)) return;
  teacherUi.busy = true;
  teacherUi.el.send.disabled = true;
  teacherUi.el.suggest.hidden = true;
  player.unlock();

  let userBubble = text ? teacherMessage("user", text) : null;
  const bot = teacherMessage("assistant", "");
  bot.classList.add("pending");
  let reply = "";
  try {
    const res = await fetch("/api/teacher/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: teacherUi.sessionId, text, context: isNew ? teacherUi.context : null }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    for await (const { event, data } of readSSE(res)) {
      if (event === "meta") {
        teacherUi.sessionId = teacherUi.shownSessionId = data.session_id;
        store.set("teacherSessionId", data.session_id);
        teacherUi.context = null;
        teacherUi.el.del.hidden = false;
        showTeacherBanner(data.context);
        if (data.user_text && !userBubble) {  // the question the app asked for the learner
          userBubble = teacherMessage("user", data.user_text);
          teacherUi.el.chat.append(bot);
        }
        if (userBubble) userBubble.dataset.messageId = data.user_message_id;
      } else if (event === "status") {
        showBubbleStatus(bot, data.message);
      } else if (event === "correction") {
        markBubble(userBubble, data);
      } else if (event === "delta") {
        showBubbleStatus(bot, null);
        reply += data.text;
        Text.append(bot.textEl, data.text);
      } else if (event === "done") {
        renderTeacherReply(bot.textEl, data.text || reply);
        const btn = addReadButton(bot, () => bot.textEl._text);
        if (teacherAutoRead() && btn) teacherReadAloud(bot.textEl._text, btn);
      } else if (event === "error") {
        throw new Error(data.message);
      }
      teacherUi.el.chat.scrollTop = teacherUi.el.chat.scrollHeight;
    }
  } catch (err) {
    if (!reply) bot.remove();
    teacherMessage("error", `⚠️ ${err.message}`);
    refreshStatus();
  } finally {
    bot.classList.remove("pending");
    showBubbleStatus(bot, null);
    teacherUi.busy = false;
    teacherUi.el.send.disabled = false;
    loadTeacherHistory();
  }
}

teacherUi.el.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = teacherUi.el.input.value;
  if (!text.trim() || teacherUi.busy) return;
  teacherUi.el.input.value = "";
  teacherUi.el.input.style.height = "auto";
  sendTeacher(text);
});
teacherUi.el.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    teacherUi.el.form.requestSubmit();
  }
});
teacherUi.el.input.addEventListener("input", () => {
  const i = teacherUi.el.input;
  i.style.height = "auto";
  if (i.value) i.style.height = `${i.scrollHeight}px`;
});
$("#teacher-new").addEventListener("click", () => {
  if (!teacherUi.busy) resetTeacherChat();
});

function showTeacherVoiceToggle() {
  const b = $("#teacher-voice");
  Text.render(b, teacherAutoRead() ? "🔊 Sesli cevap" : "🔇 Sesli cevap kapalı");
  b.setAttribute("aria-pressed", String(teacherAutoRead()));
}
$("#teacher-voice").addEventListener("click", () => {
  store.set("teacherVoice", teacherAutoRead() ? "0" : "1");
  if (!teacherAutoRead()) stopSpeaking();
  showTeacherVoiceToggle();
});
showTeacherVoiceToggle();

/* -------------------------------------------------------------- history */

async function showTeacherSession(id) {
  try {
    const s = await api(`/api/teacher/sessions/${id}`);
    resetTeacherChat();
    teacherUi.sessionId = teacherUi.shownSessionId = s.id;
    store.set("teacherSessionId", s.id);
    teacherUi.el.chat.replaceChildren();
    showTeacherBanner(s.context);
    teacherUi.el.suggest.hidden = true;
    teacherUi.el.del.hidden = false;
    for (const m of s.messages) {
      const el = teacherMessage(m.role, m.text);
      const c = s.corrections[m.id];
      if (m.role === "user" && c) markBubble(el, c);
    }
  } catch {
    resetTeacherChat();
  }
}

async function deleteTeacherSession(id) {
  await api(`/api/sessions/${id}`, { method: "DELETE" });
  if (teacherUi.sessionId === id) resetTeacherChat();
  loadTeacherHistory();
}

teacherUi.el.del.addEventListener("click", async () => {
  const id = teacherUi.sessionId;
  if (!id || !window.confirm("Bu konuşma silinsin mi? Geri alınamaz.")) return;
  try {
    await deleteTeacherSession(id);
  } catch (err) {
    window.alert(`Silinemedi: ${err.message}`);
  }
});

async function loadTeacherHistory() {
  const list = teacherUi.el.history;
  try {
    const items = await api("/api/teacher/sessions");
    teacherUi.el.historyCount.textContent = items.length ? `(${items.length})` : "";
    list.replaceChildren();
    if (!items.length) list.append(Text.create("p", "Henüz konuşma yok.", "muted"));
    for (const s of items) {
      const a = document.createElement("a");
      a.className = `session-item${s.id === teacherUi.sessionId ? " current" : ""}`;
      a.href = "#/teacher";
      a.append(Text.create("span", s.title),
        Text.create("span", `${formatDate(s.started_at)} · ${s.message_count} mesaj`, "muted small"),
        deleteButton("Bu konuşma silinsin mi? Geri alınamaz.", () => deleteTeacherSession(s.id)));
      a.addEventListener("click", (e) => {
        e.preventDefault();
        if (teacherUi.busy) return;
        list.closest("details").open = false;
        showTeacherSession(s.id).then(loadTeacherHistory);
      });
      list.append(a);
    }
  } catch (err) {
    list.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted"));
  }
}

/* ----------------------------------------------------------------- page */

function loadTeacherPage() {
  const pending = teacherUi.pending;
  teacherUi.pending = null;
  if (pending && !teacherUi.busy) {
    resetTeacherChat(pending);
    if (pending.type !== "lesson") sendTeacher("");  // the app asks the first question for the learner
  } else if (teacherUi.shownSessionId === undefined) {  // first visit: continue the last conversation
    if (teacherUi.sessionId) showTeacherSession(teacherUi.sessionId);
    else resetTeacherChat();
  }
  loadTeacherHistory();
  teacherUi.el.input.focus();
}
