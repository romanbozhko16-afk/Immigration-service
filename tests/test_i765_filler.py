"""Filling the official PDF. Expected PDF values are written by hand, not derived from the
field map, so a wrong map entry cannot make the test agree with itself. Fictitious data."""

import io
from functools import cache

import pytest
from pypdf import PdfReader, PdfWriter

from uscis_assistant.forms.i765.filler import (
    FillError,
    FillVerificationError,
    fill_i765,
    read_pdf_values,
)
from uscis_assistant.forms.i765.schema import I765Application
from uscis_assistant.forms.registry import REPO_ROOT, load_registry

P1, P2, P3 = "form1[0].Page1[0].", "form1[0].Page2[0].", "form1[0].Page3[0]."
P4, P5, P6, P7 = (
    "form1[0].Page4[0].",
    "form1[0].Page5[0].",
    "form1[0].Page6[0].",
    "form1[0].Page7[0].",
)


def full_data() -> dict:
    address = {
        "street": "100 Example St",
        "city": "Springfield",
        "state": "IL",
        "zip_code": "62701",
    }
    return {
        "reason_for_applying": "renewal",
        "applicant": {
            "name": {"family_name": "Testova", "given_name": "Olena", "middle_name": "Ivanivna"},
            "other_names": [
                {"family_name": f"Alias{i}", "given_name": "Test", "middle_name": "M"}
                for i in range(4)
            ],
            "mailing_address": {
                **address,
                "in_care_of": "Care Name",
                "unit_type": "apt",
                "unit_number": "5B",
            },
            "mailing_same_as_physical": False,
            "physical_address": {
                **address,
                "street": "200 Other Ave",
                "unit_type": "flr",
                "unit_number": "3",
            },
            "a_number": "A-123456789",
            "uscis_online_account_number": "ABC123DEF456",
            "sex": "female",
            "marital_status": "married",
            "previously_filed_i765": True,
            "ssn": "123-45-6789",
            "citizenship_countries": ["Ukraine", "Poland", "Germany"],
            "birth_city": "Kyiv",
            "birth_state_province": "Kyiv Oblast",
            "birth_country": "Ukraine",
            "date_of_birth": "1990-01-02",
            "i94_number": "12345678901",
            "passport_number": "FX0000000",
            "travel_document_number": "TD111",
            "passport_issuing_country": "Ukraine",
            "passport_expiration_date": "2030-03-04",
            "last_entry_date": "2024-05-06",
            "last_entry_place": "New York, NY",
            "status_at_last_arrival": "B-2 visitor",
            "current_status": "F-1 student",
            "sevis_number": "N0000000001",
            "eligibility": {"category": "(c)(17)(iii)", "c8_ever_arrested_or_convicted": False},
        },
        "statement": {
            "statement": "interpreter_read",
            "interpreter_language": "Ukrainian",
            "prepared_by_preparer": True,
            "preparer_name": "Pat Preparer",
            "daytime_phone": "5555550100",
            "mobile_phone": "5555550101",
            "email": "olena.testova@example.com",
            "abc_settlement_class_member": True,
        },
        "interpreter": {
            "name": {"family_name": "Interp", "given_name": "Ivan"},
            "organization": "Lang Org",
            "address": {
                "street": "1 Lang St",
                "unit_type": "ste",
                "unit_number": "7",
                "city": "Austin",
                "state": "TX",
                "zip_code": "73301",
                "country": "USA",
            },
            "daytime_phone": "5555550102",
            "language": "Ukrainian",
        },
        "preparer": {
            "name": {"family_name": "Preparer", "given_name": "Pat"},
            "business_name": "Prep LLC",
            "address": {
                "street": "2 Prep Rd",
                "unit_type": "apt",
                "unit_number": "9",
                "city": "Dallas",
                "state": "TX",
                "zip_code": "75001",
                "country": "USA",
            },
            "daytime_phone": "5555550103",
            "statement": "attorney",
            "representation_extends_beyond_preparation": False,
        },
        "attorney": {
            "g28_attached": True,
            "state_bar_number": "BAR123",
            "uscis_online_account_number": "ZZZ000111222",
        },
        "additional_info": [
            {
                "page_number": "3",
                "part_number": "2",
                "item_number": "24",
                "text": "Extra explanation",
            }
        ],
    }


