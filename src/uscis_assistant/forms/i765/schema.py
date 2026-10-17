"""Data schema for Form I-765, edition 08/21/25.

Holds the English values that go onto the form. The user's original-language answers and
the audit trail are stored separately (storage layer). Every leaf field here is linked to a
PDF field in `forms/i765/mappings/<edition>.json`; a test enforces full coverage.

Item references in comments ("P2.10") mean Part 2, Item Number 10 of the printed form.

Type checks only reject values of the wrong shape. Content rules (A-Number format,
consistency between answers, ...) are validation flags, not schema errors: suspicious data
is flagged for review, never silently corrected.
"""

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EDITION = "08/21/25"

# State / territory codes exactly as offered by the PDF's state lists (a test compares them).
US_STATE_CODES = (
    "AA", "AE", "AK", "AL", "AP", "AR", "AS", "AZ", "CA", "CO", "CT", "DC", "DE", "FL",
    "FM", "GA", "GU", "HI", "IA", "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD", "ME",
    "MH", "MI", "MN", "MO", "MP", "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM", "NV",
    "NY", "OH", "OK", "OR", "PA", "PR", "PW", "RI", "SC", "SD", "TN", "TX", "UT", "VA",
    "VI", "VT", "WA", "WI", "WV", "WY",
)  # fmt: skip
USState = Literal[
    "AA", "AE", "AK", "AL", "AP", "AR", "AS", "AZ", "CA", "CO", "CT", "DC", "DE", "FL",
    "FM", "GA", "GU", "HI", "IA", "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD", "ME",
    "MH", "MI", "MN", "MO", "MP", "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM", "NV",
    "NY", "OH", "OK", "OR", "PA", "PR", "PW", "RI", "SC", "SD", "TN", "TX", "UT", "VA",
    "VI", "VT", "WA", "WI", "WV", "WY",
]  # fmt: skip

# How many entries of each list fit on the form; extra entries go to Part 6 when filling.
LIST_CAPACITY = {
    "applicant.other_names": 3,  # P2.2-P2.4
    "applicant.citizenship_countries": 2,  # P2.14.A-B
    "additional_info": 5,  # P6.3-P6.7
}


class FormModel(BaseModel):
    # extra="forbid": an unknown key is a bug, not data to drop silently.
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ReasonForApplying(StrEnum):  # P1.1
    INITIAL = "initial"  # 1.A initial permission to accept employment
    REPLACEMENT = "replacement"  # 1.B replacement / correction NOT due to USCIS error
    RENEWAL = "renewal"  # 1.C renewal


class Sex(StrEnum):  # P2.10
    FEMALE = "female"
    MALE = "male"


class MaritalStatus(StrEnum):  # P2.11
    SINGLE = "single"
    MARRIED = "married"
    DIVORCED = "divorced"
    WIDOWED = "widowed"


class UnitType(StrEnum):
    APT = "apt"
    STE = "ste"
    FLR = "flr"


class ApplicantStatementChoice(StrEnum):  # P3.1 (requires attorney decision)
    READS_ENGLISH = "reads_english"  # 1.A
    INTERPRETER_READ = "interpreter_read"  # 1.B


class PreparerStatementChoice(StrEnum):  # P5.7
    NOT_ATTORNEY = "not_attorney"  # 7.A
    ATTORNEY = "attorney"  # 7.B


class Name(FormModel):
    family_name: str
    given_name: str
    middle_name: str | None = None


class ShortName(FormModel):
    """Interpreter / preparer name: the form has no middle-name box for them."""

    family_name: str
    given_name: str


class USAddress(FormModel):
    street: str
    unit_type: UnitType | None = None
    unit_number: str | None = None
    city: str
    state: USState
    zip_code: str


class MailingAddress(USAddress):  # P2.5
    in_care_of: str | None = None


class ContactAddress(FormModel):
    """Interpreter / preparer mailing address; may be outside the U.S."""

    street: str
    unit_type: UnitType | None = None
    unit_number: str | None = None
    city: str
    state: USState | None = None
    zip_code: str | None = None
    province: str | None = None
    postal_code: str | None = None
    country: str


