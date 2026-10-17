"""Formal checks for Form I-765 (edition 08/21/25).

Every rule cites the official text it comes from. Rules only produce flags; the application
is never modified. Checks are formal: they never judge eligibility or the merits of a case.
"""

import re
from collections.abc import Callable
from datetime import date

from uscis_assistant.forms.i765.schema import (
    LIST_CAPACITY,
    ApplicantStatementChoice,
    ContactAddress,
    I765Application,
    ReasonForApplying,
    USAddress,
)
from uscis_assistant.validation.flags import (
    Flag,
    FlagCode,
    instructions_source,
    tooltip_source,
)

# Shape of every category code listed in the instructions, e.g. (a)(3), (c)(17)(iii), (b)(1)(A).
CATEGORY_SHAPE = re.compile(r"^\([a-z]\)\(\d{1,2}\)(\((?:[ivx]+|[A-Z])\))?$")

RECEIPT_NUMBER = re.compile(r"^[A-Za-z0-9]{13}$")
FORMATS: dict[str, tuple[str, re.Pattern[str], str]] = {
    # path: (item, pattern, what the form asks for)
    "applicant.a_number": (
        "2.8",
        # "If you do not have an A-Number, type or print N/A" (Instructions, page 18).
        re.compile(r"^(?:(?:A-?)?\d{9}|N/A)$", re.IGNORECASE),
        "9 digits, or N/A if you have none",
    ),
    "applicant.uscis_online_account_number": (
        "2.9",
        re.compile(r"^[A-Za-z0-9]{12}$"),
        "12 characters",
    ),
    "applicant.ssn": ("2.13", re.compile(r"^\d{3}-?\d{2}-?\d{4}$"), "9 digits"),
    "applicant.i94_number": ("2.17", re.compile(r"^\d{11}$"), "11 digits"),
    "applicant.eligibility.c26_spouse_receipt_number": ("2.29", RECEIPT_NUMBER, "13 characters"),
    "applicant.eligibility.c35_c36_receipt_number": ("2.31.A", RECEIPT_NUMBER, "13 characters"),
}


# Instructions page that explains each category-specific item.
INSTRUCTION_PAGE = {"2.28.A": 19, "2.28.B": 19, "2.28.C": 19, "2.29": 19, "2.30": 20,
                    "2.31.A": 20, "2.31.B": 20}  # fmt: skip


def category_key(category: str | None) -> str | None:
    """Comparison key for recognising which category-specific items apply. Used only to
    decide which checks to run; the stored answer is never changed."""
    return re.sub(r"\s+", "", category).lower() if category else None


def _get(app: I765Application, path: str) -> object:
    value: object = app
    for part in path.split("."):
        value = getattr(value, part)
    return value


def validate_i765(app: I765Application, today: date) -> list[Flag]:
    flags: list[Flag] = []
    for rule in RULES:
        flags.extend(rule(app, today))
    return flags


def _interpreter_preparer_question(app: I765Application, today: date) -> list[Flag]:
    # Product rule 7: always flagged, for every case.
    return [
        Flag(
            code=FlagCode.ATTORNEY_DECISION,
            item="3.1",
            path=None,
            message=(
                "Whether Part 3 Items 1-2 and Parts 4-5 (interpreter and preparer) must be "
                "completed when this software conducts the interview is an open legal question. "
                "An attorney decides before the form is filed."
            ),
            source=instructions_source(20, "Part 3, Item Numbers 1.a.-7.b., and Parts 4-5"),
        )
    ]


