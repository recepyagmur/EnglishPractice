"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// How the learner starts the app here: Baslat.bat (Windows) or baslat.sh (Linux). /api/health tells it; this
// guess only shows until then (or when the server cannot be reached at all).
let startScript = /Linux/.test(navigator.userAgent) && !/Android/.test(navigator.userAgent) ? "baslat.sh" : "Baslat.bat";

const store = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) {
    try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch {}
  },
};

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body && typeof options.body !== "string" ? JSON.stringify(options.body) : options.body,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}

/** Work in progress kept on the server until the learner deletes it (backend/ui_state.py): lesson pages
 *  ("lesson:<id>") and a running exam ("exam:<level>"). Writes are batched; pending ones are sent when
 *  the page is closed or reloaded. */
const savedState = {
  pending: {},
  timers: {},
  async get(key) {
    if (key in savedState.pending) return savedState.pending[key];
    try {
      return (await api(`/api/state/${encodeURIComponent(key)}`)).value;
    } catch {
      return null;
    }
  },
  set(key, value, delay = 400) {
    savedState.pending[key] = value;
    clearTimeout(savedState.timers[key]);
    savedState.timers[key] = setTimeout(() => savedState.flush(key), delay);
  },
  flush(key, keepalive = false) {
    if (!(key in savedState.pending)) return;
    const value = savedState.pending[key];
    delete savedState.pending[key];
    clearTimeout(savedState.timers[key]);
    fetch(`/api/state/${encodeURIComponent(key)}`, { method: "PUT", keepalive,
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value }) }).catch(() => {});
  },
  del(key) {
    delete savedState.pending[key];
    clearTimeout(savedState.timers[key]);
    return api(`/api/state/${encodeURIComponent(key)}`, { method: "DELETE" }).catch(() => {});
  },
};
window.addEventListener("pagehide", () => Object.keys(savedState.pending).forEach((k) => savedState.flush(k, true)));

const MODE_NAMES = { conversation: "Konuşma", scenario: "Senaryo" };

/** A 🗑 button: asks first, then runs `onDelete` (works inside links and clickable rows). */
function deleteButton(question, onDelete, label = "🗑") {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "del-btn";
  b.title = "Sil";
  b.setAttribute("aria-label", "Sil");
  Text.render(b, label);
  b.addEventListener("click", async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm(question)) return;
    b.disabled = true;
    try {
      await onDelete();
    } catch (err) {
      window.alert(`Silinemedi: ${err.message}`);
      b.disabled = false;
    }
  });
  return b;
}

async function deleteSession(id) {
  await api(`/api/sessions/${id}`, { method: "DELETE" });
  if (chat.sessionId === Number(id) || chat.endedSessionId === Number(id)) {  // it is on the conversation page
    chat.sessionId = null;
    resetChat();
  }
}

function formatDate(iso) {
  return new Date(iso).toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" });
}

/* ------------------------------------------------------------------ theme */

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
}
applyTheme(store.get("theme") || "dark");
$("#theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(next);
  store.set("theme", next);
  api("/api/settings", { method: "PUT", body: { theme: next } }).catch(() => {});
});

/* --------------------------------------------------------------- settings */

// Last known settings; refreshed at boot and whenever the settings form is saved.
let appSettings = { talk_button_mode: "hold" };

async function loadAppSettings() {
  try {
    appSettings = await api("/api/settings");
    applyTheme(appSettings.theme);
    store.set("theme", appSettings.theme);
    updateTalkHint();
    updateCorrectionsNote();
  } catch {}
}

/* ----------------------------------------------------------------- router */

// The sidebar. A new section (e.g. lessons) = one entry here + a <section id="page-…">.
const NAV = [
  { page: "conversation", icon: "💬", label: "Konuşma" },
  { page: "lessons", icon: "📘", label: "Dersler" },
  { page: "teacher", icon: "🧑‍🏫", label: "Öğretmen" },
  { page: "scenarios", icon: "🎭", label: "Senaryolar" },
  { page: "writing", icon: "✍️", label: "Yazma" },
  { page: "words", icon: "🧠", label: "Kelime Çalış" },
  { page: "patterns", icon: "🧩", label: "Kalıplar" },
  { page: "vocab", icon: "📒", label: "Kelime Defteri" },
  { page: "selftest", icon: "🎯", label: "Kendini Test Et" },
  { page: "progress", icon: "📈", label: "İlerleme" },
  { page: "settings", icon: "⚙️", label: "Ayarlar" },
];
// Pages reachable only by link, shown under a sidebar entry.
const SUBPAGES = { session: "progress", lesson: "lessons", exam: "lessons" };

function renderNav() {
  const nav = $("#nav");
  nav.innerHTML = "";
  for (const item of NAV) {
    const a = document.createElement("a");
    a.href = `#/${item.page}`;
    a.dataset.page = item.page;
    a.append(Text.create("span", item.icon, "nav-icon"), Text.create("span", item.label, "nav-label"));
    nav.append(a);
  }
}

const pageLoaders = {
  lessons: () => loadLessonsPage(),
  teacher: () => loadTeacherPage(),
  words: () => loadWordsPage(),
  patterns: () => loadPatternsPage(),
  scenarios: () => loadScenarios(),
  writing: () => loadWritingPage(),
  vocab: () => loadVocabPage(),
  selftest: () => loadSelftestPage(),
  progress: () => loadProgressPage(),
  settings: () => { loadSettings(); loadModelsSection(); loadUpdateSection(); loadSyncSection(); loadResetSection(); },
};

// Where each page was scrolled to (by address): coming back to a page, also after a restart, returns to
// the same place.
const scrollMemory = (() => { try { return JSON.parse(store.get("scrollMemory")) || {}; } catch { return {}; } })();
let currentAddress = location.hash;

function rememberScroll() {
  const page = $(".page.active");
  if (!page) return;
  delete scrollMemory[currentAddress];
  scrollMemory[currentAddress] = page.scrollTop;
  const keys = Object.keys(scrollMemory);  // the most recent 100 addresses
  for (const k of keys.slice(0, Math.max(0, keys.length - 100))) delete scrollMemory[k];
  store.set("scrollMemory", JSON.stringify(scrollMemory));
}
window.addEventListener("pagehide", rememberScroll);

let routed = false;  // the first route (page load) has nothing drawn to remember yet

