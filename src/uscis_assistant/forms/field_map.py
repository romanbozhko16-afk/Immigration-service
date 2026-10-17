"""Field map: links schema paths to PDF fields for one form edition.

The map is data (`forms/<form>/mappings/<edition>.json`). Each entry names the printed
item, the schema path, the PDF field, and tooltip snippets that must appear in that PDF
field's tooltip, so a wrong link is caught by tests against the real PDF.
"""

import json
import re
import types
from enum import Enum
from pathlib import Path
from typing import Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict

PATH_PART = re.compile(r"^(?P<name>[a-z0-9_]+)(?:\[(?P<index>\d+)\])?$")


class FieldMapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item: str
    path: str
    kind: Literal["text", "checkbox", "choice"]
    pdf_field: str
    tooltip: list[str]
    when: str | bool | None = None  # checkbox: schema value that ticks this box
    on_value: str | None = None  # checkbox: the widget's own "on" state name
    format: str | None = None
    attorney_decision: bool = False
    note: str | None = None


class UnmappedField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pdf_field: str
    reason: str


class FieldMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    form: str
    edition: str
    rules: list[str]
    entries: list[FieldMapEntry]
    unmapped: list[UnmappedField]


def load_field_map(path: Path) -> FieldMap:
    return FieldMap.model_validate(json.loads(path.read_text()))


def normalize_tooltip(text: str) -> str:
    """Lowercase alphanumerics only: tooltips contain stray spaces like "I - 7 65"."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _unwrap(annotation: object) -> object:
    """Strip Optional[...] and list[...] down to the element type."""
    while True:
        origin = get_origin(annotation)
        if origin in (Union, types.UnionType):
            args = [a for a in get_args(annotation) if a is not type(None)]
            if len(args) != 1:
                return annotation
            annotation = args[0]
        elif origin is list:
            annotation = get_args(annotation)[0]
        else:
            return annotation


def _is_list(annotation: object) -> bool:
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        return any(_is_list(a) for a in get_args(annotation))
    return origin is list


def resolve_path(model: type[BaseModel], path: str) -> object:
    """Return the leaf type a dotted path such as `applicant.other_names[0].family_name`
    points to. Raises KeyError for unknown fields and ValueError for misused indexes."""
    current: object = model
    for part in path.split("."):
        match = PATH_PART.match(part)
        if match is None or not (isinstance(current, type) and issubclass(current, BaseModel)):
            raise ValueError(f"cannot resolve {part!r} in {path!r}")
        field = current.model_fields[match["name"]]
        if (match["index"] is not None) != _is_list(field.annotation):
            raise ValueError(f"index use does not match list type at {part!r} in {path!r}")
        current = _unwrap(field.annotation)
    return current


def leaf_paths(
    model: type[BaseModel], list_capacity: dict[str, int], prefix: str = ""
) -> list[str]:
    """All leaf paths of a model, expanding lists up to their capacity on the form."""
    paths = []
    for name, field in model.model_fields.items():
        path = f"{prefix}{name}"
        element = _unwrap(field.annotation)
        targets = (
            [f"{path}[{i}]" for i in range(list_capacity[path])]
            if _is_list(field.annotation)
            else [path]
        )
        for target in targets:
            if isinstance(element, type) and issubclass(element, BaseModel):
                paths += leaf_paths(element, list_capacity, f"{target}.")
            else:
                paths.append(target)
    return paths


def allowed_checkbox_values(annotation: object) -> set[str | bool]:
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return {member.value for member in annotation}
    if annotation is bool:
        return {True, False}
    return set()
