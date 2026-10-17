"""Validation rules for I-765. All data here is fictitious."""

import re
from datetime import date
from functools import cache

import pytest
from pypdf import PdfReader

from uscis_assistant.forms.i765.schema import I765Application
from uscis_assistant.forms.registry import REPO_ROOT, load_registry
from uscis_assistant.validation.flags import FlagCode, Severity
from uscis_assistant.validation.i765 import CATEGORY_SHAPE, validate_i765

TODAY = date(2026, 10, 17)


def clean_data() -> dict:
    """A complete, consistent application that should raise no flag except the one that
    is raised for every case (interpreter / preparer question)."""
    return {
        "reason_for_applying": "initial",
        "applicant": {
            "name": {"family_name": "Testova", "given_name": "Olena"},
            "mailing_address": {
                "street": "100 Example St",
                "city": "Springfield",
                "state": "IL",
                "zip_code": "62701",
            },
            "mailing_same_as_physical": True,
            "a_number": "A123456789",
            "sex": "female",
            "marital_status": "single",
            "previously_filed_i765": False,
            "citizenship_countries": ["Ukraine"],
            "birth_city": "Kyiv",
            "birth_country": "Ukraine",
            "date_of_birth": "1990-01-02",
            "i94_number": "12345678901",
            "passport_number": "FX0000000",
            "passport_expiration_date": "2030-01-01",
            "last_entry_date": "2024-05-01",
            "eligibility": {"category": "(c)(11)"},
        },
        "statement": {"statement": "reads_english", "daytime_phone": "5555550100"},
    }


def build(**changes) -> I765Application:
    """Apply dotted-path changes, e.g. build(**{"applicant.ssn": "1"})."""
    data = clean_data()
    for path, value in changes.items():
        target = data
        *parents, last = path.split(".")
        for key in parents:
            target = target.setdefault(key, {})
        target[last] = value
    return I765Application.model_validate(data)


def flags_of(app, code=None, item=None):
    return [
        f
        for f in validate_i765(app, TODAY)
        if (code is None or f.code is code) and (item is None or f.item == item)
    ]


def test_clean_application_has_only_the_always_present_attorney_decision():
    flags = validate_i765(build(), TODAY)
    assert [(f.code, f.item) for f in flags] == [(FlagCode.ATTORNEY_DECISION, "3.1")]


def test_validation_never_changes_the_data():
    app = build(**{"applicant.eligibility.category": "C8", "applicant.ssn": "12"})
    before = app.model_dump()
    validate_i765(app, TODAY)
    assert app.model_dump() == before


def test_every_flag_cites_an_official_source():
    app = build(**{"applicant.eligibility.category": None, "statement.daytime_phone": None})
    for flag in validate_i765(app, TODAY):
        assert "Form I-765" in flag.source


# --- Eligibility category -------------------------------------------------------------


def test_missing_category_requires_attorney_review():
    flags = flags_of(build(**{"applicant.eligibility.category": None}), item="2.27")
    assert [f.code for f in flags] == [FlagCode.ATTORNEY_REVIEW]
    assert flags[0].severity is Severity.ATTORNEY


def test_badly_shaped_category_is_flagged_not_fixed():
    app = build(**{"applicant.eligibility.category": "c8"})
    assert [f.code for f in flags_of(app, item="2.27")] == [FlagCode.FORMAT]
    assert app.applicant.eligibility.category == "c8"


