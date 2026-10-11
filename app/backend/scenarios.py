"""Role-play scenarios: the ready-made ones and the learner's own (custom) ones.

A scenario is stored with its session (sessions.scenario_json), so the chat prompt
and the end-of-session report always know the context, even for custom ones.
"""

from . import llm_models, ollama_client
from .settings_store import get_level

# Fields: id · icon · title_tr / description_tr (UI) · role / learner_role / setting (prompt,
# English) · tasks: (Turkish for the UI, English for the prompt)
SCENARIOS = [
    {
        "id": "job_interview", "icon": "💼",
        "title_tr": "İş görüşmesi (yazılım geliştirici)",
        "description_tr": "Bir teknoloji şirketinde yazılım geliştirici pozisyonu için mülakattasın.",
        "role": "a friendly but professional hiring manager at a software company",
        "learner_role": "a candidate applying for a software developer position",
        "setting": "a job interview in a meeting room at a mid-sized tech company",
        "tasks": [
            ("Kendini ve deneyimini tanıt", "introduce themselves and their experience"),
            ("Bir projeni anlat", "describe a project they worked on"),
            ("Şirket hakkında bir soru sor", "ask a question about the company or the team"),
        ],
    },
    {
        "id": "restaurant", "icon": "🍽️",
        "title_tr": "Restoranda sipariş",
        "description_tr": "Bir restorandasın; garsondan menü hakkında bilgi alıp sipariş vereceksin.",
        "role": "a waiter at a busy but friendly restaurant",
        "learner_role": "a customer having dinner",
        "setting": "a restaurant in the evening; the customer has just sat down",
        "tasks": [
            ("Bir yemeğin içeriğini sor", "ask what is in a dish"),
            ("Ana yemek ve içecek sipariş et", "order a main course and a drink"),
            ("Hesabı iste", "ask for the bill"),
        ],
    },
    {
        "id": "airport", "icon": "🛂",
        "title_tr": "Havalimanı / pasaport kontrolü",
        "description_tr": "Londra'ya indin; pasaport kontrolünde görevlinin sorularını cevaplıyorsun.",
        "role": "a border control officer at London Heathrow airport",
        "learner_role": "a traveller arriving from Istanbul",
        "setting": "the passport control desk at the airport",
        "tasks": [
            ("Seyahatinin amacını söyle", "explain the purpose of the trip"),
            ("Ne kadar kalacağını ve nerede kalacağını söyle", "say how long they will stay and where"),
            ("Dönüş biletin hakkında bilgi ver", "talk about their return ticket"),
        ],
    },
    {
        "id": "hotel", "icon": "🏨",
        "title_tr": "Otel check-in",
        "description_tr": "Otele vardın; resepsiyonda giriş yapıp otel hakkında sorular soruyorsun.",
        "role": "a receptionist at a city-centre hotel",
        "learner_role": "a guest who has a reservation",
        "setting": "the hotel reception desk in the afternoon",
        "tasks": [
            ("Rezervasyonunu belirt", "say they have a reservation and give their name"),
            ("Kahvaltı saatini sor", "ask about breakfast times"),
            ("Bir sorun ya da özel istek belirt", "make a special request or mention a problem"),
        ],
    },
    {
        "id": "doctor", "icon": "🩺",
        "title_tr": "Doktor randevusu",
        "description_tr": "Kendini iyi hissetmiyorsun; doktora şikayetlerini anlatıyorsun.",
        "role": "a general practitioner (family doctor)",
        "learner_role": "a patient who has felt unwell for a few days",
        "setting": "a doctor's consultation room",
        "tasks": [
            ("Belirtilerini anlat", "describe their symptoms"),
            ("Ne zamandır böyle olduğunu söyle", "say how long they have felt this way"),
            ("İlaç nasıl kullanılır, sor", "ask how to take the medicine"),
        ],
    },
    {
        "id": "small_talk", "icon": "👋",
        "title_tr": "Yeni biriyle tanışma (small talk)",
        "description_tr": "Bir etkinlikte yeni biriyle tanışıp sohbet ediyorsun.",
        "role": "a friendly person the learner meets at a tech meetup",
        "learner_role": "an attendee at the same meetup",
        "setting": "a casual tech meetup with snacks and drinks",
        "tasks": [
            ("Kendini tanıt", "introduce themselves"),
            ("Ortak bir ilgi alanı bul", "find a shared interest"),
            ("Sohbeti nazikçe bitir", "politely end the conversation"),
        ],
    },
    {
        "id": "tech_meeting", "icon": "🧑‍💻",
        "title_tr": "Teknik toplantıda fikir sunma",
        "description_tr": "Ekip toplantısında yeni bir fikri ya da teknik çözümü sunuyorsun.",
        "role": "a team lead in a software team meeting, curious and asking follow-up questions",
        "learner_role": "a developer presenting an idea to improve the product",
        "setting": "a weekly team meeting (video call)",
        "tasks": [
            ("Fikrini kısaca açıkla", "briefly explain their idea"),
            ("Faydalarını anlat", "explain the benefits"),
            ("Bir itiraza cevap ver", "respond to a concern or objection"),
        ],
    },
    {
        "id": "return_product", "icon": "📦",
        "title_tr": "Ürün iadesi / şikayet",
        "description_tr": "Aldığın ürün bozuk çıktı; mağazada iade ya da değişim istiyorsun.",
        "role": "a customer service assistant in an electronics store",
        "learner_role": "a customer whose new headphones stopped working",
        "setting": "the customer service desk of an electronics store",
        "tasks": [
            ("Sorunu açıkla", "explain the problem"),
            ("Ne zaman satın aldığını söyle", "say when they bought it"),
            ("İade ya da değişim iste", "ask for a refund or a replacement"),
        ],
    },
]