async function route() {
  if (routed) rememberScroll();
  routed = true;
  currentAddress = location.hash;
  const address = currentAddress;
  const [, page = "conversation", arg] = location.hash.split("/");
  const target = $(`#page-${page}`) ? page : "conversation";
  $$(".page").forEach((p) => p.classList.toggle("active", p.id === `page-${target}`));
  const navPage = SUBPAGES[target] || target;
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.page === navPage));
  const el = $(`#page-${target}`);
  const restoreScroll = () => {
    if (address === currentAddress && scrollMemory[address] != null) el.scrollTop = scrollMemory[address];
  };
  restoreScroll();
  try {
    if (target === "session") await loadSessionDetail(arg);
    if (target === "lesson") await loadLessonDetail(decodeURIComponent(arg || ""));
    if (target === "exam") await loadExam(decodeURIComponent(arg || ""));
    await pageLoaders[target]?.();
  } finally {
    restoreScroll();  // after the page has been drawn again
  }
}
window.addEventListener("hashchange", route);

/* ----------------------------------------------------------------- status */

async function refreshStatus() {
  let health;
  try {
    health = await api("/api/health");
  } catch {
    health = null;
  }
  const problems = [];
  for (const pill of $$("#status .pill")) {
    const name = pill.dataset.service;
    const label = { ollama: "Ollama", whisper: "Whisper", tts: "TTS" }[name];
    const s = health?.[name];
    pill.classList.remove("ok", "err");
    if (!health) {
      pill.textContent = `${label} ?`;
      pill.title = "Sunucuya ulaşılamıyor.";
      continue;
    }
    pill.title = s.message;
    if (s.ok === true) { pill.textContent = `${label} ✓`; pill.classList.add("ok"); }
    else if (s.ok === false) { pill.textContent = `${label} ✗`; pill.classList.add("err"); problems.push(s.message); }
    else if (s.state === "loading") { pill.textContent = `${label} ⏳`; }
    else { pill.textContent = `${label} –`; }
  }
  if (health?.start_script) startScript = health.start_script;
  if (health?.restart_needed) {
    problems.unshift(`⟳ Uygulama güncellendi: yeni özelliklerin çalışması için uygulamayı kapatıp ${startScript} ile yeniden açın.`);
  }
  if (health?.sync_notice) problems.unshift(`${health.sync_notice} (Ayarlar → İki bilgisayar)`);
  $("#status-msg").textContent = health ? problems.join(" · ")
    : updating ? "" : `Sunucuya ulaşılamıyor — ${startScript} çalışıyor mu?`;
  renderUpdateBanner(health ? health.update : updating && { state: "restarting" });

  const whisper = health?.whisper;
  talkBtn.disabled = whisper?.ok !== true;
  talkBtn.title = whisper?.message || "";
  if (talkBtn.disabled) talkHint.textContent = whisper?.state === "loading" ? whisper.message : "Ses girişi kullanılamıyor";
  else updateTalkHint();

  // Poll faster while a model is still loading.
  const loading = whisper?.state === "loading" || health?.tts?.state === "loading";
  clearTimeout(refreshStatus.timer);
  refreshStatus.timer = setTimeout(refreshStatus, loading ? 2000 : 15000);
}

/* ------------------------------------------------------------------- chat */

const chat = {
  sessionId: Number(store.get("sessionId")) || null,
  turn: null,      // { id, userBubble, botBubble } of the reply being streamed
  speaking: null,  // { id, bubble, done, t0, first } of the reply being spoken
};
const chatEl = $("#chat");
const input = $("#chat-input");
const stopBtn = $("#stop-btn");

function addMessage(container, role, text) {
  container.querySelector(".empty-hint")?.remove();
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textEl = Text.create("span", text, "text", { words: role === "assistant" });
  el.appendChild(el.textEl);
  if (role === "user" || role === "assistant") {
    // The whole message in Turkish, shown inside the bubble (under the correction, if any).
    el.append(translateButton(() => (el.classList.contains("pending") ? "" : Text.get(el.textEl)),
      () => el.querySelector(".msg-fix, .msg-note") || el.textEl, "msg-tool translate"));
  }
  container.appendChild(el);
  return el;
}

/**
 * 🌐: translates getText() into Turkish and shows it after anchor(); a second click hides it.
 * The translation is kept until the text changes.
 */
function translateButton(getText, anchor, className = "icon-btn") {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = className;
  btn.title = "Türkçeye çevir";
  btn.setAttribute("aria-label", "Türkçeye çevir");
  Text.render(btn, "🌐");
  let cache = { text: null, translation: null };
  btn.addEventListener("click", async (e) => {
    e.stopPropagation();
    const host = anchor();
    const shown = host.parentElement.querySelector(":scope > .translation");
    if (shown) {
      shown.remove();
      btn.classList.remove("on");
      return;
    }
    const text = getText().trim();
    if (!text) return;
    const box = Text.create("div", "🌐 Çevriliyor…", "translation muted");
    host.after(box);
    btn.classList.add("on");
    if (cache.text !== text) {
      try {
        cache = { text, translation: (await api("/api/translate", { method: "POST", body: { text } })).translation };
      } catch (err) {
        Text.render(box, `⚠️ Çevrilemedi: ${err.message}`);
        return;
      }
    }
    box.className = "translation";
    box.title = "Yapay zeka çevirisi — küçük hatalar olabilir";
    Text.render(box, `🇹🇷 ${cache.translation}`);
  });
  return btn;
}

function addReplayButton(bubble) {
  if (bubble.querySelector(".replay")) return;
  const btn = document.createElement("button");
  btn.className = "replay";
  btn.title = "Tekrar dinle";
  btn.setAttribute("aria-label", "Tekrar dinle");
  btn.textContent = "🔊";
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    replay(bubble);
  });
  bubble.appendChild(btn);
}

/** Show stored messages; with `inlineCorrections`, put each correction under its message. */
function showMessages(container, messages, inlineCorrections = null) {
  for (const m of messages) {
    const el = addMessage(container, m.role, m.text);
    el.dataset.messageId = m.id;
    if (m.words) {
      el.spokenWords = m.words;
      Text.renderSpoken(el.textEl, m.text, m.words);  // pronunciation hints
    }
    if (m.role === "assistant") addReplayButton(el);
    const c = inlineCorrections?.[m.id];
    if (c) {
      markBubble(el, c);
      container.append(correctionCard(c));
    }
  }
}

function scrollChat() {
  chatEl.scrollTop = chatEl.scrollHeight;
}

