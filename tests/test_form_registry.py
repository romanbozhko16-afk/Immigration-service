import json
import re

import pytest
from pydantic import ValidationError
from pypdf import PdfReader

from uscis_assistant.forms.registry import (
    REPO_ROOT,
    FormRegistry,
    load_registry,
    verify_pinned_files,
)


def test_registry_loads_with_a_single_active_edition():
    registry = load_registry()
    assert registry.form == "I-765"
    assert registry.active_edition in registry.editions
    # Only the one accepted edition is supported; superseded editions are not kept.
    assert len(registry.editions) == 1


def test_pinned_files_match_their_sha256():
    assert verify_pinned_files(load_registry().active) == []


def test_tampered_file_is_detected(tmp_path):
    edition = load_registry().active
    for pinned in (edition.form_pdf, edition.instructions_pdf):
        target = tmp_path / pinned.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"not the official file")
    assert len(verify_pinned_files(edition, root=tmp_path)) == 2


def test_missing_file_is_reported(tmp_path):
    assert all("missing" in p for p in verify_pinned_files(load_registry().active, tmp_path))


def test_active_edition_must_be_registered():
    data = json.loads((REPO_ROOT / "forms/i765/editions.json").read_text())
    data["active_edition"] = "01/01/99"
    with pytest.raises(ValidationError):
        FormRegistry.model_validate(data)


@pytest.mark.parametrize("which", ["form_pdf", "instructions_pdf"])
def test_edition_printed_inside_the_pdf_matches_the_registry(which):
    # The date printed in the PDF itself is the primary source for the edition.
    registry = load_registry()
    pinned = getattr(registry.active, which)
    reader = PdfReader(REPO_ROOT / pinned.path)
    text = reader.pages[0].extract_text() or ""
    assert registry.active_edition in text


def test_field_list_matches_the_pdf():
    registry = load_registry()
    reader = PdfReader(REPO_ROOT / registry.active.form_pdf.path)
    widgets = [n for n, f in (reader.get_fields() or {}).items() if f.get("/FT") is not None]
    listed = json.loads((REPO_ROOT / registry.active.fields_json).read_text())
    assert len(listed) == len(widgets) == 161
    assert sum(1 for r in listed if r["is_barcode"]) == 7
    assert all(re.search(r"PDF417BarCode", r["name"]) for r in listed if r["is_barcode"])
