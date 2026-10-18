"""Actions available to an attorney on a case."""

from datetime import date
from typing import Any

from uscis_assistant.forms.i765.filler import FillError, FillReport, fill_i765
from uscis_assistant.interview.bank import QuestionBank
from uscis_assistant.interview.engine import load_active_bank
from uscis_assistant.lawyer.render import render_audit_log, render_summary
from uscis_assistant.lawyer.review import (
    DECISIONS,
    CaseReview,
    assemble_application,
    build_review,
    is_attorney_path,
    latest_attorney_decision,
    require_lawyer,
)
from uscis_assistant.storage.store import ActorRole, CaseStore


class LawyerSession:
    def __init__(
        self,
        store: CaseStore,
        case_id: str,
        actor: ActorRole,
        bank: QuestionBank | None = None,
    ):
        require_lawyer(actor)
        self._store = store
        self._case_id = case_id
        self._actor = actor
        self._bank = bank or load_active_bank()

    def review(self, today: date) -> CaseReview:
        return build_review(self._store, self._case_id, today, self._bank)

    def summary(self, today: date) -> str:
        return render_summary(self.review(today))

    def audit_log(self, today: date) -> str:
        return render_audit_log(self.review(today))

    def enter_attorney_data(self, path: str, value: Any, item: str = "attorney") -> None:
        """Record a value for an item the interview never asks (interpreter, preparer, ...)."""
        if not is_attorney_path(path):
            raise ValueError(f"{path!r} is not an attorney-entered item")
        self._store.record_answer(
            self._case_id,
            path=path,
            item=item,
            original=None if not isinstance(value, str) else value,
            original_language="en",
            english=value,
            translation_method="user",
            actor=self._actor,
        )

    def record_decision(self, decision: str, note: str = "") -> None:
        """Decide the interpreter / preparer question: "complete" (data entered above) or
        "not_required" (the sections stay blank). Later calls supersede earlier ones."""
        if decision not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        self._store.record_attorney_decision(
            self._case_id, decision=decision, note=note, actor=self._actor
        )

    def fill_pdf(self) -> tuple[str, FillReport]:
        """Fill the official PDF and keep the encrypted copy. Items reserved for an attorney
        are filled only after a decision was recorded."""
        built = assemble_application(self._store, self._case_id, self._bank)
        if built.application is None:
            raise FillError("the form cannot be built yet: answers are missing or unconfirmed")
        decided = latest_attorney_decision(self._store.audit_log(self._case_id)) is not None
        result = fill_i765(built.application, attorney_decisions_made=decided)
        doc_id = self._store.add_document(
            self._case_id,
            kind="filled_i765_draft",
            filename="I-765_draft.pdf",
            content_type="application/pdf",
            data=result.pdf,
            actor=self._actor,
        )
        return doc_id, result.report