class Eligibility(FormModel):
    # P2.27, exactly as the user states it from their own documents, e.g. "(c)(8)".
    # The service never chooses it; None means "requires attorney review".
    category: str | None = None
    # P2.28 (c)(3)(C) STEM OPT
    stem_degree: str | None = None
    stem_employer_name: str | None = None
    stem_everify_company_id: str | None = None
    # P2.29 (c)(26): receipt number of the H-1B spouse's Form I-797 for Form I-129
    c26_spouse_receipt_number: str | None = None
    # P2.30 (c)(8): ever arrested for and/or convicted of any crime
    c8_ever_arrested_or_convicted: bool | None = None
    # P2.31.A (c)(35)/(c)(36): receipt number of the Form I-797 for Form I-140
    c35_c36_receipt_number: str | None = None
    # P2.31.B (c)(35)/(c)(36): ever arrested for and/or convicted of any crime
    c35_c36_ever_arrested_or_convicted: bool | None = None


class Applicant(FormModel):  # Part 2
    name: Name  # P2.1
    other_names: list[Name] = Field(default_factory=list)  # P2.2-P2.4
    mailing_address: MailingAddress  # P2.5
    mailing_same_as_physical: bool  # P2.6
    physical_address: USAddress | None = None  # P2.7, when P2.6 is "No"
    a_number: str | None = None  # P2.8
    uscis_online_account_number: str | None = None  # P2.9
    sex: Sex  # P2.10
    marital_status: MaritalStatus  # P2.11
    previously_filed_i765: bool  # P2.12
    ssn: str | None = None  # P2.13
    citizenship_countries: list[str] = Field(min_length=1)  # P2.14
    birth_city: str  # P2.15.A
    birth_state_province: str | None = None  # P2.15.B
    birth_country: str  # P2.15.C
    date_of_birth: date  # P2.16
    i94_number: str | None = None  # P2.17
    passport_number: str | None = None  # P2.18
    travel_document_number: str | None = None  # P2.19
    passport_issuing_country: str | None = None  # P2.20
    passport_expiration_date: date | None = None  # P2.21
    last_entry_date: date | None = None  # P2.22
    last_entry_place: str | None = None  # P2.23
    status_at_last_arrival: str | None = None  # P2.24
    current_status: str | None = None  # P2.25
    sevis_number: str | None = None  # P2.26
    eligibility: Eligibility = Field(default_factory=Eligibility)  # P2.27-P2.31


class ApplicantStatement(FormModel):  # Part 3
    # P3.1 and P3.2 depend on the Interpreter / Preparer question: attorney decision.
    statement: ApplicantStatementChoice | None = None  # P3.1.A / P3.1.B
    interpreter_language: str | None = None  # P3.1.B language
    prepared_by_preparer: bool | None = None  # P3.2 checkbox
    preparer_name: str | None = None  # P3.2 name
    daytime_phone: str | None = None  # P3.3
    mobile_phone: str | None = None  # P3.4
    email: str | None = None  # P3.5
    abc_settlement_class_member: bool | None = None  # P3.6, user states from own documents
    # P3.7 signature and date are never filled: the applicant signs and dates in ink.


class Interpreter(FormModel):  # Part 4 (requires attorney decision)
    name: ShortName  # P4.1
    organization: str | None = None  # P4.2
    address: ContactAddress  # P4.3
    daytime_phone: str | None = None  # P4.4
    mobile_phone: str | None = None  # P4.5
    email: str | None = None  # P4.6
    language: str | None = None  # language in the Interpreter's Certification


class Preparer(FormModel):  # Part 5 (requires attorney decision)
    name: ShortName  # P5.1
    business_name: str | None = None  # P5.2
    address: ContactAddress  # P5.3
    daytime_phone: str | None = None  # P5.4
    mobile_phone: str | None = None  # P5.5
    email: str | None = None  # P5.6
    statement: PreparerStatementChoice | None = None  # P5.7.A / P5.7.B
    representation_extends_beyond_preparation: bool | None = None  # P5.7.B yes/no


class AttorneyRepresentative(FormModel):  # page 1 box, completed by an attorney only
    g28_attached: bool = False
    state_bar_number: str | None = None
    uscis_online_account_number: str | None = None


class AdditionalInfoEntry(FormModel):  # P6.3-P6.7
    page_number: str
    part_number: str
    item_number: str
    text: str


class I765Application(FormModel):
    edition: Literal["08/21/25"] = EDITION
    reason_for_applying: ReasonForApplying  # Part 1
    applicant: Applicant  # Part 2
    statement: ApplicantStatement = Field(default_factory=ApplicantStatement)  # Part 3
    interpreter: Interpreter | None = None  # Part 4
    preparer: Preparer | None = None  # Part 5
    attorney: AttorneyRepresentative | None = None  # page 1
    # Part 6 name and A-Number are copied from Part 2 when filling.
    additional_info: list[AdditionalInfoEntry] = Field(default_factory=list)
