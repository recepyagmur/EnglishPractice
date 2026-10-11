"use strict";

/* Setup wizard UI: install / new computer / maintenance. */

const $ = (s) => document.querySelector(s);
const view = $("#view");

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

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== false && v !== null && v !== undefined) e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) e.append(c);
  return e;
}

/** Replace the step view; null / false children (from `cond && el(...)`) are skipped. */
function show(...children) {
  view.replaceChildren(...children.flat().filter((c) => c !== null && c !== undefined && c !== false));
}

const size = ModelCards.size;  // model cards are shared with the app (/shared/model-cards.js)

const W = {
  state: null, hw: null, catalog: null,
  steps: [], index: 0,
  plan: {
    models: [], default_model: null, copy_from_system: {}, whisper_model: "small.en", whisper_device: "cuda",
    tts_accent: "a", tts_voice: "af_heart", dictionary: true, translation: false, shortcut: false,
  },
  copyChoice: {},   // model → use the system copy?
  poll: 0,
};

const STEP_TITLES = {
  welcome: "Hoş geldin", hardware: "Donanım", models: "Dil modeli", voice: "Ses", extras: "Ek bileşenler",
  summary: "Özet", install: "Kurulum", test: "Test", done: "Bitti", maintenance: "Bakım",
};

/* ------------------------------------------------------------------ steps */

function setSteps(steps, index = 0) {
  W.steps = steps;
  go(index);
}

function go(i) {
  clearInterval(W.poll);
  W.index = Math.max(0, Math.min(i, W.steps.length - 1));
  const list = $("#steps");
  list.replaceChildren(...W.steps.map((s, n) => el("li", {
    class: n === W.index ? "current" : n < W.index ? "done" : "",
  }, STEP_TITLES[s])));
  $("#back").hidden = W.index === 0 || ["install", "done"].includes(W.steps[W.index]);
  $("#next").hidden = false;
  $("#next").disabled = false;
  $("#next").textContent = "İleri →";
  show(el("p", { class: "muted" }, el("span", { class: "spinner" }), "Yükleniyor…"));
  RENDER[W.steps[W.index]]().catch((err) => {
    show(el("div", { class: "card alert err" }, `⚠️ ${err.message}`));
  });
}

$("#back").addEventListener("click", () => go(W.index - 1));
$("#next").addEventListener("click", async () => {
  const step = W.steps[W.index];
  if (BEFORE_NEXT[step]) {
    $("#next").disabled = true;
    try {
      if ((await BEFORE_NEXT[step]()) === false) return;
    } catch (err) {
      alert(err.message);
      return;
    } finally {
      $("#next").disabled = false;
    }
  }
  go(W.index + 1);
});

/* ---------------------------------------------------------------- renders */