def _eligibility(app: I765Application, today: date) -> list[Flag]:
    e = app.applicant.eligibility
    flags: list[Flag] = []
    if e.category is None:
        # Without a category we cannot tell which of Items 28-31 apply; this flag covers it.
        return [
            Flag(
                code=FlagCode.ATTORNEY_REVIEW,
                item="2.27",
                path="applicant.eligibility.category",
                message=(
                    "No eligibility category was entered. The service does not determine the "
                    "category; it must come from the applicant's own documents or an attorney."
                ),
                source=instructions_source(1, "Item Number 27 must contain the category"),
            )
        ]

    if not CATEGORY_SHAPE.match(e.category):
        flags.append(
            Flag(
                code=FlagCode.FORMAT,
                item="2.27",
                path="applicant.eligibility.category",
                message=(
                    "The category does not have the shape used in the instructions, for example "
                    "(a)(3), (c)(8) or (c)(17)(iii). Enter exactly one category as written in "
                    "your documents."
                ),
                source=instructions_source(1, "Who May File Form I-765, examples of categories"),
            )
        )

    key = category_key(e.category)
    required: list[tuple[str, str, object]] = []  # (item, path, value)
    if key == "(c)(3)(c)":
        required += [
            ("2.28.A", "applicant.eligibility.stem_degree", e.stem_degree),
            ("2.28.B", "applicant.eligibility.stem_employer_name", e.stem_employer_name),
            ("2.28.C", "applicant.eligibility.stem_everify_company_id", e.stem_everify_company_id),
        ]
    if key == "(c)(26)":
        required.append(
            ("2.29", "applicant.eligibility.c26_spouse_receipt_number", e.c26_spouse_receipt_number)
        )
    if key == "(c)(8)":
        required.append(
            (
                "2.30",
                "applicant.eligibility.c8_ever_arrested_or_convicted",
                e.c8_ever_arrested_or_convicted,
            )
        )
    if key in ("(c)(35)", "(c)(36)"):
        required += [
            ("2.31.A", "applicant.eligibility.c35_c36_receipt_number", e.c35_c36_receipt_number),
            (
                "2.31.B",
                "applicant.eligibility.c35_c36_ever_arrested_or_convicted",
                e.c35_c36_ever_arrested_or_convicted,
            ),
        ]
    for item, path, value in required:
        if value is None:
            flags.append(
                Flag(
                    code=FlagCode.MISSING_REQUIRED,
                    item=item,
                    path=path,
                    message=f"Item {item} must be answered for the category entered in Item 27.",
                    source=instructions_source(INSTRUCTION_PAGE[item], f"Item Number {item}"),
                )
            )

    for item, path, applies in (
        ("2.28", "applicant.eligibility.stem_degree", key == "(c)(3)(c)"),
        ("2.28", "applicant.eligibility.stem_employer_name", key == "(c)(3)(c)"),
        ("2.28", "applicant.eligibility.stem_everify_company_id", key == "(c)(3)(c)"),
        ("2.29", "applicant.eligibility.c26_spouse_receipt_number", key == "(c)(26)"),
        ("2.30", "applicant.eligibility.c8_ever_arrested_or_convicted", key == "(c)(8)"),
        (
            "2.31.A",
            "applicant.eligibility.c35_c36_receipt_number",
            key in ("(c)(35)", "(c)(36)"),
        ),
        (
            "2.31.B",
            "applicant.eligibility.c35_c36_ever_arrested_or_convicted",
            key in ("(c)(35)", "(c)(36)"),
        ),
    ):
        if not applies and _get(app, path) is not None:
            flags.append(
                Flag(
                    code=FlagCode.INCONSISTENT,
                    item=item,
                    path=path,
                    message=(
                        f"Item {item} is answered, but the form asks it only for another "
                        "category than the one entered in Item 27."
                    ),
                    source=tooltip_source(item),
                )
            )
    return flags


def _legally_sensitive_answers(app: I765Application, today: date) -> list[Flag]:
    # Owner's decision (2026-10-17): flag these for attorney review ("the safest option").
    e = app.applicant.eligibility
    flags = []
    arrest_questions = (
        (
            "2.30",
            "applicant.eligibility.c8_ever_arrested_or_convicted",
            e.c8_ever_arrested_or_convicted,
            "Item Number 30 and Special Filing Instructions (c)(8)",
        ),
        (
            "2.31.B",
            "applicant.eligibility.c35_c36_ever_arrested_or_convicted",
            e.c35_c36_ever_arrested_or_convicted,
            "Item Number 31.b. and court dispositions",
        ),
    )
    for item, path, value, section in arrest_questions:
        if value is True:
            flags.append(
                Flag(
                    code=FlagCode.ATTORNEY_REVIEW,
                    item=item,
                    path=path,
                    message=(
                        f"Item {item} is answered 'Yes' (arrested and/or convicted). The "
                        "instructions require court dispositions in this case. An attorney "
                        "must review this answer and the documents."
                    ),
                    source=instructions_source(20, section),
                )
            )
    if app.statement.abc_settlement_class_member is True:
        flags.append(
            Flag(
                code=FlagCode.ATTORNEY_REVIEW,
                item="3.6",
                path="statement.abc_settlement_class_member",
                message=(
                    "Item 3.6 (ABC settlement class member) is selected. Whether this applies "
                    "is stated by the applicant from their own documents; an attorney must "
                    "review it."
                ),
                source=instructions_source(20, "Part 3, Item Number 6"),
            )
        )
        key = category_key(app.applicant.eligibility.category)
        if key is not None and key != "(c)(8)":
            flags.append(
                Flag(
                    code=FlagCode.INCONSISTENT,
                    item="3.6",
                    path="statement.abc_settlement_class_member",
                    message="Item 3.6 refers to the (c)(8) category, but Item 27 is different.",
                    source=instructions_source(20, "Part 3, Item Number 6"),
                )
            )
    return flags