_BY_ID = {s["id"]: s for s in SCENARIOS}


def public(s: dict) -> dict:
    """What the UI needs (Turkish texts, tasks)."""
    return {
        "id": s["id"], "icon": s.get("icon", "🎭"), "title_tr": s["title_tr"],
        "description_tr": s.get("description_tr", ""), "tasks_tr": [t[0] for t in s.get("tasks", [])],
        "custom": s["id"] == "custom",
    }


def get(scenario_id: str) -> dict | None:
    return _BY_ID.get(scenario_id)


PROMPT = """You are role-playing as {role} in this scenario: {setting}.
The learner is a Turkish {level}-level English speaker playing {learner_role}.

- Stay in character the whole time. Speak naturally as {role} would.
- Keep each reply to 1-3 sentences, spoken style, no markdown, lists or emojis. Your output will be read aloud.
- Adjust difficulty to {level}. If the learner struggles, simplify your language.
- Do NOT correct the learner's mistakes, not even by repeating their sentence correctly — corrections are handled separately.
- During the conversation, naturally give the learner chances to: {tasks}.
- If the learner switches to Turkish, stay in character and gently help them say it in English."""

OPENING_REQUEST = ("(Start the role-play now. You are {role}; the learner, {learner_role}, has just come to talk "
                   "to you. Say your opening line as {role} would.)")


FOCUS_OPENING_REQUEST = "(Start the conversation now with a friendly greeting and your first question.)"


def opening_request(scenario: dict) -> str:
    if scenario.get("kind") in ("focus", "lesson"):
        return FOCUS_OPENING_REQUEST
    return OPENING_REQUEST.format(role=scenario["role"], learner_role=scenario["learner_role"])


FOCUS_PROMPT = """You are a friendly English conversation partner and teacher. The learner is a Turkish speaker at CEFR level {level} who often makes "{category}" mistakes.
Have a natural conversation about {focus}.

- Ask questions that make the learner use this structure; one question at a time.
- Keep each reply to 1-3 sentences, spoken style, no markdown, lists or emojis. Your output will be read aloud.
- Do NOT correct the learner's mistakes in your reply — corrections are handled separately.
- Model the correct structure naturally in your own sentences.
- If the learner switches to Turkish, gently help them say it in English."""


def focus_scenario(category_id: str) -> dict | None:
    """A practice session aimed at one error category (weak points → "pratik yap")."""
    from . import errors

    practice = errors.PRACTICE.get(category_id)
    category = errors.BY_ID.get(category_id)
    if not practice or not category:
        return None
    return {
        "id": f"focus_{category_id}", "icon": "🎯", "kind": "focus", "category": category_id,
        "title_tr": f"Odaklı pratik: {category['tr']}",
        "description_tr": f"{category['tr']} konusunu sohbet içinde çalış.",
        "role": "a friendly conversation partner", "learner_role": "themselves",
        "setting": practice["focus"], "focus": practice["focus"],
        "tasks": practice["tasks"],
    }


LESSON_PROMPT = """You are a friendly English conversation partner and teacher. The learner is a Turkish speaker at CEFR level {level} who has just studied this lesson: "{topic}".
Have a natural conversation about {focus}.

- Ask questions that make the learner use the structure of the lesson; one question at a time.
- Keep each reply to 1-3 sentences, spoken style, no markdown, lists or emojis. Your output will be read aloud.
- Do NOT correct the learner's mistakes in your reply — corrections are handled separately.
- Use the structure naturally in your own sentences, so the learner hears it.
- If the learner switches to Turkish, gently help them say it in English."""


