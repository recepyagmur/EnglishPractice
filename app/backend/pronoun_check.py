"""Rule-based he/she check (Turkish has one pronoun, "o", so this is the most common mistake).

The small LLM misses a pronoun that does not match a person named in an EARLIER sentence
("Tell me about your sister." → "He is a teacher."). This check is deterministic:
a learner pronoun of one gender is wrong when, before it (in the context or the learner's
own text), only people of the other gender were mentioned. Names are not used (their gender
is unknown); the LLM still checks those.
"""

import re

FEMALE_NOUNS = {"mother", "mom", "mum", "mommy", "sister", "wife", "daughter", "aunt", "grandmother", "grandma",
                "granny", "girlfriend", "girl", "woman", "lady", "niece", "queen", "actress", "waitress"}
MALE_NOUNS = {"father", "dad", "daddy", "brother", "husband", "son", "uncle", "grandfather", "grandpa",
              "boyfriend", "boy", "man", "gentleman", "nephew", "king", "actor", "waiter"}
FEMALE_PRONOUNS = {"she", "her", "hers", "herself"}
MALE_PRONOUNS = {"he", "him", "his", "himself"}

# pronoun → the other gender's form; "her" depends on what follows (her car → his car, love her → him)
SWAP = {"he": "she", "she": "he", "him": "her", "himself": "herself", "herself": "himself", "hers": "his",
        "his": "her"}
# Words after "her" that make it possessive ("her new car" → "his"); otherwise it is an object ("love her").
_NOT_A_NOUN_AFTER = {"and", "or", "but", "to", "for", "with", "at", "in", "on", "very", "so", "too", "a", "an", "the",
                     "about", "from", "that", "because", "when", "if", "yesterday", "today", "now", "again", "back",
                     "up", "out", "of", "every", "last", "this", "much", "lot", "is", "was", "will", "can"}

FEMALE_NOUNS |= {"mrs", "ms"}  # not "miss": also a verb ("I miss him")
MALE_NOUNS |= {"mr"}
# People whose gender we don't know. Once one is mentioned (as a new person, not "she is a teacher"),
# a later he/she may refer to them: not flagged (a false alarm is worse than a miss).
NEUTRAL_PERSONS = {
    "friend", "colleague", "coworker", "co-worker", "boss", "manager", "teacher", "doctor", "neighbour", "neighbor",
    "cousin", "customer", "client", "partner", "student", "classmate", "roommate", "flatmate", "engineer", "nurse",
    "person", "someone", "somebody", "child", "kid", "baby", "parent", "director", "assistant", "guest", "teammate",
    "supervisor", "employee", "lawyer", "dentist", "driver", "owner", "officer", "relative", "sibling", "spouse",
    "chef", "cook", "secretary", "receptionist", "developer", "designer", "accountant", "author", "writer", "artist",
}
_PREDICATE_BEFORE = {"is", "was", "are", "were", "am", "be", "been", "as", "becomes", "became"}
_PLACE_BEFORE = {"in", "at", "to", "from", "near", "into", "around", "visit", "visited", "visiting", "of"}

# Unicode letters: Turkish names ("Ayşe") stay one token.
_TOKEN = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")


def _is_name(tok: re.Match, text: str) -> bool:
    """A capitalized word in the middle of a sentence that is not an English word: probably a name."""
    word = tok.group(0).split("'")[0]
    if not word[:1].isupper() or word == "I":
        return False
    before = text[:tok.start()].rstrip()
    if not before or before[-1] in ".!?:\"“":  # sentence start
        return False
    if before.split()[-1].lower() in _PLACE_BEFORE:  # "in İstanbul", "to Ankara": a place
        return False
    if not word.isascii():
        return True
    try:
        from .dictionary import is_english_word  # dictionary imports corrections → this module
        return not is_english_word(word)
    except Exception:  # dictionary not installed
        return False


def _new_unknown_person(tokens: list, i: int, text: str) -> bool:
    """tokens[i] mentions a person of unknown gender (a name, or "my friend" but not "she is a teacher")."""
    m = tokens[i]
    low = m.group(0).lower().split("'")[0]
    if _is_name(m, text):
        return True
    noun = low[:-1] if low.endswith("s") and low[:-1] in NEUTRAL_PERSONS else low
    if noun not in NEUTRAL_PERSONS:
        return False
    prev = [t.group(0).lower() for t in tokens[max(0, i - 2):i]]
    predicate = (len(prev) == 2 and prev[1] in ("a", "an", "the", "my", "your", "our", "their")
                 and prev[0].split("'")[-1] in _PREDICATE_BEFORE | {"s"})  # "she is a teacher", "Ali is my friend"
    return not predicate