def _addresses(app: I765Application, today: date) -> list[Flag]:
    a = app.applicant
    flags = []
    if not a.mailing_same_as_physical and a.physical_address is None:
        flags.append(
            Flag(
                code=FlagCode.MISSING_REQUIRED,
                item="2.7",
                path="applicant.physical_address",
                message="Item 6 is 'No', so the U.S. physical address (Item 7) is required.",
                source=tooltip_source("2.6"),
            )
        )
    if a.mailing_same_as_physical and a.physical_address is not None:
        flags.append(
            Flag(
                code=FlagCode.INCONSISTENT,
                item="2.7",
                path="applicant.physical_address",
                message=(
                    "Item 6 says the mailing and physical addresses are the same, but a "
                    "physical address was also given. Item 7 is for a different address."
                ),
                source=instructions_source(18, "Item Numbers 7.a.-7.e."),
            )
        )
    addresses: list[tuple[str, str, USAddress | ContactAddress | None]] = [
        ("2.5.C", "applicant.mailing_address", a.mailing_address),
        ("2.7.B", "applicant.physical_address", a.physical_address),
        ("4.3.B", "interpreter.address", app.interpreter.address if app.interpreter else None),
        ("5.3.B", "preparer.address", app.preparer.address if app.preparer else None),
    ]
    for item, path, address in addresses:
        if address is not None and (address.unit_type is None) != (address.unit_number is None):
            flags.append(
                Flag(
                    code=FlagCode.INCONSISTENT,
                    item=item,
                    path=f"{path}.unit_type",
                    message="Apt./Ste./Flr. and its number must be given together.",
                    source=tooltip_source(item),
                )
            )
    return flags


def _history(app: I765Application, today: date) -> list[Flag]:
    if (
        app.reason_for_applying in (ReasonForApplying.RENEWAL, ReasonForApplying.REPLACEMENT)
        and app.applicant.previously_filed_i765 is False
    ):
        return [
            Flag(
                code=FlagCode.INCONSISTENT,
                item="2.12",
                path="applicant.previously_filed_i765",
                message=(
                    "Part 1 is a renewal or replacement of an existing EAD, but Item 12 says "
                    "no Form I-765 was filed before."
                ),
                source=instructions_source(18, "Part 1, Item Numbers 1.b.-1.c., and Item 12"),
            )
        ]
    return []


def _formats(app: I765Application, today: date) -> list[Flag]:
    flags = []
    for path, (item, pattern, expected) in FORMATS.items():
        value = _get(app, path)
        if isinstance(value, str) and not pattern.match(value):
            flags.append(
                Flag(
                    code=FlagCode.FORMAT,
                    item=item,
                    path=path,
                    message=(
                        f"The form asks for {expected} here. Please check it against the document."
                    ),
                    source=tooltip_source(item),
                )
            )
    if app.attorney and app.attorney.uscis_online_account_number is not None:
        if not re.match(r"^[A-Za-z0-9]{12}$", app.attorney.uscis_online_account_number):
            flags.append(
                Flag(
                    code=FlagCode.FORMAT,
                    item="G-28",
                    path="attorney.uscis_online_account_number",
                    message="The form asks for 12 characters here.",
                    source="Form I-765 (edition 08/21/25), PDF field help text, attorney box",
                )
            )
    return flags


