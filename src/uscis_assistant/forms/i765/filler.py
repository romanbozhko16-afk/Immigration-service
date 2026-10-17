"""Fill the official Form I-765 PDF from an `I765Application`.

Rules:
- Literal: the filler writes what the application contains. It never invents an answer, so
  "N/A" appears only when the user's answer is "N/A".
- Signatures, their dates, and barcodes are never filled (they are not in the field map).
- Entries marked `attorney_decision` (Part 3 items 1-2, Parts 4-5) are skipped unless the
  caller says an attorney has decided.
- After writing, the PDF is read back and every written value is compared. A mismatch
  raises an error instead of producing a form with a silently wrong field.
- The result is a copy: the official source file is never modified.
"""

import io
import re
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

from uscis_assistant.forms.field_map import FieldMapEntry, load_field_map
from uscis_assistant.forms.i765.schema import (
    LIST_CAPACITY,
    AdditionalInfoEntry,
    I765Application,
)
from uscis_assistant.forms.registry import REPO_ROOT, load_registry, verify_pinned_files

CATEGORY = re.compile(r"^\(([a-z])\)\((\d{1,2})\)(?:\(([A-Za-z]+)\))?$")
NINE_DIGITS = re.compile(r"^(?:A-?)?(\d{9})$", re.IGNORECASE)
SSN = re.compile(r"^(\d{3})-?(\d{2})-?(\d{4})$")


class FillError(Exception):
    pass


class FillVerificationError(FillError):
    """The PDF read back differs from what was written."""