@cache
def result():
    return fill_i765(I765Application.model_validate(full_data()), attorney_decisions_made=True)


@cache
def values() -> dict[str, str]:
    return read_pdf_values(result().pdf)


# Hand-written expectations: (PDF field, expected value). Checkboxes show the ticked state.
EXPECTED = {
    # Part 1 and names
    P1 + "Part1_Checkbox[2]": "/3",  # renewal = 1.c
    P1 + "Part1_Checkbox[0]": "/Off",
    P1 + "Line1a_FamilyName[0]": "Testova",
    P1 + "Line1c_MiddleName[0]": "Ivanivna",
    P1 + "Line2a_FamilyName[0]": "Alias0",  # other name 1 = item 2
    P1 + "Line3a_FamilyName[1]": "Alias1",  # other name 2 = item 3
    P1 + "Line3a_FamilyName[0]": "Alias2",  # other name 3 = item 4
    P1 + "Attorney-Rep[0].CheckBox1[0]": "/1",
    P1 + "Attorney-Rep[0].attorneyBarNumber[0]": "BAR123",
    # Mailing address (item 5), apartment box ticked
    P2 + "Line4a_InCareofName[0]": "Care Name",
    P2 + "Pt2Line5_Unit[2]": "/ APT ",
    P2 + "Pt2Line5_Unit[0]": "/Off",
    P2 + "Pt2Line5_AptSteFlrNumber[0]": "5B",
    P2 + "Pt2Line5_State[0]": "IL",
    P2 + "Part2Line5_Checkbox[0]": "/N",  # item 6 "No"
    P2 + "Part2Line5_Checkbox[1]": "/Off",
    P2 + "Pt2Line7_StreetNumberName[0]": "200 Other Ave",
    P2 + "Pt2Line7_Unit[1]": "/ FLR ",  # floor
    # Other information
    P2 + "Line7_AlienNumber[0]": "123456789",  # digits only: "A-" is printed on the form
    P2 + "Line8_ElisAccountNumber[0]": "ABC123DEF456",
    P2 + "Line9_Checkbox[0]": "/N",  # item 10: female is /N
    P2 + "Line9_Checkbox[1]": "/Off",
    P2 + "Line10_Checkbox[3]": "/Married",
    P2 + "Line10_Checkbox[2]": "/Off",
    P2 + "Line19_Checkbox[1]": "/Y",  # item 12: yes
    P2 + "Line12b_SSN[0]": "123456789",
    P2 + "Line17a_CountryOfBirth[0]": "Ukraine",  # item 14.a citizenship
    P2 + "Line17b_CountryOfBirth[0]": "Poland",
    # Birth, arrival, category
    P3 + "Line18a_CityTownOfBirth[0]": "Kyiv",
    P3 + "Line18b_CityTownOfBirth[0]": "Kyiv Oblast",
    P3 + "Line18c_CountryOfBirth[0]": "Ukraine",
    P3 + "Line19_DOB[0]": "01/02/1990",
    P3 + "Line20e_ExpDate[0]": "03/04/2030",
    P3 + "Line21_DateOfLastEntry[0]": "05/06/2024",
    P3 + "place_entry[0]": "New York, NY",
    P3 + "#area[1].section_1[0]": "c",
    P3 + "#area[1].section_2[0]": "17",
    P3 + "#area[1].section_3[0]": "iii",
    P3 + "PtLine29_YesNo[1]": "/N",  # item 30: never arrested = No
    P3 + "PtLine29_YesNo[0]": "/Off",
    # Part 3 (attorney decision items, filled because the caller said so)
    P4 + "Pt3Line1Checkbox[0]": "/B",  # interpreter read to me
    P4 + "Pt3Line1Checkbox[1]": "/Off",
    P4 + "Pt3Line1b_Language[0]": "Ukrainian",
    P4 + "Part3_Checkbox[0]": "/C",
    P4 + "Pt4Line6_Checkbox[0]": "/A",  # item 6 ABC settlement (named Pt4...)
    P4 + "Pt4Line1a_InterpreterFamilyName[0]": "Interp",
    # Part 4 interpreter address uses "Pt5Line3" names; suite box is the one printed "Ste."
    P5 + "Pt5Line3a_StreetNumberName[0]": "1 Lang St",
    P5 + "Pt5Line3b_Unit[2]": "/ APT ",  # printed "Ste." has on-value "/ APT " here
    P5 + "Pt5Line3b_Unit[1]": "/Off",
    P5 + "Pt5Line3d_State[0]": "TX",
    # Part 5 preparer address uses "Pt6Line3" names; apartment box is the one printed "Apt."
    P5 + "Pt5Line1a_PreparerFamilyName[0]": "Preparer",
    P5 + "Pt6Line3a_StreetNumberName[0]": "2 Prep Rd",
    P5 + "Pt6Line3b_Unit[1]": "/ FLR ",  # printed "Apt." has on-value "/ FLR " here
    P5 + "Pt6Line3b_Unit[0]": "/Off",
    P6 + "Part5Line7_Checkbox[1]": "/B",
    P6 + "Part5Line7b_Checkbox[1]": "/N",
    # Part 6: copies of name and A-Number, the user's entry, then overflow
    P7 + "Line1a_FamilyName[0]": "Testova",
    P7 + "Line7_AlienNumber[0]": "123456789",
    P7 + "Pt6Line3a_PageNumber[0]": "3",
}


