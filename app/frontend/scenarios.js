"use strict";

/* Role-play scenarios, the scenario banner, "finish session" and the session report. */

const scenarioUi = {
  grid: document.querySelector("#scenario-grid"),
  banner: document.querySelector("#scenario-banner"),
  finishBtn: document.querySelector("#finish-session"),
  list: [],
};

/* ------------------------------------------------------------- scenarios page */

async function loadScenarios() {
  if (scenarioUi.list.length) return;
  try {
    scenarioUi.list = await api("/api/scenarios");
  } catch (err) {
    Text.render(scenarioUi.grid, `⚠️ ${err.message}`);
    return;
  }
  scenarioUi.grid.innerHTML = "";
  for (const s of scenarioUi.list) {
    const card = document.createElement("button");
    card.className = "scenario-card";
    card.append(
      Text.create("span", s.icon, "scenario-icon"),
      Text.create("strong", s.title_tr),
      Text.create("span", s.description_tr, "muted"),
    );
    card.addEventListener("click", () => startScenario({ scenario_id: s.id }));
    scenarioUi.grid.append(card);
  }
}

document.querySelector("#custom-scenario").addEventListener("submit", (e) => {
  e.preventDefault();
  const custom = e.target.custom.value.trim();
  if (!custom) return;
  e.target.custom.value = "";
  startScenario({ custom });
});

/** Start a role-play: the AI speaks first. */
function startScenario(spec) {
  location.hash = "#/conversation";
  resetChat();
  player.unlock();
  showBanner(null, spec.custom ? "Senaryo hazırlanıyor…" : "Senaryo başlıyor…");
  const clientId = startTurn(null);
  socket.send(JSON.stringify({ type: "start_scenario", ...spec, client_id: clientId, speak: voiceReplies() }));
}

/** WS "scenario" event: the session exists now. */
function onScenarioStarted(ev) {
  chat.sessionId = ev.session_id;
  store.set("sessionId", ev.session_id);
  showBanner(ev.scenario);
  updateFinishButton();
}

/* ---------------------------------------------------------------- banner */

function showBanner(scenario, loadingText = "") {
  const b = scenarioUi.banner;
  b.innerHTML = "";
  b.hidden = false;
  if (!scenario) {
    b.append(Text.create("span", `🎭 ${loadingText}`, "muted"));
    return;
  }
  const head = document.createElement("div");
  head.className = "scenario-head";
  head.append(Text.create("span", scenario.icon, "scenario-icon"), Text.create("strong", scenario.title_tr));
  b.append(head);
  if (scenario.tasks_tr?.length) {
    const tasks = document.createElement("div");
    tasks.className = "scenario-tasks";
    tasks.append(Text.create("span", "Görevler:", "muted small"));
    for (const t of scenario.tasks_tr) {
      const label = document.createElement("label");
      const box = document.createElement("input");
      box.type = "checkbox";
      label.append(box, Text.create("span", t));
      tasks.append(label);
    }
    b.append(tasks);
  }
}

function hideBanner() {
  scenarioUi.banner.hidden = true;
  scenarioUi.banner.innerHTML = "";
}

function updateFinishButton() {
  scenarioUi.finishBtn.hidden = !chat.sessionId;
  // Also after "Oturumu bitir": the ended session (with its report) is still on screen.
  document.querySelector("#delete-session").hidden = !(chat.sessionId || chat.endedSessionId);
}

document.querySelector("#delete-session").addEventListener("click", async () => {
  const id = chat.sessionId || chat.endedSessionId;
  if (!id || !window.confirm("Bu sohbet (mesajları, düzeltmeleri ve raporu) silinsin mi? Geri alınamaz.")) return;
  try {
    await deleteSession(id);
  } catch (err) {
    window.alert(`Silinemedi: ${err.message}`);
  }
});

/* ---------------------------------------------------------- finish + report */

scenarioUi.finishBtn.addEventListener("click", finishSession);

