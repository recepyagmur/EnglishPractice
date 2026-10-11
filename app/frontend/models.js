"use strict";

/* Language models: Ayarlar → "Dil modelleri" (installed models, default, delete, speed
   test, downloads with the setup wizard's catalog cards) and the session model picker
   above the chat. State comes from GET /api/llm and is polled while something runs. */

const modelsUi = {
  state: null,
  catalog: null,       // catalog cards, loaded when "Yeni model indir" is opened
  catalogOpen: false,
  copyChoice: {},      // model → take it from the system Ollama's copy instead of downloading
  hiddenJobs: new Set(),  // finished download / test cards the learner closed
  timer: 0,
  pullWasRunning: false,
  el: {
    picker: $("#chat-model"), select: $("#chat-model-select"), pickerStatus: $("#chat-model-status"),
    status: $("#models-status"), installed: $("#models-installed"), catalog: $("#models-catalog"),
    add: $("#models-add"), bench: $("#models-bench"),
  },
};

const elm = ModelCards.h;  // element builder (shared with the model cards)
const SLOW_TOKENS_PER_SEC = 8;  // same threshold as the setup wizard's speed test

const onSettingsPage = () => $("#page-settings").classList.contains("active");

/* ------------------------------------------------------------------ state */

async function refreshModels() {
  clearTimeout(modelsUi.timer);
  try {
    applyModels(await api("/api/llm"));
  } catch {
    modelsUi.timer = setTimeout(refreshModels, 5000);
  }
}

function applyModels(state) {
  clearTimeout(modelsUi.timer);
  modelsUi.state = state;
  renderChatModel();
  if (onSettingsPage()) renderModelsSection();
  const pullRunning = Boolean(state.pull?.running);
  if (modelsUi.pullWasRunning && !pullRunning && modelsUi.catalog) loadCatalog();  // "Kurulu ✓" now
  modelsUi.pullWasRunning = pullRunning;
  if (state.busy || pullRunning || state.benchmark?.running) {
    modelsUi.timer = setTimeout(refreshModels, 1000);
  }
}

async function modelAction(path, body, method = "POST") {
  try {
    applyModels(await api(path, { method, body: body ?? {} }));
    return true;
  } catch (err) {
    alert(err.message);
    refreshModels();
    return false;
  }
}

const chatModels = () => (modelsUi.state?.models || []).filter((m) => !m.translation);
const modelName = (id) => modelsUi.state?.models.find((m) => m.id === id)?.name || id;

function busyText(s) {
  if (s.busy === "benchmark") return "⏱ Hız testi sürüyor…";
  if (s.busy) return `⏳ ${modelName(s.busy_model || s.active)} hazırlanıyor…`;
  return "";
}

/* ------------------------------------------------------- chat model picker */

function renderChatModel() {
  const s = modelsUi.state;
  const { picker, select, pickerStatus } = modelsUi.el;
  const list = chatModels();
  picker.hidden = list.length < 2;  // nothing to choose from
  select.replaceChildren(...list.map((m) => new Option(m.id === s.default ? `${m.name} (varsayılan)` : m.name, m.id)));
  select.value = s.active;
  select.disabled = Boolean(s.busy || s.benchmark?.running);
  pickerStatus.textContent = s.load_error ? "⚠️" : busyText(s);
  pickerStatus.title = s.load_error || "";
}

modelsUi.el.select.addEventListener("change", () => {
  modelAction("/api/llm/active", { model: modelsUi.el.select.value }, "PUT");
});

/** "Yeni sohbet": the next session starts with this computer's default model again. */
function resetSessionModel() {
  if (modelsUi.state?.override) modelAction("/api/llm/active", { model: null }, "PUT");
}

/* --------------------------------------------------------- settings section */

function loadModelsSection() {
  renderModelsSection();
  refreshModels();
}

function renderModelsSection() {
  const s = modelsUi.state;
  if (!s) return;
  renderModelsStatus(s);
  renderInstalled(s);
  modelsUi.el.bench.disabled = Boolean(s.benchmark?.running) || !chatModels().length;
  modelsUi.el.add.setAttribute("aria-expanded", String(modelsUi.catalogOpen));
  modelsUi.el.catalog.hidden = !modelsUi.catalogOpen;
  if (modelsUi.catalogOpen && modelsUi.catalog) renderCatalog();
}

function formatEta(seconds) {
  if (seconds == null) return "";
  return seconds < 60 ? ` · ~${Math.ceil(seconds)} sn kaldı` : ` · ~${Math.ceil(seconds / 60)} dk kaldı`;
}

function closeButton(key) {
  return elm("button", { class: "ghost small", type: "button", onclick: () => {
    modelsUi.hiddenJobs.add(key);
    renderModelsSection();
  } }, "Kapat");
}

