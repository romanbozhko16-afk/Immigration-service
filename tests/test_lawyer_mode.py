"""Attorney review mode, end to end on a fictitious Russian-language case."""

import io
import re
from datetime import date

import pytest
from pypdf import PdfReader
from test_interview_flow import RU_ANSWERS, run_interview

from uscis_assistant.forms.i765.filler import FillError, read_pdf_values
from uscis_assistant.interview.engine import InterviewSession
from uscis_assistant.lawyer.review import assemble_application, is_attorney_path
from uscis_assistant.lawyer.session import LawyerSession
from uscis_assistant.storage import crypto
from uscis_assistant.storage.db import make_engine
from uscis_assistant.storage.keystore import KeyStore
from uscis_assistant.storage.store import ActorRole, CaseStore, EventType
from uscis_assistant.validation.flags import FlagCode

TODAY = date(2026, 10, 18)
P4, P5 = "form1[0].Page4[0].", "form1[0].Page5[0]."


@pytest.fixture
def store(tmp_path):
    keys = KeyStore(make_engine(f"sqlite:///{tmp_path}/k.db"), crypto.generate_key())
    return CaseStore(make_engine(f"sqlite:///{tmp_path}/c.db"), keys)


@pytest.fixture
def case(store):
    """A finished interview in Russian with a declined advice request and a user translation."""
    case_id = store.create_case(ActorRole.APPLICANT)
    session = InterviewSession(store, case_id, "ru")
    while session.current().id != "category":
        assert session.submit(RU_ANSWERS[session.current().id]).accepted
    assert (
        "не могу давать юридические советы" in session.submit("Какую категорию мне выбрать").message
    )
    answers = {**RU_ANSWERS, "c8_arrested": "да", "abc": "да"}
    run_interview(session, answers)
    return case_id


def lawyer(store, case_id) -> LawyerSession:
    return LawyerSession(store, case_id, ActorRole.LAWYER)


# --- access ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", [ActorRole.APPLICANT, ActorRole.SYSTEM])
def test_only_an_attorney_can_open_lawyer_mode(store, case, role):
    with pytest.raises(PermissionError):
        LawyerSession(store, case, role)


def test_attorney_data_must_be_an_attorney_item(store, case):
    with pytest.raises(ValueError):
        lawyer(store, case).enter_attorney_data("applicant.sex", "male")
    assert not is_attorney_path("applicant.name.family_name")


# --- summary --------------------------------------------------------------------------


def test_summary_shows_originals_translations_flags_and_declined_requests(store, case):
    text = lawyer(store, case).summary(TODAY)
    assert text.startswith("# Case review: Form I-765, edition 08/21/25")
    assert "Audit log intact: yes" in text
    assert "no legal analysis" in text
    # Answers table: original in Russian next to the English value
    assert "| нет | ru | N/A | same | applicant |" in text
    # Flags with sources
    assert "Requires attorney review or decision" in text
    assert "Item 2.30" in text and "Item 3.6" in text  # arrest "Yes" and ABC box
    assert "Form I-765 Instructions (edition 08/21/25), page 20" in text
    assert "Notice" not in text or "Information" in text
    # Declined advice request is shown with time, item and the person's words
    assert "Какую категорию мне выбрать" in text and "item 2.27" in text
    assert "asked 1 time(s) for legal advice" in text
    # The undecided interpreter / preparer question is the first open point
    first_point = text.split("## Open points for the attorney")[1].strip().splitlines()[0]
    assert "no decision recorded" in first_point


def test_expired_passport_appears_as_information_not_as_a_problem(store, case):
    text = lawyer(store, case).summary(TODAY)
    info = text.split("## Information")[1]
    assert "not an error" in info
    assert "## Blocking" not in text


def test_summary_marks_machine_translations_for_verification(store):
    from test_llm_guard import FakeLLM

    case_id = store.create_case(ActorRole.APPLICANT)
    session = InterviewSession(store, case_id, "ru", llm=FakeLLM(english="Kyiv"))
    while session.current().id != "birth_city":
        session.submit(RU_ANSWERS[session.current().id])
    session.submit("Киев")
    text = lawyer(store, case_id).summary(TODAY)
    assert "awaiting the applicant's English confirmation" in text  # proposed, unconfirmed
    session.submit("да")
    review = lawyer(store, case_id).review(TODAY)
    assert review.machine_translated == ["applicant.birth_city"]
    assert "`applicant.birth_city`" in lawyer(store, case_id).summary(TODAY)
    row = next(a for a in review.answers if a.path == "applicant.birth_city")
    assert (row.original, row.english, row.method) == ("Киев", "Kyiv", "machine")


def test_unfinished_case_says_what_is_missing_instead_of_showing_flags(store):
    case_id = store.create_case(ActorRole.APPLICANT)
    InterviewSession(store, case_id, "ru").submit("1")  # only the reason
    review = lawyer(store, case_id).review(TODAY)
    assert not review.application_built and review.flags == []
    assert review.unanswered_items[0] == "2.1.A"
    assert "Interview not finished" in lawyer(store, case_id).summary(TODAY)


def test_partial_attorney_data_blocks_the_form_and_names_the_gap(store, case):
    s = lawyer(store, case)
    s.enter_attorney_data("interpreter.name.family_name", "Interp")
    s.enter_attorney_data("interpreter.name.given_name", "Ivan")
    review = s.review(TODAY)
    assert not review.application_built and review.unanswered_items == []
    assert "interpreter.address" in review.missing
    assert "Information still missing" in s.summary(TODAY)
    with pytest.raises(FillError):
        s.fill_pdf()


