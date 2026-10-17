"""Interview flow: asks the next applicable question, records answers, builds the form data.

The flow is fully determined by the question bank and the answers: the first question whose
conditions hold and that has no answer yet is asked next. Answers to questions that no
longer apply (for example after the user changed an earlier answer) are kept in the audit
trail but are not used to build the application.
"""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from uscis_assistant.forms.i765.schema import I765Application
from uscis_assistant.forms.registry import REPO_ROOT, load_registry
from uscis_assistant.interview.bank import Language, Question, QuestionBank, load_bank
from uscis_assistant.interview.parse import parse_answer
from uscis_assistant.interview.texts import DATE_FORMAT, HELP_REQUEST, MESSAGES
from uscis_assistant.storage.store import ActorRole, CaseStore

INTERVIEW_PREFIX = "interview."  # control answers (e.g. "more names?") that are not on the form
PATH_PART = re.compile(r"^(?P<name>[a-z0-9_]+)(?:\[(?P<index>\d+)\])?$")


def load_active_bank() -> QuestionBank:
    return load_bank(REPO_ROOT / load_registry().active.interview)


def next_question(bank: QuestionBank, answers: dict[str, Any]) -> Question | None:
    for question in bank.questions:
        if question.path not in answers and question.applies(answers):
            return question
    return None


def applicable_answers(bank: QuestionBank, answers: dict[str, Any]) -> dict[str, Any]:
    """Answers whose question still applies, in bank order."""
    return {
        q.path: answers[q.path] for q in bank.questions if q.path in answers and q.applies(answers)
    }


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    node: Any = target
    for position, part in enumerate(parts):
        match = PATH_PART.match(part)
        name, index = match["name"], match["index"]
        last = position == len(parts) - 1
        if index is None:
            if last:
                node[name] = value
            else:
                node = node.setdefault(name, {})
        else:
            items: dict[int, Any] = node.setdefault(name, {})
            if last:
                items[int(index)] = value
            else:
                node = items.setdefault(int(index), {})


def _lists_from_indexes(node: Any) -> Any:
    if isinstance(node, dict):
        if node and all(isinstance(k, int) for k in node):
            return [_lists_from_indexes(node[k]) for k in sorted(node)]
        return {k: _lists_from_indexes(v) for k, v in node.items()}
    return node


class BuildResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    application: I765Application | None
    missing: list[str]  # schema locations still required
    pending_translation: list[str]  # answered in another script, waiting for translation


def build_application(
    bank: QuestionBank, answers: dict[str, Any], pending: set[str] | None = None
) -> BuildResult:
    pending = pending or set()
    data: dict[str, Any] = {}
    waiting = []
    for path, value in applicable_answers(bank, answers).items():
        if path.startswith(INTERVIEW_PREFIX):
            continue
        if path in pending:
            waiting.append(path)
            continue
        if value is not None:
            _set_path(data, path, value)
    try:
        return BuildResult(
            application=I765Application.model_validate(_lists_from_indexes(data)),
            missing=[],
            pending_translation=waiting,
        )
    except ValidationError as exc:
        missing = sorted({".".join(str(p) for p in error["loc"]) for error in exc.errors()})
        return BuildResult(application=None, missing=missing, pending_translation=waiting)


class SubmitResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    accepted: bool
    message: str  # in the user's language


class InterviewSession:
    """One person's interview for one case, stored through `CaseStore`."""

    def __init__(
        self,
        store: CaseStore,
        case_id: str,
        language: Language,
        bank: QuestionBank | None = None,
        actor: ActorRole = ActorRole.APPLICANT,
    ):
        self._store = store
        self._case_id = case_id
        self._language = language
        self._bank = bank or load_active_bank()
        self._actor = actor

    def _records(self):
        return self._store.answers(self._case_id)

    def answers(self) -> dict[str, Any]:
        return {path: record.english for path, record in self._records().items()}

    def current(self) -> Question | None:
        return next_question(self._bank, self.answers())

    def prompt(self) -> str:
        question = self.current()
        lang = self._language
        if question is None:
            return MESSAGES["done"][lang]
        lines = [question.prompt[lang]]
        if question.kind == "choice":
            lines += [f"{n}. {c.labels[lang]}" for n, c in enumerate(question.choices or [], 1)]
        elif question.kind == "yes_no":
            lines.append(MESSAGES["yes_no_hint"][lang])
        elif question.kind == "date":
            lines.append(MESSAGES["date_hint"][lang])
        lines.append(MESSAGES["help_hint"][lang])
        return "\n".join(lines)

    def help(self, question: Question | None = None) -> str:
        question = question or self.current()
        if question is None:
            return MESSAGES["done"][self._language]
        source = question.help.source
        where = (
            f"Form I-765 Instructions (edition 08/21/25), page {source.page}, {source.section}"
            if source.kind == "instructions"
            else "Form I-765 (edition 08/21/25), PDF field help text"
        )
        return "\n".join(
            [
                MESSAGES["help_header"][self._language],
                f'"{question.help.quote}"',
                f"{MESSAGES['source'][self._language]}: {where}; https://www.uscis.gov/i-765",
            ]
        )

    def submit(self, raw: str) -> SubmitResult:
        question = self.current()
        if question is None:
            return SubmitResult(accepted=False, message=MESSAGES["done"][self._language])
        if raw.strip().lower() in HELP_REQUEST:
            return SubmitResult(accepted=False, message=self.help(question))
        return self.answer(question, raw)

    def answer(self, question: Question, raw: str) -> SubmitResult:
        """Record an answer to a given question (also used to change an earlier answer)."""
        parsed = parse_answer(question, raw, self._language)
        if not parsed.ok:
            return SubmitResult(accepted=False, message=MESSAGES[parsed.error][self._language])
        self._store.record_answer(
            self._case_id,
            path=question.path,
            item=question.item,
            original=raw,
            original_language=self._language,
            english=parsed.value,
            translation_method=parsed.translation_method,
            actor=self._actor,
        )
        key = "translation_pending" if parsed.translation_method == "pending" else "saved"
        return SubmitResult(accepted=True, message=MESSAGES[key][self._language])

    def build(self) -> BuildResult:
        records = self._records()
        pending = {p for p, r in records.items() if r.translation_method == "pending"}
        return build_application(self._bank, self.answers(), pending)

    def date_format(self) -> str:
        return DATE_FORMAT[self._language]
