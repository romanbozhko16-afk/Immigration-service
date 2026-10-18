"""Interview flow: asks the next applicable question, records answers, builds the form data.

The flow is fully determined by the question bank and the answers: the first question whose
conditions hold and that has no answer yet is asked next. Answers to questions that no
longer apply (for example after the user changed an earlier answer) are kept in the audit
trail but are not used to build the application.

Every message passes `guard.route` first. Requests for legal advice are declined with a
fixed text; the model, when available, only labels messages and proposes English
renderings, which the user must confirm before they can reach the form.
"""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from uscis_assistant.forms.i765.schema import I765Application
from uscis_assistant.forms.registry import REPO_ROOT, load_registry
from uscis_assistant.interview.bank import Language, Question, QuestionBank, load_bank
from uscis_assistant.interview.guard import Route, looks_like_advice_request, route
from uscis_assistant.interview.parse import CYRILLIC, Parsed
from uscis_assistant.interview.texts import DATE_FORMAT, HELP_REQUEST, MESSAGES, YES
from uscis_assistant.llm.client import LLMUnavailable, StructuredLLM
from uscis_assistant.llm.tasks import (
    ENGLISH_VALUE,
    MessageKind,
    classify_message,
    translate_answer,
)
from uscis_assistant.storage.store import ActorRole, AnswerRecord, CaseStore

UNCONFIRMED = ("pending", "proposed")  # translation states that keep an answer off the form

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
    bank: QuestionBank,
    answers: dict[str, Any],
    pending: set[str] | None = None,
    attorney_values: dict[str, Any] | None = None,
) -> BuildResult:
    """`attorney_values` holds values entered by an attorney for items the interview never
    asks (interpreter, preparer, Part 3 items 1-2, G-28 box, Part 6)."""
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
    for path, value in (attorney_values or {}).items():
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
        llm: StructuredLLM | None = None,
    ):
        self._store = store
        self._case_id = case_id
        self._language = language
        self._bank = bank or load_active_bank()
        self._actor = actor
        self._llm = llm

    # --- state -----------------------------------------------------------------------------

    def _records(self) -> dict[str, AnswerRecord]:
        return self._store.answers(self._case_id)

    def answers(self) -> dict[str, Any]:
        return {path: record.english for path, record in self._records().items()}

    def awaiting_translation(self) -> tuple[Question, AnswerRecord] | None:
        """An answer waiting for its English version; it is handled before the next question."""
        records = self._records()
        answers = {path: record.english for path, record in records.items()}
        for question in self._bank.questions:
            record = records.get(question.path)
            if record and record.translation_method in UNCONFIRMED and question.applies(answers):
                return question, record
        return None

    def current(self) -> Question | None:
        waiting = self.awaiting_translation()
        return waiting[0] if waiting else next_question(self._bank, self.answers())

    def prompt(self) -> str:
        lang = self._language
        waiting = self.awaiting_translation()
        if waiting:
            question, record = waiting
            if record.translation_method == "proposed":
                return MESSAGES["translation_confirm"][lang].format(
                    english=record.english, original=record.original
                )
            return MESSAGES["type_latin"][lang].format(original=record.original)
        question = self.current()
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

    # --- answering ---------------------------------------------------------------------------

    def _reply(self, key: str, accepted: bool = False) -> "SubmitResult":
        return SubmitResult(accepted=accepted, message=MESSAGES[key][self._language])

    def _decline(self, question: Question, raw: str) -> "SubmitResult":
        self._store.record_advice_declined(
            self._case_id, text=raw, language=self._language, item=question.item, actor=self._actor
        )
        return self._reply("decline_advice")

    def _classify(self, question: Question, raw: str) -> MessageKind:
        if self._llm is None:
            return MessageKind.UNCLEAR
        try:
            return classify_message(self._llm, question, raw, self._language)
        except LLMUnavailable:
            return MessageKind.UNCLEAR

    def _record(
        self,
        question: Question,
        *,
        original: str,
        english: Any,
        method: str,
        original_language: str | None = None,
    ) -> None:
        self._store.record_answer(
            self._case_id,
            path=question.path,
            item=question.item,
            original=original,
            original_language=original_language or self._language,
            english=english,
            translation_method=method,
            actor=self._actor,
        )

    def submit(self, raw: str) -> "SubmitResult":
        waiting = self.awaiting_translation()
        if waiting:
            return self._resolve_translation(*waiting, raw)
        question = self.current()
        if question is None:
            return self._reply("done")
        if raw.strip().lower() in HELP_REQUEST:
            return SubmitResult(accepted=False, message=self.help(question))
        return self.answer(question, raw)

    def answer(self, question: Question, raw: str) -> "SubmitResult":
        """Handle an answer to a given question (also used to change an earlier answer)."""
        decision, parsed = route(question, raw, self._language)
        if decision is Route.DECLINE:
            return self._decline(question, raw)
        if decision is Route.CLASSIFY:
            kind = self._classify(question, raw)
            if kind is MessageKind.ADVICE_REQUEST:
                return self._decline(question, raw)
            if kind is MessageKind.FORM_QUESTION:
                return self._reply("form_question")
            if not parsed.ok:
                return self._reply(parsed.error)
            if "?" in raw and kind is not MessageKind.ANSWER:
                return self._reply("rephrase")
        if parsed.translation_method == "pending":
            return self._translate(question, raw)
        return self._store_parsed(question, raw, parsed)

    def _store_parsed(self, question: Question, raw: str, parsed: Parsed) -> "SubmitResult":
        self._record(question, original=raw, english=parsed.value, method="same")
        return self._reply("saved", accepted=True)

    def _translate(self, question: Question, raw: str) -> "SubmitResult":
        proposal = None
        if self._llm is not None:
            try:
                proposal = translate_answer(self._llm, question, raw, self._language)
            except LLMUnavailable:
                proposal = None
        if proposal is not None and proposal.kind is MessageKind.ADVICE_REQUEST:
            return self._decline(question, raw)
        if proposal is not None and proposal.kind is MessageKind.FORM_QUESTION:
            return self._reply("form_question")
        if proposal is not None and proposal.english is not None:
            self._record(question, original=raw, english=proposal.english, method="proposed")
        else:
            self._record(question, original=raw, english=None, method="pending")
        return SubmitResult(accepted=True, message=self.prompt())

    def _resolve_translation(
        self, question: Question, record: AnswerRecord, raw: str
    ) -> "SubmitResult":
        text = raw.strip()
        lowered = text.lower()
        if lowered in HELP_REQUEST:
            return SubmitResult(accepted=False, message=self.help(question))
        if looks_like_advice_request(text, self._language):
            return self._decline(question, raw)
        keep = {"original": record.original, "original_language": record.original_language}
        confirmed = lowered in YES[self._language] or lowered in YES["en"]
        if record.translation_method == "proposed" and confirmed:
            self._record(question, english=record.english, method="machine", **keep)
            return self._reply("saved", accepted=True)
        if CYRILLIC.search(text) or not ENGLISH_VALUE.match(text):
            return self._reply("latin")
        self._record(question, english=text, method="user", **keep)
        return self._reply("saved", accepted=True)

    def build(self) -> BuildResult:
        records = self._records()
        pending = {p for p, r in records.items() if r.translation_method in UNCONFIRMED}
        return build_application(self._bank, self.answers(), pending)

    def date_format(self) -> str:
        return DATE_FORMAT[self._language]
