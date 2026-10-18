"""Build the attorney's review of a case from stored answers and validation results."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict

from uscis_assistant.forms.field_map import load_field_map
from uscis_assistant.forms.registry import REPO_ROOT, load_registry
from uscis_assistant.interview.bank import QuestionBank
from uscis_assistant.interview.engine import (
    INTERVIEW_PREFIX,
    UNCONFIRMED,
    BuildResult,
    build_application,
    load_active_bank,
)
from uscis_assistant.storage.store import (
    ActorRole,
    AuditEntry,
    CaseStore,
    EventType,
)
from uscis_assistant.validation.flags import Flag
from uscis_assistant.validation.i765 import validate_i765

# Values only an attorney may enter: the items the interview never asks.
ATTORNEY_PATHS = (
    "statement.statement",
    "statement.interpreter_language",
    "statement.prepared_by_preparer",
    "statement.preparer_name",
    "interpreter.",
    "preparer.",
    "attorney.",
    "additional_info[",
)
DECISIONS = ("complete", "not_required")  # data entered / sections intentionally left blank


def is_attorney_path(path: str) -> bool:
    return path.startswith(ATTORNEY_PATHS)


class ReviewAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: str
    path: str
    question: str  # English text of the question as asked, or the form item for attorney data
    original: str | None
    original_language: str | None
    english: Any
    method: str
    entered_by: str  # role that recorded the latest version


class DeclinedRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    occurred_at: Any
    item: str
    language: str
    text: str


class AttorneyDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    occurred_at: Any
    decision: str
    note: str


class CaseReview(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    case_id: str
    form: str
    edition: str
    status: str
    answers: list[ReviewAnswer]
    flags: list[Flag]
    missing: list[str]  # schema locations still required before the form can be built
    unanswered_items: list[str]  # form items of questions the interview has not got answers to
    awaiting_translation: list[str]  # answers not yet confirmed in English
    machine_translated: list[str]  # answers whose English text came from the model
    declined_requests: list[DeclinedRequest]
    attorney_decision: AttorneyDecision | None
    audit_verified: bool
    audit_log: list[AuditEntry]
    application_built: bool


def _attorney_values(answers: dict[str, Any], bank: QuestionBank) -> dict[str, Any]:
    bank_paths = {q.path for q in bank.questions}
    return {
        path: value
        for path, value in answers.items()
        if path not in bank_paths and is_attorney_path(path) and value is not None
    }


def assemble_application(
    store: CaseStore, case_id: str, bank: QuestionBank | None = None
) -> BuildResult:
    bank = bank or load_active_bank()
    records = store.answers(case_id)
    answers = {path: record.english for path, record in records.items()}
    pending = {p for p, r in records.items() if r.translation_method in UNCONFIRMED}
    return build_application(bank, answers, pending, _attorney_values(answers, bank))


def latest_attorney_decision(log: list[AuditEntry]) -> AttorneyDecision | None:
    decisions = [e for e in log if e.event_type is EventType.ATTORNEY_DECISION]
    if not decisions:
        return None
    last = decisions[-1]
    return AttorneyDecision(
        occurred_at=last.occurred_at,
        decision=last.details["decision"],
        note=last.details["note"],
    )


def _item_labels() -> dict[str, str]:
    field_map = load_field_map(REPO_ROOT / load_registry().active.field_map)
    labels: dict[str, str] = {}
    for entry in field_map.entries:
        labels.setdefault(entry.path, f"Form item {entry.item}")
    return labels


def build_review(
    store: CaseStore, case_id: str, today: date, bank: QuestionBank | None = None
) -> CaseReview:
    bank = bank or load_active_bank()
    records = store.answers(case_id)
    log = store.audit_log(case_id)
    built = assemble_application(store, case_id, bank)
    labels = _item_labels()

    question_text = {q.path: q.prompt["en"] for q in bank.questions}
    order = {q.path: index for index, q in enumerate(bank.questions)}
    last_actor: dict[str, str] = {}
    for event in log:
        if event.path and event.event_type in (EventType.ANSWER_RECORDED, EventType.ANSWER_CHANGED):
            last_actor[event.path] = event.actor_role.value

    rows = [
        ReviewAnswer(
            item=record.item,
            path=path,
            question=question_text.get(path, labels.get(path, f"Form item {record.item}")),
            original=record.original,
            original_language=record.original_language,
            english=record.english,
            method=record.translation_method,
            entered_by=last_actor.get(path, "unknown"),
        )
        for path, record in records.items()
        if not path.startswith(INTERVIEW_PREFIX)
    ]
    rows.sort(key=lambda r: (order.get(r.path, len(order)), r.path))

    answered = {path: record.english for path, record in records.items()}
    unanswered = [q.item for q in bank.questions if q.path not in answered and q.applies(answered)]
    flags: list[Flag] = []
    if built.application is not None:
        flags = validate_i765(built.application, today)

    return CaseReview(
        case_id=case_id,
        form=load_registry().form,
        edition=load_registry().active_edition,
        status=store.case_status(case_id),
        answers=rows,
        flags=flags,
        missing=built.missing,
        unanswered_items=unanswered,
        awaiting_translation=built.pending_translation,
        machine_translated=[p for p, r in records.items() if r.translation_method == "machine"],
        declined_requests=[
            DeclinedRequest(
                occurred_at=e.occurred_at,
                item=e.details["item"],
                language=e.details["language"],
                text=e.details["text"],
            )
            for e in log
            if e.event_type is EventType.ADVICE_DECLINED
        ],
        attorney_decision=latest_attorney_decision(log),
        audit_verified=store.verify_audit_log(case_id),
        audit_log=log,
        application_built=built.application is not None,
    )


def require_lawyer(actor: ActorRole) -> None:
    if actor is not ActorRole.LAWYER:
        raise PermissionError("only an attorney may do this")
