"""Parsing and the full interview flow, end to end through storage, validation and the PDF.
All answers are fictitious."""

from datetime import date

import pytest

from uscis_assistant.forms.i765.filler import fill_i765, read_pdf_values
from uscis_assistant.interview.engine import (
    InterviewSession,
    build_application,
    load_active_bank,
    next_question,
)
from uscis_assistant.interview.parse import parse_answer
from uscis_assistant.storage import crypto
from uscis_assistant.storage.db import make_engine
from uscis_assistant.storage.keystore import KeyStore
from uscis_assistant.storage.store import ActorRole, CaseStore
from uscis_assistant.validation.flags import FlagCode
from uscis_assistant.validation.i765 import validate_i765

BANK = load_active_bank()
BY_ID = {q.id: q for q in BANK.questions}


@pytest.fixture
def store(tmp_path):
    keys = KeyStore(make_engine(f"sqlite:///{tmp_path}/k.db"), crypto.generate_key())
    return CaseStore(make_engine(f"sqlite:///{tmp_path}/c.db"), keys)


# --- parsing --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "raw", "expected"),
    [
        ("ru", "05.10.1967", "1967-10-05"),
        ("uk", "05.10.1967", "1967-10-05"),
        ("en", "10/05/1967", "1967-10-05"),
        ("ru", "1967-10-05", "1967-10-05"),  # ISO is unambiguous in every language
    ],
)
def test_dates_in_the_announced_format(language, raw, expected):
    parsed = parse_answer(BY_ID["dob"], raw, language)
    assert (parsed.ok, parsed.value) == (True, expected)


@pytest.mark.parametrize(
    ("language", "raw"),
    [
        ("en", "05.10.1967"),  # day-first format is not the English format: never guessed
        ("ru", "10/05/1967"),  # US format is not the Russian one
        ("ru", "31.02.1990"),  # no such date
        ("ru", "5.10.67"),
    ],
)
def test_ambiguous_or_invalid_dates_are_rejected(language, raw):
    assert parse_answer(BY_ID["dob"], raw, language).error == "date"


@pytest.mark.parametrize(
    ("language", "raw", "value"),
    [("ru", "да", True), ("ru", "Нет", False), ("uk", "так", True), ("uk", "ні", False),
     ("en", "yes", True), ("ru", "yes", True)],
)  # fmt: skip
def test_yes_no(language, raw, value):
    assert parse_answer(BY_ID["prev_filed"], raw, language).value is value


def test_yes_no_rejects_anything_else():
    assert parse_answer(BY_ID["prev_filed"], "может быть", "ru").error == "yes_no"


def test_choice_by_number_or_label():
    assert parse_answer(BY_ID["sex"], "1", "ru").value == "female"
    assert parse_answer(BY_ID["sex"], "мужской", "ru").value == "male"
    assert parse_answer(BY_ID["sex"], "3", "ru").error == "choice"


def test_names_must_be_latin():
    assert parse_answer(BY_ID["family_name"], "Тестова", "ru").error == "latin"
    assert parse_answer(BY_ID["family_name"], "Testova", "ru").value == "Testova"


def test_cyrillic_place_waits_for_translation_instead_of_reaching_the_form():
    parsed = parse_answer(BY_ID["birth_city"], "Киев", "ru")
    assert (parsed.ok, parsed.value, parsed.translation_method) == (True, None, "pending")


def test_no_a_number_is_recorded_as_na_as_the_instructions_say():
    assert parse_answer(BY_ID["a_number"], "нет", "ru").value == "N/A"
    assert parse_answer(BY_ID["a_number"], "немає", "uk").value == "N/A"


def test_optional_answer_none():
    assert parse_answer(BY_ID["ssn"], "нет", "ru").value is None


def test_category_is_stored_as_typed_or_left_to_an_attorney():
    assert parse_answer(BY_ID["category"], " (c)(8) ", "ru").value == "(c)(8)"
    assert parse_answer(BY_ID["category"], "C8", "ru").value == "C8"  # not normalized
    assert parse_answer(BY_ID["category"], "не знаю", "ru").value is None


def test_state_code():
    assert parse_answer(BY_ID["mail_state"], "il", "ru").value == "IL"
    assert parse_answer(BY_ID["mail_state"], "Illinois", "ru").error == "state"


# --- flow -----------------------------------------------------------------------------

RU_ANSWERS = {
    "reason": "1",
    "family_name": "Testova",
    "given_name": "Olena",
    "middle_name": "нет",
    "has_other_names": "да",
    "other_family_0": "Ivanova",
    "other_given_0": "Olena",
    "other_middle_0": "нет",
    "more_other_names_0": "нет",
    "mail_care": "нет",
    "mail_street": "100 Example St",
    "mail_unit_type": "1",
    "mail_unit_number": "5B",
    "mail_city": "Springfield",
    "mail_state": "IL",
    "mail_zip": "62701",
    "same_address": "нет",
    "phys_street": "200 Other Ave",
    "phys_unit_type": "4",
    "phys_city": "Springfield",
    "phys_state": "IL",
    "phys_zip": "62702",
    "a_number": "нет",
    "oan": "нет",
    "sex": "1",
    "marital": "1",
    "prev_filed": "нет",
    "ssn": "нет",
    "citizenship_0": "Ukraine",
    "more_citizenship_0": "нет",
    "birth_city": "Kyiv",
    "birth_state": "нет",
    "birth_country": "Ukraine",
    "dob": "02.01.1990",
    "i94": "12345678901",
    "passport": "FX0000000",
    "travel_doc": "нет",
    "passport_country": "Ukraine",
    "passport_exp": "01.01.2020",
    "last_entry": "01.05.2024",
    "last_place": "New York",
    "status_arrival": "B-2 visitor",
    "status_current": "no status",
    "sevis": "нет",
    "category": "(c)(8)",
    "c8_arrested": "нет",
    "phone_day": "5555550100",
    "phone_mobile": "нет",
    "email": "нет",
    "abc": "нет",
}