def _dates(app: I765Application, today: date) -> list[Flag]:
    a = app.applicant
    flags = []
    if a.date_of_birth > today:
        flags.append(
            Flag(
                code=FlagCode.INCONSISTENT,
                item="2.16",
                path="applicant.date_of_birth",
                message="The date of birth is in the future.",
                source=instructions_source(19, "Item Number 16"),
            )
        )
    if a.last_entry_date is not None and (
        a.last_entry_date > today or a.last_entry_date < a.date_of_birth
    ):
        flags.append(
            Flag(
                code=FlagCode.INCONSISTENT,
                item="2.22",
                path="applicant.last_entry_date",
                message="The date of last arrival is in the future or before the date of birth.",
                source=instructions_source(19, "Item Number 22"),
            )
        )
    # An expired passport is not an error. The user only gets a notice that quotes the rule.
    if a.passport_expiration_date is not None and a.passport_expiration_date < today:
        flags.append(
            Flag(
                code=FlagCode.NOTICE,
                item="2.21",
                path="applicant.passport_expiration_date",
                message=(
                    "The passport or travel document expiration date is in the past. This is "
                    'not an error: the instructions say to "enter the passport or travel '
                    "document information in the appropriate space on the application, even "
                    'if the passport or travel document is currently expired."'
                ),
                source=instructions_source(19, "Passport and Travel Document Numbers"),
            )
        )
    return flags


def _lists_and_part_6(app: I765Application, today: date) -> list[Flag]:
    a = app.applicant
    flags = []
    overflow = 0
    for item, path, values in (
        ("2.2", "applicant.other_names", a.other_names),
        ("2.14", "applicant.citizenship_countries", a.citizenship_countries),
    ):
        extra = len(values) - LIST_CAPACITY[path]
        if extra > 0:
            overflow += extra
            flags.append(
                Flag(
                    code=FlagCode.OVERFLOW,
                    item=item,
                    path=path,
                    message=f"{extra} more entries than the form has space for; they go to Part 6.",
                    source=instructions_source(17, "How To Complete Form I-765, step 2"),
                )
            )
    if len(app.additional_info) + overflow > LIST_CAPACITY["additional_info"]:
        flags.append(
            Flag(
                code=FlagCode.OVERFLOW,
                item="6",
                path="additional_info",
                message="Part 6 is full; the remaining information needs a separate sheet.",
                source=instructions_source(17, "How To Complete Form I-765, step 2"),
            )
        )
    stateless = any(c.strip().lower() == "stateless" for c in a.citizenship_countries)
    explained = any(
        e.part_number.strip() == "2" and e.item_number.strip().startswith("14")
        for e in app.additional_info
    )
    if stateless and not explained:
        flags.append(
            Flag(
                code=FlagCode.MISSING_REQUIRED,
                item="2.14",
                path="additional_info",
                message="'Stateless' requires an explanation in Part 6 for Item 14.",
                source=instructions_source(19, "Item Numbers 14.a.-14.b."),
            )
        )
    return flags


def _statement(app: I765Application, today: date) -> list[Flag]:
    s = app.statement
    flags = []
    if s.daytime_phone is None:
        flags.append(
            Flag(
                code=FlagCode.MISSING_REQUIRED,
                item="3.3",
                path="statement.daytime_phone",
                message="The applicant's daytime telephone number is required.",
                source=instructions_source(20, "Part 3, Item Numbers 1.a.-7.b."),
            )
        )
    interpreter_said = s.statement is ApplicantStatementChoice.INTERPRETER_READ
    if interpreter_said != (app.interpreter is not None):
        flags.append(
            Flag(
                code=FlagCode.INCONSISTENT,
                item="3.1.B",
                path="statement.statement",
                message="Part 3 Item 1.b and Part 4 (interpreter) do not match each other.",
                source=tooltip_source("3.1"),
            )
        )
    if (s.prepared_by_preparer is True) != (app.preparer is not None):
        flags.append(
            Flag(
                code=FlagCode.INCONSISTENT,
                item="3.2",
                path="statement.prepared_by_preparer",
                message="Part 3 Item 2 and Part 5 (preparer) do not match each other.",
                source=tooltip_source("3.2"),
            )
        )
    return flags


RULES: tuple[Callable[[I765Application, date], list[Flag]], ...] = (
    _interpreter_preparer_question,
    _eligibility,
    _legally_sensitive_answers,
    _addresses,
    _history,
    _formats,
    _dates,
    _lists_and_part_6,
    _statement,
)