class SkippedField(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: str
    path: str
    pdf_field: str
    reason: str


class FillReport(BaseModel):
    """What happened, without any personal data (safe to log)."""

    model_config = ConfigDict(frozen=True)

    edition: str
    filled_fields: int
    skipped: list[SkippedField]
    moved_to_part_6: int  # entries that did not fit their boxes and were added to Part 6
    not_placed: int  # entries that fit nowhere: a separate sheet is needed


class FillResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    pdf: bytes
    report: FillReport


def _us_date(value: date) -> str:
    return value.strftime("%m/%d/%Y")


def _get(app: I765Application, path: str) -> Any:
    value: Any = app
    for part in path.split("."):
        match = re.fullmatch(r"([a-z0-9_]+)(?:\[(\d+)\])?", part)
        if value is None:
            return None
        value = getattr(value, match[1])
        if match[2] is not None:
            index = int(match[2])
            value = value[index] if value is not None and index < len(value) else None
    return value


def _with_part_6_overflow(app: I765Application) -> tuple[I765Application, int, int]:
    """Copy of the application where entries that do not fit their boxes move to Part 6."""
    a = app.applicant
    extra: list[AdditionalInfoEntry] = []
    for name in a.other_names[LIST_CAPACITY["applicant.other_names"] :]:
        parts = [name.family_name, name.given_name, name.middle_name or ""]
        extra.append(
            AdditionalInfoEntry(
                page_number="1",
                part_number="2",
                item_number="2.-4.",
                text="Other name used (continued): " + ", ".join(parts),
            )
        )
    for country in a.citizenship_countries[LIST_CAPACITY["applicant.citizenship_countries"] :]:
        extra.append(
            AdditionalInfoEntry(
                page_number="2",
                part_number="2",
                item_number="14.",
                text="Country of citizenship or nationality (continued): " + country,
            )
        )
    capacity = LIST_CAPACITY["additional_info"]
    combined = [*app.additional_info, *extra]
    placed = combined[:capacity]
    effective_applicant = a.model_copy(
        update={
            "other_names": a.other_names[: LIST_CAPACITY["applicant.other_names"]],
            "citizenship_countries": a.citizenship_countries[
                : LIST_CAPACITY["applicant.citizenship_countries"]
            ],
        }
    )
    effective = app.model_copy(update={"applicant": effective_applicant, "additional_info": placed})
    moved = max(0, len(placed) - len(app.additional_info))
    return effective, moved, len(combined) - len(placed)


def _format_text(entry: FieldMapEntry, value: Any) -> str | None:
    if entry.format == "date":
        return _us_date(value)
    if entry.format and entry.format.startswith("category_segment_"):
        match = CATEGORY.match(value)
        if match is None:
            return None  # the validator already flags the shape; nothing is guessed
        return match[int(entry.format[-1])] or ""
    text = str(value)
    # The printed boxes already contain "A-"; the form asks for the 9 digits only.
    if entry.path == "applicant.a_number" and (m := NINE_DIGITS.match(text)):
        return m[1]
    if entry.path == "applicant.ssn" and (m := SSN.match(text)):
        return "".join(m.groups())
    return text


def compute_values(
    app: I765Application, field_map_entries: list[FieldMapEntry], attorney_decisions_made: bool
) -> tuple[dict[str, str], list[SkippedField]]:
    """PDF field name -> value to write (checkbox: its on-value, which is "/N", "/1", ...)."""
    values: dict[str, str] = {}
    skipped: list[SkippedField] = []

    def skip(entry: FieldMapEntry, reason: str) -> None:
        skipped.append(
            SkippedField(item=entry.item, path=entry.path, pdf_field=entry.pdf_field, reason=reason)
        )

    for entry in field_map_entries:
        if entry.attorney_decision and not attorney_decisions_made:
            skip(entry, "attorney decision pending")
            continue
        value = _get(app, entry.path)
        if value is None:
            continue
        if entry.kind == "checkbox":
            ticked = value is entry.when if isinstance(entry.when, bool) else value == entry.when
            if ticked:
                values[entry.pdf_field] = entry.on_value
        elif entry.kind == "choice":
            values[entry.pdf_field] = str(value)
        else:
            text = _format_text(entry, value)
            if text is None:
                skip(entry, "value does not have the expected shape; left empty")
            elif text != "" or entry.format:
                values[entry.pdf_field] = text
    return values, skipped


def _full_name(annot: Any) -> str | None:
    names, node = [], annot
    while node is not None:
        if node.get("/T"):
            names.append(str(node["/T"]))
        node = node["/Parent"].get_object() if node.get("/Parent") else None
    return ".".join(reversed(names)) or None


def _page_widget_names(page: Any) -> set[str]:
    names = set()
    for annot in page.get("/Annots", []) or []:
        annot = annot.get_object()
        if annot.get("/Subtype") == "/Widget" and (name := _full_name(annot)):
            names.add(name)
    return names


def read_pdf_values(pdf: bytes) -> dict[str, str]:
    """PDF field name -> current value; for a checkbox the ticked state name or "/Off"."""
    reader = PdfReader(io.BytesIO(pdf))
    result: dict[str, str] = {}
    for page in reader.pages:
        for annot in page.get("/Annots", []) or []:
            annot = annot.get_object()
            name = _full_name(annot)
            if annot.get("/Subtype") != "/Widget" or name is None:
                continue
            if str(annot.get("/FT")) == "/Btn":
                result[name] = str(annot.get("/AS", "/Off"))
            else:
                value = annot.get("/V")
                result[name] = "" if value is None else str(value)
    return result


def fill_i765(
    app: I765Application,
    *,
    attorney_decisions_made: bool = False,
    root: Path = REPO_ROOT,
) -> FillResult:
    registry = load_registry()
    edition = registry.active
    if app.edition != registry.active_edition:
        raise FillError(f"application is for edition {app.edition}, not {registry.active_edition}")
    problems = verify_pinned_files(edition, root)
    if problems:
        raise FillError("official files do not match the registry: " + "; ".join(problems))

    field_map = load_field_map(root / edition.field_map)
    effective, moved, not_placed = _with_part_6_overflow(app)
    values, skipped = compute_values(effective, field_map.entries, attorney_decisions_made)

    reader = PdfReader(root / edition.form_pdf.path)
    writer = PdfWriter(clone_from=reader)
    acroform = writer._root_object["/AcroForm"]
    # Fill the AcroForm layer and drop XFA, otherwise XFA-aware viewers show the empty
    # XFA data instead. Drop the Adobe usage-rights signature: any change invalidates it.
    if "/XFA" in acroform:
        del acroform["/XFA"]
    if "/Perms" in writer._root_object:
        del writer._root_object["/Perms"]
    acroform[NameObject("/NeedAppearances")] = BooleanObject(True)

    on_pages: set[str] = set()
    for page in writer.pages:
        names = _page_widget_names(page)
        on_pages |= names
        here = {name: value for name, value in values.items() if name in names}
        if here:
            writer.update_page_form_field_values(page, here, auto_regenerate=False)
    missing = sorted(set(values) - on_pages)
    if missing:
        raise FillError(f"PDF has no field {missing[0]!r}")

    buffer = io.BytesIO()
    writer.write(buffer)
    pdf = buffer.getvalue()

    # Read back: every written value must be there, and nothing else may be filled.
    actual = read_pdf_values(pdf)
    wrong = []
    for entry in field_map.entries:
        name = entry.pdf_field
        expected = values.get(name, "/Off" if entry.kind == "checkbox" else "")
        if actual.get(name, "") != expected:
            wrong.append(name)
    if wrong:
        raise FillVerificationError(f"{len(wrong)} field(s) differ after writing, e.g. {wrong[0]}")

    return FillResult(
        pdf=pdf,
        report=FillReport(
            edition=registry.active_edition,
            filled_fields=len(values),
            skipped=skipped,
            moved_to_part_6=moved,
            not_placed=not_placed,
        ),
    )