EXPLAIN = {
    "tr": "Bahsedilen kişi {who} ({noun}) olduğu için '{right}' kullanılmalı. Türkçedeki 'o' İngilizcede ikiye ayrılır.",
    "en": "The person you are talking about is {who_en} ({noun}), so use '{right}'.",
}
EXPLAIN_BY_PRONOUN = {  # the person was only referred to with a pronoun before ("What does she do?")
    "tr": "Konuşulan kişi {who} (önceki cümlede '{noun}' geçiyor), bu yüzden '{right}' kullanılmalı. "
          "Türkçedeki 'o' İngilizcede ikiye ayrılır.",
    "en": "The person being talked about is {who_en} ('{noun}' before), so use '{right}'.",
}


def _gender(word: str) -> str | None:
    w = word.lower()
    if w in FEMALE_NOUNS or w + "s" in FEMALE_NOUNS:
        return "f"
    if w in MALE_NOUNS:
        return "m"
    if w.endswith("s") and (w[:-1] in FEMALE_NOUNS or w[:-1] in MALE_NOUNS):  # sisters, brothers
        return "f" if w[:-1] in FEMALE_NOUNS else "m"
    return None


def _match_case(word: str, like: str) -> str:
    return word.capitalize() if like[:1].isupper() else word


def find_errors(context: str, text: str, lang: str = "tr") -> list[dict]:
    """Pronoun errors in `text` as correction errors ({wrong, right, category, explanation})."""
    seen = {"f": None, "m": None}  # gender → the first noun/pronoun that introduced it
    unknown = False  # a person of unknown gender was mentioned: he/she may refer to them
    context = context or ""
    ctx_tokens = list(_TOKEN.finditer(context))
    for i, tok in enumerate(ctx_tokens):
        low = tok.group(0).lower().split("'")[0]
        g = _gender(low) or ("f" if low in FEMALE_PRONOUNS else "m" if low in MALE_PRONOUNS else None)
        if g and not seen[g]:
            seen[g] = low
        unknown = unknown or _new_unknown_person(ctx_tokens, i, context)
    errors = []
    tokens = list(_TOKEN.finditer(text))
    for i, m in enumerate(tokens):
        word = m.group(0).split("'")[0]  # "He's" → "He"
        low = word.lower()
        g = _gender(low)
        if g:
            seen[g] = seen[g] or low
            continue
        pron = "f" if low in FEMALE_PRONOUNS else "m" if low in MALE_PRONOUNS else None
        if not pron:
            unknown = unknown or _new_unknown_person(tokens, i, text)
            continue
        other = "m" if pron == "f" else "f"
        if seen[pron] or not seen[other] or unknown:
            seen[pron] = seen[pron] or low  # a pronoun the learner used consistently is a referent too
            continue
        if low == "her":
            nxt = tokens[i + 1].group(0).lower() if i + 1 < len(tokens) else ""
            right = "his" if nxt and nxt not in _NOT_A_NOUN_AFTER else "him"
        else:
            right = SWAP[low]
        right = _match_case(right, word)
        noun = seen[other]
        who = "erkek" if other == "m" else "kadın"
        errors.append({
            "wrong": word, "right": right, "category": "pronoun",
            "explanation": (EXPLAIN_BY_PRONOUN if noun in FEMALE_PRONOUNS | MALE_PRONOUNS else EXPLAIN).get(
                lang, EXPLAIN["tr"]).format(
                who=who, who_en="a man" if other == "m" else "a woman", noun=noun, right=right),
        })
    return errors


def apply(text: str, errors: list[dict]) -> str:
    """The text with each pronoun error replaced (whole words, in order)."""
    out, pos = [], 0
    for e in errors:
        m = re.compile(rf"\b{re.escape(e['wrong'])}\b").search(text, pos)
        if not m:
            continue
        out.append(text[pos:m.start()] + e["right"])
        pos = m.end()
    return "".join(out) + text[pos:]
