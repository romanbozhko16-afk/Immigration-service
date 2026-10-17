"""Registry of official form editions.

The registry pins which edition of a form the app fills, together with a SHA-256 of the
official files. Switching editions is a data change: add the new edition's entry, point
`active_edition` at it, and supply its field map. Superseded editions are deliberately
not kept, because the product supports only the one edition currently accepted.
"""

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator

REPO_ROOT = Path(__file__).resolve().parents[3]
I765_REGISTRY_PATH = REPO_ROOT / "forms" / "i765" / "editions.json"


class PinnedFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    sha256: str
    bytes: int
    pdf_created: str


class FormEdition(BaseModel):
    model_config = ConfigDict(frozen=True)

    omb_expires: str
    source_page: str
    obtained: str
    verified_against_uscis_page: bool
    form_pdf: PinnedFile
    instructions_pdf: PinnedFile
    fields_json: str


class FormRegistry(BaseModel):
    model_config = ConfigDict(frozen=True)

    form: str
    active_edition: str
    editions: dict[str, FormEdition]

    @model_validator(mode="after")
    def _active_edition_is_registered(self) -> "FormRegistry":
        if self.active_edition not in self.editions:
            raise ValueError(f"active_edition {self.active_edition!r} is not in editions")
        return self

    @property
    def active(self) -> FormEdition:
        return self.editions[self.active_edition]


def load_registry(path: Path = I765_REGISTRY_PATH) -> FormRegistry:
    return FormRegistry.model_validate(json.loads(path.read_text()))


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_pinned_files(edition: FormEdition, root: Path = REPO_ROOT) -> list[str]:
    """Return a list of problems; an empty list means every pinned file matches."""
    problems = []
    for pinned in (edition.form_pdf, edition.instructions_pdf):
        file_path = root / pinned.path
        if not file_path.exists():
            problems.append(f"missing file: {pinned.path}")
        elif sha256_of(file_path) != pinned.sha256:
            problems.append(f"sha256 mismatch: {pinned.path}")
    return problems