function resetChat() {
  stopSpeaking();
  if (chat.turn) finishTurn(null, true);
  if (chat.sessionId) api(`/api/sessions/${chat.sessionId}/end`, { method: "POST" }).catch(() => {});
  chat.sessionId = null;
  chat.endedSessionId = null;
  store.set("sessionId", null);
  chatEl.innerHTML = `<div class="empty-hint">Yeni sohbet. 🎤 butonuna basılı tutup konuş ya da yaz!</div>`;
  clearCorrections();
  hideBanner();
  updateFinishButton();
  resetSessionModel();  // a model picked above the chat belongs to that session only
}

async function restoreChat() {
  if (!chat.sessionId) return;
  try {
    const session = await api(`/api/sessions/${chat.sessionId}`);
    if (session.ended_at) throw new Error("ended");
    showMessages(chatEl, session.messages);
    showSessionCorrections(session.corrections);
    if (session.scenario) showBanner(session.scenario);
    updateFinishButton();
    scrollChat();
  } catch {
    chat.sessionId = null;
    store.set("sessionId", null);
  }
}

/* ----------------------------------------------------------------- player */

// Plays WAV chunks back to back without gaps, in the order they arrive.
const player = {
  ctx: null,
  sources: new Set(),
  nextStart: 0,
  chain: Promise.resolve(),
  epoch: 0,  // bumped by stop() so in-flight decodes are dropped

  unlock() {
    // Browsers only allow audio after a user gesture: call from click/key handlers.
    this.ctx ||= new AudioContext();
    if (this.ctx.state === "suspended") this.ctx.resume();
  },

  /** Decode and queue; resolves with the AudioBuffer (or null if stopped meanwhile). */
  enqueue(data, onStart) {
    this.unlock();
    const epoch = this.epoch;
    const job = this.chain.then(async () => {
      const buffer = data instanceof AudioBuffer ? data : await this.ctx.decodeAudioData(data);
      if (epoch !== this.epoch) return null;
      this.schedule(buffer, onStart);
      return buffer;
    });
    this.chain = job.catch(() => null);
    return this.chain;
  },

  schedule(buffer, onStart) {
    const src = this.ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(this.ctx.destination);
    const at = Math.max(this.ctx.currentTime + 0.03, this.nextStart);
    src.start(at);
    this.nextStart = at + buffer.duration;
    this.sources.add(src);
    if (onStart) setTimeout(onStart, Math.max(0, (at - this.ctx.currentTime) * 1000));
    src.onended = () => {
      this.sources.delete(src);
      updateSpeaking();
    };
    updateSpeaking();
  },

  stop() {
    this.epoch++;
    for (const src of this.sources) {
      try { src.stop(); } catch {}
    }
    this.sources.clear();
    this.nextStart = 0;
    this.chain = Promise.resolve();
  },

  get playing() {
    return this.sources.size > 0;
  },
};

function updateSpeaking() {
  const s = chat.speaking;
  if (s && s.done && !player.playing) chat.speaking = null;
  const active = player.playing || Boolean(chat.speaking);
  stopBtn.hidden = !active;
  chatEl.classList.toggle("speaking", active);
}

function stopSpeaking() {
  const s = chat.speaking;
  player.stop();
  if (s && !s.done) socket.send(JSON.stringify({ type: "cancel" }));  // stop generating speech
  if (chat.turn && s && chat.turn.id === s.id) finishTurn(null, true);
  chat.speaking = null;
  updateSpeaking();
}