def test_answers_follow_the_order_of_the_interview(store, case):
    items = [a.item for a in lawyer(store, case).review(TODAY).answers]
    assert items[:4] == ["1.1", "2.1.A", "2.1.B", "2.1.C"]


# --- audit log ------------------------------------------------------------------------


def test_audit_log_lists_every_event_with_time_role_and_original_text(store, case):
    review = lawyer(store, case).review(TODAY)
    log = lawyer(store, case).audit_log(TODAY)
    assert "Intact: yes" in log
    assert len(re.findall(r"\| \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \|", log)) == len(
        review.audit_log
    )
    assert "case_created" in log and "advice_request_declined" in log
    assert "Какую категорию мне выбрать" in log
    assert "| applicant |" in log


def test_tampering_is_reported_in_the_summary(store, case, tmp_path):
    from sqlalchemy import text

    with make_engine(f"sqlite:///{tmp_path}/c.db").begin() as conn:
        conn.execute(text("UPDATE audit_events SET actor_role = 'lawyer' WHERE seq = 2"))
    assert "NO: records were altered" in lawyer(store, case).summary(TODAY)


# --- attorney decision and filling ----------------------------------------------------


INTERPRETER = {
    "interpreter.name.family_name": "Interp",
    "interpreter.name.given_name": "Ivan",
    "interpreter.address.street": "1 Lang St",
    "interpreter.address.city": "Austin",
    "interpreter.address.state": "TX",
    "interpreter.address.zip_code": "73301",
    "interpreter.address.country": "USA",
    "interpreter.language": "Russian",
}


def test_filling_before_a_decision_leaves_reserved_sections_blank(store, case):
    s = lawyer(store, case)
    for path, value in INTERPRETER.items():
        s.enter_attorney_data(path, value)
    doc_id, report = s.fill_pdf()
    values = read_pdf_values(store.document(case, doc_id).data)
    assert values[P4 + "Pt4Line1a_InterpreterFamilyName[0]"] == ""
    assert {s_.reason for s_ in report.skipped} == {"attorney decision pending"}


def test_decision_then_fill_includes_the_attorneys_data(store, case):
    s = lawyer(store, case)
    for path, value in {
        "statement.statement": "interpreter_read",
        "statement.interpreter_language": "Russian",
        **INTERPRETER,
    }.items():
        s.enter_attorney_data(path, value)
    s.record_decision("complete", "Interview read to the applicant in Russian.")

    doc_id, report = s.fill_pdf()
    values = read_pdf_values(store.document(case, doc_id).data)
    assert values[P4 + "Pt4Line1a_InterpreterFamilyName[0]"] == "Interp"
    assert values[P4 + "Pt3Line1Checkbox[0]"] == "/B"
    assert values[P5 + "Pt5Line3d_State[0]"] == "TX"
    assert report.skipped == []

    review = s.review(TODAY)
    assert review.attorney_decision.decision == "complete"
    text = s.summary(TODAY)
    assert "decision **complete** recorded" in text
    assert "Interview read to the applicant in Russian." in text
    # The consistency flags see the attorney's data too: interpreter chosen and present.
    assert not [f for f in review.flags if f.code is FlagCode.INCONSISTENT and f.item == "3.1.B"]
    assert any(a.entered_by == "lawyer" for a in review.answers)


def test_not_required_decision_fills_nothing_extra_but_is_recorded(store, case):
    s = lawyer(store, case)
    s.record_decision("not_required", "Applicant reads English.")
    doc_id, report = s.fill_pdf()
    assert (
        report.skipped == []
        or all(x.reason == "attorney decision pending" for x in report.skipped) is False
    )
    events = [e for e in store.audit_log(case) if e.event_type is EventType.ATTORNEY_DECISION]
    assert events[0].details == {"decision": "not_required", "note": "Applicant reads English."}
    assert events[0].actor_role is ActorRole.LAWYER
    assert PdfReader(io.BytesIO(store.document(case, doc_id).data))


def test_a_later_decision_supersedes_an_earlier_one(store, case):
    s = lawyer(store, case)
    s.record_decision("not_required")
    s.record_decision("complete", "Changed after talking to the applicant.")
    assert s.review(TODAY).attorney_decision.decision == "complete"


def test_invalid_decision_is_rejected(store, case):
    with pytest.raises(ValueError):
        lawyer(store, case).record_decision("approved")


def test_cannot_fill_while_translations_are_unconfirmed(store):
    case_id = store.create_case(ActorRole.APPLICANT)
    session = InterviewSession(store, case_id, "ru")
    while session.current().id != "birth_city":
        session.submit(RU_ANSWERS[session.current().id])
    session.submit("Киев")  # no model: stays pending
    with pytest.raises(FillError):
        lawyer(store, case_id).fill_pdf()


def test_filled_pdf_is_stored_encrypted(store, case, tmp_path):
    lawyer(store, case).fill_pdf()
    for path in tmp_path.glob("*.db"):
        assert b"Testova" not in path.read_bytes()
        assert b"%PDF" not in path.read_bytes()


def test_assembled_application_contains_the_attorneys_data(store, case):
    s = lawyer(store, case)
    for path, value in INTERPRETER.items():
        s.enter_attorney_data(path, value)
    application = assemble_application(store, case).application
    assert application.interpreter.name.family_name == "Interp"
    assert application.interpreter.address.state == "TX"