@pytest.mark.parametrize(("field", "expected"), list(EXPECTED.items()))
def test_value_written_to_the_right_pdf_field(field, expected):
    assert values()[field] == expected


def test_part_6_item_3d_text_is_in_its_odd_named_widget():
    assert values()[P7 + "Pt6Line4d_AdditionalInfo[1]"] == "Extra explanation"


def test_overflow_goes_to_part_6_in_order():
    v = values()
    # entry 1 = the user's, entry 2 = 4th other name, entry 3-4... = 3rd citizenship
    assert v[P7 + "Pt6Line4d_AdditionalInfo[0]"].startswith("Other name used (continued): Alias3")
    assert v[P7 + "Pt6Line4a_PageNumber[0]"] == "1"
    assert v[P7 + "Pt6Line5d_AdditionalInfo[0]"] == (
        "Country of citizenship or nationality (continued): Germany"
    )
    assert result().report.moved_to_part_6 == 2
    assert result().report.not_placed == 0


def test_signatures_stay_empty_and_barcodes_are_untouched():
    source = read_pdf_values((REPO_ROOT / load_registry().active.form_pdf.path).read_bytes())
    for name, value in values().items():
        if "Signature" in name:
            assert value == "", name
        if "PDF417BarCode" in name:
            assert value == source[name], name


def test_barcodes_carry_form_id_edition_and_page_not_personal_data():
    barcodes = {n: v for n, v in values().items() if "PDF417BarCode" in n}
    assert len(barcodes) == 7
    assert all(v.startswith("I-765|08/21/25|") for v in barcodes.values())


def test_pdf_has_no_xfa_and_no_usage_rights_signature():
    reader = PdfReader(io.BytesIO(result().pdf))
    assert "/XFA" not in reader.trailer["/Root"]["/AcroForm"]
    assert "/Perms" not in reader.trailer["/Root"]


def test_source_file_is_not_modified():
    registry = load_registry()
    before = (REPO_ROOT / registry.active.form_pdf.path).read_bytes()
    fill_i765(I765Application.model_validate(full_data()))
    assert (REPO_ROOT / registry.active.form_pdf.path).read_bytes() == before


def test_report_has_no_personal_data():
    report = result().report.model_dump_json()
    for secret in ("Testova", "123456789", "Kyiv", "olena.testova"):
        assert secret not in report


# --- attorney decision items ----------------------------------------------------------


def test_attorney_decision_items_are_skipped_by_default():
    out = fill_i765(I765Application.model_validate(full_data()))
    v = read_pdf_values(out.pdf)
    for field in (
        P4 + "Pt3Line1Checkbox[0]",
        P4 + "Pt4Line1a_InterpreterFamilyName[0]",
        P5 + "Pt5Line1a_PreparerFamilyName[0]",
        P6 + "Part5Line7_Checkbox[1]",
    ):
        assert v[field] in ("", "/Off"), field
    assert v[P1 + "Line1a_FamilyName[0]"] == "Testova"  # normal items still filled
    assert {s.reason for s in out.report.skipped} == {"attorney decision pending"}
    assert len(out.report.skipped) > 40


