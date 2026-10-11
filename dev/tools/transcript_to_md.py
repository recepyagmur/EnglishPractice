"""Turn a Claude Code session transcript (.jsonl) into a readable Markdown file:
the user's messages and the assistant's text, word for word; tool calls and their
output are left out (they stay in the .jsonl).

Usage:
  runtime\\python\\python.exe dev\\tools\\transcript_to_md.py <transcript.jsonl> <out.md> [title]
"""

import json
import re
import sys
from pathlib import Path

SKIP_PREFIXES = ("<task-notification", "[SYSTEM NOTIFICATION", "<system-reminder", "<command-", "<local-command")


def user_text(message: dict) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        text = content
    else:
        parts = [b.get("text", "") for b in content or [] if b.get("type") == "text"]
        if not parts:
            return None  # tool results only
        text = "\n".join(parts)
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S).strip()
    if not text or text.startswith(SKIP_PREFIXES):
        return None
    return text


def assistant_text(message: dict) -> str | None:
    parts = [b.get("text", "") for b in message.get("content") or [] if b.get("type") == "text"]
    text = "\n".join(p for p in parts if p.strip()).strip()
    return text or None


def convert(src: Path, out: Path, title: str) -> tuple[int, int]:
    lines = [f"# {title}", "",
             "Kullanıcı mesajları ve asistan açıklamaları kelimesi kelimesine; araç çağrıları/çıktıları hariç.",
             f"Tam ham döküm: `{src.name}` (araç çağrıları dahil, git'te yok).", ""]
    n_user = n_assistant = 0
    for raw in src.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if entry.get("isMeta") or entry.get("isSidechain"):
            continue
        if entry.get("type") == "user":
            text = user_text(entry.get("message") or {})
            if text:
                n_user += 1
                lines += ["", "---", "", f"## 👤 Kullanıcı ({n_user})", "", text, ""]
        elif entry.get("type") == "assistant":
            text = assistant_text(entry.get("message") or {})
            if text:
                n_assistant += 1
                lines += ["", "### 🤖 Asistan", "", text, ""]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return n_user, n_assistant


if __name__ == "__main__":
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    title = sys.argv[3] if len(sys.argv) > 3 else f"Sohbet dökümü — {src.stem}"
    users, assistants = convert(src, out, title)
    print(f"{out}: {users} kullanıcı mesajı, {assistants} asistan metni")
