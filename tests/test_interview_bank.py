"""The question bank is product content: these tests keep it complete, sourced and safe."""

import re
from functools import cache

import pytest
from pypdf import PdfReader

from uscis_assistant.forms.field_map import (
    leaf_paths,
    load_field_map,
    normalize_tooltip,
    resolve_path,
)
from uscis_assistant.forms.i765.schema import LIST_CAPACITY, I765Application
from uscis_assistant.forms.registry import REPO_ROOT, load_registry
from uscis_assistant.interview.bank import LANGUAGES
from uscis_assistant.interview.engine import INTERVIEW_PREFIX, load_active_bank


@cache
def bank():
    return load_active_bank()


def questions():
    return bank().questions


def normalize_text(text: str) -> str:
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return re.sub(r" ([,.;:])", r"\1", text).strip()


@cache
def instruction_pages() -> list[str]:
    reader = PdfReader(REPO_ROOT / load_registry().active.instructions_pdf.path)
    return [normalize_text(page.extract_text() or "") for page in reader.pages]


@cache
def tooltips() -> dict[str, str]:
    reader = PdfReader(REPO_ROOT / load_registry().active.form_pdf.path)
    return {n: str(f.get("/TU", "")) for n, f in (reader.get_fields() or {}).items()}


def test_bank_is_for_the_active_edition():
    assert bank().edition == load_registry().active_edition


@pytest.mark.parametrize("q", questions(), ids=lambda q: q.id)
def test_every_text_exists_in_all_three_languages(q):
    assert set(q.prompt) == set(LANGUAGES) and all(q.prompt.values())
    for choice in q.choices or []:
        assert set(choice.labels) == set(LANGUAGES) and all(choice.labels.values())


@pytest.mark.parametrize("q", questions(), ids=lambda q: q.id)
def test_help_is_a_verbatim_official_quote_on_the_stated_page(q):
    source = q.help.source
    if source.kind == "instructions":
        assert normalize_text(q.help.quote) in instruction_pages()[source.page - 1]
    else:
        assert normalize_tooltip(q.help.quote) in normalize_tooltip(tooltips()[source.pdf_field])


@pytest.mark.parametrize("q", questions(), ids=lambda q: q.id)
def test_paths_exist_in_the_schema(q):
    if not q.path.startswith(INTERVIEW_PREFIX):
        resolve_path(I765Application, q.path)
    for condition in q.when:
        path = condition.get("path")
        if path and not path.startswith(INTERVIEW_PREFIX):
            resolve_path(I765Application, path)


def test_every_applicant_question_on_the_form_is_asked():
    not_asked = tuple(bank().not_asked["paths"])
    expected = {
        p
        for p in leaf_paths(I765Application, LIST_CAPACITY)
        if p != "edition" and not p.startswith(not_asked)
    }
    asked = {q.path for q in questions()}
    assert expected - asked == set()


def test_attorney_decision_items_are_never_asked():
    field_map = load_field_map(REPO_ROOT / load_registry().active.field_map)
    reserved = {e.path for e in field_map.entries if e.attorney_decision}
    assert reserved.isdisjoint(q.path for q in questions())


def test_the_bot_never_offers_categories_to_choose_from():
    category = [q for q in questions() if q.path == "applicant.eligibility.category"]
    assert len(category) == 1
    assert category[0].kind == "category" and category[0].choices is None


ADVICE = {
    "ru": re.compile(r"подход(ит|ите)|шанс|рекоменд|вам следует подать|вы имеете право", re.I),
    "uk": re.compile(r"підход(ить|ите)|шанс|рекоменд|вам слід подати|ви маєте право", re.I),
    "en": re.compile(r"you (qualify|are eligible|should file)|recommend|chance|likely", re.I),
}


@pytest.mark.parametrize("q", questions(), ids=lambda q: q.id)
def test_no_question_sounds_like_legal_advice(q):
    for language, pattern in ADVICE.items():
        texts = [q.prompt[language]] + [c.labels[language] for c in q.choices or []]
        assert not [t for t in texts if pattern.search(t)], (q.id, language)


def test_names_and_us_addresses_must_be_latin():
    # Names and U.S. addresses are copied from documents; places of birth may be typed in
    # the user's script and are translated later (step 7) before reaching the form.
    for q in questions():
        is_name = q.path.endswith(("family_name", "given_name", "middle_name"))
        is_address = "_address." in q.path
        if is_name or is_address:
            assert q.kind != "text" or q.script == "latin", q.id
