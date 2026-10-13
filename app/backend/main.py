import asyncio
import functools
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import corrections, dictionary, errors, exams, lessons, llm_models, machine, ollama_client, patterns, progress, report, reset, reviews, scenarios, selftest, sessions, sync, teacher, teacher_speech, ui_state, updates, vocab, words, writing
from .tts_tr import tts_tr
from .chat import chat_turn, opening_turn
from .corrections import worker as correction_worker
from .config import FRONTEND_DIR, script
from .db import init_db
from .ollama_client import OllamaError
from .settings_store import get_settings, update_settings
from .stt import stt
from .tts import SentenceSplitter, tts

log = logging.getLogger("app")


def _code_stamp() -> float:
    """Newest change time of the server code. The browser always loads the current page files,
    but the server keeps running the code it started with — the UI warns when they differ."""
    backend = Path(__file__).parent
    files = [*backend.glob("*.py"), *(backend.parent / "content").rglob("*.json")]
    return max((f.stat().st_mtime for f in files), default=0.0)


CODE_STAMP = _code_stamp()


def load_whisper(model_name: str) -> None:
    stt.load_async(model_name, machine.load_profile().get("whisper_device", "cuda"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    # EP_SKIP_SPEECH=1: development instance next to a running app (no VRAM for a 2nd Whisper).
    if os.environ.get("EP_SKIP_SPEECH") != "1":
        load_whisper(settings["whisper_model"])
        tts.load_async()
    corrections.worker.start()
    llm_models.manager.activate()  # load the chat model ahead of the first message
    sync.start_background()  # two computers: send changes every few minutes (when turned on)
    updates.check_in_background()  # a newer version on GitHub? (shown in the top bar)
    yield
    await corrections.worker.stop()
    await ollama_client.close()


app = FastAPI(title="English Practice", lifespan=lifespan)


@app.middleware("http")
async def revalidate_static_files(request, call_next):
    # Without this, browsers may keep running an old app.js after an update.
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ---------------------------------------------------------------- health

@app.get("/api/health")
async def health():
    model = llm_models.current()
    try:
        models = await ollama_client.list_models()
        if model in models or f"{model}:latest" in models:
            ollama = {"ok": True, "message": f"Ollama çalışıyor, model: {model}"}
        else:
            ollama = {
                "ok": False,
                "message": f"'{model}' bu bilgisayarda kurulu değil. "
                + ("Ayarlar'dan kurulu bir model seçin." if models else f"{script('setup')} ile bir model indirin."),
            }
    except OllamaError as e:
        ollama = {"ok": False, "message": str(e)}

    return {
        "restart_needed": _code_stamp() > CODE_STAMP,
        "start_script": script("start"),  # Baslat.bat / baslat.sh, for the messages in the page
        "sync_notice": sync.local().get("notice"),  # e.g. worked on both computers without closing one
        "sync_replaced_at": sync.replaced_at,  # the other computer's newer work was taken: the page reloads
        "update": {k: v for k, v in updates.status().items() if k in ("state", "latest", "received")},
        "ollama": ollama,
        "whisper": {
            "ok": {"ready": True, "error": False}.get(stt.state),
            "state": stt.state,
            "message": stt.message,
        },
        "tts": {
            "ok": {"ready": True, "error": False}.get(tts.state),
            "state": tts.state,
            "message": tts.message,
        },
    }


# -------------------------------------------------------------- settings

@app.get("/api/settings")
def read_settings():
    return get_settings()


@app.put("/api/settings")
async def write_settings(changes: dict[str, str | int | float]):
    previous = get_settings()
    if "level" in changes:
        changes = {**changes, "level_confirmed": "1"}
    settings = update_settings(changes)
    if settings["llm_model"] != previous["llm_model"]:
        llm_models.manager.activate()
    if settings["whisper_model"] != previous["whisper_model"]:
        load_whisper(settings["whisper_model"])
    return settings


@app.get("/api/state/{key}")
def state_get(key: str):
    """Saved work in progress (null when there is none)."""
    if not ui_state.valid_key(key):
        raise HTTPException(400, "Geçersiz anahtar.")
    return {"value": ui_state.get(key)}


@app.put("/api/state/{key}")
async def state_put(key: str, request: Request):
    if not ui_state.valid_key(key):
        raise HTTPException(400, "Geçersiz anahtar.")
    try:
        ui_state.put(key, (await request.json()).get("value"))
    except ValueError as e:
        raise HTTPException(413, str(e))
    return {"ok": True}


@app.delete("/api/state/{key}")
def state_delete(key: str):
    if not ui_state.valid_key(key):
        raise HTTPException(400, "Geçersiz anahtar.")
    ui_state.delete(key)
    return {"ok": True}


@app.get("/api/sync")
def sync_status():
    """Two computers through a cloud folder (backend/sync.py)."""
    return sync.status()


class SyncSetup(BaseModel):
    dir: str = Field(min_length=3, max_length=400)


@app.post("/api/sync/setup")
def sync_setup(body: SyncSetup):
    try:
        return sync.setup(body.dir)
    except (sync.SyncError, OSError) as e:
        raise HTTPException(400, str(e))


class SyncChoice(BaseModel):
    action: str  # "pull" | "push"


@app.post("/api/sync/choose")
def sync_choose(body: SyncChoice):
    try:
        sync.choose(body.action)
    except (sync.SyncError, OSError) as e:
        raise HTTPException(400, str(e))
    return {"reload": body.action == "pull"}


@app.post("/api/sync/now")
def sync_now():
    """Take the other computer's newer work or send this one's; reload the page when data was replaced."""
    if not sync.enabled():
        raise HTTPException(400, "Eşitleme kapalı ya da klasör bulunamadı.")
    try:
        messages = sync.sync_on_open()
        sent = sync.push()
    except (sync.SyncError, OSError) as e:
        raise HTTPException(400, str(e))
    pulled = any("alındı" in m for m in messages)  # this computer's data was replaced
    return {"messages": messages or (["Buluta gönderildi ✓"] if sent else ["Zaten eşit ✓"]), "reload": pulled}


@app.post("/api/sync/off")
def sync_off():
    sync.turn_off()
    return {"ok": True}


@app.post("/api/sync/dismiss")
def sync_dismiss():
    sync._save_local(notice=None)
    return {"ok": True}


@app.get("/api/update")
def update_status():
    """A newer version on GitHub (backend/updates.py), checked when the app opened."""
    return updates.status()


@app.post("/api/update/check")
def update_check():
    updates.check()
    return updates.status()


@app.post("/api/update/apply")
def update_apply():
    """Download the latest version; the app then closes, is updated and opens again by itself."""
    try:
        return updates.start_update()
    except updates.UpdateError as e:
        raise HTTPException(400, str(e))


class UpdateSettings(BaseModel):
    enabled: bool


@app.put("/api/update/settings")
def update_check_setting(body: UpdateSettings):
    updates.set_enabled(body.enabled)
    return updates.status()


@app.get("/api/reset")
def reset_counts():
    """What a reset would delete, per group."""
    rows = reset.counts()
    return {"groups": [{"id": g, "label": spec["label"], "rows": rows[g]} for g, spec in reset.GROUPS.items()]}


class ResetRequest(BaseModel):
    groups: list[str]


@app.post("/api/reset")
async def reset_data(body: ResetRequest):
    try:
        return await reset.reset(body.groups)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------- models

def _model_call(fn):
    """Run a model-manager request; its refusals become 400s with the Turkish message.
    Answers with the new model state."""
    @functools.wraps(fn)  # FastAPI reads the endpoint's parameters through this
    async def wrapper(*args, **kwargs):
        try:
            result = await fn(*args, **kwargs)
        except llm_models.ModelError as e:
            raise HTTPException(400, str(e))
        except OllamaError as e:
            raise HTTPException(503, str(e))
        return result if result is not None else await llm_models.manager.state()
    return wrapper


@app.get("/api/llm")
async def llm_state():
    """Installed models, default / active model, download and speed-test progress."""
    return await llm_models.manager.state()


@app.get("/api/llm/catalog")
async def llm_catalog():
    """Catalog cards with the setup wizard's fit badges for this computer."""
    return {"models": await llm_models.manager.catalog()}


class ModelChoice(BaseModel):
    model: str | None = None


@app.put("/api/llm/active")
@_model_call
async def llm_active(body: ModelChoice):
    """The session model (null = this computer's default). The default is not changed."""
    await llm_models.manager.set_session_model(body.model)


@app.put("/api/llm/default")
@_model_call
async def llm_default(body: ModelChoice):
    await llm_models.manager.set_default(body.model or "")


@app.post("/api/llm/delete")
@_model_call
async def llm_delete(body: ModelChoice):
    await llm_models.manager.remove(body.model or "")


class PullRequest(BaseModel):
    model: str
    copy_from: str | None = None


@app.post("/api/llm/pull")
@_model_call
async def llm_pull(body: PullRequest):
    llm_models.manager.start_pull(body.model, body.copy_from)


@app.post("/api/llm/pull/cancel")
@_model_call
async def llm_pull_cancel():
    llm_models.manager.cancel_pull()


class BenchmarkRequest(BaseModel):
    models: list[str] | None = None


@app.post("/api/llm/benchmark")
@_model_call
async def llm_benchmark(body: BenchmarkRequest):
    """Speed test (chat requests wait meanwhile); results go to the computer profile."""
    await llm_models.manager.start_benchmark(body.models)


# -------------------------------------------------------------- sessions

class NewSession(BaseModel):
    mode: Literal["conversation", "scenario"] = "conversation"
    scenario_id: str | None = None


@app.post("/api/sessions")
def create_session(body: NewSession):
    scenario = scenarios.get(body.scenario_id) if body.scenario_id else None
    if body.scenario_id and scenario is None:
        raise HTTPException(404, "Senaryo bulunamadı.")
    return {"id": sessions.create_session("scenario" if scenario else body.mode, scenario)}


@app.get("/api/sessions")
def list_sessions():
    return sessions.list_sessions()


@app.get("/api/sessions/{session_id}")
def get_session(session_id: int):
    session = sessions.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Oturum bulunamadı.")
    session["corrections"] = corrections.for_session(session_id)
    session["scenario"] = scenarios.public(session["scenario"]) if session["scenario"] else None
    return session


@app.post("/api/sessions/{session_id}/report")
async def session_report(session_id: int):
    """End the session and build its report (waits for pending corrections first)."""
    try:
        return await report.build(session_id)
    except report.ReportError as e:
        raise HTTPException(400, str(e))
    except OllamaError as e:
        raise HTTPException(503, str(e))


# -------------------------------------------------------------- progress

@app.get("/api/stats")
def stats(days: int = Query(default=30, ge=7, le=365)):
    return progress.overview(days)


@app.get("/api/weak-points")
def weak_points(days: int = Query(default=30, ge=7, le=365)):
    items = progress.weak_points(days)
    for w in items:
        w["lessons"] = lessons.for_category(w["category"])  # "📘 İlgili ders"
    return items


# --------------------------------------------------------------- lessons

@app.get("/api/lessons")
def lessons_overview():
    """All lessons with progress, per-level counts and recommendations; the reviews due (backend/reviews.py)."""
    return lessons.overview() | {"reviews": reviews.overview()}


@app.get("/api/lessons/{lesson_id}")
def lesson_detail(lesson_id: str):
    lesson = lessons.open_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(404, "Ders bulunamadı.")
    return lesson | {"review_card": reviews.card(lessons.BY_ID[lesson_id])}  # 📌 Özet


@app.get("/api/reviews")
def reviews_overview():
    """Finished lessons due for review today (spaced repetition), the next ones and the weak topics."""
    return reviews.overview()


@app.get("/api/reviews/count")
def reviews_count():
    return {"due": reviews.due_count()}  # the number next to 📘 Dersler in the menu


@app.get("/api/reviews/{lesson_id}")
def review_start(lesson_id: str):
    """A review: the lesson's summary card and a short quiz of its own exercises."""
    r = reviews.start(lesson_id)
    if r is None:
        raise HTTPException(404, "Ders bulunamadı.")
    return r


class ReviewResult(BaseModel):
    items: list[int] = Field(min_length=1, max_length=50)
    wrong: list[int] = Field(default_factory=list, max_length=50)


@app.post("/api/reviews/{lesson_id}")
def review_record(lesson_id: str, body: ReviewResult):
    try:
        return reviews.record(lesson_id, body.items, body.wrong)
    except ValueError as e:
        raise HTTPException(400, str(e))


class LessonResult(BaseModel):
    correct: int = Field(ge=0)
    total: int = Field(ge=1)


@app.delete("/api/lessons/{lesson_id}/progress")
def lesson_reset(lesson_id: str):
    lessons.reset(lesson_id)
    return {"ok": True}


@app.post("/api/lessons/{lesson_id}/result")
def lesson_result(lesson_id: str, body: LessonResult):
    if lesson_id not in lessons.BY_ID:
        raise HTTPException(404, "Ders bulunamadı.")
    return lessons.save_result(lesson_id, min(body.correct, body.total), body.total)


class AnswerCheck(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=600)


@app.post("/api/lessons/{lesson_id}/check")
async def lesson_check(lesson_id: str, body: AnswerCheck):
    """Check an answer of "Kendi cümlelerini kur": grammar, relevance, the lesson's structure."""
    if lesson_id not in lessons.BY_ID:
        raise HTTPException(404, "Ders bulunamadı.")
    try:
        return await lessons.check_answer(lesson_id, body.question.strip(), body.answer.strip())
    except OllamaError as e:
        raise HTTPException(503, str(e))


# ----------------------------------------------------------------- exams

@app.get("/api/exams")
def exams_status():
    """Per level: exam available / unlocked (all lessons done) / results."""
    return exams.status()


@app.post("/api/exams/{level}/start")
def exam_start(level: str):
    if level not in exams.EXAMS:
        raise HTTPException(404, "Bu seviyenin sınavı henüz yok.")
    return exams.start(level)


class ExamAnswers(BaseModel):
    grammar: dict[str, int | str] = {}
    listening: dict[str, int | str] = {}
    speaking: dict[str, dict] = {}   # id → {"text", "typed"}
    writing: str = Field(default="", max_length=6000)


@app.post("/api/exams/attempts/{attempt_id}/submit")
async def exam_submit(attempt_id: int, body: ExamAnswers):
    """Grade the whole exam (speaking and writing use the LLM: ~20–40 s)."""
    try:
        return await exams.submit(attempt_id, body.model_dump())
    except KeyError:
        raise HTTPException(404, "Sınav bulunamadı.")
    except OllamaError as e:
        raise HTTPException(503, str(e))


@app.get("/api/exams/attempts/{attempt_id}")
def exam_result(attempt_id: int):
    result = exams.get_result(attempt_id)
    if result is None:
        raise HTTPException(404, "Sınav sonucu bulunamadı.")
    return result


@app.delete("/api/exams/attempts/{attempt_id}")
def exam_delete(attempt_id: int):
    exams.delete_attempt(attempt_id)
    return {"ok": True}


@app.post("/api/stt")
async def speech_to_text(request: Request):
    """One recording (webm/opus…) → text, for answers outside the chat (exam speaking part)."""
    audio = await request.body()
    if not audio:
        raise HTTPException(400, "Ses kaydı boş.")
    if stt.state != "ready":
        raise HTTPException(503, stt.message or "Konuşma tanıma hazır değil.")
    try:
        result = await asyncio.to_thread(stt.transcribe, audio)
    except Exception as e:
        raise HTTPException(400, f"Ses yazıya çevrilemedi: {e}")
    return {"text": result["text"], "audio_seconds": result["audio_seconds"]}


@app.post("/api/lessons/{lesson_id}/prompts")
async def lesson_prompts(lesson_id: str):
    """Questions for "Kendi cümlelerini kur" (answers are checked with /api/correct)."""
    if lesson_id not in lessons.BY_ID:
        raise HTTPException(404, "Ders bulunamadı.")
    try:
        return {"items": await lessons.sentence_prompts(lesson_id)}
    except OllamaError as e:
        raise HTTPException(503, str(e))


# ------------------------------------------------------ dictionary + vocab

@app.get("/api/dictionary/lookup")
def dictionary_lookup(word: str):
    result = dictionary.lookup(word)
    result["available"] = dictionary.available()
    result["in_vocab"] = bool(vocab.contains([result["lemma"], result["query"]]))
    return result


class ExplainRequest(BaseModel):
    word: str = Field(min_length=1, max_length=60)
    sentence: str = Field(default="", max_length=600)


@app.post("/api/dictionary/explain")
async def dictionary_explain(body: ExplainRequest):
    """The word's meaning in its sentence, from the LLM."""
    try:
        return await dictionary.explain(body.word, body.sentence or body.word)
    except OllamaError as e:
        raise HTTPException(503, str(e))


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1500)


@app.post("/api/translate")
async def translate(body: TranslateRequest):
    """Sentence translation (TranslateGemma if installed, else the chat model)."""
    try:
        return await dictionary.translate(body.text)
    except OllamaError as e:
        raise HTTPException(503, str(e))


class VocabRequest(BaseModel):
    word: str = Field(min_length=1, max_length=120)
    meaning_tr: str = Field(default="", max_length=300)
    definition: str = Field(default="", max_length=500)
    example: str = Field(default="", max_length=500)
    context: str = Field(default="", max_length=600)
    ipa: str = Field(default="", max_length=80)
    source: str = Field(default="manual", max_length=20)
    session_id: int | None = None


@app.get("/api/vocab")
def vocab_list(q: str = ""):
    return vocab.list_all(q)


@app.post("/api/vocab")
def vocab_add(body: VocabRequest):
    entry, created = vocab.add(**body.model_dump())
    return {**entry, "created": created}


class VocabUpdate(BaseModel):
    meaning_tr: str | None = None
    definition: str | None = None
    example: str | None = None


@app.patch("/api/vocab/{vocab_id}")
def vocab_update(vocab_id: int, body: VocabUpdate):
    entry = vocab.update(vocab_id, body.model_dump(exclude_none=True))
    if entry is None:
        raise HTTPException(404, "Kelime bulunamadı.")
    return entry


@app.delete("/api/vocab/{vocab_id}")
def vocab_delete(vocab_id: int):
    vocab.delete(vocab_id)
    return {"ok": True}


@app.get("/api/vocab/due")
def vocab_due(limit: int = Query(50, ge=1, le=10000)):
    return vocab.due(limit)


@app.get("/api/vocab/stats")
def vocab_stats():
    return {**vocab.stats(), "dictionary": dictionary.available()}


class ReviewRequest(BaseModel):
    grade: Literal["again", "hard", "good"]


@app.post("/api/vocab/{vocab_id}/review")
def vocab_review(vocab_id: int, body: ReviewRequest):
    entry = vocab.review(vocab_id, body.grade)
    if entry is None:
        raise HTTPException(404, "Kelime bulunamadı.")
    return entry


# ------------------------------------------------------ word study (level lists)

@app.get("/api/words")
def words_overview():
    return words.overview()


@app.get("/api/words/level/{level}")
def words_level(level: str):
    if level not in words.LISTS:
        raise HTTPException(404, "Seviye bulunamadı.")
    return {"level": level, "words": words.level_words(level)}


class LearnRequest(BaseModel):
    words: list[str] = Field(min_length=1, max_length=50)


@app.post("/api/words/learn")
def words_learn(body: LearnRequest):
    return words.learn(body.words)


@app.get("/api/words/examples")
def words_examples(word: str):
    return {"examples": words.examples(word)}


class WordRequest(BaseModel):
    word: str = Field(min_length=1, max_length=60)


@app.post("/api/words/examples")
async def words_generate_examples(body: WordRequest):
    try:
        return await words.generate_examples(body.word)
    except OllamaError as e:
        raise HTTPException(503, str(e))


@app.delete("/api/words/examples/{example_id}")
def words_delete_example(example_id: int):
    words.delete_example(example_id)
    return {"ok": True}


class SentenceCheck(BaseModel):
    word: str = Field(min_length=1, max_length=60)
    text: str = Field(min_length=1, max_length=400)


@app.post("/api/words/check")
async def words_check(body: SentenceCheck):
    try:
        return await words.check_sentence(body.word, body.text)
    except OllamaError as e:
        raise HTTPException(503, str(e))


# -------------------------------------------------------------- patterns

@app.get("/api/patterns")
def patterns_overview():
    return patterns.overview()


@app.get("/api/patterns/level/{level}")
def patterns_level(level: str):
    if level not in patterns.LEVELS:
        raise HTTPException(404, "Seviye bulunamadı.")
    return {"level": level, "patterns": patterns.level_patterns(level)}


@app.get("/api/patterns/due")
def patterns_due(limit: int = Query(50, ge=1, le=10000)):
    return patterns.due(limit)


class PatternIds(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=50)


@app.post("/api/patterns/learn")
def patterns_learn(body: PatternIds):
    return patterns.learn(body.ids)


@app.post("/api/patterns/{pattern_id}/review")
def patterns_review(pattern_id: str, body: ReviewRequest):
    entry = patterns.review(pattern_id, body.grade)
    if entry is None:
        raise HTTPException(404, "Kalıp öğrenme listende değil.")
    return entry


@app.delete("/api/patterns/{pattern_id}/progress")
def patterns_forget(pattern_id: str):
    return {"ok": patterns.forget(pattern_id)}


class PatternSentence(BaseModel):
    id: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=400)


