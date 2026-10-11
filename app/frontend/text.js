"use strict";

/**
 * Shared text rendering. Every piece of learning content shown in the app (chat
 * bubbles, corrections, history, lessons, writing feedback) goes through here, so
 * features like clickable words live in one place.
 *
 * Do not set .textContent of such elements directly; use Text.render / Text.append.
 *
 * With { words: true } each English word becomes a <span class="w">; a click on one
 * opens the word popup (vocab.js listens for it on the document).
 */
const Text = {
  WORD: /([A-Za-z]+(?:['’][A-Za-z]+)*)/,
  // Term markup in the hand-written content (lessons, exams): [en:English] → blue chip with clickable
  // words, [tr:Türkçe] → italic, [key:.] → a keyboard key. See app/content/lessons/README.md.
  MARK: /\[(en|tr|key):([^\[\]]+)\]/g,

  /** Show `text` in `el` (replacing what was there). */
  render(el, text, { words = false } = {}) {
    text = text ?? "";
    el._text = Text.plain(text);
    if (!words && !text.includes("[")) {
      el.textContent = text;
      return el;
    }
    el.textContent = "";
    let last = 0;
    for (const m of text.matchAll(Text.MARK)) {
      Text._words(el, text.slice(last, m.index), words);
      const [, kind, inner] = m;
      if (kind === "en") {
        el.append(Text._words(Object.assign(document.createElement("span"), { className: "en-term" }), inner, true));
      } else {
        el.append(Object.assign(document.createElement(kind === "key" ? "kbd" : "span"),
          { className: `${kind}-term`, textContent: inner }));
      }
      last = m.index + m[0].length;
    }
    Text._words(el, text.slice(last), words);
    return el;
  },

  /** The text without term markup ("[en:does]" → "does"). */
  plain(text) {
    return (text ?? "").replace(Text.MARK, "$2");
  },

  /** Append `text` to `el`; with `words`, each English word is a clickable <span class="w">. */
  _words(el, text, words) {
    if (!words) {
      if (text) el.append(text);
      return el;
    }
    for (const part of text.split(Text.WORD)) {
      if (!part) continue;
      if (Text.WORD.test(part) && /^[A-Za-z]/.test(part)) {
        const w = document.createElement("span");
        w.className = "w";
        w.textContent = part;
        el.append(w);
      } else {
        el.append(part);
      }
    }
    return el;
  },

  // Whisper word confidence below this = "not heard clearly" (a rough hint, not a pronunciation score).
  UNCLEAR_BELOW: 0.6,

  /**
   * Show what the learner said or wrote, with marks:
   * - `errors` ([{wrong, right, explanation}] from a correction): the wrong part becomes
   *   <span class="msg-err"> (red);
   * - `words` ([{word, probability}] from Whisper, in order): words it was unsure about become
   *   <span class="w unclear"> — a click plays the right pronunciation (vocab.js).
   * An error mark wins where both overlap.
   */
  renderAnnotated(el, text, { words = null, errors = null } = {}) {
    Text.render(el, text);
    const full = el._text;
    // Same length as `full` ("İ".toLowerCase() is two characters and would shift every mark after it).
    const lower = Array.from(full, (c) => { const l = c.toLowerCase(); return l.length === c.length ? l : c; }).join("");
    const isLetter = (c) => c !== undefined && /[A-Za-z'’]/.test(c);
    const find = (needle, from) => {  // a whole-word, case-insensitive occurrence ("a" not inside "cat")
      const n = needle.toLowerCase();
      for (let at = lower.indexOf(n, from); at >= 0; at = lower.indexOf(n, at + 1)) {
        if (!isLetter(full[at - 1]) && !isLetter(full[at + n.length])) return at;
      }
      return -1;
    };
    const marks = [];
    const free = (start, end) => !marks.some((m) => start < m.end && m.start < end);
    for (const e of errors || []) {
      const wrong = (e.wrong || "").trim();
      for (let at = wrong ? find(wrong, 0) : -1; at >= 0; at = find(wrong, at + 1)) {
        if (free(at, at + wrong.length)) {
          marks.push({ start: at, end: at + wrong.length, error: e });
          break;
        }
      }
    }
    let pos = 0;
    for (const w of words || []) {
      const word = w.word.match(Text.WORD)?.[0];
      const at = word ? find(word, pos) : -1;
      if (at < 0) continue;
      pos = at + word.length;
      if (w.probability < Text.UNCLEAR_BELOW && free(at, pos)) marks.push({ start: at, end: pos, unclear: w });
    }
    if (!marks.length) return el;

    marks.sort((a, b) => a.start - b.start);
    el.textContent = "";
    pos = 0;
    for (const m of marks) {
      if (m.start > pos) el.append(full.slice(pos, m.start));
      const span = document.createElement("span");
      span.textContent = full.slice(m.start, m.end);
      if (m.error) {
        span.className = "msg-err";
        span.title = `${m.error.wrong} → ${m.error.right}${m.error.explanation ? ` — ${m.error.explanation}` : ""}`;
      } else {
        span.className = "w unclear";
        span.title = `Net anlaşılmadı (%${Math.round(m.unclear.probability * 100)}) — doğru telaffuzu dinlemek için `
          + "tıkla. Kaba bir göstergedir, tam telaffuz analizi değil.";
      }
      el.append(span);
      pos = m.end;
    }
    el.append(full.slice(pos));
    return el;
  },

  /** What the learner said (Whisper's word confidences → pronunciation hints). */
  renderSpoken(el, text, words) {
    return Text.renderAnnotated(el, text, { words });
  },

  /** Add streamed text to `el` (cheap: called for every LLM token; plain text). */
  append(el, chunk) {
    el._text = (el._text ?? el.textContent) + chunk;
    el.textContent = el._text;
    return el;
  },

  /** The plain text currently shown in `el`. */
  get(el) {
    return el._text ?? el.textContent;
  },

  /** Create an element showing `text`. */
  create(tag, text, className = "", options = {}) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    return Text.render(el, text, options);
  },

  /** The sentence around a clicked word (context for meanings / notebook). */
  sentenceAround(wordEl) {
    const host = wordEl.closest("[data-text-host]") || wordEl.parentElement;
    const full = Text.get(host);
    let offset = 0;
    for (const node of host.childNodes) {
      if (node === wordEl) break;
      offset += node.textContent.length;
    }
    const start = Math.max(full.lastIndexOf(".", offset - 1), full.lastIndexOf("!", offset - 1),
      full.lastIndexOf("?", offset - 1), full.lastIndexOf("\n", offset - 1)) + 1;
    const ends = [".", "!", "?", "\n"].map((c) => full.indexOf(c, offset)).filter((i) => i >= 0);
    const end = ends.length ? Math.min(...ends) + 1 : full.length;
    return full.slice(start, end).trim();
  },
};