# --- literal behaviour ----------------------------------------------------------------


def minimal() -> dict:
    data = full_data()
    for key in ("interpreter", "preparer", "attorney", "additional_info"):
        data.pop(key)
    data["applicant"]["other_names"] = []
    data["applicant"]["citizenship_countries"] = ["Ukraine"]
    data["statement"] = {"daytime_phone": "5555550100"}
    return data


def fill_values(data: dict) -> dict[str, str]:
    return read_pdf_values(fill_i765(I765Application.model_validate(data)).pdf)


def test_missing_answers_stay_empty_and_na_is_never_invented():
    data = minimal()
    data["applicant"]["a_number"] = None
    v = fill_values(data)
    assert v[P2 + "Line7_AlienNumber[0]"] == ""
    assert "N/A" not in v.values()


def test_na_is_written_when_the_user_answered_na():
    data = minimal()
    data["applicant"]["a_number"] = "N/A"
    assert fill_values(data)[P2 + "Line7_AlienNumber[0]"] == "N/A"


def test_badly_shaped_category_is_left_empty_and_reported():
    data = minimal()
    data["applicant"]["eligibility"] = {"category": "C8"}
    out = fill_i765(I765Application.model_validate(data))
    v = read_pdf_values(out.pdf)
    assert [v[P3 + f"#area[1].section_{i}[0]"] for i in (1, 2, 3)] == ["", "", ""]
    assert sum(s.path == "applicant.eligibility.category" for s in out.report.skipped) == 3


def test_malformed_identifiers_are_written_as_given_not_repaired():
    data = minimal()
    data["applicant"]["ssn"] = "12-34"
    data["applicant"]["a_number"] = "A1234"
    v = fill_values(data)
    assert (v[P2 + "Line12b_SSN[0]"], v[P2 + "Line7_AlienNumber[0]"]) == ("12-34", "A1234")


def test_category_with_two_parts_fills_two_boxes():
    data = minimal()
    data["applicant"]["eligibility"] = {"category": "(a)(3)", "c8_ever_arrested_or_convicted": None}
    v = fill_values(data)
    assert [v[P3 + f"#area[1].section_{i}[0]"] for i in (1, 2, 3)] == ["a", "3", ""]


def test_part_6_overflow_beyond_capacity_is_reported():
    data = minimal()
    data["applicant"]["other_names"] = [
        {"family_name": f"Alias{i}", "given_name": "T"} for i in range(9)
    ]
    out = fill_i765(I765Application.model_validate(data))
    assert (out.report.moved_to_part_6, out.report.not_placed) == (5, 1)


# --- safety checks --------------------------------------------------------------------


def test_wrong_edition_is_refused():
    app = I765Application.model_validate(minimal())
    object.__setattr__(app, "edition", "09/15/26")
    with pytest.raises(FillError):
        fill_i765(app)


def test_modified_official_file_is_refused(tmp_path):
    registry = load_registry()
    for rel in (
        registry.active.form_pdf.path,
        registry.active.instructions_pdf.path,
        registry.active.field_map,
    ):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO_ROOT / rel).read_bytes())
    (tmp_path / registry.active.form_pdf.path).write_bytes(b"%PDF-tampered")
    with pytest.raises(FillError, match="do not match"):
        fill_i765(I765Application.model_validate(minimal()), root=tmp_path)


def test_a_failed_write_is_caught_by_the_read_back(monkeypatch):
    # Simulate a PDF library that silently drops values: the read-back must notice.
    monkeypatch.setattr("pypdf.PdfWriter.update_page_form_field_values", lambda self, *a, **k: None)
    with pytest.raises(FillVerificationError):
        fill_i765(I765Application.model_validate(minimal()))


def test_read_back_notices_a_silently_lost_checkbox(monkeypatch):
    real = PdfWriter.update_page_form_field_values

    def lossy(self, page, fields, *args, **kwargs):
        fields = {k: v for k, v in fields.items() if not k.endswith("Line9_Checkbox[0]")}
        return real(self, page, fields, *args, **kwargs)

    monkeypatch.setattr(PdfWriter, "update_page_form_field_values", lossy)
    with pytest.raises(FillVerificationError):
        fill_i765(I765Application.model_validate(minimal()))  # minimal() is female