@app.post("/api/patterns/check")
async def patterns_check(body: PatternSentence):
    try:
        return await patterns.check_sentence(body.id, body.text)
    except KeyError:
        raise HTTPException(404, "Kalıp bulunamadı.")
    except OllamaError as e:
        raise HTTPException(503, str(e))


# -------------------------------------------------------------- self-tests

@app.get("/api/selftest")
def selftest_overview():
    return selftest.overview()


class SelftestStart(BaseModel):
    kind: Literal["type", "mini"]
    qtype: str | None = None
    count: int | None = Field(default=None, ge=1, le=80)
    timing: Literal["standard", "relaxed", "none"] = "standard"


@app.post("/api/selftest/start")
def selftest_start(body: SelftestStart):
    try:
        return selftest.start(body.kind, body.qtype, body.count, body.timing)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/selftest/attempts/{attempt_id}")
def selftest_attempt(attempt_id: int):
    a = selftest.get_attempt(attempt_id)
    if a is None:
        raise HTTPException(404, "Süren test bulunamadı.")
    return a


class SelftestAnswers(BaseModel):
    answers: dict[str, int] = Field(default_factory=dict)


@app.put("/api/selftest/attempts/{attempt_id}/answers")
def selftest_save(attempt_id: int, body: SelftestAnswers):
    if not selftest.save_answers(attempt_id, body.answers):
        raise HTTPException(404, "Süren test bulunamadı.")
    return {"ok": True}