async function replay(bubble) {
  stopSpeaking();
  if (bubble.audioComplete && bubble.audio?.length) {
    for (const buffer of bubble.audio) player.enqueue(buffer);
    return;
  }
  // Not cached (e.g. after a reload): synthesize sentence by sentence so playback
  // starts after the first one instead of after the whole message.
  const sentences = Text.get(bubble.textEl).match(/[^.!?]+[.!?]+["')\]]*|[^.!?]+$/g) || [];
  const epoch = player.epoch;
  const buffers = [];
  bubble.classList.add("loading-audio");
  try {
    for (const sentence of sentences.map((s) => s.trim()).filter(Boolean)) {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: sentence }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
      const data = await res.arrayBuffer();
      if (player.epoch !== epoch) return;  // stopped meanwhile
      player.enqueue(data).then((buffer) => buffer && buffers.push(buffer));
    }
    await player.chain;
    if (player.epoch === epoch) {
      bubble.audio = buffers;
      bubble.audioComplete = true;
    }
  } catch (err) {
    addMessage(chatEl, "error", `⚠️ Ses çalınamadı: ${err.message}`);
    scrollChat();
  } finally {
    bubble.classList.remove("loading-audio");
  }
}

function onAudio(header, data) {
  const s = chat.speaking;
  if (!s || header.client_id !== s.id) return;  // speech of a stopped turn
  const bubble = s.bubble;
  player.enqueue(data, () => {
    if (!s.first) return;
    s.first = false;
    const ms = Math.round(performance.now() - s.t0);
    console.info(`[latency] input → first audio: ${ms} ms`);
    if (bubble) bubble.title = `Sesin başlama süresi: ${(ms / 1000).toFixed(2)} sn`;
  }).then((buffer) => {
    if (buffer && bubble) (bubble.audio ||= []).push(buffer);
  });
}

function onAudioEnd(ev) {
  const s = chat.speaking;
  if (!s || ev.client_id !== s.id) return;
  s.done = true;
  // The bubble's cached audio is complete only if the whole reply was spoken.
  s.chain = player.chain.then(() => {
    if (s.bubble) s.bubble.audioComplete = true;
  });
  updateSpeaking();
}

stopBtn.addEventListener("click", stopSpeaking);

/* ------------------------------------------------------- voice socket */

// One WebSocket carries typed and spoken turns plus the spoken replies.
const socket = {
  ws: null,
  queue: [],
  retry: 0,
  audioHeader: null,  // an "audio" event is followed by one binary WAV frame
  connect() {
    const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/voice`);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      this.retry = 0;
      for (const m of this.queue.splice(0)) ws.send(m);
    };
    ws.onmessage = (e) => {
      if (typeof e.data !== "string") {
        const header = this.audioHeader;
        this.audioHeader = null;
        if (header) onAudio(header, e.data);
        return;
      }
      const ev = JSON.parse(e.data);
      if (ev.type === "audio") this.audioHeader = ev;
      else if (ev.type === "audio_end") onAudioEnd(ev);
      else if (ev.type === "correction") onCorrection(ev);  // may come after the turn ended
      else onServerEvent(ev);
    };
    ws.onclose = () => {
      this.ws = null;
      if (chat.turn) finishTurn("Bağlantı koptu, tekrar deneyin.");
      chat.speaking = null;
      updateSpeaking();
      setTimeout(() => this.connect(), Math.min(5000, 300 * 2 ** this.retry++));
    };
    this.ws = ws;
  },
  send(...messages) {
    for (const m of messages) {
      if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(m);
      else this.queue.push(m);
    }
  },
};

const newId = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random()));

function startTurn(userBubble, t0 = performance.now()) {
  stopSpeaking();
  if (chat.turn) finishTurn(null, true);  // the server cancels the previous turn
  const id = newId();
  chat.turn = { id, userBubble, botBubble: null };
  if (voiceReplies()) chat.speaking = { id, bubble: null, done: false, t0, first: true };
  updateSpeaking();
  setBusy(true);
  return id;
}

function finishTurn(errorMessage = null, interrupted = false) {
  const turn = chat.turn;
  if (!turn) return;
  turn.userBubble?.classList.remove("pending");
  const bubble = turn.botBubble;
  if (bubble) {
    bubble.classList.remove("pending");
    if (!Text.get(bubble.textEl)) bubble.remove();
    else {
      if (interrupted) bubble.classList.add("interrupted");
      Text.render(bubble.textEl, Text.get(bubble.textEl), { words: true });  // streamed as plain text
      addReplayButton(bubble);
    }
  }
  if (errorMessage) {
    addMessage(chatEl, "error", `⚠️ ${errorMessage}`);
    refreshStatus();
  }
  if (chat.speaking?.id === turn.id && (errorMessage || !bubble)) {
    chat.speaking.done = true;
    updateSpeaking();
  }
  chat.turn = null;
  setBusy(false);
  scrollChat();
}

function botBubble(turn) {
  if (!turn.botBubble) {
    turn.botBubble = addMessage(chatEl, "assistant", "");
    turn.botBubble.classList.add("pending");
    if (chat.speaking?.id === turn.id) chat.speaking.bubble = turn.botBubble;
  }
  return turn.botBubble;
}

function onServerEvent(ev) {
  const turn = chat.turn;
  if (!turn || ev.client_id !== turn.id) return;  // stale event of an interrupted turn
  switch (ev.type) {
    case "transcript":
      turn.userBubble.classList.remove("pending");
      if (ev.text) {
        turn.userBubble.spokenWords = ev.words;  // kept for the correction marks later
        Text.renderSpoken(turn.userBubble.textEl, ev.text, ev.words);
        botBubble(turn);
      } else {
        turn.userBubble.remove();
        turn.userBubble = null;
      }
      break;
    case "scenario":
      onScenarioStarted(ev);
      break;
    case "meta":
      chat.sessionId = ev.session_id;
      store.set("sessionId", ev.session_id);
      updateFinishButton();
      onUserMessageStored(turn.userBubble, ev.user_message_id);
      botBubble(turn);
      break;
    case "status":  // e.g. the model is still loading: shown until the reply starts
      showBubbleStatus(botBubble(turn), ev.message);
      refreshModels();
      break;
    case "delta":
      showBubbleStatus(botBubble(turn), null);
      Text.append(botBubble(turn).textEl, ev.text);
      break;
    case "done":
      if (ev.text) Text.render(botBubble(turn).textEl, ev.text, { words: true });
      finishTurn();
      return;
    case "error":
      if (!chat.sessionId) hideBanner();  // e.g. a custom scenario could not be prepared
      finishTurn(ev.message);
      return;
  }
  scrollChat();
}

function showBubbleStatus(bubble, message) {
  bubble.querySelector(".msg-status")?.remove();
  if (message) bubble.prepend(Text.create("span", `⏳ ${message}`, "msg-status"));
}

function setBusy(busy) {
  $("#send-btn").disabled = busy;
}

function sendText(text) {
  text = text.trim();
  if (!text) return;
  player.unlock();
  const bubble = addMessage(chatEl, "user", text);
  const clientId = startTurn(bubble);
  botBubble(chat.turn);
  scrollChat();
  socket.send(JSON.stringify({
    type: "text", text, session_id: chat.sessionId, client_id: clientId, speak: voiceReplies(),
  }));
}

function sendAudio(blob, releasedAt) {
  const bubble = addMessage(chatEl, "user", "🎤 …");
  bubble.classList.add("pending");
  const clientId = startTurn(bubble, releasedAt);
  scrollChat();
  socket.send(
    JSON.stringify({ type: "audio", session_id: chat.sessionId, client_id: clientId, speak: voiceReplies() }),
    blob,
  );
}

/* ------------------------------------------------------ chat view toggles */

const toggles = {
  voice: { el: $("#toggle-voice"), key: "voiceReplies", default: true,
    labels: ["🔇 Sesli cevap kapalı", "🔊 Sesli cevap"] },
  subs: { el: $("#toggle-subs"), key: "hideSubtitles", default: false,
    labels: ["👁 Altyazı açık", "🙈 Altyazı gizli"] },
};

function toggleValue(t) {
  const v = store.get(t.key);
  return v === null ? t.default : v === "1";
}

function renderToggles() {
  for (const t of Object.values(toggles)) {
    const on = toggleValue(t);
    t.el.textContent = t.labels[on ? 1 : 0];
    t.el.setAttribute("aria-pressed", String(on));
  }
  chatEl.classList.toggle("hide-subs", toggleValue(toggles.subs));
}

for (const t of Object.values(toggles)) {
  t.el.addEventListener("click", () => {
    store.set(t.key, toggleValue(t) ? "0" : "1");
    if (t === toggles.voice && !toggleValue(t)) stopSpeaking();
    renderToggles();
  });
}

const voiceReplies = () => toggleValue(toggles.voice);

// With hidden subtitles, the first click on a reply reveals it (listening practice);
// after that, words can be clicked as usual.
chatEl.addEventListener("click", (e) => {
  const bubble = e.target.closest(".msg.assistant");
  if (bubble && chatEl.classList.contains("hide-subs") && !bubble.classList.contains("revealed")) {
    bubble.classList.add("revealed");
    e.stopPropagation();
  }
});

renderToggles();

/* --------------------------------------------------------------- recorder */

const MIN_RECORDING_MS = 350;
const RELEASE_MIC_AFTER_MS = 2 * 60 * 1000;
const talkBtn = $("#talk-btn");
const talkHint = $("#talk-hint");

const recorder = {
  stream: null,
  media: null,
  chunks: [],
  startedAt: 0,
  wanted: false,  // the user is still holding the button
  audioCtx: null,
  analyser: null,
  raf: 0,
  releaseTimer: 0,

  async ensureStream() {
    if (this.stream) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
    });
    this.audioCtx = new AudioContext();
    this.audioCtx.resume();  // may start "suspended" when created after an await
    this.analyser = this.audioCtx.createAnalyser();
    this.analyser.fftSize = 1024;
    this.audioCtx.createMediaStreamSource(this.stream).connect(this.analyser);
  },

  async start() {
    if (this.media) return;
    this.wanted = true;
    clearTimeout(this.releaseTimer);
    try {
      await this.ensureStream();
    } catch (err) {
      this.wanted = false;
      const denied = err.name === "NotAllowedError";
      addMessage(chatEl, "error", denied
        ? "⚠️ Mikrofon izni verilmedi. Adres çubuğundaki kilit/mikrofon simgesinden izin verin."
        : `⚠️ Mikrofon açılamadı: ${err.message}`);
      scrollChat();
      return;
    }
    if (!this.wanted) return;  // released while the permission prompt was open
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
    this.media = new MediaRecorder(this.stream, mimeType ? { mimeType } : undefined);
    this.chunks = [];
    this.media.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    this.media.start();
    this.startedAt = performance.now();
    talkBtn.classList.add("recording");
    talkHint.textContent = appSettings.talk_button_mode === "toggle"
      ? "Dinliyorum… bitirmek için tekrar tıkla"
      : "Dinliyorum… bırakınca gönderilir";
    this.meter();
  },

  stop() {
    this.wanted = false;
    const media = this.media;
    if (!media) return Promise.resolve(null);
    this.media = null;
    cancelAnimationFrame(this.raf);
    talkBtn.classList.remove("recording");
    talkBtn.style.setProperty("--level", 0);
    updateTalkHint();
    this.releaseTimer = setTimeout(() => this.release(), RELEASE_MIC_AFTER_MS);
    const duration = performance.now() - this.startedAt;
    return new Promise((resolve) => {
      media.onstop = () => {
        if (duration < MIN_RECORDING_MS) {
          talkHint.textContent = "Çok kısa — butonu basılı tutarak konuşun";
          resolve(null);
        } else {
          resolve(new Blob(this.chunks, { type: media.mimeType }));
        }
      };
      media.stop();
    });
  },

  release() {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.audioCtx?.close();
    this.stream = this.audioCtx = this.analyser = null;
  },

  meter() {
    const buf = new Float32Array(this.analyser.fftSize);
    const tick = () => {
      this.analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += v * v;
      const level = Math.min(1, Math.sqrt(sum / buf.length) * 6);
      talkBtn.style.setProperty("--level", level.toFixed(3));
      this.raf = requestAnimationFrame(tick);
    };
    tick();
  },
};

async function pressTalk() {
  if (talkBtn.disabled) return;
  player.unlock();
  if (chat.speaking || player.playing) stopSpeaking();  // talking interrupts the reply
  if (appSettings.talk_button_mode === "toggle" && recorder.media) return releaseTalk(true);
  await recorder.start();
}

async function releaseTalk(force = false) {
  if (appSettings.talk_button_mode === "toggle" && !force) return;
  const releasedAt = performance.now();
  const blob = await recorder.stop();
  if (blob) sendAudio(blob, releasedAt);
}

function updateTalkHint() {
  if (talkBtn.disabled) return;
  talkHint.textContent = appSettings.talk_button_mode === "toggle"
    ? "Tıkla, konuş, tekrar tıkla (veya Boşluk)"
    : "Basılı tut ve konuş (veya Boşluk tuşu)";
}

talkBtn.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  try {
    talkBtn.setPointerCapture(e.pointerId);  // keep receiving pointerup if the finger slides off
  } catch {}
  pressTalk();
});
talkBtn.addEventListener("pointerup", () => releaseTalk());
talkBtn.addEventListener("pointercancel", () => releaseTalk());
talkBtn.addEventListener("contextmenu", (e) => e.preventDefault());

const isTyping = (el) => el instanceof Element && el.closest("input, textarea, select, [contenteditable]");
const onConversationPage = () => $("#page-conversation").classList.contains("active");
document.addEventListener("keydown", (e) => {
  if (e.code !== "Space" || isTyping(e.target) || !onConversationPage()) return;
  e.preventDefault();
  if (!e.repeat) pressTalk();
});
document.addEventListener("keyup", (e) => {
  if (e.code !== "Space" || isTyping(e.target) || !onConversationPage()) return;
  e.preventDefault();
  releaseTalk();
});

$("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value;
  input.value = "";
  autoGrow();
  sendText(text);
});
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $("#chat-form").requestSubmit();
  }
});
function autoGrow() {
  input.style.height = "auto";
  // An empty textarea's scrollHeight includes the wrapped placeholder; keep it one row.
  if (input.value) input.style.height = `${input.scrollHeight}px`;
}
input.addEventListener("input", autoGrow);
$("#new-chat").addEventListener("click", resetChat);

/* ---------------------------------------------------------------- history */

async function loadSessionList() {
  const list = $("#session-list");
  list.innerHTML = `<p class="muted">Yükleniyor…</p>`;
  try {
    const sessions = await api("/api/sessions");
    if (!sessions.length) {
      list.innerHTML = `<p class="muted">Henüz oturum yok.</p>`;
      return;
    }
    list.innerHTML = "";
    for (const s of sessions) {
      const a = document.createElement("a");
      a.className = "session-item";
      a.href = `#/session/${s.id}`;
      a.innerHTML = `<span><strong></strong> <span class="muted"></span></span><span class="muted"></span>`;
      a.querySelector("strong").textContent = MODE_NAMES[s.mode] || s.mode;
      a.querySelector("span .muted").textContent =
        (s.scenario_title ? `· ${s.scenario_title}` : "") + (s.has_summary ? " · 📋 rapor" : "");
      const minutes = Math.max(1, Math.round((new Date(s.last_message_at) - new Date(s.started_at)) / 60000));
      a.lastElementChild.textContent = `${formatDate(s.started_at)} · ${s.message_count} mesaj · ~${minutes} dk`;
      a.append(deleteButton("Bu oturum (mesajları, düzeltmeleri ve raporu) silinsin mi? Geri alınamaz.", async () => {
        await deleteSession(s.id);
        loadProgressPage();  // the statistics change too
      }));
      list.appendChild(a);
    }
  } catch (err) {
    list.innerHTML = "";
    addMessage(list, "error", `⚠️ ${err.message}`);
  }
}

