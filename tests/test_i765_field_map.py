"""The field map is checked against the real PDF, so a wrong link fails here, not on a form."""

import re
from collections import Counter, defaultdict
from functools import cache

import pytest
from pypdf import PdfReader

from uscis_assistant.forms.field_map import (
    allowed_checkbox_values,
    leaf_paths,
    load_field_map,
    normalize_tooltip,
    resolve_path,
)
from uscis_assistant.forms.i765.schema import (
    LIST_CAPACITY,
    US_STATE_CODES,
    I765Application,
    UnitType,
)
from uscis_assistant.forms.registry import REPO_ROOT, load_registry

PDF_TYPE = {"text": "/Tx", "checkbox": "/Btn", "choice": "/Ch"}
# Items whose answer depends on the Interpreter / Preparer question (owner's rule 7).
ATTORNEY_DECISION_ITEMS = {"3.1.A", "3.1.B", "3.2"}


@cache
def field_map():
    return load_field_map(REPO_ROOT / load_registry().active.field_map)


@cache
def pdf_fields():
    reader = PdfReader(REPO_ROOT / load_registry().active.form_pdf.path)
    return {n: f for n, f in (reader.get_fields() or {}).items() if f.get("/FT") is not None}


@cache
def widget_x_positions():
    reader = PdfReader(REPO_ROOT / load_registry().active.form_pdf.path)
    positions = {}
    for page in reader.pages:
        for annot in page.get("/Annots", []) or []:
            annot = annot.get_object()
            names, node = [], annot
            while node is not None:
                if node.get("/T"):
                    names.append(str(node["/T"]))
                node = node["/Parent"].get_object() if node.get("/Parent") else None
            positions[".".join(reversed(names))] = float(annot["/Rect"][0])
    return positions


def entries():
    return field_map().entries


def test_map_is_for_the_active_edition():
    assert field_map().edition == load_registry().active_edition


def test_every_fillable_pdf_field_is_mapped_or_deliberately_unmapped():
    fillable = {n for n in pdf_fields() if "PDF417BarCode" not in n}
    mapped = [e.pdf_field for e in entries()]
    unmapped = [u.pdf_field for u in field_map().unmapped]
    assert [n for n, k in Counter(mapped + unmapped).items() if k > 1] == []
    assert set(mapped) | set(unmapped) == fillable


def test_barcodes_are_never_mapped():
    assert not any("PDF417BarCode" in e.pdf_field for e in entries())


def test_signatures_are_never_filled():
    signature_fields = {n for n in pdf_fields() if re.search(r"Signature\[", n)}
    assert signature_fields == {u.pdf_field for u in field_map().unmapped}
    assert signature_fields.isdisjoint(e.pdf_field for e in entries())


@pytest.mark.parametrize("entry", entries(), ids=lambda e: f"{e.item}:{e.pdf_field}")
def test_entry_matches_the_pdf(entry):
    field = pdf_fields().get(entry.pdf_field)
    assert field is not None, "PDF field does not exist"
    assert str(field["/FT"]) == PDF_TYPE[entry.kind]

    tooltip = normalize_tooltip(str(field.get("/TU", "")))
    for snippet in entry.tooltip:
        assert normalize_tooltip(snippet) in tooltip, f"tooltip lacks {snippet!r}"
    part = entry.item.split(".")[0]
    if part.isdigit():
        assert tooltip.startswith(f"part{part}"), "tooltip belongs to another Part"

    if entry.kind == "checkbox":
        assert entry.on_value in [str(s) for s in field.get("/_States_", [])]


@pytest.mark.parametrize("entry", entries(), ids=lambda e: f"{e.item}:{e.path}")
def test_entry_path_exists_in_schema(entry):
    leaf = resolve_path(I765Application, entry.path)
    if entry.kind == "checkbox":
        assert entry.when in allowed_checkbox_values(leaf)


def _expected_label(path: str, when: str | bool) -> str:
    """Words the PDF tooltip must contain for this schema value (normalized form)."""
    if path.endswith("unit_type"):
        return {"apt": "selectapartment", "ste": "selectsuite", "flr": "floor"}[when]
    if path == "preparer.representation_extends_beyond_preparation":
        return "caseextendsbeyond" if when else "doesnotextendbeyond"
    if isinstance(when, bool):
        return "selectyes" if when else "selectno"
    labels = {
        "initial": "selectinitialpermission",
        "replacement": "selectreplacement",
        "renewal": "selectrenewal",
        "reads_english": "icanreadandunderstandenglish",
        "interpreter_read": "theinterpreternamedinpart4",
        "not_attorney": "iamnotanattorney",
        "attorney": "iamanattorney",
    }
    return labels.get(when, f"select{when}")


def test_checkbox_value_matches_the_meaning_of_its_box():
    # Catches swaps such as Female <-> Male that keep every field name valid.
    boxes_per_path = Counter(e.path for e in entries() if e.kind == "checkbox")
    for e in entries():
        if e.kind != "checkbox" or boxes_per_path[e.path] == 1:
            continue  # single "select this box if ..." boxes carry no alternative
        tooltip = normalize_tooltip(str(pdf_fields()[e.pdf_field].get("/TU", "")))
        assert _expected_label(e.path, e.when) in tooltip, (e.item, e.path, e.when)


def test_every_schema_field_reaches_the_pdf():
    expected = set(leaf_paths(I765Application, LIST_CAPACITY)) - {"edition"}
    assert expected - {e.path for e in entries()} == set()


def test_checkbox_groups_cover_every_choice():
    groups = defaultdict(set)
    for e in entries():
        if e.kind == "checkbox":
            groups[(e.item.split(".")[0], e.path)].add(e.when)
    for (_, path), whens in groups.items():
        allowed = allowed_checkbox_values(resolve_path(I765Application, path))
        # A bool with a single box (e.g. "select this box if ...") only needs True.
        assert whens == allowed or whens == {True}, path


def test_unit_boxes_follow_printed_apt_ste_flr_order():
    # Printed labels read "Apt. Ste. Flr." left to right in every address block. In Parts 4
    # and 5 the widgets' on-values are scrambled, so we check the mapping by position.
    groups = defaultdict(list)
    for e in entries():
        if e.path.endswith("unit_type"):
            groups[(e.item, e.path)].append(e)
    assert len(groups) == 4
    for group in groups.values():
        ordered = sorted(group, key=lambda e: widget_x_positions()[e.pdf_field])
        assert [e.when for e in ordered] == [u.value for u in UnitType]


def test_state_lists_match_schema_codes():
    for e in entries():
        if e.kind == "choice":
            options = [str(o) for o in pdf_fields()[e.pdf_field].get("/_States_", [])]
            codes = [
                re.findall(r"'([A-Z]{2})'", o)[0] for o in options if re.search(r"[A-Z]{2}", o)
            ]
            assert tuple(codes) == US_STATE_CODES


def test_interpreter_and_preparer_items_require_attorney_decision():
    for e in entries():
        part = e.item.split(".")[0]
        should = part in {"4", "5"} or any(e.item == i for i in ATTORNEY_DECISION_ITEMS)
        assert e.attorney_decision is should, e.item


def test_eligibility_category_fills_three_segments():
    segments = [e for e in entries() if e.path == "applicant.eligibility.category"]
    assert [e.format for e in segments] == [f"category_segment_{i}" for i in (1, 2, 3)]
