"use strict";

/**
 * Model cards shared by the app (Ayarlar → Modeller) and the setup wizard (step 3):
 * the same card with the same fit badges. Self-contained (the wizard has no other
 * app script); the wizard loads it from /shared/model-cards.js. Styles: model-cards.css.
 *
 * A model is a catalog entry from setup/installer.catalog_for(): name, description_tr,
 * size_bytes, quality, speed, badge (recommended | fit | slow | no), installed.
 */
const ModelCards = (() => {
  const BADGES = {
    recommended: "✓ Önerilir", fit: "✓ Uygun", slow: "⚠ Yavaş olabilir", no: "✗ Sığmaz",
  };

  /** Tiny element builder: strings become text nodes; null / false children are skipped. */
  function h(tag, attrs = {}, ...children) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") e.className = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (v !== false && v !== null && v !== undefined) e.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) e.append(c);
    return e;
  }

  const size = (bytes) => (bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`);

  const stars = (n) => h("span", { class: "stars", title: `${n}/5` },
    "★".repeat(n), h("span", { class: "off" }, "★".repeat(5 - n)));

  const badge = (m) => (m.installed
    ? h("span", { class: "badge installed" }, "Kurulu ✓")
    : h("span", { class: `badge ${m.badge}` }, BADGES[m.badge]));

  /**
   * One card. opts: selectable (click toggles, keyboard too), selected, disabled,
   * onclick, footer (nodes under the card's info: checkboxes, buttons…).
   */
  function card(m, opts = {}) {
    const classes = ["model-card", opts.selectable && "selectable", opts.selected && "selected",
      opts.disabled && "disabled"].filter(Boolean).join(" ");
    const attrs = { class: classes };
    if (opts.selectable) {
      Object.assign(attrs, {
        role: "checkbox", "aria-checked": String(Boolean(opts.selected)), tabindex: 0,
        onclick: opts.onclick,
        onkeydown: (e) => {
          if (e.target === e.currentTarget && (e.key === " " || e.key === "Enter")) {
            e.preventDefault();
            opts.onclick?.(e);
          }
        },
      });
    }
    return h("div", attrs,
      h("div", { class: "row" }, h("span", { class: "name" }, m.name), badge(m)),
      h("div", { class: "muted small" }, m.description_tr),
      h("div", { class: "row small" }, `İndirme: ${size(m.size_bytes)}`,
        h("span", {}, "· Kalite ", stars(m.quality)), h("span", {}, "· Hız ", stars(m.speed))),
      speedLine(m),
      m.verified === false && h("div", { class: "small warn-text" },
        "⚠ Türkçe açıklamalarda ve düzeltmelerde hata yapabilir (testlerimizden geçmedi)."),
      ...(opts.footer || []));
  }

  /** "On this computer: ~X tokens/s, a short reply in ~Y s" (an estimate; the speed test decides). */
  function speedLine(m) {
    if (!m.est_tps || m.badge === "no") return null;
    const reply = Math.max(1, Math.round(30 / m.est_tps));
    return h("div", { class: "small muted" },
      `Bu bilgisayarda tahmini: ~${m.est_tps} kelime parçası/sn — kısa bir cevap ~${reply} sn`);
  }

  return { BADGES, h, size, stars, card };
})();