async function loadSessionDetail(id) {
  const box = $("#session-chat");
  box.innerHTML = "";
  try {
    const s = await api(`/api/sessions/${id}`);
    const title = s.scenario ? `${s.scenario.icon} ${s.scenario.title_tr}` : MODE_NAMES[s.mode] || s.mode;
    $("#session-title").textContent = `${title} · ${formatDate(s.started_at)}`;
    $("#session-delete").replaceChildren(deleteButton("Bu oturum (mesajları, düzeltmeleri ve raporu) silinsin mi? Geri alınamaz.",
      async () => {
        await deleteSession(s.id);
        location.hash = "#/progress";
      }, "🗑 Oturumu sil"));
    showMessages(box, s.messages, s.corrections);
    if (s.summary) box.append(reportCard(s.summary));
  } catch (err) {
    addMessage(box, "error", `⚠️ ${err.message}`);
  }
}

/* --------------------------------------------------------------- settings */

const settingsForm = $("#settings-form");
const speedOut = $("#speed-out");
settingsForm.tts_speed.addEventListener("input", () => {
  speedOut.textContent = `${Number(settingsForm.tts_speed.value).toFixed(2)}x`;
});

const VOICE_GENDER = { f: "kadın", m: "erkek" };
let ttsVoices = [];

function fillVoiceSelect(selected) {
  const accent = settingsForm.tts_accent.value;
  const select = $("#tts-voice-select");
  select.innerHTML = "";
  for (const v of ttsVoices.filter((v) => v[0] === accent)) {
    const name = v.slice(3).replace(/^\w/, (c) => c.toUpperCase());
    select.add(new Option(`${name} (${VOICE_GENDER[v[1]] || ""})`, v));
  }
  if (!select.options.length) select.add(new Option("TTS hazır değil", ""));
  select.value = [...select.options].some((o) => o.value === selected) ? selected : select.options[0].value;
}