def lesson_scenario(lesson: dict) -> dict:
    """Conversation practice for a lesson (Dersler → "Konuşarak pratik yap")."""
    practice = lesson["practice"]
    return {
        "id": f"lesson_{lesson['id']}", "icon": "📘", "kind": "lesson", "lesson_id": lesson["id"],
        "level": lesson["level"],
        "title_tr": f"Ders pratiği: {lesson['title_tr']}",
        "description_tr": f"{lesson['title_tr']} konusunu sohbet içinde kullan.",
        "role": "a friendly conversation partner", "learner_role": "themselves",
        "setting": practice["focus"], "focus": practice["focus"], "topic": lesson["title_en"],
        "tasks": [tuple(t) for t in practice.get("tasks", [])],
    }


def system_prompt(scenario: dict) -> str:
    if scenario.get("kind") == "lesson":
        # The lesson's own level: an A1 lesson stays simple even for a B1 learner.
        return LESSON_PROMPT.format(level=scenario.get("level") or get_level(), topic=scenario["topic"],
                                    focus=scenario["focus"])
    if scenario.get("kind") == "focus":
        from . import errors

        return FOCUS_PROMPT.format(level=get_level(), category=errors.BY_ID[scenario["category"]]["name"],
                                   focus=scenario["focus"])
    return PROMPT.format(
        role=scenario["role"],
        setting=scenario["setting"],
        learner_role=scenario["learner_role"],
        level=get_level(),
        tasks="; ".join(t[1] for t in scenario.get("tasks", [])) or "talk naturally about the situation",
    )


CUSTOM_PROMPT = """A Turkish English learner wants to practice this situation (it may be written in Turkish):
"{description}"

The learner plays THEMSELVES — the person who wrote this ("I", "my"). The AI plays the OTHER person in the situation.
Turn it into a short role-play setup:
- "title_tr": a short Turkish title (max 6 words)
- "role": the other person, whom the AI plays (English, a short phrase)
- "learner_role": the learner's own part in this situation (English, a short phrase, not "a learner")
- "setting": where and when it happens (English, one sentence)
- "tasks": exactly 3 things THE LEARNER should try to do in the conversation, each as {{"tr": Turkish, "en": English}}

Example — "Komşumun köpeği bütün gün havlıyor, onunla konuşacağım":
{{"title_tr": "Havlayan köpek hakkında konuşma", "role": "a neighbour whose dog barks all day",
 "learner_role": "a neighbour who is bothered by the barking", "setting": "in the hallway of an apartment building in the evening",
 "tasks": [{{"tr": "Sorunu kibarca anlat", "en": "politely explain the problem"}}, {{"tr": "Ne zamandır sürdüğünü söyle", "en": "say how long it has been going on"}}, {{"tr": "Bir çözüm öner", "en": "suggest a solution"}}]}}"""

CUSTOM_SCHEMA = {
    "type": "object",
    "properties": {
        "title_tr": {"type": "string"},
        "role": {"type": "string"},
        "learner_role": {"type": "string"},
        "setting": {"type": "string"},
        "tasks": {
            "type": "array",
            "items": {"type": "object", "properties": {"tr": {"type": "string"}, "en": {"type": "string"}},
                      "required": ["tr", "en"]},
        },
    },
    "required": ["title_tr", "role", "learner_role", "setting", "tasks"],
}


async def build_custom(description: str) -> dict:
    """Ask the LLM to structure the learner's own situation into a scenario."""
    raw = await ollama_client.chat_json(
        llm_models.current(),
        [{"role": "user", "content": CUSTOM_PROMPT.format(description=description.replace('"', "'"))}],
        CUSTOM_SCHEMA,
        options={"temperature": 0.3, "num_predict": 300},
    )
    return {
        "id": "custom", "icon": "✏️",
        "title_tr": (raw.get("title_tr") or "Özel senaryo").strip(),
        "description_tr": description.strip(),
        "role": (raw.get("role") or "the other person in this situation").strip(),
        "learner_role": (raw.get("learner_role") or "themselves").strip(),
        "setting": (raw.get("setting") or description).strip(),
        "tasks": [(t.get("tr", ""), t.get("en", "")) for t in (raw.get("tasks") or [])[:3] if t.get("en")],
    }