const RENDER = {
  async welcome() {
    const s = W.state;
    const isNew = s.mode === "new_machine";
    show(
      el("h2", {}, isNew ? `Yeni bilgisayar: ${s.machine_name}` : "Hoş geldin! 👋"),
      el("p", {}, isNew
        ? "Bu klasör bu bilgisayarda ilk kez açılıyor. Donanımını tarayıp sana uygun modeli seçeceğiz; klasörde zaten olan modeller tekrar indirilmeyecek."
        : "Bu sihirbaz her şeyi bu klasörün içine kurar: Python, Ollama, dil modeli, konuşma tanıma, ses ve sözlük. Bilgisayarına başka bir şey kurulmaz, yönetici izni gerekmez."),
      el("div", { class: "card" }, el("dl", { class: "kv" },
        el("dt", {}, "Klasör"), el("dd", {}, s.root),
        el("dt", {}, "Boş disk"), el("dd", {}, `${s.disk_free_gb} GB`),
        el("dt", {}, "Bilgisayar"), el("dd", {}, s.machine_name))),
      s.path_problem && el("div", { class: "card alert err" },
        `⚠️ ${s.path_problem}. Klasörü örneğin ${s.platform === "linux" ? "~/EnglishPractice" : "C:\\IngilizcePratik"} gibi Türkçe karakter ve boşluk içermeyen bir yere taşıyıp ${s.scripts.setup} dosyasını yeniden çalıştırın.`),
      s.app_running && el("div", { class: "card alert" }, "⚠️ Uygulama şu an açık. Kuruluma başlamadan önce uygulamanın konsol penceresinde Ctrl+C ile kapatın."),
      el("p", { class: "muted small" }, "Kullanıcı verilerine (geçmiş, kelime defteri, ayarlar) dokunulmaz; her işlemden önce yedek alınır."),
      s.pending_plan && el("div", { class: "card alert" },
        el("strong", {}, "Yarım kalan bir kurulum bulundu."),
        el("p", { class: "small" }, "İndirilen kısımlar korunuyor; kaldığı yerden devam edebilirsin."),
        el("button", { class: "primary", onclick: async () => {
          try {
            await api("/api/install", { method: "POST", body: s.pending_plan });
            W.plan = { ...W.plan, ...s.pending_plan };
            setSteps(["welcome", "install", "test", "done"], 1);
          } catch (e) { alert(e.message); }
        } }, "↻ Kaldığı yerden devam et")),
    );
    $("#next").disabled = Boolean(s.path_problem);
  },

  async hardware() {
    W.hw = await api("/api/hardware");
    const hw = W.hw;
    const accel = { cuda: "NVIDIA CUDA (ekran kartı)", vulkan: "Vulkan (dahili ekran kartı)", cpu: "Sadece işlemci" }[hw.accel];
    if (hw.accel !== "cuda") W.plan.whisper_device = "cpu";
    show(
      el("h2", {}, "Donanım taraması"),
      el("div", { class: "card" }, el("dl", { class: "kv" },
        el("dt", {}, "İşlemci"), el("dd", {}, `${hw.cpu || "?"} (${hw.cpu_cores || "?"} çekirdek / ${hw.cpu_threads} iş parçacığı)`),
        el("dt", {}, "RAM"), el("dd", {}, `${hw.ram_gb} GB (şu an boş: ${hw.ram_free_gb} GB)`),
        el("dt", {}, "Ekran kartı"), el("dd", {}, hw.gpus.length
          ? hw.gpus.map((g) => `${g.name}${g.vram_gb ? ` — ${g.vram_gb} GB VRAM` : " — paylaşımlı bellek"}`).join(", ")
          : "bulunamadı"),
        el("dt", {}, "Hızlandırma"), el("dd", {}, accel),
        el("dt", {}, "Boş disk"), el("dd", {}, `${hw.disk_free_gb} GB`))),
      hw.accel === "vulkan" && el("p", { class: "muted small" },
        "Dahili ekran kartları sistem belleğini paylaşır. Uygunluk tahmini RAM'in yarısına göre yapılır; asıl karar hız testinde verilir."),
    );
  },

  async models() {
    W.catalog = await api(`/api/catalog?whisper_device=${W.plan.whisper_device}`);
    const maint = W.state.mode === "maintenance";
    if (!W.plan.models.length && !maint) {
      const rec = W.catalog.models.find((m) => m.badge === "recommended");
      const already = W.catalog.models.filter((m) => m.installed).map((m) => m.id);
      W.plan.models = already.length ? [] : rec ? [rec.id] : [];
      W.plan.default_model = W.state.profile?.default_model || (already[0] ?? rec?.id ?? null);
    }
    const grid = el("div", { class: "model-grid" });
    const render = () => {
      grid.replaceChildren(...W.catalog.models.map((m) => {
        const selected = W.plan.models.includes(m.id);
        const disabled = m.badge === "no" && !m.installed;
        return ModelCards.card(m, {
          selectable: true, selected, disabled,
          onclick: () => {
            if (disabled || m.installed) return;
            W.plan.models = selected ? W.plan.models.filter((x) => x !== m.id) : [...W.plan.models, m.id];
            if (!selected && !W.plan.default_model) W.plan.default_model = m.id;
            render();
          },
          footer: [
            !m.installed && m.system_copy && selected && el("label", { class: "choice small", onclick: (e) => e.stopPropagation() },
              el("input", { type: "checkbox", checked: W.copyChoice[m.id] !== false,
                onchange: (e) => { W.copyChoice[m.id] = e.target.checked; } }),
              el("span", {}, `Bu model bilgisayarında zaten var — indirmek yerine kopyala (${m.system_copy})`)),
            (selected || m.installed) && el("label", { class: "choice small", onclick: (e) => e.stopPropagation() },
              el("input", { type: "radio", name: "default", checked: W.plan.default_model === m.id,
                onchange: () => { W.plan.default_model = m.id; } }),
              el("span", {}, "Bu bilgisayarın varsayılanı")),
          ],
        });
      }));
    };
    render();
    const anyRecommended = W.catalog.models.some((m) => m.badge === "recommended" || (m.installed && m.verified));
    show(
      el("h2", {}, maint ? "Model ekle" : "Dil modeli seçimi"),
      el("p", { class: "muted" }, "Birden fazla model seçebilirsin; biri bu bilgisayarın varsayılanı olur. \"Önerilir\" rozeti, "
        + "doğruluk testlerimizden geçen modeller arasında bu bilgisayarda en hızlı ve verimli olanı gösterir. "
        + "Kurulumdan sonraki hız testi gerçek hızı ölçer."),
      W.hw?.accel !== "cuda" && el("div", { class: "card" },
        "💻 Bu bilgisayarda NVIDIA ekran kartı yok: model işlemcide çalışır, cevaplar birkaç saniye sürer. "
        + "Kartlardaki tahmini süreler buna göredir."),
      !anyRecommended && el("div", { class: "card alert" },
        "⚠️ Bu bilgisayarın belleği, doğruluğunu test ettiğimiz modellere yetmiyor (en az 16 GB RAM ya da 8 GB ekran kartı gerekir). "
        + "Daha küçük modeller çalışır ama Türkçe açıklamalarda ve düzeltmelerde hata yapabilir; seçersen bunu bilerek seç."),
      grid,
    );
  },

  async voice() {
    const c = W.catalog || (W.catalog = await api("/api/catalog"));
    const nvidia = W.hw?.accel === "cuda";
    const rec = c.whisper_recommendation;
    if (rec && !W.whisperTouched) {  // the suggestion for this computer, until the user picks something else
      W.plan.whisper_model = rec.model;
      W.plan.whisper_device = rec.device;
    }
    const voiceSelect = el("select", { onchange: (e) => { W.plan.tts_voice = e.target.value; } });
    const fillVoices = () => {
      const list = c.voices[W.plan.tts_accent];
      if (!list.includes(W.plan.tts_voice)) W.plan.tts_voice = list[0];
      voiceSelect.replaceChildren(...list.map((v) => el("option", { value: v, selected: v === W.plan.tts_voice },
        `${v.slice(3).replace(/^\w/, (x) => x.toUpperCase())} (${v[1] === "f" ? "kadın" : "erkek"})`)));
    };
    fillVoices();
    show(
      el("h2", {}, "Ses"),
      el("div", { class: "card" },
        el("h3", {}, "Konuşma tanıma (Whisper)"),
        ...c.whisper.map((w) => el("label", { class: "choice" },
          el("input", { type: "radio", name: "whisper", checked: W.plan.whisper_model === w.id,
            onchange: () => { W.plan.whisper_model = w.id; W.whisperTouched = true; } }),
          el("span", {}, el("strong", {}, w.name), ` — ${w.description_tr} (${w.download_mb} MB)`,
            rec?.model === w.id && el("span", { class: "badge recommended" }, " ✓ Bu bilgisayar için önerilen")))),
        rec && el("p", { class: "muted small" }, rec.note_tr),
        el("h4", {}, "Nerede çalışsın?"),
        el("label", { class: "choice" }, el("input", { type: "radio", name: "dev", checked: W.plan.whisper_device === "cuda",
          disabled: !nvidia, onchange: () => { W.plan.whisper_device = "cuda"; W.whisperTouched = true; } }),
          el("span", {}, "Ekran kartı (önerilen)", !nvidia && el("span", { class: "muted" }, " — NVIDIA kart yok"))),
        el("label", { class: "choice" }, el("input", { type: "radio", name: "dev", checked: W.plan.whisper_device === "cpu",
          onchange: () => { W.plan.whisper_device = "cpu"; W.whisperTouched = true; } }),
          el("span", {}, "İşlemci", el("span", { class: "muted" }, nvidia ? " — ekran kartından yavaş" : " — bu bilgisayarda tek seçenek")))),
      el("div", { class: "card" },
        el("h3", {}, "Yapay zekanın sesi (Kokoro)"),
        el("label", { class: "choice" }, el("input", { type: "radio", name: "acc", checked: W.plan.tts_accent === "a",
          onchange: () => { W.plan.tts_accent = "a"; fillVoices(); } }), el("span", {}, "Amerikan aksanı")),
        el("label", { class: "choice" }, el("input", { type: "radio", name: "acc", checked: W.plan.tts_accent === "b",
          onchange: () => { W.plan.tts_accent = "b"; fillVoices(); } }), el("span", {}, "İngiliz aksanı")),
        el("p", {}, "Ses: ", voiceSelect),
        el("p", { class: "muted small" }, "Sesi kurulumdan sonraki test adımında dinleyebilir, Ayarlar'dan istediğin zaman değiştirebilirsin.")),
    );
  },

  async extras() {
    const s = W.state.installed;
    const t = W.catalog.translation;
    show(
      el("h2", {}, "Ek bileşenler"),
      el("label", { class: "choice card" }, el("input", { type: "checkbox", checked: W.plan.dictionary || s.dictionary,
        disabled: s.dictionary, onchange: (e) => { W.plan.dictionary = e.target.checked; } }),
        el("span", {}, el("strong", {}, "Çevrimdışı İngilizce–Türkçe sözlük"), s.dictionary ? " — kurulu ✓" : " (önerilen)",
          el("div", { class: "muted small" }, "Kelimeye tıklayınca anlamı. ~520 MB indirilir, işlenince ~13 MB'a iner; ham dosya silinir."))),
      el("label", { class: "choice card" }, el("input", { type: "checkbox", checked: W.plan.translation || t.installed,
        disabled: t.installed, onchange: (e) => { W.plan.translation = e.target.checked; } }),
        el("span", {}, el("strong", {}, t.name), t.installed ? " — kurulu ✓" : ` (isteğe bağlı, ${size(t.size_bytes)})`,
          el("div", { class: "muted small" }, t.description_tr))),
      el("label", { class: "choice card" }, el("input", { type: "checkbox", checked: W.plan.shortcut,
        onchange: (e) => { W.plan.shortcut = e.target.checked; } }),
        el("span", {}, el("strong", {}, W.state.platform === "linux" ? "Uygulama menüsüne ve masaüstüne kısayol oluştur"
          : "Masaüstüne kısayol oluştur"),
          el("div", { class: "muted small" }, "Bilgisayarında değişiklik yapılan tek şey budur (izninle)."))),
    );
  },

  async summary() {
    W.plan.copy_from_system = {};
    for (const m of W.catalog?.models || []) {
      if (W.plan.models.includes(m.id) && m.system_copy && W.copyChoice[m.id] !== false) W.plan.copy_from_system[m.id] = m.system_copy;
    }
    const sum = await api("/api/plan", { method: "POST", body: W.plan });
    const enough = sum.disk_free_gb >= sum.disk_needed_gb;
    show(
      el("h2", {}, "Özet"),
      el("table", {},
        el("tr", {}, el("th", {}, "Bileşen"), el("th", { class: "num" }, "İndirme")),
        ...sum.rows.map((r) => el("tr", {}, el("td", {}, r.title),
          el("td", { class: "num" }, r.installed ? "kurulu ✓" : r.size ? size(r.size) : "—")))),
      el("div", { class: "card" }, el("dl", { class: "kv" },
        el("dt", {}, "Toplam indirme"), el("dd", {}, size(sum.total_bytes)),
        el("dt", {}, "Gereken disk"), el("dd", {}, `~${sum.disk_needed_gb} GB (boş: ${sum.disk_free_gb} GB)`),
        el("dt", {}, "Tahmini süre"), el("dd", {}, sum.minutes_estimate ? `~${sum.minutes_estimate} dakika (internet hızına bağlı)` : "1 dakikadan az"))),
      !enough && el("div", { class: "card alert err" }, "⚠️ Disk alanı yetersiz. Bazı modelleri seçimden çıkarın ya da yer açın."),
      W.state.app_running && el("div", { class: "card alert" }, "⚠️ Uygulama açık; kurmadan önce kapatın."),
      el("p", { class: "muted small" }, "İndirmeler yarıda kalırsa sihirbaz kaldığı yerden devam eder — kapatıp tekrar açsan bile."),
    );
    $("#next").textContent = "Kur ⬇";
    $("#next").disabled = !enough;
  },

  async install() {
    const list = el("div");
    const footer = el("div", { class: "actions" });
    show(el("h2", {}, "Kuruluyor…"), list, footer);
    $("#next").disabled = true;
    const tick = async () => {
      const s = await api("/api/install/status");
      list.replaceChildren(...s.tasks.map(renderTask));
      if (s.running) return;
      clearInterval(W.poll);
      const failed = s.tasks.filter((t) => t.status === "failed");
      view.querySelector("h2").textContent = failed.length ? "Kurulum tamamlandı (bazı bileşenler kurulamadı)" : "Kurulum tamamlandı ✓";
      footer.replaceChildren(failed.length
        ? el("button", { class: "ghost", onclick: async () => { await api("/api/install/retry", { method: "POST" }); W.poll = setInterval(tick, 700); footer.replaceChildren(); } },
          `↻ Kurulamayanları tekrar dene (${failed.length})`)
        : "");
      $("#next").disabled = false;
      $("#next").textContent = "Test et →";
    };
    W.poll = setInterval(tick, 700);
    tick();
  },

  async test() {
    const box = el("div");
    show(el("h2", {}, "Kısa test"), el("p", { class: "muted" },
      "Her bileşen gerçek bir örnekle denenir: dil modelinin hızı, konuşma tanıma ve ses."), box);
    $("#next").disabled = true;
    const status = await api("/api/test/status");
    if (!status.running && !status.llm) await api("/api/test", { method: "POST", body: {} });
    const tick = async () => {
      const t = await api("/api/test/status");
      box.replaceChildren(renderTest(t));
      if (t.running) return;
      clearInterval(W.poll);
      $("#next").disabled = false;
    };
    W.poll = setInterval(tick, 1000);
    tick();
  },

  async done() {
    const s = await api("/api/state");
    const isNew = W.state.mode === "new_machine";
    $("#next").hidden = true;
    show(
      el("h2", {}, "Hazır! 🎉"),
      el("div", { class: "card" }, el("dl", { class: "kv" },
        el("dt", {}, "Varsayılan model"), el("dd", {}, s.profile?.default_model || "—"),
        el("dt", {}, "Uygulamayı açmak için"), el("dd", {}, s.platform === "linux" ? `bash ${s.start_path}` : s.start_path),
        W.plan.shortcut && el("dt", {}, "Kısayol"), W.plan.shortcut && el("dd", {},
          s.platform === "linux" ? "Uygulama menüsünde ve masaüstünde \"English Practice\"" : "Masaüstünde \"English Practice\""))),
      el("div", { class: "actions" },
        el("button", { class: "primary", onclick: () => finish(true) }, "▶ Uygulamayı başlat"),
        !isNew && el("button", { class: "ghost", onclick: () => finish(false) }, "Kapat")),
    );
  },

  async maintenance() {
    const s = W.state;
    const catalog = await api("/api/catalog");
    W.catalog = catalog;
    const names = Object.fromEntries(catalog.models.map((m) => [m.id, m.name]));
    const installed = s.installed.models;
    $("#next").hidden = true;
    const modelRows = installed.map((m) => el("tr", {},
      el("td", {}, names[m] || m),
      el("td", {}, m === s.profile?.default_model ? "✓ varsayılan"
        : el("button", { class: "ghost", onclick: async () => { await api("/api/profile/default", { method: "POST", body: { model: m } }); boot(); } }, "Varsayılan yap")),
      el("td", { class: "num" }, s.profile?.benchmarks?.[m] ? `${s.profile.benchmarks[m].tokens_per_sec} token/sn` : "—"),
      el("td", {}, el("button", { class: "ghost danger", onclick: async () => {
        if (!confirm(`${m} silinsin mi? (Gerekirse tekrar indirilebilir.)`)) return;
        try { await api("/api/maintenance/remove-model", { method: "POST", body: { model: m } }); boot(); } catch (e) { alert(e.message); }
      } }, "Sil"))));
    const runJob = (path) => async () => {
      try {
        await api(path, { method: "POST" });
        setSteps(["maintenance", "install", "done"], 1);
      } catch (e) { alert(e.message); }
    };
    show(
      el("h2", {}, `Bakım — ${s.machine_name}`),
      s.app_running && el("div", { class: "card alert" }, "⚠️ Uygulama açık. Kurma/silme/onarma işlemleri için önce kapatın."),
      el("div", { class: "card" }, el("h3", {}, "Kurulu dil modelleri"),
        el("table", {}, el("tr", {}, el("th", {}, "Model"), el("th", {}, ""), el("th", { class: "num" }, "Hız"), el("th", {}, "")), ...modelRows),
        el("div", { class: "actions" },
          el("button", { class: "primary", onclick: () => { W.plan.models = []; setSteps(["maintenance", "models", "summary", "install", "test", "done"], 1); } }, "➕ Model ekle"),
          el("button", { class: "ghost", onclick: () => setSteps(["maintenance", "test", "done"], 1) }, "⏱ Hız testi"))),
      el("div", { class: "grid" },
        el("div", { class: "card" }, el("h3", {}, "🔧 Onar"), el("p", { class: "muted small" }, "Eksik ya da bozuk dosyaları yeniden indirir."),
          el("button", { class: "ghost", onclick: runJob("/api/maintenance/repair") }, "Onar")),
        el("div", { class: "card" }, el("h3", {}, "⬆ Güncelle"), el("p", { class: "muted small" }, "Ollama'nın yeni sürümü ve Python paketleri."),
          el("button", { class: "ghost", onclick: runJob("/api/maintenance/update") }, "Güncelle")),
        el("div", { class: "card" }, el("h3", {}, "🖥 Yeniden tara"), el("p", { class: "muted small" }, "Ekran kartı değiştiyse donanım bilgisini yeniler."),
          el("button", { class: "ghost", onclick: async () => { const hw = await api("/api/maintenance/rescan", { method: "POST" }); alert(`Tarandı: ${hw.gpu || "ekran kartı yok"}, ${hw.ram_gb} GB RAM`); boot(); } }, "Tara"))),
      el("p", { class: "muted small" }, "Kullanıcı verilerine dokunulmaz; her bakım işleminden önce data/backups içine yedek alınır."),
      el("div", { class: "actions" }, el("button", { class: "primary", onclick: () => finish(true) }, "▶ Uygulamayı başlat"),
        el("button", { class: "ghost", onclick: () => finish(false) }, "Kapat")),
    );
  },
};