@app.post("/api/selftest/attempts/{attempt_id}/finish")
def selftest_finish(attempt_id: int, body: SelftestAnswers):
    r = selftest.finish(attempt_id, body.answers)
    if r is None:
        raise HTTPException(404, "Süren test bulunamadı.")
    return r


@app.get("/api/selftest/attempts/{attempt_id}/result")
def selftest_result(attempt_id: int):
    r = selftest.get_result(attempt_id)
    if r is None:
        raise HTTPException(404, "Sonuç bulunamadı.")
    return r


@app.delete("/api/selftest/attempts/{attempt_id}")
def selftest_delete(attempt_id: int):
    selftest.delete_attempt(attempt_id)
    return {"ok": True}


# --------------------------------------------------------------- writing

@app.get("/api/writing/types")
def writing_types():
    return writing.task_types()


@app.get("/api/writing/prompt")
async def writing_prompt(type: str = "free", avoid: list[str] = Query(default=[])):
    """Suggest a topic for a writing task (level- and interest-aware)."""
    return await writing.suggest_topic(type, avoid)


class WritingRequest(BaseModel):
    task_type: str = "free"
    prompt: str = Field(default="", max_length=1000)
    text: str = Field(min_length=1, max_length=8000)


@app.post("/api/writing/review")
async def writing_review(body: WritingRequest):
    """Review a text. Streams SSE: saved → sentence* → assessment → improved_delta* → done | error."""
    text = body.text.strip()
    if writing.word_count(text) > writing.MAX_WORDS:
        raise HTTPException(400, f"Metin çok uzun (en fazla {writing.MAX_WORDS} kelime).")
    if writing.word_count(text) < 3:
        raise HTTPException(400, "Değerlendirmek için biraz daha yaz.")
    if corrections.not_english(text):
        raise HTTPException(400, "Bu metin İngilizce görünmüyor. Yazma modunda İngilizce bir metin yazmalısın.")

    async def events():
        async for event, data in writing.review(body.task_type, body.prompt.strip(), text):
            yield _sse(event, data)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/writings")