function renderModelsStatus(s) {
  const out = [];
  if (s.ollama_error) out.push(elm("div", { class: "models-job error" }, `⚠️ ${s.ollama_error}`));
  if (s.busy === "loading") {
    out.push(elm("div", { class: "models-job inline" }, elm("span", { class: "spinner" }),
      `${modelName(s.busy_model || s.active)} belleğe yükleniyor… (önceki model boşaltıldı)`));
  }
  if (s.load_error && !s.busy) out.push(elm("div", { class: "models-job error" }, `⚠️ Model yüklenemedi: ${s.load_error}`));

  const p = s.pull;
  const pullKey = p && `pull:${p.model}:${p.done}:${p.error}`;
  if (p && !modelsUi.hiddenJobs.has(pullKey)) {
    const pct = p.total ? p.completed / p.total : 0;
    const speed = p.running && p.speed > 1e5 ? ` · ${(p.speed / 1e6).toFixed(1)} MB/s` : "";
    const actions = [];
    if (p.running && !p.copy) actions.push(elm("button", { class: "ghost small", type: "button",
      onclick: () => modelAction("/api/llm/pull/cancel") }, "İptal"));
    if (p.done) {
      actions.push(elm("button", { class: "primary small", type: "button",
        onclick: () => startBenchmark([p.model]) }, "⏱ Hızını test et"));
      if (p.model !== s.default) actions.push(elm("button", { class: "ghost small", type: "button",
        onclick: () => modelAction("/api/llm/default", { model: p.model }, "PUT") }, "Varsayılan yap"));
    }
    if (p.error) actions.push(elm("button", { class: "ghost small", type: "button",
      onclick: () => startPull(p.model, null, false) }, "↻ Tekrar dene"));
    if (!p.running) actions.push(closeButton(pullKey));
    out.push(elm("div", { class: `models-job ${p.error ? "error" : p.done ? "ok" : ""}` },
      elm("div", { class: "job-head" }, elm("strong", {}, `⬇ ${p.name}`), elm("span", { class: "muted" }, p.status)),
      elm("div", { class: "bar", style: `--p:${pct.toFixed(3)}` }),
      elm("div", { class: "muted small" },
        `${ModelCards.size(p.completed)} / ${ModelCards.size(p.total)}${speed}${p.running ? formatEta(p.eta) : ""}`),
      p.error && elm("div", { class: "small err-text" }, p.error),
      actions.length && elm("div", { class: "actions" }, ...actions)));
  }

  const b = s.benchmark;
  const benchKey = b && `bench:${b.models.join(",")}:${b.running}`;
  if (b && !modelsUi.hiddenJobs.has(benchKey)) {
    const n = b.models.length;
    const i = b.current ? b.models.indexOf(b.current) + 1 : n;
    out.push(elm("div", { class: `models-job ${b.running ? "" : "ok"}` },
      elm("div", { class: "job-head" }, elm("strong", {}, "⏱ Hız testi"),
        elm("span", { class: "muted" }, b.running
          ? (b.current ? `${modelName(b.current)} (${i}/${n}) — test bitene kadar sohbet bekler` : "Model yeniden yükleniyor…")
          : "Bitti ✓")),
      b.running && elm("div", { class: "bar", style: `--p:${((i - 1) / n).toFixed(3)}` }),
      elm("ul", { class: "bench-results" }, ...b.models.map((m) => {
        const r = b.results[m];
        return elm("li", {}, elm("span", {}, modelName(m)), elm("span", { class: "muted" },
          !r ? (m === b.current ? "ölçülüyor…" : "sırada") : r.ok ? speedText(r) : `✗ ${r.error}`));
      })),
      ...(b.warnings || []).map((w) => elm("div", { class: "small warn-text" }, `⚠️ ${w}`)),
      !b.running && elm("div", { class: "actions" }, closeButton(benchKey))));
  }
  modelsUi.el.status.replaceChildren(...out);
}

function speedText(r) {
  return `${r.tokens_per_sec} token/sn · ilk kelime ${r.first_token_ms} ms · yükleme ${r.load_s} sn`;
}