const BEFORE_NEXT = {
  async models() {
    const s = W.state;
    const any = W.plan.models.length || s.installed.models.length;
    if (!any) {
      alert("En az bir dil modeli seçin.");
      return false;
    }
    if (!W.plan.default_model) W.plan.default_model = W.plan.models[0] || s.installed.models[0];
    if (s.mode === "maintenance" && !W.plan.models.length) {
      alert("Eklemek için bir model seçin.");
      return false;
    }
  },
  async summary() {
    if (!confirm("Kurulum başlasın mı?")) return false;
    await api("/api/install", { method: "POST", body: W.plan });
  },
  async test() {
    const t = await api("/api/test/status");
    const pick = document.querySelector("input[name=test-default]:checked");
    if (pick) await api("/api/profile/default", { method: "POST", body: { model: pick.value } });
    return t;
  },
};

function renderTask(t) {
  const labels = { pending: "bekliyor", running: "kuruluyor…", done: "✓ tamam", failed: "✗ hata", skipped: "✓ zaten var" };
  const speed = t.status === "running" && t.speed > 1e5 ? ` · ${(t.speed / 1e6).toFixed(1)} MB/s` : "";
  const eta = t.status === "running" && t.eta ? ` · ~${Math.ceil(t.eta / 60)} dk kaldı` : "";
  return el("div", { class: `card task ${t.status}` },
    el("span", { class: "title" }, t.title),
    el("span", { class: `state ${t.status}` }, labels[t.status]),
    el("div", { class: "bar" }, el("span", { style: `width:${Math.round(t.progress * 100)}%` })),
    (t.detail || speed) && el("div", { class: "detail" }, `${t.detail}${speed}${eta}`),
    t.error && el("div", { class: "err" }, t.error));
}