def list_writings():
    return writing.list_writings()


@app.get("/api/writings/{writing_id}")
def get_writing(writing_id: int):
    w = writing.get_writing(writing_id)
    if w is None:
        raise HTTPException(404, "Yazı bulunamadı.")
    return w


@app.delete("/api/writings/{writing_id}")
def delete_writing(writing_id: int):
    writing.delete_writing(writing_id)
    return {"ok": True}


# ------------------------------------------------------------- scenarios

@app.get("/api/scenarios")
def list_scenarios():
    return [scenarios.public(s) for s in scenarios.SCENARIOS]


# ----------------------------------------------------------- corrections

@app.get("/api/error-categories")
def error_categories():
    """The fixed error taxonomy (stable ids + labels) — the only source the UI uses."""
    return {"version": errors.TAXONOMY_VERSION,
            "categories": [{k: c[k] for k in ("id", "name", "tr")} for c in errors.CATEGORIES]}


class CorrectRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    source: Literal["voice", "text"] = "text"


@app.post("/api/correct")
async def correct(body: CorrectRequest):
    """Correct one sentence without storing it."""
    try:
        return await corrections.analyze(body.text.strip(), body.source)
    except OllamaError as e:
        raise HTTPException(503, str(e))


@app.post("/api/sessions/{session_id}/end")
def end_session(session_id: int):
    sessions.end_session(session_id)
    return {"ok": True}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: int):
    sessions.delete_session(session_id)
    return {"ok": True}


