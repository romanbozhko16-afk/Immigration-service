"""Question bank: the questions of the interview, loaded from JSON data.

Each question names the schema path it fills, the printed form item, how the answer is
parsed, when it is asked, and an official quote shown as help ("?"). Help is the verbatim
English text of the USCIS instructions or the form's help text, never a paraphrase.
"""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from uscis_assistant.validation.i765 import category_key

Language = Literal["ru", "uk", "en"]
LANGUAGES: tuple[Language, ...] = ("ru", "uk", "en")


class HelpSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["instructions", "tooltip"]
    page: int | None = None
    section: str | None = None
    pdf_field: str | None = None


class Help(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    quote: str
    source: HelpSource


class Choice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str | None
    labels: dict[Language, str]


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    path: str
    item: str
    kind: Literal["text", "date", "yes_no", "choice", "state", "category"]
    prompt: dict[Language, str]
    help: Help
    when: list[dict[str, Any]] = []
    optional: bool = False
    allow_na: bool = False
    script: Literal["latin", "any"] | None = None
    choices: list[Choice] | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "Question":
        if (self.kind == "choice") != bool(self.choices):
            raise ValueError(f"{self.id}: choices are required exactly for kind 'choice'")
        if (self.kind == "text") != (self.script is not None):
            raise ValueError(f"{self.id}: script is required exactly for kind 'text'")
        for condition in self.when:
            if not ({"path", "equals"} == set(condition) or {"path", "not_equals"} == set(condition)
                    or {"category_in"} == set(condition)):  # fmt: skip
                raise ValueError(f"{self.id}: unknown condition {condition}")
        return self

    def applies(self, answers: dict[str, Any]) -> bool:
        """All conditions hold for the answers given so far."""
        for condition in self.when:
            if "category_in" in condition:
                key = category_key(answers.get("applicant.eligibility.category"))
                if key not in condition["category_in"]:
                    return False
            elif "equals" in condition:
                if (
                    condition["path"] not in answers
                    or answers[condition["path"]] != condition["equals"]
                ):
                    return False
            elif answers.get(condition["path"]) == condition["not_equals"]:
                return False
        return True


class QuestionBank(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    form: str
    edition: str
    not_asked: dict[str, Any]
    questions: list[Question]

    @model_validator(mode="after")
    def _unique(self) -> "QuestionBank":
        for attr in ("id", "path"):
            values = [getattr(q, attr) for q in self.questions]
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate question {attr}")
        return self


def load_bank(path: Path) -> QuestionBank:
    return QuestionBank.model_validate(json.loads(path.read_text()))
