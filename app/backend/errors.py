"""The one fixed list of error categories.

Every correction (speech, writing, …) is stored with one of these ids, so statistics
stay comparable over time and can later be mapped to lesson topics.

Rules: never rename or reuse an id. To change the list, add new ids, bump
TAXONOMY_VERSION, and keep the old ids readable.
"""

TAXONOMY_VERSION = 1

# id: stable key stored in the DB · name: what the LLM picks · tr: label shown to the user
# hint: one-line definition given to the LLM so it classifies consistently
CATEGORIES = [
    {"id": "tense", "name": "Tense", "tr": "Zaman",
     "hint": "wrong verb tense, e.g. 'Yesterday I go' instead of 'went'"},
    {"id": "verb_form", "name": "Verb Form", "tr": "Fiil yapısı",
     "hint": "wrong form of the verb (not tense): gerund vs infinitive, modal + verb, participles, e.g. 'I enjoy to swim', 'he can goes'"},
    {"id": "subject_verb_agreement", "name": "Subject-Verb Agreement", "tr": "Özne-yüklem uyumu",
     "hint": "verb does not agree with subject, e.g. 'he go', 'they was'"},
    {"id": "article", "name": "Article", "tr": "Tanımlık (a/an/the)",
     "hint": "missing, extra or wrong a/an/the"},
    {"id": "preposition", "name": "Preposition", "tr": "Edat",
     "hint": "wrong, missing or extra preposition, e.g. 'arrive to', 'good in'"},
    {"id": "pronoun", "name": "Pronoun", "tr": "Zamir",
     "hint": "wrong pronoun, e.g. he/she/it confusion, 'me and him went'"},
    {"id": "plural", "name": "Plural", "tr": "Çoğul",
     "hint": "singular/plural noun error, e.g. 'two book', 'many informations'"},
    {"id": "word_order", "name": "Word Order", "tr": "Kelime sırası",
     "hint": "words in the wrong order, including question word order, e.g. 'Where you are going?'"},
    {"id": "word_choice", "name": "Word Choice", "tr": "Kelime seçimi",
     "hint": "wrong or unnatural word for the meaning, e.g. 'make a photo', 'I learned him English'"},
    {"id": "missing_word", "name": "Missing Word", "tr": "Eksik kelime",
     "hint": "a needed word is missing (other than an article or preposition), e.g. 'I very happy'"},
    {"id": "extra_word", "name": "Extra Word", "tr": "Fazla kelime",
     "hint": "an unnecessary word (other than an article or preposition), e.g. 'I am agree'"},
    {"id": "spelling", "name": "Spelling", "tr": "Yazım",
     "hint": "misspelled word (written text only)"},
    {"id": "punctuation", "name": "Punctuation", "tr": "Noktalama",
     "hint": "punctuation or capitalization error (written text only)"},
    {"id": "other", "name": "Other", "tr": "Diğer",
     "hint": "anything that fits no other category"},
]

# How to practise each category in a focused conversation ("Bu konuda pratik yap").
# focus: what the AI steers the conversation towards (prompt, English)
# tasks: (Turkish for the UI, English for the prompt). Written-only categories are
# practised in the writing mode instead.
PRACTICE = {
    "tense": {"focus": "past experiences, recent news and future plans, so the learner must use past simple, "
                       "present perfect and future forms",
              "tasks": [("Geçen hafta sonu ne yaptığını anlat", "describe what they did last weekend"),
                        ("Gelecek planlarından bahset", "talk about their plans for next month")]},
    "verb_form": {"focus": "likes, plans and abilities, so the learner uses verbs like enjoy, want, decide, avoid "
                           "and modal verbs (can, should, must) correctly",
                  "tasks": [("Yapmaktan hoşlandığın şeyleri anlat (enjoy …ing)", "say what they enjoy doing"),
                            ("Yapabildiğin / yapman gereken şeyleri söyle", "talk about what they can and should do")]},
    "subject_verb_agreement": {"focus": "other people's daily routines and habits (he/she/it + verb with -s)",
                               "tasks": [("Bir aile üyesinin günlük rutinini anlat", "describe a family member's daily routine"),
                                         ("Bir arkadaşının alışkanlıklarını anlat", "describe a friend's habits")]},
    "article": {"focus": "describing places, objects and people's jobs, which needs a/an/the",
                "tasks": [("Evini ya da odanı tarif et", "describe their home or room"),
                          ("Ailende kim ne iş yapıyor, anlat", "say what jobs people in their family do")]},
    "preposition": {"focus": "where things are, when events happen and how people travel (in/on/at, to, by)",
                    "tasks": [("Bir günün saatleriyle programını anlat", "describe their schedule with times and days"),
                              ("İşe/okula nasıl gittiğini anlat", "explain how they get to work or school")]},
    "pronoun": {"focus": "other people — family, friends and colleagues — so the learner uses he/she/they/him/her "
                         "correctly",
                "tasks": [("Bir kadın ve bir erkek arkadaşını anlat", "describe a female friend and a male friend"),
                          ("Ailen hakkında konuş", "talk about their family members")]},
    "plural": {"focus": "quantities, shopping and collections (plural and uncountable nouns)",
               "tasks": [("Alışveriş listeni söyle", "list what they need to buy"),
                         ("Odanda kaç tane ne var, anlat", "say how many of different things they have")]},
    "word_order": {"focus": "lots of questions: ask the learner to ask YOU questions too, and to describe things "
                            "with adjectives",
                   "tasks": [("Bana en az üç soru sor", "ask the partner at least three questions"),
                             ("Bir eşyayı birkaç sıfatla tarif et", "describe an object using several adjectives")]},
    "word_choice": {"focus": "everyday activities that need common collocations (make/do, say/tell, take/have)",
                    "tasks": [("Ev işlerini anlat (do/make)", "talk about housework"),
                              ("Bir anını anlat (say/tell)", "tell a short story about something that happened")]},
    "missing_word": {"focus": "feelings, opinions and descriptions in full sentences with the verb 'be'",
                     "tasks": [("Bugün nasıl hissettiğini anlat", "say how they feel today and why"),
                               ("Şehrini tarif et", "describe their city")]},
    "extra_word": {"focus": "agreeing, disagreeing and giving opinions (I agree, I think, I like)",
                   "tasks": [("Bir konuda katıl ya da katılma", "agree or disagree with an opinion"),
                             ("Sevdiğin ve sevmediğin şeyleri söyle", "say what they like and don't like")]},
    "other": {"focus": "an everyday topic with full, careful sentences",
              "tasks": [("Kendini tanıt", "introduce themselves"), ("Hobilerini anlat", "talk about their hobbies")]},
}

BY_ID = {c["id"]: c for c in CATEGORIES}
_BY_NAME = {c["name"].lower(): c["id"] for c in CATEGORIES}

# Categories that make no sense for a speech transcript.
WRITTEN_ONLY = {"spelling", "punctuation"}


def names(spoken: bool = False) -> list[str]:
    return [c["name"] for c in CATEGORIES if not (spoken and c["id"] in WRITTEN_ONLY)]


def normalize(value: str) -> str:
    """Map an LLM-provided category (name or id, any case) to a stable id."""
    key = (value or "").strip().lower()
    if key in BY_ID:
        return key
    return _BY_NAME.get(key, _BY_NAME.get(key.replace("_", " "), "other"))


def prompt_lines(spoken: bool = False) -> str:
    return "\n".join(
        f'- "{c["name"]}": {c["hint"]}'
        for c in CATEGORIES
        if not (spoken and c["id"] in WRITTEN_ONLY)
    )