function renderInstalled(s) {
  const busy = Boolean(s.busy || s.benchmark?.running);
  if (!s.models.length) {
    modelsUi.el.installed.replaceChildren(elm("p", { class: "muted" },
      s.ollama_error ? "Model listesi alınamadı." : "Kurulu model yok. \"Yeni model indir\" ile bir model ekle."));
    return;
  }
  modelsUi.el.installed.replaceChildren(...s.models.map((m) => {
    const isDefault = m.id === s.default;
    const r = m.benchmark;
    const tags = [
      isDefault && elm("span", { class: "badge recommended" }, "✓ Varsayılan"),
      s.override === m.id && elm("span", { class: "badge fit" }, "Bu oturumda kullanılıyor"),
      m.translation && elm("span", { class: "badge installed" }, "Çeviri modeli"),
    ];
    const details = [m.id, ModelCards.size(m.size_bytes), m.parameter_size, m.quantization].filter(Boolean).join(" · ");
    const speed = m.translation ? elm("span", { class: "muted small" }, "Sadece cümle çevirisi")
      : r ? elm("span", { class: r.tokens_per_sec < SLOW_TOKENS_PER_SEC ? "warn-text" : "" },
        elm("strong", {}, `${r.tokens_per_sec} token/sn`),
        elm("span", { class: "muted small" }, ` · ilk kelime ${r.first_token_ms} ms · ${formatDate(r.measured_at)}`))
        : elm("span", { class: "muted small" }, "Hız henüz ölçülmedi");
    return elm("div", { class: `model-row ${isDefault ? "default" : ""}` },
      elm("div", { class: "model-main" },
        elm("div", { class: "model-title" }, elm("strong", {}, m.name), ...tags),
        elm("div", { class: "muted small" }, details),
        elm("div", { class: "model-speed" }, speed)),
      elm("div", { class: "model-actions" },
        !m.translation && !isDefault && elm("button", { class: "ghost small", type: "button", disabled: busy,
          onclick: () => modelAction("/api/llm/default", { model: m.id }, "PUT") }, "Varsayılan yap"),
        !m.translation && elm("button", { class: "ghost small", type: "button", disabled: busy,
          title: "Bu modelin bu bilgisayardaki hızını ölç", onclick: () => startBenchmark([m.id]) }, "⏱ Test"),
        elm("button", { class: "ghost small danger", type: "button", disabled: busy || isDefault,
          title: isDefault ? "Varsayılan model silinemez; önce başka bir modeli varsayılan yap." : "",
          onclick: () => deleteModel(m) }, "Sil")));
  }));
}

function deleteModel(m) {
  if (!confirm(`${m.name} silinsin mi? (${ModelCards.size(m.size_bytes)} yer açılır; gerekirse tekrar indirilebilir.)`)) return;
  modelAction("/api/llm/delete", { model: m.id });
}

function startBenchmark(models) {
  const many = !models;
  const text = many
    ? "Kurulu tüm modeller sırayla test edilir (model başına yaklaşık 20–60 sn). Test sürerken sohbet bekler. Başlasın mı?"
    : `${modelName(models[0])} test edilsin mi? (yaklaşık 20–60 sn; bu sırada sohbet bekler)`;
  if (!confirm(text)) return;
  modelAction("/api/llm/benchmark", { models: models || null });
}

modelsUi.el.bench.addEventListener("click", () => startBenchmark(null));

/* ---------------------------------------------------------------- catalog */

modelsUi.el.add.addEventListener("click", () => {
  modelsUi.catalogOpen = !modelsUi.catalogOpen;
  renderModelsSection();
  if (modelsUi.catalogOpen && !modelsUi.catalog) loadCatalog();
});

async function loadCatalog() {
  const box = modelsUi.el.catalog;
  if (!modelsUi.catalog) {
    box.replaceChildren(elm("p", { class: "muted" }, elm("span", { class: "spinner" }),
      "Donanım taranıyor ve model boyutları alınıyor…"));
  }
  try {
    modelsUi.catalog = (await api("/api/llm/catalog")).models;
    if (modelsUi.catalogOpen) renderCatalog();
  } catch (err) {
    box.replaceChildren(elm("p", { class: "err-text" }, `⚠️ ${err.message}`));
  }
}

function renderCatalog() {
  const s = modelsUi.state;
  const pulling = Boolean(s?.pull?.running);
  modelsUi.el.catalog.replaceChildren(
    elm("p", { class: "muted small" },
      "Rozetler bu bilgisayarın ekran kartı ve belleğine göre bir tahmindir; indirdikten sonra ⏱ hız testi asıl kararı verir."),
    elm("div", { class: "model-grid" }, ...modelsUi.catalog.map((m) => {
      const unfit = m.badge === "no";
      return ModelCards.card(m, {
        disabled: unfit && !m.installed,
        footer: m.installed ? [] : [
          m.system_copy && elm("label", { class: "choice small" },
            elm("input", { type: "checkbox", checked: modelsUi.copyChoice[m.id] !== false,
              onchange: (e) => { modelsUi.copyChoice[m.id] = e.target.checked; } }),
            elm("span", {}, "Bilgisayarında zaten var — indirmek yerine kopyala")),
          elm("div", { class: "actions" }, elm("button", {
            class: "primary small", type: "button", disabled: unfit || pulling,
            title: unfit ? "Bu bilgisayarın belleğine sığmaz." : pulling ? "Önce süren indirme bitsin." : "",
            onclick: () => startPull(m.id, m.system_copy && modelsUi.copyChoice[m.id] !== false ? m.system_copy : null,
              true, m),
          }, `⬇ İndir (${ModelCards.size(m.size_bytes)})`)),
        ],
      });
    })));
}

function startPull(model, copyFrom, ask, card = null) {
  if (ask && !confirm(copyFrom
    ? `${card.name} bilgisayarındaki kopyadan alınsın mı? (${ModelCards.size(card.size_bytes)} kopyalanır)`
    : `${card.name} indirilsin mi? (${ModelCards.size(card.size_bytes)}) İndirme sürerken uygulamayı kullanmaya devam edebilirsin.`)) return;
  modelAction("/api/llm/pull", { model, copy_from: copyFrom });
}
