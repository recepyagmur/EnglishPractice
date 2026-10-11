"""Conversation turns: store the user message, stream the LLM reply, store it,
then queue a correction of the user's message. Also the opening line of role-plays.

Shared by the SSE endpoint (/api/chat) and the WebSocket (/ws/voice).
"""

import asyncio
from typing import AsyncIterator, Awaitable, Callable

from . import llm_models, ollama_client, scenarios, sessions
from .config import CHAT_HISTORY_LIMIT
from .corrections import Job
from .corrections import worker as correction_worker
from .ollama_client import OllamaError
from .prompts import chat_system_prompt
from .settings_store import get_settings

Event = tuple[str, dict]
CorrectionCallback = Callable[[dict], Awaitable[None]]


def system_prompt(session_id: int, settings: dict) -> str:
    scenario = sessions.scenario_of(session_id)
    return scenarios.system_prompt(scenario) if scenario else chat_system_prompt(settings)


async def _stream_reply(session_id: int, llm_messages: list[dict], on_saved=None) -> AsyncIterator[Event]:
    """Stream and store the assistant reply. Yields status? delta* then done | error.

    on_saved(reply_was_stored) runs once the outcome is known (not on errors)."""
    reply, model = "", None
    try:
        if waiting := llm_models.manager.wait_message():
            yield "status", {"message": waiting}  # a model is loading / being tested
        async with correction_worker.chat_priority():  # corrections wait while we talk
            model = llm_models.current()
            async for chunk in ollama_client.chat_stream(model, llm_messages):
                reply += chunk
                yield "delta", {"text": chunk}
    except (asyncio.CancelledError, GeneratorExit):
        # Interrupted (stop button / user started talking): keep what was said so far.
        if reply.strip():
            sessions.add_message(session_id, "assistant", reply.strip(), {"interrupted": True, "model": model})
        if on_saved:
            on_saved()
        raise
    except OllamaError as e:
        yield "error", {"message": str(e), "_partial": bool(reply)}
        return
    reply = reply.strip()
    message_id = sessions.add_message(session_id, "assistant", reply, {"model": model}) if reply else None
    if on_saved:
        on_saved()
    yield "done", {"message_id": message_id, "text": reply}


async def chat_turn(
    session_id: int | None,
    user_text: str,
    user_meta: dict | None = None,
    on_correction: CorrectionCallback | None = None,
) -> AsyncIterator[Event]:
    """Yields ("meta" | "delta" | "done" | "error", data).

    on_correction is awaited later with the correction of the user's message when the
    correction mode is "every"; with "end" it is only stored (for the session report).
    """
    settings = get_settings()
    if session_id is None or not sessions.session_exists(session_id):
        session_id = sessions.create_session("conversation")

    user_message_id = sessions.add_message(session_id, "user", user_text, user_meta)
    history = sessions.recent_messages(session_id, CHAT_HISTORY_LIMIT)
    llm_messages = [{"role": "system", "content": system_prompt(session_id, settings)}, *history]

    def queue_correction() -> None:
        mode = settings["correction_mode"]
        if mode == "off":
            return
        source = (user_meta or {}).get("source", "text")
        notify = on_correction if mode == "every" else None
        # The AI's previous line as context, so "He is a teacher" after "your sister?" is caught.
        previous = next((m["content"] for m in reversed(history[:-1]) if m["role"] == "assistant"), "")
        correction_worker.submit(Job(user_message_id, user_text, source, notify, context=previous))

    yield "meta", {"session_id": session_id, "user_message_id": user_message_id}
    async for event, data in _stream_reply(session_id, llm_messages, queue_correction):
        if event == "error":
            # Drop the unanswered message so a retry doesn't leave duplicates in history.
            if not data.pop("_partial"):
                sessions.delete_message(user_message_id)
        yield event, data


async def opening_turn(session_id: int) -> AsyncIterator[Event]:
    """The AI's first line of a role-play (the learner has said nothing yet)."""
    settings = get_settings()
    llm_messages = [
        {"role": "system", "content": system_prompt(session_id, settings)},
        # Not stored: only asks the model to begin.
        {"role": "user", "content": scenarios.opening_request(sessions.scenario_of(session_id))},
    ]
    yield "meta", {"session_id": session_id, "user_message_id": None}
    async for event, data in _stream_reply(session_id, llm_messages):
        data.pop("_partial", None)
        yield event, data