def run_interview(session: InterviewSession, answers: dict[str, str]) -> list[str]:
    asked = []
    while (question := session.current()) is not None:
        asked.append(question.id)
        result = session.submit(answers[question.id])
        assert result.accepted, (question.id, result.message)
        assert len(asked) < 200
    return asked


def test_full_interview_in_russian_reaches_a_valid_filled_form(store):
    case_id = store.create_case(ActorRole.APPLICANT)
    session = InterviewSession(store, case_id, "ru")
    asked = run_interview(session, RU_ANSWERS)

    # Conditions: physical address asked because it differs; (c)(8) items asked; STEM not.
    assert "phys_street" in asked and "phys_unit_number" not in asked
    assert {"c8_arrested", "abc"} <= set(asked)
    assert not {"stem_degree", "c26_receipt", "c35_receipt"} & set(asked)
    assert "other_family_1" not in asked

    built = session.build()
    assert (built.missing, built.pending_translation) == ([], [])
    app = built.application
    assert app.applicant.date_of_birth == date(1990, 1, 2)  # 02.01 = 2 January in Russian
    assert app.applicant.a_number == "N/A"
    assert app.applicant.physical_address.street == "200 Other Ave"
    assert app.applicant.eligibility.category == "(c)(8)"

    flags = validate_i765(app, date(2026, 10, 17))
    codes = {(f.code, f.item) for f in flags}
    assert (FlagCode.NOTICE, "2.21") in codes  # expired passport: notice only
    assert (FlagCode.ATTORNEY_DECISION, "3.1") in codes
    assert not [f for f in flags if f.code is FlagCode.MISSING_REQUIRED]

    pdf = read_pdf_values(fill_i765(app).pdf)
    assert pdf["form1[0].Page2[0].Line7_AlienNumber[0]"] == "N/A"
    assert pdf["form1[0].Page3[0].Line19_DOB[0]"] == "01/02/1990"


def test_the_audit_trail_keeps_original_answers_and_language(store):
    case_id = store.create_case(ActorRole.APPLICANT)
    session = InterviewSession(store, case_id, "ru")
    run_interview(session, RU_ANSWERS)
    a_number = [e for e in store.audit_log(case_id) if e.path == "applicant.a_number"]
    assert a_number[0].details["original"] == "нет"
    assert a_number[0].details["original_language"] == "ru"
    assert a_number[0].details["english"] == "N/A"


def test_unknown_category_goes_to_attorney_and_skips_category_items(store):
    case_id = store.create_case(ActorRole.APPLICANT)
    session = InterviewSession(store, case_id, "ru")
    asked = run_interview(session, {**RU_ANSWERS, "category": "не знаю"})
    assert not {"c8_arrested", "abc"} & set(asked)
    app = session.build().application
    flags = validate_i765(app, date(2026, 10, 17))
    assert (FlagCode.ATTORNEY_REVIEW, "2.27") in {(f.code, f.item) for f in flags}


def test_changed_answer_drops_answers_that_no_longer_apply():
    answers = {"interview.has_other_names": True,
               "applicant.other_names[0].family_name": "Ivanova",
               "applicant.other_names[0].given_name": "Olena"}  # fmt: skip
    answers["interview.has_other_names"] = False
    built = build_application(BANK, answers)
    assert "applicant.other_names" not in str(built.missing)
    assert next_question(BANK, answers).id == "reason"


def test_untranslated_answer_blocks_the_application(store):
    case_id = store.create_case(ActorRole.APPLICANT)
    session = InterviewSession(store, case_id, "ru")
    run_interview(session, {**RU_ANSWERS, "birth_city": "Киев"})
    built = session.build()
    assert built.application is None
    assert built.pending_translation == ["applicant.birth_city"]
    original = store.answers(case_id)["applicant.birth_city"]
    assert (original.original, original.english, original.translation_method) == (
        "Киев",
        None,
        "pending",
    )


def test_wrong_answer_is_asked_again_in_the_users_language(store):
    case_id = store.create_case(ActorRole.APPLICANT)
    session = InterviewSession(store, case_id, "uk")
    result = session.submit("5")  # reason has 3 options
    assert not result.accepted and "оберіть" in result.message
    assert session.current().id == "reason"


def test_help_shows_the_official_quote_and_source(store):
    case_id = store.create_case(ActorRole.APPLICANT)
    session = InterviewSession(store, case_id, "ru")
    text = session.submit("?").message
    assert "Официальный текст инструкции USCIS" in text
    assert "You must select one Item Number" in text
    assert "page 18" in text and "uscis.gov/i-765" in text


def test_prompt_lists_options_and_the_help_hint(store):
    case_id = store.create_case(ActorRole.APPLICANT)
    prompt = InterviewSession(store, case_id, "en").prompt()
    assert "1. Initial permission to accept employment" in prompt
    assert 'Type "?"' in prompt


def test_same_address_skips_the_physical_address_questions(store):
    case_id = store.create_case(ActorRole.APPLICANT)
    session = InterviewSession(store, case_id, "ru")
    asked = run_interview(session, {**RU_ANSWERS, "same_address": "да"})
    assert not [q for q in asked if q.startswith("phys_")]
    assert session.build().application.applicant.physical_address is None
