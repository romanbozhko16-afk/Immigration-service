from datetime import date

import pytest
from pydantic import ValidationError

from uscis_assistant.forms.i765.schema import (
    I765Application,
    ReasonForApplying,
    Sex,
)

# Fictitious test data only.


def minimal_application(**overrides) -> dict:
    data = {
        "reason_for_applying": "initial",
        "applicant": {
            "name": {"family_name": "Testova", "given_name": "Olena"},
            "mailing_address": {
                "street": "100 Example St",
                "city": "Springfield",
                "state": "IL",
                "zip_code": "62701",
            },
            "mailing_same_as_physical": True,
            "sex": "female",
            "marital_status": "single",
            "previously_filed_i765": False,
            "citizenship_countries": ["Ukraine"],
            "birth_city": "Kyiv",
            "birth_country": "Ukraine",
            "date_of_birth": "1990-01-02",
        },
    }
    data.update(overrides)
    return data


def test_minimal_application_is_valid():
    app = I765Application.model_validate(minimal_application())
    assert app.edition == "08/21/25"
    assert app.reason_for_applying is ReasonForApplying.INITIAL
    assert app.applicant.sex is Sex.FEMALE
    assert app.applicant.date_of_birth == date(1990, 1, 2)


def test_eligibility_category_is_empty_unless_the_user_states_it():
    app = I765Application.model_validate(minimal_application())
    assert app.applicant.eligibility.category is None


def test_unknown_keys_are_rejected():
    with pytest.raises(ValidationError):
        I765Application.model_validate(minimal_application(unexpected="x"))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("applicant", "sex"), "other"),
        (("applicant", "mailing_address", "state"), "XX"),
        (("applicant", "date_of_birth"), "not a date"),
    ],
)
def test_wrong_shape_is_rejected(path, value):
    data = minimal_application()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        I765Application.model_validate(data)


def test_at_least_one_citizenship_is_required():
    data = minimal_application()
    data["applicant"]["citizenship_countries"] = []
    with pytest.raises(ValidationError):
        I765Application.model_validate(data)


def test_more_other_names_than_the_form_holds_are_kept_for_part_6():
    data = minimal_application()
    data["applicant"]["other_names"] = [
        {"family_name": f"Alias{i}", "given_name": "Test"} for i in range(5)
    ]
    assert len(I765Application.model_validate(data).applicant.other_names) == 5


def test_edition_cannot_be_changed():
    with pytest.raises(ValidationError):
        I765Application.model_validate(minimal_application(edition="09/15/26"))
