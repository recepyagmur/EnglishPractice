"use strict";

/* Progress page: stat tiles, 30-day activity, error categories chart, weak points. */

const progressUi = {
  days: Number(store.get("errorRangeDays")) || 30,
  el: {
    tiles: $("#stat-tiles"), activity: $("#activity"), chart: $("#error-chart"), table: $("#error-table"),
    range: $("#error-range"), weak: $("#weak-points"),
  },
};

const SERIES = [
  { key: "speech", label: "Konuşma", cssVar: "--series-1" },
  { key: "writing", label: "Yazma", cssVar: "--series-2" },
];

async function loadProgressPage() {
  loadSessionList();
  renderRangeButtons();
  try {
    const [stats, weak] = await Promise.all([
      api(`/api/stats?days=${progressUi.days}`),
      api(`/api/weak-points?days=${progressUi.days}`),
    ]);
    // The tiles and the calendar always describe the last 30 days.
    const month = progressUi.days === 30 ? stats : await api("/api/stats?days=30");
    renderTiles(month);
    renderActivity(month.streak.calendar);
    renderErrorChart(stats.errors);
    renderWeakPoints(weak);
  } catch (err) {
    progressUi.el.tiles.replaceChildren(Text.create("p", `⚠️ ${err.message}`, "muted"));
  }
}

/* ------------------------------------------------------------------ tiles */

function formatMinutes(min) {
  if (min > 0 && min < 1) return "<1 dk";
  if (min < 60) return `${Math.round(min)} dk`;
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return m ? `${h} sa ${m} dk` : `${h} sa`;
}

function renderTiles(s) {
  const t = s.totals;
  const tiles = [
    ["🔥", s.streak.current ? `${s.streak.current} gün` : "0 gün", "Seri",
      s.streak.today_active ? `en uzun: ${s.streak.longest} gün` : "bugün pratik yaparak seriyi sürdür"],
    ["⏱", formatMinutes(t.practice_minutes), "Pratik süresi", `${t.sessions} oturum`],
    ["🎤", formatMinutes(t.speaking_minutes), "Konuştuğun süre", `${t.user_messages} mesaj`],
    ["✍️", `${t.writing_words}`, "Yazılan kelime", `${t.writings} yazı · sohbette ${t.chat_words}`],
    ["📒", `${t.vocab_learned} / ${t.vocab_total}`, "Öğrenilen kelime", "21+ gün aralıklı tekrar = öğrenildi"],
  ];
  progressUi.el.tiles.replaceChildren(...tiles.map(([icon, value, label, sub]) => {
    const tile = document.createElement("div");
    tile.className = "stat-tile";
    tile.append(Text.create("div", `${icon} ${label}`, "stat-label"), Text.create("div", value, "stat-value"),
      Text.create("div", sub, "stat-sub"));
    return tile;
  }));
}

/* --------------------------------------------------------------- activity */

// Sequential scale: one hue (series 1), light → dark with practice minutes.
const ACTIVITY_STEPS = [[0, 0], [10, 1], [20, 2], [40, 3], [Infinity, 4]];

function activityLevel(minutes, active) {
  if (!active) return 0;
  for (const [limit, level] of ACTIVITY_STEPS.slice(1)) if (minutes < limit) return level;
  return 4;
}

function renderActivity(calendar) {
  const box = progressUi.el.activity;
  box.replaceChildren();
  const grid = document.createElement("div");
  grid.className = "activity-grid";
  for (const day of calendar) {
    const cell = document.createElement("div");
    cell.className = `activity-cell l${activityLevel(day.minutes, day.active)}`;
    const label = new Date(day.date).toLocaleDateString("tr-TR", { day: "numeric", month: "short", weekday: "short" });
    cell.title = day.active ? `${label}: ~${formatMinutes(day.minutes)}` : `${label}: pratik yok`;
    cell.setAttribute("aria-label", cell.title);
    grid.append(cell);
  }
  const legend = document.createElement("div");
  legend.className = "activity-legend muted small";
  legend.append(Text.create("span", "Az"));
  for (let i = 0; i <= 4; i++) {
    const sw = document.createElement("span");
    sw.className = `activity-cell l${i}`;
    legend.append(sw);
  }
  legend.append(Text.create("span", "Çok"));
  box.append(grid, legend);
}

/* ------------------------------------------------------------ error chart */

function renderRangeButtons() {
  for (const b of progressUi.el.range.querySelectorAll("button")) {
    b.setAttribute("aria-checked", String(Number(b.dataset.days) === progressUi.days));
  }
}

progressUi.el.range.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-days]");
  if (!b) return;
  progressUi.days = Number(b.dataset.days);
  store.set("errorRangeDays", String(progressUi.days));
  loadProgressPage();
});