function renderTest(t) {
  const box = el("div");
  if (t.running) box.append(el("p", {}, el("span", { class: "spinner" }), `Test ediliyor: ${t.current || "…"}`));
  const llm = Object.entries(t.llm || {});
  if (llm.length) {
    box.append(el("table", {},
      el("tr", {}, el("th", {}, "Model"), el("th", { class: "num" }, "Hız"), el("th", { class: "num" }, "İlk kelime"),
        el("th", { class: "num" }, "Yükleme"), el("th", {}, "Varsayılan")),
      ...llm.map(([m, r]) => el("tr", {},
        el("td", {}, m),
        el("td", { class: "num" }, r.ok ? `${r.tokens_per_sec} token/sn` : "✗"),
        el("td", { class: "num" }, r.ok ? `${r.first_token_ms} ms` : "—"),
        el("td", { class: "num" }, r.ok ? `${r.load_s} sn` : "—"),
        el("td", {}, r.ok ? el("input", { type: "radio", name: "test-default", value: m,
          checked: m === (t.suggested_default || W.state.profile?.default_model) }) : "")))));
    const sample = llm.find(([, r]) => r.ok);
    if (sample) box.append(el("details", {}, el("summary", { class: "muted small" }, "Örnek cevap"),
      el("p", { class: "small" }, sample[1].sample)));
  }
  if (t.whisper) box.append(el("div", { class: `card ${t.whisper.ok ? "alert ok" : "alert err"}` },
    t.whisper.ok ? `🎤 Konuşma tanıma (${t.whisper.device === "cuda" ? "ekran kartı" : "işlemci"}): ${t.whisper.audio_seconds} sn ses ${t.whisper.elapsed_ms} ms'de yazıya döküldü — "${t.whisper.text}"`
      : `🎤 Konuşma tanıma çalışmadı: ${t.whisper.error}`));
  if (t.kokoro) {
    const card = el("div", { class: `card ${t.kokoro.ok ? "alert ok" : "alert err"}` },
      t.kokoro.ok ? `🔊 Ses: örnek cümle ${t.kokoro.elapsed_ms} ms'de üretildi. ` : `🔊 Ses çalışmadı: ${t.kokoro.error}`);
    if (t.kokoro.ok) card.append(el("button", { class: "ghost", onclick: () => new Audio(`/api/test/sample.wav?${Date.now()}`).play() }, "▶ Dinle"));
    box.append(card);
  }
  for (const w of t.warnings || []) box.append(el("div", { class: "card alert" }, `⚠️ ${w}`));
  if (!t.running && llm.length && !(t.warnings || []).length) box.append(el("p", { class: "muted" }, "Her şey yolunda görünüyor. ✓"));
  return box;
}