# ------------------------------------------------------------------ chat

class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    session_id: int | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chat")
async def chat(body: ChatRequest):
    """Text chat. Streams Server-Sent Events: meta → delta* → done | error."""

    async def events():
        async for event, data in chat_turn(body.session_id, body.text.strip(), {"source": "text"}):
            yield _sse(event, data)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------- teacher

class TeacherRequest(BaseModel):
    session_id: int | None = None
    text: str = Field(default="", max_length=2000)
    context: dict | None = None  # a new session: {"type": "lesson" | "error" | "practice", …}


@app.post("/api/teacher/chat")
async def teacher_chat(body: TeacherRequest):
    """Ask the Turkish teacher. SSE: meta → status* → correction? → delta* → done | error."""

    async def events():
        async for event, data in teacher.turn(body.session_id, body.text, body.context):
            yield _sse(event, data)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/teacher/sessions")
def teacher_sessions():
    return teacher.history()


@app.get("/api/teacher/sessions/{session_id}")
def teacher_session(session_id: int):
    s = teacher.get(session_id)
    if s is None:
        raise HTTPException(404, "Konuşma bulunamadı.")
    return s


# ------------------------------------------------------------------- tts

class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    accent: str | None = None
    voice: str | None = None
    speed: float | None = None


@app.post("/api/tts")
async def speak(body: TtsRequest):
    """WAV for "listen again" and word pronunciation. Unset fields use the settings."""
    settings = get_settings()
    try:
        wav = await asyncio.to_thread(
            tts.synthesize,
            body.text,
            body.accent or settings["tts_accent"],
            body.voice or settings["tts_voice"],
            body.speed or settings["tts_speed"],
        )
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return Response(wav, media_type="audio/wav")