function renderErrorChart(errs) {
  const chart = progressUi.el.chart;
  chart.replaceChildren();
  const cats = errs.categories;
  if (!cats.length) {
    chart.append(Text.create("p", "Bu dönemde kayıtlı hata yok. Konuştukça ve yazdıkça burada görünecek.", "muted"));
    progressUi.el.table.replaceChildren();
    return;
  }

  const legend = document.createElement("div");
  legend.className = "viz-legend";
  for (const s of SERIES) {
    const item = document.createElement("span");
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = `var(${s.cssVar})`;
    item.append(sw, Text.create("span", s.label));
    legend.append(item);
  }
  chart.append(legend,
    Text.create("div", `${errs.total} hata · ${errs.checked_sentences} cümle kontrol edildi · son ${progressUi.days} gün`,
      "muted small"));

  const max = Math.max(...cats.map((c) => c.total));
  const tip = document.createElement("div");
  tip.className = "viz-tip";
  tip.hidden = true;
  const rows = document.createElement("div");
  rows.className = "hbar-rows";
  for (const c of cats) {
    const row = document.createElement("div");
    row.className = "hbar-row";
    const track = document.createElement("div");
    track.className = "hbar-track";
    const bar = document.createElement("div");
    bar.className = "hbar";
    bar.style.width = `${(c.total / max) * 100}%`;
    for (const s of SERIES) {
      if (!c[s.key]) continue;
      const seg = document.createElement("div");
      seg.className = "hbar-seg";
      seg.style.flexGrow = c[s.key];
      seg.style.background = `var(${s.cssVar})`;
      seg.tabIndex = 0;
      const text = `${categoryLabel(c.id)} · ${s.label}: ${c[s.key]}`;
      seg.setAttribute("aria-label", text);
      const show = (x, y) => {
        Text.render(tip, text);
        tip.hidden = false;
        const box = chart.getBoundingClientRect();
        tip.style.left = `${Math.min(x - box.left + 12, box.width - tip.offsetWidth - 4)}px`;
        tip.style.top = `${y - box.top + 12}px`;
      };
      seg.addEventListener("pointermove", (e) => show(e.clientX, e.clientY));
      seg.addEventListener("pointerleave", () => (tip.hidden = true));
      seg.addEventListener("focus", () => {
        const r = seg.getBoundingClientRect();
        show(r.left + r.width / 2, r.top);
      });
      seg.addEventListener("blur", () => (tip.hidden = true));
      bar.append(seg);
    }
    track.append(bar, Text.create("span", String(c.total), "hbar-value"));
    row.append(Text.create("span", categoryLabel(c.id), "hbar-label"), track);
    rows.append(row);
  }
  chart.append(rows, tip);

  // Table view: the same numbers without the chart.
  const table = progressUi.el.table;
  table.replaceChildren();
  const head = document.createElement("tr");
  for (const h of ["Hata türü", "Konuşma", "Yazma", "Toplam"]) head.append(Text.create("th", h));
  table.append(head);
  for (const c of cats) {
    const tr = document.createElement("tr");
    for (const v of [categoryLabel(c.id), c.speech, c.writing, c.total]) tr.append(Text.create("td", String(v)));
    table.append(tr);
  }
}

/* ------------------------------------------------------------ weak points */

function renderWeakPoints(items) {
  const box = progressUi.el.weak;
  box.replaceChildren();
  if (!items.length) {
    box.append(Text.create("p", "Henüz yeterli veri yok. Biraz konuş ya da yaz; sık yaptığın hatalar burada toplanacak.",
      "muted"));
    return;
  }
  for (const w of items) {
    const card = document.createElement("div");
    card.className = "weak-card";
    const head = document.createElement("div");
    head.className = "weak-head";
    const diff = w.this_week - w.last_week;
    const trend = !w.last_week && !w.this_week ? ""
      : diff < 0 ? `↓ bu hafta ${w.this_week} (geçen hafta ${w.last_week}) — iyileşiyor`
      : diff > 0 ? `↑ bu hafta ${w.this_week} (geçen hafta ${w.last_week})`
      : `bu hafta ${w.this_week}`;
    head.append(Text.create("span", categoryLabel(w.category), "tag"), Text.create("strong", `${w.count} hata`),
      Text.create("span", trend, `muted small ${diff < 0 ? "trend-good" : ""}`));
    card.append(head);
    for (const ex of w.examples) {
      const line = document.createElement("div");
      line.className = "corr-change";
      line.append(Text.create("span", ex.wrong, "wrong"), " → ", Text.create("span", ex.right, "right", { words: true }));
      card.append(line);
      if (ex.explanation) card.append(Text.create("div", ex.explanation, "expl"));
    }
    for (const l of w.lessons || []) {  // the lessons that teach this category
      const link = Text.create("a", `📘 Konuyu öğren: ${l.title_tr} (${l.level})${l.status === "done" ? " ✓" : ""}`,
        "weak-lesson");
      link.href = `#/lesson/${encodeURIComponent(l.id)}`;
      card.append(link);
    }
    const btn = document.createElement("button");
    btn.className = "primary small";
    Text.render(btn, w.practice === "writing" ? "✍️ Yazarak pratik yap" : "🎯 Bu konuda pratik yap");
    btn.addEventListener("click", () => practiceWeakPoint(w));
    const teach = Text.create("button", "🧑‍🏫 Öğretmenle çalış", "ghost small");
    teach.title = "Öğretmen bu konuda kısa alıştırmalar sorsun, cevaplarını kontrol etsin";
    teach.addEventListener("click", () => Teacher.open({
      type: "practice", category: w.category, title: `🎯 ${categoryLabel(w.category)} alıştırması`,
    }));
    card.append(lnode("div", "weak-actions", btn, teach));
    box.append(card);
  }
}

function practiceWeakPoint(w) {
  if (w.practice === "writing") {
    // Spelling / punctuation: practised by writing (a journal entry is short and personal).
    writingUi.type = "journal";
    store.set("writingType", "journal");
    location.hash = "#/writing";
    if (writingUi.types.length) renderWritingTypes();
    return;
  }
  startScenario({ focus: w.category });
}
