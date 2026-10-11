"""Offline test of the rule-based he/she check (pronoun_check.find_errors): no server, no LLM.
Usage: python pronoun_rule_test.py"""

import os
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓ on a Windows (cp1254) console

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "app"))
from backend.pronoun_check import find_errors  # noqa: E402

CASES = [  # (context, learner text, should be flagged)
    ("", "Yes, I have a sister. He is a teacher and his school is near our house.", True),
    ("", "My mother is a nurse. He works at night.", True),
    ("", "My father is very busy, she works every day.", True),
    ("", "I called my brother and talked to her for an hour.", True),
    ("", "My sister is a teacher. She loves her job.", False),
    ("", "My brother lives in Izmir with his wife.", False),
    ("", "I met Can yesterday. He told me about his new job.", False),
    ("Tell me about your sister.", "He's a teacher.", True),
    ("Tell me about your sister.", "He is a teacher.", True),
    ("What does your mother do?", "He is a doctor.", True),
    ("Do you have a brother?", "Yes, my brother is a manager. She works in Ankara.", True),
    ("What does your brother do?", "My brother is an engineer and she is happy.", True),
    ("", "I live in İstanbul with my wife. He is a teacher.", True),
    # a person of unknown gender was mentioned: not flagged
    ("What does your father do?", "My father works with my friend Ayşe and she is very kind.", False),
    ("What does your father do?", "He works with a colleague and she helps him a lot.", False),
    ("Is your sister married?", "Yes, her husband is a doctor. He is very nice.", False),
    ("", "My dad and Mrs Yılmaz are neighbours. She is very old.", False),
]

ok = 0
for context, text, expected in CASES:
    found = find_errors(context, text)
    good = bool(found) == expected
    ok += good
    print(f"{'✓' if good else '✗'} {expected!s:5} {[(e['wrong'], e['right']) for e in found]} | {context} | {text}")
print(f"\n{ok}/{len(CASES)} doğru")
sys.exit(0 if ok == len(CASES) else 1)
