"""Flags produced by validation and shown to the user and, in lawyer mode, to the attorney."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

USCIS_FORM_PAGE = "https://www.uscis.gov/i-765"


class FlagCode(StrEnum):
    MISSING_REQUIRED = "missing_required"  # the form or instructions require an answer
    INCONSISTENT = "inconsistent"  # two answers contradict each other
    FORMAT = "format"  # value does not have the shape the form asks for
    ATTORNEY_REVIEW = "requires_attorney_review"  # legally sensitive: an attorney must look
    ATTORNEY_DECISION = "requires_attorney_decision"  # open legal question: attorney decides
    OVERFLOW = "overflow_to_part_6"  # more entries than the form has space for


class Severity(StrEnum):
    BLOCKING = "blocking"  # must be resolved before the form can be filed
    CHECK = "check"  # may be correct; the user or attorney should confirm
    ATTORNEY = "attorney"  # only an attorney can resolve it
    INFO = "info"  # nothing is wrong; tells how the answer will be placed


SEVERITY = {
    FlagCode.MISSING_REQUIRED: Severity.BLOCKING,
    FlagCode.INCONSISTENT: Severity.CHECK,
    FlagCode.FORMAT: Severity.CHECK,
    FlagCode.ATTORNEY_REVIEW: Severity.ATTORNEY,
    FlagCode.ATTORNEY_DECISION: Severity.ATTORNEY,
    FlagCode.OVERFLOW: Severity.INFO,
}


class Flag(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: FlagCode
    item: str  # printed item, e.g. "2.8" = Part 2, Item Number 8
    path: str | None  # schema path, None for flags about the case as a whole
    message: str  # English; describes the problem, never advises what to file
    source: str  # the official text the rule comes from

    @property
    def severity(self) -> Severity:
        return SEVERITY[self.code]


def tooltip_source(item: str) -> str:
    part, number = item.split(".", 1)
    return f"Form I-765 (edition 08/21/25), PDF field help text, Part {part}, Item {number}"


def instructions_source(page: int, section: str) -> str:
    return f"Form I-765 Instructions (edition 08/21/25), page {page}, {section}; {USCIS_FORM_PAGE}"
