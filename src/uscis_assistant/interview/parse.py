"""Turn a typed answer into the value stored for the form. Deterministic, no model.

Nothing is guessed: an answer that cannot be read unambiguously is rejected with a message
asking again. Dates are accepted only in the format the user was told, or ISO yyyy-mm-dd.
"""

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from uscis_assistant.forms.i765.schema import US_STATE_CODES
from uscis_assistant.interview.bank import Language, Question
from uscis_assistant.interview.texts import DONT_KNOW, NO, NONE_WORDS, YES

CYRILLIC = re.compile(r"[Ѐ-ӿ]")
DATE_PATTERNS: dict[Language, re.Pattern[str]] = {
    "ru": re.compile(r"^(?P<d>\d{2})\.(?P<m>\d{2})\.(?P<y>\d{4})$"),
    "uk": re.compile(r"^(?P<d>\d{2})\.(?P<m>\d{2})\.(?P<y>\d{4})$"),
    "en": re.compile(r"^(?P<m>\d{2})/(?P<d>\d{2})/(?P<y>\d{4})$"),
}
ISO_DATE = re.compile(r"^(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})$")


class Parsed(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: bool
    value: Any = None  # JSON value stored as the English answer
    error: str | None = None  # key into texts.MESSAGES
    translation_method: Literal["same", "pending"] = "same"


def _fail(error: str) -> Parsed:
    return Parsed(ok=False, error=error)


def _date(text: str, language: Language) -> Parsed:
    match = DATE_PATTERNS[language].match(text) or ISO_DATE.match(text)
    if match is None:
        return _fail("date")
    try:
        value = date(int(match["y"]), int(match["m"]), int(match["d"]))
    except ValueError:
        return _fail("date")
    return Parsed(ok=True, value=value.isoformat())


def parse_answer(question: Question, raw: str, language: Language) -> Parsed:
    text = raw.strip()
    lowered = text.lower()
    if not text:
        return _fail("empty")

    if question.allow_na and (lowered in NONE_WORDS[language] or lowered == "n/a"):
        return Parsed(ok=True, value="N/A")
    if question.optional and question.kind != "yes_no" and lowered in NONE_WORDS[language]:
        return Parsed(ok=True, value=None)

    if question.kind == "yes_no":
        if lowered in YES[language] or lowered in YES["en"]:
            return Parsed(ok=True, value=True)
        if lowered in NO[language] or lowered in NO["en"]:
            return Parsed(ok=True, value=False)
        return _fail("yes_no")

    if question.kind == "choice":
        choices = question.choices or []
        for number, choice in enumerate(choices, start=1):
            if lowered in (str(number), choice.labels[language].lower()):
                return Parsed(ok=True, value=choice.value)
        return _fail("choice")

    if question.kind == "state":
        code = text.upper()
        return Parsed(ok=True, value=code) if code in US_STATE_CODES else _fail("state")

    if question.kind == "date":
        return _date(text, language)

    if question.kind == "category":
        # The user's own words; "I don't know" means an attorney reviews the case.
        if lowered in DONT_KNOW[language] or lowered in DONT_KNOW["en"]:
            return Parsed(ok=True, value=None)
        return Parsed(ok=True, value=text)

    # Free text
    if CYRILLIC.search(text):
        if question.script == "latin":
            return _fail("latin")
        return Parsed(ok=True, value=None, translation_method="pending")
    return Parsed(ok=True, value=text)