async function finishSession() {
  const sessionId = chat.sessionId;
  if (!sessionId) return;
  stopSpeaking();
  if (chat.turn) finishTurn(null, true);
  const loading = Text.create("div", "📋 Rapor hazırlanıyor… (düzeltmelerin bitmesi bekleniyor, 10–20 sn sürebilir)", "report-loading");
  chatEl.append(loading);
  scrollChat();
  scenarioUi.finishBtn.disabled = true;
  try {
    const report = await api(`/api/sessions/${sessionId}/report`, { method: "POST" });
    const session = report.correction_mode === "end" ? await api(`/api/sessions/${sessionId}`) : null;
    const card = reportCard(report, session?.corrections);
    card.append(lnode("div", "actions", deleteButton("Bu oturum (mesajları, düzeltmeleri ve raporu) silinsin mi? Geri alınamaz.",
      () => deleteSession(sessionId), "🗑 Bu oturumu sil")));
    loading.replaceWith(card);
    // The next message starts a new session; the ended one can still be deleted from here.
    chat.sessionId = null;
    chat.endedSessionId = sessionId;
    store.set("sessionId", null);
    updateFinishButton();
  } catch (err) {
    loading.remove();
    addMessage(chatEl, "error", `⚠️ ${err.message}`);
  } finally {
    scenarioUi.finishBtn.disabled = false;
    scrollChat();
  }
}

function section(title, ...children) {
  const el = document.createElement("section");
  el.append(Text.create("h4", title), ...children);
  return el;
}

/** The session report (chat view and history page). */
function reportCard(report, correctionsByMessage = null) {
  const card = document.createElement("div");
  card.className = "report-card";
  const st = report.stats;
  card.append(
    Text.create("h3", "📋 Oturum raporu"),
    Text.create("div", `${st.user_messages} mesaj · ${st.perfect} hatasız · ${st.error_count} hata`, "muted"),
  );

  if (report.went_well?.length) {
    const ul = document.createElement("ul");
    for (const w of report.went_well) ul.append(Text.create("li", w));
    card.append(section("👍 İyi gidenler", ul));
  }

  if (report.main_mistakes?.length) {
    const box = document.createElement("div");
    box.className = "report-mistakes";
    for (const m of report.main_mistakes) {
      const item = document.createElement("div");
      item.className = "report-mistake";
      const head = document.createElement("div");
      head.append(Text.create("span", categoryLabel(m.category), "tag"), Text.create("span", ` × ${m.count}`, "muted"));
      item.append(head);
      for (const ex of m.examples) {
        const line = document.createElement("div");
        line.className = "corr-change";
        line.append(Text.create("span", ex.wrong, "wrong"), " → ", Text.create("span", ex.right, "right"));
        item.append(line);
      }
      if (m.tip) item.append(Text.create("div", `💡 ${m.tip}`, "expl"));
      box.append(item);
    }
    card.append(section("🎯 Üzerinde çalış", box));
  } else if (st.checked) {
    card.append(section("🎯 Üzerinde çalış", Text.create("p", "Bu oturumda hata bulunmadı. Harika! 🎉")));
  }

  if (report.phrases_to_learn?.length) {
    const box = document.createElement("div");
    box.className = "report-phrases";
    for (const p of report.phrases_to_learn) {
      const row = document.createElement("div");
      row.className = "report-phrase";
      const listen = document.createElement("button");
      listen.className = "replay inline";
      listen.title = "Dinle";
      listen.textContent = "🔊";
      listen.addEventListener("click", () => speakText(p.example || p.phrase));
      const text = document.createElement("div");
      text.append(
        Text.create("strong", p.phrase, "", { words: true }),
        Text.create("span", ` — ${p.meaning_tr}`, "muted"),
        Text.create("div", p.example, "example", { words: true }),
      );
      row.append(listen, text, addPhraseButton(p.phrase, p.meaning_tr, p.example, card));
      box.append(row);
    }
    card.append(section("📚 Öğrenilecek ifadeler", box));
  }

  // With "corrections at the end", the corrections are shown here for the first time.
  const all = Object.values(correctionsByMessage || {}).sort((a, b) => a.message_id - b.message_id);
  if (all.length) {
    const box = document.createElement("div");
    box.className = "corrections-list";
    for (const c of all) box.append(correctionCard(c));
    card.append(section("✏️ Bu oturumdaki düzeltmeler", box));
  }
  return card;
}

async function speakText(text) {
  stopSpeaking();
  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    await player.enqueue(await res.arrayBuffer());
  } catch (err) {
    addMessage(chatEl, "error", `⚠️ Ses çalınamadı: ${err.message}`);
  }
}