settingsForm.tts_accent.addEventListener("change", () => fillVoiceSelect(null));

$("#tts-preview").addEventListener("click", async () => {
  const btn = $("#tts-preview");
  btn.disabled = true;
  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: "Hi! This is how I sound. Let's practice English together.",
        accent: settingsForm.tts_accent.value,
        voice: settingsForm.tts_voice.value,
        speed: Number(settingsForm.tts_speed.value),
      }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    stopSpeaking();
    await player.enqueue(await res.arrayBuffer());
  } catch (err) {
    $("#settings-saved").textContent = `Ses çalınamadı: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
});

async function loadSettings() {
  const [settings, voices] = await Promise.all([
    api("/api/settings"),
    api("/api/tts/voices").catch(() => ({ voices: [] })),
  ]);
  ttsVoices = voices.voices;

  for (const [key, value] of Object.entries(settings)) {
    const field = settingsForm.elements[key];
    if (field) field.value = value;
  }
  fillVoiceSelect(settings.tts_voice);
  speedOut.textContent = `${Number(settings.tts_speed).toFixed(2)}x`;
}

settingsForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(settingsForm));
  const saved = $("#settings-saved");
  try {
    await api("/api/settings", { method: "PUT", body: data });
    saved.textContent = "Kaydedildi ✓";
    loadAppSettings();
    refreshStatus();
  } catch (err) {
    saved.textContent = `Hata: ${err.message}`;
  }
  setTimeout(() => (saved.textContent = ""), 2500);
});

/* ------------------------------------------------- updates (backend/updates.py) */

let updating = false;  // "Güncelle" was pressed: the server goes away for a moment, then comes back updated
const updateDay = (iso) => (iso ? new Date(iso).toLocaleDateString("tr-TR", { day: "numeric", month: "long", year: "numeric" }) : "");
const megabytes = (n) => `${((n || 0) / 1e6).toFixed(1)} MB`;

function renderUpdateBanner(u) {
  const text = {
    available: `🆕 Yeni sürüm var (${updateDay(u?.latest?.date)}) · Güncelle →`,
    downloading: `⬇ Güncelleme indiriliyor… ${megabytes(u?.received)}`,
    restarting: "⟳ Uygulama güncelleniyor, birazdan yeniden açılacak…",
  }[u?.state];
  const banner = $("#update-banner");
  banner.hidden = !text;
  if (text) Text.render(banner, text);
}

$("#update-banner").addEventListener("click", () => {
  location.hash = "#/settings";
  setTimeout(() => $("#update-section")?.scrollIntoView({ behavior: "smooth", block: "start" }), 300);
});

/** A button that is disabled while its (async) action runs; errors are shown in msg. */
function asyncButton(label, cls, msg, onClick) {
  const b = Text.create("button", label, cls);
  b.type = "button";
  b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      await onClick();
    } catch (err) {
      Text.render(msg, `⚠️ ${err.message}`);
    } finally {
      b.disabled = false;
    }
  });
  return b;
}

/** After "Güncelle": follow the download, then wait until the app is back (updated) and reload the page. */
async function followUpdate(show) {
  updating = true;
  let wentDown = false;
  const started = Date.now();
  while (Date.now() - started < 5 * 60 * 1000) {
    await new Promise((r) => setTimeout(r, 1500));
    let health = null;
    try {
      const r = await fetch("/api/health", { cache: "no-store" });
      health = r.ok ? await r.json() : null;
    } catch { /* closed for the update */ }
    if (!health) {
      wentDown = true;
      show("⟳ Uygulama güncelleniyor, birazdan yeniden açılacak…");
      renderUpdateBanner({ state: "restarting" });
      continue;
    }
    if (wentDown) return location.reload();  // back with the new version
    const u = health.update || {};
    renderUpdateBanner(u);
    if (u.state === "downloading") show(`⬇ İndiriliyor… ${megabytes(u.received)}`);
    else if (u.state === "restarting") show("⟳ İndirildi; uygulama kapanıp güncelleniyor…");
    else {  // the download failed, or there was nothing new: nothing was changed
      updating = false;
      return loadUpdateSection();
    }
  }
  show("Uygulama yeni bir pencerede açılmış olabilir; bu pencereyi kapatabilirsin.");
}

async function loadUpdateSection() {
  const box = $("#update-body");
  const show = (...nodes) => box.replaceChildren(...nodes.filter(Boolean));
  let u;
  try {
    u = await api("/api/update");
  } catch (err) {
    show(Text.create("p", `⚠️ ${err.message}`, "muted small"));
    return;
  }
  const msg = Text.create("span", "", "muted small");
  if (u.dev) {
    show(Text.create("p", "Bu klasör geliştirme kopyası (git deposu): güncellemeler git pull ile alınır.", "muted small"));
    return;
  }
  const state = {
    checking: "Denetleniyor…",
    current: "✓ En güncel sürümü kullanıyorsun.",
    available: `🆕 Yeni sürüm var (${updateDay(u.latest?.date)}).`,
    error: `⚠️ ${u.message}`,
    downloading: `⬇ İndiriliyor… ${megabytes(u.received)}`,
    restarting: "⟳ Uygulama güncelleniyor…",
    ready: "İndirildi: uygulamayı kapatıp açınca uygulanacak.",
  }[u.state] || (u.enabled ? "Henüz denetlenmedi." : "Açılışta denetleme kapalı.");
  const changes = u.state === "available" && lnode("ul", "update-changes", (u.changes || []).map((c) => lnode("li", "",
    Text.create("strong", c.title), Text.create("span", ` · ${updateDay(c.date)}`, "muted small"),
    c.body && lnode("details", "", Text.create("summary", "Ayrıntı", "small"), Text.create("p", c.body, "small update-body-text")))));
  const auto = document.createElement("label");
  auto.className = "small";
  const check = document.createElement("input");
  check.type = "checkbox";
  check.checked = u.enabled;
  check.addEventListener("change", async () => {
    await api("/api/update/settings", { method: "PUT", body: { enabled: check.checked } });
  });
  auto.append(check, " Açılışta yeni sürümü denetle");
  show(
    lnode("div", "sync-status",
      Text.create("span", state),
      Text.create("span", `Kullandığın sürüm: ${u.current ? u.current.slice(0, 7) : "bilinmiyor"}`, "muted small")),
    changes && Text.create("p", "Neler değişti:", "small"), changes,
    lnode("div", "sync-row",
      u.state === "available" && asyncButton("⬆ Güncelle", "primary small", msg, async () => {
        if (!window.confirm("Önce verilerin yedeklenir; uygulama kapanıp güncellenir ve kendiliğinden yeniden açılır "
          + "(yaklaşık yarım dakika). Devam edilsin mi?")) return;
        await api("/api/update/apply", { method: "POST" });
        followUpdate((text) => Text.render(msg, text));
      }),
      asyncButton("🔄 Şimdi denetle", "ghost small", msg, async () => {
        Text.render(msg, "Denetleniyor…");
        await api("/api/update/check", { method: "POST" });
        await loadUpdateSection();
      }),
      auto),
    msg);
  if (u.state === "checking") setTimeout(() => location.hash === "#/settings" && loadUpdateSection(), 1500);
}

/* --------------------------------------------- two computers (backend/sync.py) */

const syncTime = (iso) => (iso ? new Date(iso).toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" }) : "—");

async function loadSyncSection() {
  const box = $("#sync-body");
  const show = (...nodes) => box.replaceChildren(...nodes.filter(Boolean));  // optional parts may be null/false
  let s;
  try {
    s = await api("/api/sync");
  } catch (err) {
    box.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted small"));
    return;
  }
  const msg = Text.create("span", "", "muted small");
  const button = (label, cls, onClick) => {
    const b = Text.create("button", label, cls);
    b.type = "button";
    b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        await onClick();
      } catch (err) {
        Text.render(msg, `⚠️ ${err.message}`);
      } finally {
        b.disabled = false;
      }
    });
    return b;
  };

  if (!s.enabled) {
    const input = document.createElement("input");
    input.value = s.dir || s.suggested || "";
    input.placeholder = "ör. G:\\My Drive\\EnglishPractice";
    const on = button("☁️ Eşitlemeyi aç", "primary small", async () => {
      Text.render(msg, "Hazırlanıyor…");
      const r = await api("/api/sync/setup", { method: "POST", body: { dir: input.value } });
      if (!r.choose) return loadSyncSection();
      // The folder already has data from the other computer: which one to keep? Each side's latest work is shown
      // (and the older one needs a confirmation), so week-old data does not replace newer work by mistake.
      const other = r.cloud.machine;
      const older = (side) => r.newer && r.newer !== side
        && !window.confirm(`${side === "cloud" ? `${other} bilgisayarındaki` : "Bu bilgisayardaki"} veri daha ESKİ `
          + `(son çalışma ${syncTime(r[`${side}_activity`])}). Yine de bu mu kalsın? Öbürü yedekte kalır.`);
      const mark = (side) => (r.newer === side ? " · daha yeni ✓" : "");
      Text.render(msg, "");
      box.replaceChildren(
        Text.create("p", `Bu klasörde ${other} bilgisayarının verileri var (${syncTime(r.cloud.saved_at)}). Hangisi kalsın?`),
        Text.create("p", `${other}: son çalışma ${syncTime(r.cloud_activity)}${mark("cloud")}`, "muted small"),
        Text.create("p", `Bu bilgisayar: son çalışma ${syncTime(r.local_activity)}${mark("local")}`, "muted small"),
        lnode("div", "sync-row",
          button(`⬇ ${other} verilerini al`, r.newer === "local" ? "ghost small" : "primary small", async () => {
            if (older("cloud")) return;
            const c = await api("/api/sync/choose", { method: "POST", body: { action: "pull" } });
            if (c.reload) location.reload();
          }),
          button("⬆ Bu bilgisayardakini gönder", r.newer === "local" ? "primary small" : "ghost small", async () => {
            if (older("local")) return;
            await api("/api/sync/choose", { method: "POST", body: { action: "push" } });
            loadSyncSection();
          })),
        Text.create("p", "Hangisini seçersen seç, öbürü yedekte kalır (data\\backups).", "muted small"), msg);
    });
    show(
      s.dir_missing && Text.create("p", `⚠️ Klasör bulunamadı: ${s.dir}. Google Drive bu bilgisayarda açık mı?`, "sync-notice"),
      !s.suggested && Text.create("p", "Google Drive bulunamadı. Google Drive masaüstü uygulamasını kurup aynı hesapla giriş yap; "
        + "sonra klasörü buraya yaz.", "muted small"),
      lnode("div", "sync-row", input, on), msg);
    return;
  }

  show(
    lnode("div", "sync-status",
      Text.create("span", `✓ Açık · ${s.dir}`),
      Text.create("span", `Bu bilgisayar: ${s.machine} · son eşitleme: ${syncTime(s.last_sync)}`, "muted small"),
      s.cloud && Text.create("span", `Buluttaki son kayıt: ${s.cloud.machine} · ${syncTime(s.cloud.saved_at)}`
        + (s.cloud.activity ? ` · son çalışma: ${syncTime(s.cloud.activity)}` : ""), "muted small"),
      s.other_open && Text.create("span", `⚠️ Uygulama şu anda ${s.other_open} bilgisayarında da açık görünüyor.`, "sync-notice")),
    s.notice && lnode("div", "sync-notice", Text.create("span", s.notice),
      button("Tamam", "ghost small", async () => {
        await api("/api/sync/dismiss", { method: "POST" });
        loadSyncSection();
        refreshStatus();
      })),
    lnode("div", "sync-row",
      button("🔄 Şimdi eşitle", "primary small", async () => {
        Text.render(msg, "Eşitleniyor…");
        const r = await api("/api/sync/now", { method: "POST" });
        if (r.reload) return location.reload();
        await loadSyncSection();
        Text.render($("#sync-body").querySelector(".sync-row + span") || msg, r.messages.join(" · "));
      }),
      button("Kapat", "ghost small", async () => {
        if (!window.confirm("Eşitleme kapatılsın mı? Veriler bu bilgisayarda kalır; bulut klasöründeki kopya silinmez.")) return;
        await api("/api/sync/off", { method: "POST" });
        loadSyncSection();
      })),
    msg);
}

/* ------------------------------------------------------------------ reset */

const RESET_INFO = {
  lessons: "Tamamlanan dersler, puanlar, sınav sonuçları ve Kendini Test Et sonuçları.",
  words: "Kelime Çalış'ta öğrendiklerin, Kelime Defteri ve Kalıplar'daki ilerlemen (tekrar takvimleri dahil).",
  history: "Sohbet, senaryo, öğretmen ve yazma kayıtları, düzeltmeler, hata istatistikleri, zayıf noktalar ve pratik serisi.",
  level: "Seviyen silinir; uygulama ilk açılıştaki gibi seviyeni yeniden sorar.",
};
// Page state that points at deleted data (localStorage).
const RESET_STORE_KEYS = { history: ["sessionId", "teacherSessionId"], level: ["lessonsLevel", "wordsLevel", "patternsLevel"] };

async function loadResetSection() {
  const box = $("#reset-groups");
  const run = $("#reset-run");
  let groups;
  try {
    groups = (await api("/api/reset")).groups;
  } catch (err) {
    box.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted small"));
    return;
  }
  const checks = groups.map((g) => {
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = g.id;
    input.addEventListener("change", () => {
      run.disabled = !checks.some((c) => c.checked);
    });
    return input;
  });
  box.replaceChildren(...groups.map((g, i) => lnode("label", "", checks[i], lnode("span", "",
    Text.create("strong", `${g.label} (${g.id === "level" ? `şu an ${appSettings.level}` : `${g.rows} kayıt`})`),
    Text.create("small", RESET_INFO[g.id] || "", "muted")))));
  run.disabled = true;
  run.onclick = async () => {
    const picked = checks.filter((c) => c.checked);
    if (!picked.length) return;
    const names = picked.map((c) => groups.find((g) => g.id === c.value).label).join(", ");
    if (!window.confirm(`Şunlar sıfırlansın mı?\n\n${names}\n\nÖnce otomatik yedek alınır.`)) return;
    run.disabled = true;
    const msg = $("#reset-msg");
    Text.render(msg, "Sıfırlanıyor…");
    try {
      const r = await api("/api/reset", { method: "POST", body: { groups: picked.map((c) => c.value) } });
      for (const g of r.groups) for (const key of RESET_STORE_KEYS[g] || []) store.set(key, null);
      Text.render(msg, `✓ Sıfırlandı (yedek: ${r.backup || "yok"}). Sayfa yenileniyor…`);
      setTimeout(() => location.reload(), 1500);
    } catch (err) {
      Text.render(msg, `Sıfırlanamadı: ${err.message}`);
      run.disabled = false;
    }
  };
}

/* ------------------------------------------------- first run: the level */

const LEVEL_CHOICES = [
  ["A1", "Başlangıç", "Çok az biliyorum: tanışma, basit cümleler."],
  ["A2", "Temel", "Günlük konularda basit konuşabiliyorum."],
  ["B1", "Orta", "İşte ve seyahatte derdimi anlatabiliyorum."],
  ["B2", "İyi", "Toplantılara katılıp fikrimi savunabiliyorum."],
  ["C1", "İleri", "Akıcıyım; ince farkları çalışmak istiyorum."],
];

/** Lessons, chat and corrections follow the level: ask it once instead of silently using B1. */
function askLevelIfNeeded() {
  if (appSettings.level_confirmed !== "0") return;
  const overlay = document.createElement("div");
  overlay.className = "level-overlay";
  const box = document.createElement("div");
  box.className = "level-dialog";
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-modal", "true");
  box.append(Text.create("h2", "Hoş geldin! 👋 İngilizce seviyen ne?"),
    Text.create("p", "Dersler, sohbetin zorluğu ve düzeltmeler buna göre ayarlanır. Sonra Ayarlar'dan değiştirebilirsin.", "muted"));
  const pick = async (level) => {
    box.querySelectorAll("button").forEach((b) => (b.disabled = true));
    try {
      await api("/api/settings", { method: "PUT", body: { level } });
      await loadAppSettings();
      lessonsUi.level = level;  // the lessons page opens on the chosen level
      store.set("lessonsLevel", level);
      overlay.remove();
      route();
    } catch (err) {
      box.querySelectorAll("button").forEach((b) => (b.disabled = false));
      window.alert(`Kaydedilemedi: ${err.message}`);
    }
  };
  for (const [level, name, desc] of LEVEL_CHOICES) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "level-choice";
    b.append(Text.create("strong", `${level} · ${name}`), Text.create("span", desc, "muted small"));
    b.addEventListener("click", () => pick(level));
    box.append(b);
  }
  const unsure = Text.create("button", "Emin değilim → A2'den başla (seviye sınavlarıyla ilerlersin)", "ghost small");
  unsure.type = "button";
  unsure.addEventListener("click", () => pick("A2"));
  box.append(unsure);
  overlay.append(box);
  document.body.append(overlay);
}

/* ------------------------------------------------------------------- boot */

window.addEventListener("DOMContentLoaded", async () => {
  renderNav();
  refreshVocabBadge();
  refreshStatus();
  socket.connect();
  refreshModels();
  // Pages render category labels and settings-dependent text: load those first.
  await Promise.all([loadAppSettings(), loadErrorCategories()]);
  route();
  updateCorrectionsNote();
  restoreChat();
  askLevelIfNeeded();
});
