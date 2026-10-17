"""Decide how an incoming message is handled before anything is recorded.

1. Obvious requests for legal advice are caught by patterns, without any model call, and
   politely declined.
2. Messages that might not be answers go to the model for a label: they contain "?", fail
   deterministic parsing, are a category that does not look like a category code, or are
   long free text.
3. Plain answers are recorded without a model call, which also keeps personal data such as
   names and numbers away from the model.
"""

import re
from enum import StrEnum

from uscis_assistant.interview.bank import Language, Question
from uscis_assistant.interview.parse import Parsed, parse_answer
from uscis_assistant.validation.i765 import CATEGORY_SHAPE

LONG_ANSWER_WORDS = 8

ADVICE_PATTERNS: dict[Language, list[re.Pattern[str]]] = {
    "ru": [
        re.compile(p, re.IGNORECASE)
        for p in (
            r"подхож(у|у ли|ит ли|ит мне)",
            r"\bшанс",
            r"(какую|какой|какие|что) .{0,25}(подать|подавать|выбрать|указать)",
            r"(стоит|надо|нужно) ли (мне )?(подавать|подать|указывать|писать)",
            r"(одобрят|откажут) ли",
            r"имею ли (я )?право",
            r"посоветуй|посоветуете|посоветовать|совет(а|у)? (по|для)",
            r"что (мне )?(делать|лучше)",
            r"\bмой (кейс|случай) .{0,20}(сильн|слаб|хорош|пройд)",
        )
    ],
    "uk": [
        re.compile(p, re.IGNORECASE)
        for p in (
            r"підход(жу|ить мені|жу чи)",
            r"\bшанс",
            r"(яку|який|які|що) .{0,25}(подати|подавати|обрати|вибрати|вказати)",
            r"(чи )?(варто|треба|потрібно) (мені )?(подавати|подати|вказувати|писати)",
            r"(схвалять|відмовлять) (мені|чи)",
            r"чи маю (я )?право",
            r"порад(ьте|ь|а|у)",
            r"що (мені )?(робити|краще)",
            r"\bмій (кейс|випадок) .{0,20}(сильн|слабк|добр|пройд)",
        )
    ],
    "en": [
        re.compile(p, re.IGNORECASE)
        for p in (
            r"\b(do|would|will|can|could) i (qualify|be eligible|get (approved|a work permit))",
            r"\bam i (eligible|qualified)",
            # Not a bare "chance": it is also a first and last name.
            r"\bchances?\s+(of|to|for|that|are|is)\b",
            r"\b(my|any|the|what are (the|my)) chances?\b",
            r"\bshould i (file|apply|choose|select|use|put|enter|write)",
            r"\bwhich (category|form|option)\b",
            r"\bwhat (category|form) (should|do|must) i\b",
            # Not a bare "advise": it is also a surname.
            r"\b(give|need|want|get|any|your|some) (me )?(legal )?advi[cs]e\b",
            r"\badvise me\b",
            r"\bwill (they|uscis) (approve|deny|reject)",
            r"\bwhat should i do\b",
            r"\bis my case\b",
            r"\brecommend",
        )
    ],
}


class Route(StrEnum):
    DECLINE = "decline"  # advice request caught by a pattern
    CLASSIFY = "classify"  # ask the model what this message is before using it
    TRANSLATE = "translate"  # an answer in another script: label and translate it
    RECORD = "record"  # a plain answer


def looks_like_advice_request(text: str, language: Language) -> bool:
    # English patterns apply in every language: people mix languages.
    patterns = ADVICE_PATTERNS[language] + (ADVICE_PATTERNS["en"] if language != "en" else [])
    return any(p.search(text) for p in patterns)


def route(question: Question, text: str, language: Language) -> tuple[Route, Parsed]:
    parsed = parse_answer(question, text, language)
    if looks_like_advice_request(text, language):
        return Route.DECLINE, parsed
    if "?" in text or not parsed.ok:
        return Route.CLASSIFY, parsed
    if parsed.translation_method == "pending":
        return Route.TRANSLATE, parsed
    if question.kind == "category" and parsed.value is not None:
        if not CATEGORY_SHAPE.match(parsed.value):
            return Route.CLASSIFY, parsed
    if question.kind in ("text", "category") and len(text.split()) >= LONG_ANSWER_WORDS:
        return Route.CLASSIFY, parsed
    return Route.RECORD, parsed