class TrTtsRequest(BaseModel):
    text: str = Field(max_length=4000)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


@app.post("/api/tts/tr")
async def speak_turkish(body: TrTtsRequest):
    """WAV of Turkish text (the teacher's voice; app/tts_tr). Never for English: see teacher_speech."""
    if not tts_tr.available():
        raise HTTPException(503, "Türkçe ses modeli bulunamadı (app/tts_tr).")
    try:
        wav = await asyncio.to_thread(tts_tr.synthesize, body.text, body.speed)
    except ImportError as e:
        raise HTTPException(503, f"Türkçe ses için paket eksik ({e.name}); {script('setup')} → bakım → güncelle.")
    return Response(wav, media_type="audio/wav")


class SpeechPlanRequest(BaseModel):
    text: str = Field(max_length=8000)


@app.post("/api/teacher/speech")
def teacher_speech_plan(body: SpeechPlanRequest):
    """A teacher reply split for reading aloud: Turkish parts (Turkish voice), English parts (English voice)."""
    return {"segments": teacher_speech.segments(body.text)}


@app.get("/api/tts/voices")
def voices():
    return {"voices": tts.voices}


# ----------------------------------------------------------------- voice

MIN_AUDIO_SECONDS = 0.3


@app.websocket("/ws/voice")
async def voice(ws: WebSocket):
    """Conversation channel used by the UI.

    Client → server:
      {"type": "audio", "session_id", "client_id", "speak"} followed by one binary frame (webm/opus)
      {"type": "text", "text", "session_id", "client_id", "speak"}
      {"type": "start_scenario", "scenario_id" | "custom", "client_id", "speak"}
      {"type": "cancel"}                      stop the turn in progress (and its speech)
    Server → client (JSON, each with "type"):
      transcript → meta → delta* → done | error
      for start_scenario: scenario → meta → delta* → done (the AI's opening line)
      interleaved: {"type": "audio", "seq", "text"} followed by one binary frame (WAV),
      and finally {"type": "audio_end"}
      later (after the reply): {"type": "correction", "message_id", ...} for the user's message
    """
    await ws.accept()
    turn: asyncio.Task | None = None
    audio_header: dict | None = None
    send_lock = asyncio.Lock()  # keeps an audio header and its binary frame together

    async def send(kind: str, data: dict, payload: bytes | None = None) -> None:
        async with send_lock:
            await ws.send_json({"type": kind, **data})
            if payload is not None:
                await ws.send_bytes(payload)

    async def run_chat(header: dict, text: str, meta: dict) -> None:
        client_id = header.get("client_id")

        async def on_correction(result: dict) -> None:
            await send("correction", {"client_id": client_id, **result})

        await run_turn(header, chat_turn(header.get("session_id"), text, meta, on_correction))

    async def run_turn(header: dict, events) -> None:
        """Forward a turn's events and speak the reply sentence by sentence."""
        client_id = header.get("client_id")
        settings = get_settings()
        speak_requested = header.get("speak", True)
        speak = speak_requested and tts.state == "ready"
        sentences: asyncio.Queue[str | None] = asyncio.Queue()

        async def speaker() -> None:
            # Synthesizes sentence N+1 while the browser plays sentence N.
            seq = 0
            while (sentence := await sentences.get()) is not None:
                try:
                    wav = await asyncio.to_thread(
                        tts.synthesize, sentence,
                        settings["tts_accent"], settings["tts_voice"], settings["tts_speed"],
                    )
                except Exception:
                    log.exception("TTS failed for %r", sentence)
                    continue
                await send("audio", {"client_id": client_id, "seq": seq, "text": sentence}, wav)
                seq += 1
            await send("audio_end", {"client_id": client_id})

        speaker_task = asyncio.create_task(speaker()) if speak else None
        splitter = SentenceSplitter()
        try:
            async for event, data in events:
                await send(event, {**data, "client_id": client_id})
                if not speak:
                    continue
                if event == "delta":
                    for sentence in splitter.feed(data["text"]):
                        sentences.put_nowait(sentence)
                elif event in ("done", "error"):
                    for sentence in splitter.flush():
                        sentences.put_nowait(sentence)
                    sentences.put_nowait(None)
            if speaker_task:
                await speaker_task
            elif speak_requested:
                # TTS unavailable: still tell the browser there is nothing more to play.
                await send("audio_end", {"client_id": client_id})
        finally:
            if speaker_task and not speaker_task.done():
                speaker_task.cancel()

    async def run_voice(header: dict, audio: bytes) -> None:
        client_id = header.get("client_id")
        try:
            result = await asyncio.to_thread(stt.transcribe, audio)
        except Exception as e:
            await send("error", {"client_id": client_id, "message": f"Ses yazıya çevrilemedi: {e}"})
            return
        await send("transcript", {"client_id": client_id, **result})
        if not result["text"] or result["audio_seconds"] < MIN_AUDIO_SECONDS:
            await send("error", {"client_id": client_id, "message": "Ses anlaşılamadı, tekrar deneyin."})
            return
        meta = {"source": "voice", "words": result["words"],
                "audio_seconds": result["audio_seconds"], "stt_ms": result["elapsed_ms"]}
        await run_chat(header, result["text"], meta)

    async def run_scenario(header: dict) -> None:
        client_id = header.get("client_id")
        custom = str(header.get("custom") or "").strip()
        if header.get("lesson"):
            lesson = lessons.BY_ID.get(str(header["lesson"]))
            if lesson is None:
                await send("error", {"client_id": client_id, "message": "Ders bulunamadı."})
                return
            scenario = scenarios.lesson_scenario(lesson)
            lessons.practice_started(lesson["id"])
        elif header.get("focus"):
            scenario = scenarios.focus_scenario(str(header["focus"]))
            if scenario is None:
                await send("error", {"client_id": client_id, "message": "Bu konu için pratik bulunamadı."})
                return
        elif custom:
            try:
                async with correction_worker.chat_priority():
                    scenario = await scenarios.build_custom(custom[:1000])
            except OllamaError as e:
                await send("error", {"client_id": client_id, "message": str(e)})
                return
        else:
            scenario = scenarios.get(header.get("scenario_id", ""))
            if scenario is None:
                await send("error", {"client_id": client_id, "message": "Senaryo bulunamadı."})
                return
        session_id = sessions.create_session("scenario", scenario)
        await send("scenario", {"client_id": client_id, "session_id": session_id,
                                "scenario": scenarios.public(scenario)})
        await run_turn(header, opening_turn(session_id))

    def start(coro) -> None:
        nonlocal turn
        if turn and not turn.done():
            turn.cancel()
        turn = asyncio.create_task(coro)

    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("text"):
                data = json.loads(msg["text"])
                kind = data.get("type")
                if kind == "audio":
                    audio_header = data  # the binary frame comes next
                elif kind == "text" and str(data.get("text", "")).strip():
                    start(run_chat(data, data["text"].strip()[:4000], {"source": "text"}))
                elif kind == "start_scenario":
                    start(run_scenario(data))
                elif kind == "cancel" and turn:
                    turn.cancel()
            elif msg.get("bytes") is not None and audio_header is not None:
                start(run_voice(audio_header, msg["bytes"]))
                audio_header = None
    except WebSocketDisconnect:
        pass
    finally:
        if turn and not turn.done():
            turn.cancel()


# Static frontend last so it does not shadow /api routes.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