async function finish(startApp) {
  try { await api(`/api/finish?start_app=${startApp}`, { method: "POST" }); } catch {}
  show(el("h2", {}, startApp ? "Uygulama açılıyor…" : "Kapatıldı."),
    el("p", { class: "muted" }, "Bu sekmeyi kapatabilirsin."));
  $("#next").hidden = true;
  $("#back").hidden = true;
}

/* -------------------------------------------------------------------- boot */

async function boot() {
  W.state = await api("/api/state");
  const mode = W.state.mode;
  // Start from this computer's current choices (maintenance must not reset them).
  const p = W.state.profile || {};
  if (p.whisper_model) W.plan.whisper_model = p.whisper_model;
  if (p.whisper_device) W.plan.whisper_device = p.whisper_device;
  if (p.default_model) W.plan.default_model = p.default_model;
  if (W.state.settings?.tts_accent) W.plan.tts_accent = W.state.settings.tts_accent;
  if (W.state.settings?.tts_voice) W.plan.tts_voice = W.state.settings.tts_voice;
  if (W.state.installing) setSteps(["welcome", "install", "test", "done"], 1);
  else if (mode === "maintenance") setSteps(["maintenance"]);
  else setSteps(["welcome", "hardware", "models", "voice", "extras", "summary", "install", "test", "done"]);
}

boot().catch((err) => show(el("div", { class: "card alert err" }, `⚠️ ${err.message}`)));
