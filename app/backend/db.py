import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH, DEFAULT_SETTINGS

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,
    scenario TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    summary_json TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    audio_path TEXT,
    meta_json TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    original TEXT NOT NULL,
    corrected TEXT,
    errors_json TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS error_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correction_id INTEGER REFERENCES corrections(id) ON DELETE CASCADE,
    source TEXT NOT NULL DEFAULT 'speech',
    category TEXT NOT NULL,
    wrong TEXT,
    right TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS writings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    prompt TEXT,
    text TEXT NOT NULL,
    review_json TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vocab (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL,
    meaning_tr TEXT,
    definition TEXT,
    example TEXT,
    source_session_id INTEGER,
    ease REAL NOT NULL DEFAULT 2.5,
    interval INTEGER NOT NULL DEFAULT 0,
    repetitions INTEGER NOT NULL DEFAULT 0,
    due_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_error_log_created ON error_log(created_at);
CREATE INDEX IF NOT EXISTS idx_vocab_due ON vocab(due_date);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Schema changes after the first version, applied in order and tracked with
# PRAGMA user_version. Append only; never edit a migration that has shipped.
MIGRATIONS = [
    # 1: correction details for the side panel and the weak-points page
    """
    ALTER TABLE corrections ADD COLUMN more_natural TEXT;
    ALTER TABLE corrections ADD COLUMN source TEXT;
    ALTER TABLE error_log ADD COLUMN message_id INTEGER;
    ALTER TABLE error_log ADD COLUMN explanation TEXT;
    ALTER TABLE error_log ADD COLUMN taxonomy_version INTEGER NOT NULL DEFAULT 1;
    CREATE INDEX IF NOT EXISTS idx_error_log_category ON error_log(category);
    CREATE INDEX IF NOT EXISTS idx_corrections_message ON corrections(message_id);
    """,
    # 2: the full scenario definition of role-play sessions (custom ones have no id)
    """
    ALTER TABLE sessions ADD COLUMN scenario_json TEXT;
    """,
    # 3: writing-mode errors in the same error log (source = 'writing')
    """
    ALTER TABLE error_log ADD COLUMN writing_id INTEGER REFERENCES writings(id) ON DELETE CASCADE;
    CREATE INDEX IF NOT EXISTS idx_error_log_writing ON error_log(writing_id);
    """,
    # 4: vocabulary notebook details (the sentence a word was saved from, review stats)
    """
    ALTER TABLE vocab ADD COLUMN context TEXT;
    ALTER TABLE vocab ADD COLUMN source TEXT;
    ALTER TABLE vocab ADD COLUMN ipa TEXT;
    ALTER TABLE vocab ADD COLUMN last_reviewed_at TEXT;
    ALTER TABLE vocab ADD COLUMN review_count INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE vocab ADD COLUMN lapses INTEGER NOT NULL DEFAULT 0;
    CREATE UNIQUE INDEX IF NOT EXISTS idx_vocab_word ON vocab(word COLLATE NOCASE);
    """,
    # 5: lessons (A1–C1): progress per lesson id (content lives in app/content/lessons/)
    """
    CREATE TABLE IF NOT EXISTS lesson_progress (
        lesson_id TEXT PRIMARY KEY,
        first_opened_at TEXT NOT NULL,
        last_opened_at TEXT NOT NULL,
        best_score REAL,
        last_score REAL,
        attempts INTEGER NOT NULL DEFAULT 0,
        practice_count INTEGER NOT NULL DEFAULT 0,
        completed_at TEXT
    );
    """,
    # 6: a learner message that is not English (Turkish, random letters) — not "perfect"
    """
    ALTER TABLE corrections ADD COLUMN not_english INTEGER NOT NULL DEFAULT 0;
    """,
    # 7: level exams (content: app/content/exams/), one row per attempt
    """
    CREATE TABLE IF NOT EXISTS exam_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        questions_json TEXT,
        score REAL,
        passed INTEGER,
        result_json TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_exam_attempts_level ON exam_attempts(level);
    """,
    # 8: teacher sessions (mode 'teacher'): what they were opened from (lesson, correction, weak point)
    """
    ALTER TABLE sessions ADD COLUMN context_json TEXT;
    """,
    # 9: practice days of activities that keep no dated rows of their own (flashcard reviews only kept
    # the last review date, so reviewing a word again erased an earlier day from the streak; lessons)
    """
    CREATE TABLE IF NOT EXISTS practice_days (
        day TEXT NOT NULL,
        kind TEXT NOT NULL,
        minutes REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (day, kind)
    );
    INSERT OR IGNORE INTO practice_days (day, kind, minutes)
        SELECT date(last_reviewed_at, 'localtime'), 'vocab', 0.5 * COUNT(*) FROM vocab
        WHERE last_reviewed_at IS NOT NULL GROUP BY 1;
    """,
    # 10: level word lists (app/content/vocab/): a notebook word learned from a list keeps its level and
    # part of speech; example sentences generated on request (checked) are kept for the next time
    """
    ALTER TABLE vocab ADD COLUMN level TEXT;
    ALTER TABLE vocab ADD COLUMN pos TEXT;
    CREATE TABLE IF NOT EXISTS word_examples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT NOT NULL,
        en TEXT NOT NULL,
        tr TEXT NOT NULL,
        model TEXT,
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_word_examples_word ON word_examples(word COLLATE NOCASE);
    """,
    # 11: the first-run level question is only for new users: someone who already used the app
    # (init_db has just inserted level_confirmed = '0' for everyone) keeps the level they have
    """
    UPDATE settings SET value = '1' WHERE key = 'level_confirmed' AND (
        EXISTS (SELECT 1 FROM messages) OR EXISTS (SELECT 1 FROM lesson_progress) OR EXISTS (SELECT 1 FROM vocab)
        OR EXISTS (SELECT 1 FROM writings) OR EXISTS (SELECT 1 FROM exam_attempts));
    """,
    # 12: work in progress kept until the learner deletes it (backend/ui_state.py): lesson exercises and
    # own sentences ("lesson:<id>"), a running exam ("exam:<level>")
    """
    CREATE TABLE IF NOT EXISTS ui_state (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    # 13: patterns being learned (🧩 Kalıplar, backend/patterns.py): spaced repetition as in vocab,
    # keyed by the content id (app/content/patterns/<LEVEL>.json)
    """
    CREATE TABLE IF NOT EXISTS pattern_progress (
        pattern_id TEXT PRIMARY KEY,
        ease REAL NOT NULL DEFAULT 2.5,
        interval INTEGER NOT NULL DEFAULT 0,
        repetitions INTEGER NOT NULL DEFAULT 0,
        due_date TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_reviewed_at TEXT,
        review_count INTEGER NOT NULL DEFAULT 0,
        lapses INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_pattern_progress_due ON pattern_progress(due_date);
    """,
    # 14: self-tests (🎯 Kendini Test Et, backend/selftest.py): timed YDS-style sets; a running attempt keeps
    # its answers and deadline here, a finished one its graded result
    """
    CREATE TABLE IF NOT EXISTS selftest_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        qtype TEXT,
        timing TEXT NOT NULL DEFAULT 'standard',
        started_at TEXT NOT NULL,
        deadline TEXT,
        finished_at TEXT,
        time_limit_s INTEGER,
        time_used_s INTEGER,
        questions_json TEXT NOT NULL,
        answers_json TEXT,
        correct INTEGER,
        total INTEGER,
        result_json TEXT
    );
    """,
    # 15: spaced review of finished lessons (backend/reviews.py): the step on the interval ladder, the next
    # date, and which exercises the review quizzes asked / got wrong (JSON lists of exercise indices)
    """
    CREATE TABLE IF NOT EXISTS lesson_review (
        lesson_id TEXT PRIMARY KEY,
        step INTEGER NOT NULL DEFAULT 0,
        due_date TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_reviewed_at TEXT,
        last_score REAL,
        review_count INTEGER NOT NULL DEFAULT 0,
        lapses INTEGER NOT NULL DEFAULT 0,
        last_items TEXT,
        wrong_items TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_lesson_review_due ON lesson_review(due_date);
    """,
]


def log_practice(kind: str, minutes: float) -> None:
    """Count today (local day) as a practice day for the streak and the activity calendar."""
    from datetime import date

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO practice_days (day, kind, minutes) VALUES (?, ?, ?) "
            "ON CONFLICT(day, kind) DO UPDATE SET minutes = minutes + excluded.minutes",
            (date.today().isoformat(), kind, minutes),
        )


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
            )
        version = conn.execute("PRAGMA user_version").fetchone()[0]

    if version < len(MIGRATIONS):
        from .backup import backup_now

        backup_now(f"pre-schema-v{len(MIGRATIONS)}")
        for number, sql in enumerate(MIGRATIONS[version:], start=version + 1):
            with get_conn() as conn:
                conn.executescript(f"BEGIN; {sql}; PRAGMA user_version = {number}; COMMIT;")
    _housekeeping()


def _housekeeping() -> None:
    """No wasted space: drop exams that were started but never handed in, and give the
    space of deleted rows back to the disk (SQLite keeps it until VACUUM)."""
    from datetime import timedelta

    day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    with get_conn() as conn:
        # An exam the learner left half done (saved in ui_state) stays until they finish or change it.
        conn.execute("DELETE FROM exam_attempts WHERE finished_at IS NULL AND started_at < ? AND id NOT IN ("
                     "SELECT json_extract(value_json, '$.exam.attempt_id') FROM ui_state WHERE key LIKE 'exam:%' "
                     "AND json_extract(value_json, '$.exam.attempt_id') IS NOT NULL)", (day_ago,))
        free = conn.execute("PRAGMA freelist_count").fetchone()[0]
        total = conn.execute("PRAGMA page_count").fetchone()[0]
    if free > 64 and free > total * 0.2:
        vacuum()


def vacuum() -> None:
    """Give the space of deleted rows back to the disk (SQLite keeps it until VACUUM)."""
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()


def rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]
