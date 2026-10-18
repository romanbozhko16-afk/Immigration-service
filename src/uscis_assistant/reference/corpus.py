"""Official source documents split into sentences, each with its page.

Only documents pinned in the form registry are used (today: the I-765 instructions of the
active edition). Sentences are the unit the model can cite and the user is shown.
"""

import re
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from pypdf import PdfReader

from uscis_assistant.forms.registry import REPO_ROOT, load_registry

SOURCE_URL = "https://www.uscis.gov/i-765"
PAGE_HEADER = re.compile(r"Form I-765 Instructions\s+\d{2}/\d{2}/\d{2}\s+Page \d+ of \d+")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"“])")


class Sentence(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    page: int
    text: str


class Corpus(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    sentences: list[Sentence]


def normalize(text: str) -> str:
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return re.sub(r" ([,.;:])", r"\1", text).strip()


# A period after these is part of a reference ("Part 6.", "Item Number 16.", "U.S."), not
# the end of a sentence.
NOT_AN_END = re.compile(
    r"(\b(Parts?|Item Numbers?|Items?|Numbers?|No|Pages?|Sections?)\s+[0-9][0-9a-z.,\- ]*\.|"
    r"\b(U\.S|e\.g|i\.e|Mr|Mrs|Ms|Dr|St|v)\.)$"
)


def split_sentences(page_text: str) -> list[str]:
    text = normalize(PAGE_HEADER.sub(" ", page_text))
    sentences: list[str] = []
    for piece in SENTENCE_END.split(text):
        piece = piece.strip()
        if sentences and NOT_AN_END.search(sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {piece}"
        elif piece:
            sentences.append(piece)
    return [s for s in sentences if len(s) >= 3]


def build_corpus(pdf: Path, title: str) -> Corpus:
    sentences: list[Sentence] = []
    for page_number, page in enumerate(PdfReader(pdf).pages, start=1):
        for text in split_sentences(page.extract_text() or ""):
            sentences.append(Sentence(index=len(sentences), page=page_number, text=text))
    return Corpus(title=title, url=SOURCE_URL, sentences=sentences)


@cache
def instructions_corpus() -> Corpus:
    registry = load_registry()
    return build_corpus(
        REPO_ROOT / registry.active.instructions_pdf.path,
        f"Form I-765 Instructions (edition {registry.active_edition})",
    )