@cache
def categories_in_instructions() -> list[str]:
    reader = PdfReader(REPO_ROOT / load_registry().active.instructions_pdf.path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    found = re.findall(r"\(\s*[a-zA-Z]\s*\)\s*\(\s*\d+\s*\)(?:\s*\(\s*[A-Za-z]+\s*\))?", text)
    return sorted({re.sub(r"\s+", "", c) for c in found})


def test_category_shape_accepts_every_code_in_the_instructions():
    codes = categories_in_instructions()
    assert len(codes) >= 50  # guard against a broken extraction
    assert [c for c in codes if not CATEGORY_SHAPE.match(c)] == []


def test_c8_requires_item_30():
    app = build(**{"applicant.eligibility.category": "(c)(8)"})
    assert [f.code for f in flags_of(app, item="2.30")] == [FlagCode.MISSING_REQUIRED]


def test_uppercase_category_still_triggers_its_items_and_a_format_flag():
    app = build(**{"applicant.eligibility.category": "(C)(8)"})
    assert flags_of(app, FlagCode.FORMAT, "2.27")
    assert flags_of(app, FlagCode.MISSING_REQUIRED, "2.30")


def test_stem_opt_requires_items_28_a_to_c():
    app = build(**{"applicant.eligibility.category": "(c)(3)(C)"})
    items = {f.item for f in flags_of(app, FlagCode.MISSING_REQUIRED)}
    assert {"2.28.A", "2.28.B", "2.28.C"} <= items


def test_answers_for_another_category_are_inconsistent():
    app = build(
        **{
            "applicant.eligibility.category": "(c)(8)",
            "applicant.eligibility.c8_ever_arrested_or_convicted": False,
            "applicant.eligibility.c35_c36_receipt_number": "IOE0000000000",
        }
    )
    assert flags_of(app, FlagCode.INCONSISTENT, "2.31.A")


@pytest.mark.parametrize(
    ("category", "field", "item"),
    [
        ("(c)(8)", "c8_ever_arrested_or_convicted", "2.30"),
        ("(c)(35)", "c35_c36_ever_arrested_or_convicted", "2.31.B"),
    ],
)
def test_yes_to_arrest_question_requires_attorney_review(category, field, item):
    app = build(
        **{
            "applicant.eligibility.category": category,
            f"applicant.eligibility.{field}": True,
            "applicant.eligibility.c35_c36_receipt_number": "IOE0000000000"
            if category == "(c)(35)"
            else None,
        }
    )
    assert flags_of(app, FlagCode.ATTORNEY_REVIEW, item)


def test_no_to_arrest_question_needs_no_review():
    app = build(
        **{
            "applicant.eligibility.category": "(c)(8)",
            "applicant.eligibility.c8_ever_arrested_or_convicted": False,
        }
    )
    assert not flags_of(app, item="2.30")


def test_abc_settlement_requires_attorney_review_and_matches_c8():
    app = build(**{"statement.abc_settlement_class_member": True})
    assert flags_of(app, FlagCode.ATTORNEY_REVIEW, "3.6")
    assert flags_of(app, FlagCode.INCONSISTENT, "3.6")  # category is (c)(11), not (c)(8)


# --- Addresses, history, formats, dates ---------------------------------------------


def test_physical_address_required_when_mailing_differs():
    app = build(**{"applicant.mailing_same_as_physical": False})
    assert flags_of(app, FlagCode.MISSING_REQUIRED, "2.7")


def test_physical_address_given_although_same_is_inconsistent():
    address = {"street": "1 A St", "city": "Springfield", "state": "IL", "zip_code": "62701"}
    app = build(**{"applicant.physical_address": address})
    assert flags_of(app, FlagCode.INCONSISTENT, "2.7")


def test_unit_type_without_number_is_inconsistent():
    app = build(**{"applicant.mailing_address.unit_type": "apt"})
    assert flags_of(app, FlagCode.INCONSISTENT, "2.5.C")


def test_renewal_without_previous_filing_is_inconsistent():
    app = build(reason_for_applying="renewal")
    assert flags_of(app, FlagCode.INCONSISTENT, "2.12")


@pytest.mark.parametrize(
    ("path", "value", "flagged"),
    [
        ("applicant.a_number", "A123456789", False),
        ("applicant.a_number", "123456789", False),
        ("applicant.a_number", "A-123456789", False),
        ("applicant.a_number", "A12345678", True),
        ("applicant.a_number", "N/A", False),
        ("applicant.ssn", "123-45-6789", False),
        ("applicant.ssn", "12345", True),
        ("applicant.i94_number", "12345678901", False),
        ("applicant.i94_number", "1234567890", True),
        ("applicant.uscis_online_account_number", "000000000000", False),
        ("applicant.uscis_online_account_number", "0000", True),
    ],
)
def test_identifier_formats(path, value, flagged):
    app = build(**{path: value})
    assert bool(flags_of(app, FlagCode.FORMAT)) is flagged


def test_expired_passport_gives_only_a_notice_not_an_error():
    # Instructions: enter the passport "even if the passport ... is currently expired".
    app = build(**{"applicant.passport_expiration_date": "2020-01-01"})
    flags = flags_of(app, item="2.21")
    assert [f.code for f in flags] == [FlagCode.NOTICE]
    assert flags[0].severity is Severity.INFO
    assert "not an error" in flags[0].message
    assert "even if the passport or travel document is currently expired" in flags[0].message


@pytest.mark.parametrize("expires", ["2026-10-17", "2030-01-01"])
def test_valid_passport_gives_no_notice(expires):
    # Expiring today still counts as valid; only a date before today gets the notice.
    assert not flags_of(build(**{"applicant.passport_expiration_date": expires}), item="2.21")


def test_expired_passport_quote_matches_the_instructions_text():
    reader = PdfReader(REPO_ROOT / load_registry().active.instructions_pdf.path)
    text = " ".join(" ".join(p.extract_text().split()) for p in reader.pages)
    quote = (
        "enter the passport or travel document information in the appropriate space on the "
        "application, even if the passport or travel document is currently expired."
    )
    assert quote in text


def test_future_birth_date_is_flagged():
    app = build(**{"applicant.date_of_birth": "2030-01-01"})
    assert flags_of(app, FlagCode.INCONSISTENT, "2.16")


def test_arrival_before_birth_is_flagged():
    app = build(**{"applicant.last_entry_date": "1980-01-01"})
    assert flags_of(app, FlagCode.INCONSISTENT, "2.22")


# --- Lists and Part 6 ------------------------------------------------------------------


def test_extra_other_names_overflow_to_part_6():
    names = [{"family_name": f"Alias{i}", "given_name": "Test"} for i in range(4)]
    flags = flags_of(build(**{"applicant.other_names": names}), FlagCode.OVERFLOW)
    assert [f.item for f in flags] == ["2.2"]
    assert flags[0].severity is Severity.INFO


def test_part_6_full_needs_separate_sheet():
    entries = [
        {"page_number": "1", "part_number": "2", "item_number": "2", "text": "x"} for _ in range(5)
    ]
    names = [{"family_name": f"Alias{i}", "given_name": "Test"} for i in range(4)]
    app = build(**{"additional_info": entries, "applicant.other_names": names})
    assert flags_of(app, FlagCode.OVERFLOW, "6")


def test_stateless_needs_explanation_in_part_6():
    app = build(**{"applicant.citizenship_countries": ["Stateless"]})
    assert flags_of(app, FlagCode.MISSING_REQUIRED, "2.14")
    explained = build(
        **{
            "applicant.citizenship_countries": ["Stateless"],
            "additional_info": [
                {"page_number": "2", "part_number": "2", "item_number": "14.a", "text": "x"}
            ],
        }
    )
    assert not flags_of(explained, FlagCode.MISSING_REQUIRED, "2.14")


# --- Part 3 ---------------------------------------------------------------------------


def test_daytime_phone_is_required():
    app = build(**{"statement.daytime_phone": None})
    assert flags_of(app, FlagCode.MISSING_REQUIRED, "3.3")


def test_interpreter_statement_without_part_4_is_inconsistent():
    app = build(**{"statement.statement": "interpreter_read"})
    assert flags_of(app, FlagCode.INCONSISTENT, "3.1.B")


# --- No legal advice in messages ------------------------------------------------------

ADVICE = re.compile(
    r"\b(you (qualify|are eligible|should file)|recommend|chance|likely|approv)", re.IGNORECASE
)


def test_messages_never_sound_like_legal_advice():
    app = build(
        **{
            "applicant.eligibility.category": "(c)(8)",
            "applicant.eligibility.c8_ever_arrested_or_convicted": True,
            "statement.abc_settlement_class_member": True,
            "applicant.mailing_same_as_physical": False,
            "applicant.ssn": "1",
            "reason_for_applying": "renewal",
            "statement.daytime_phone": None,
        }
    )
    flags = validate_i765(app, TODAY)
    assert len(flags) >= 7
    assert [f.message for f in flags if ADVICE.search(f.message)] == []
