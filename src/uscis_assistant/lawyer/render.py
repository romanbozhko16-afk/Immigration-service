"""Plain-text (Markdown) rendering of a case review, in English, for the attorney."""

from collections import defaultdict

from uscis_assistant.lawyer.review import CaseReview
from uscis_assistant.validation.flags import Flag, Severity

DISCLAIMER = (
    "Prepared by software from the applicant's own answers and automatic formal checks. "
    "It contains no legal analysis; every item below is for the attorney to assess."
)
TITLES = {
    Severity.ATTORNEY: "Requires attorney review or decision",
    Severity.BLOCKING: "Blocking: answer required before filing",
    Severity.CHECK: "Please check",
    Severity.INFO: "Information",
}


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "/").replace("\n", " ")


def _flag_lines(flags: list[Flag]) -> list[str]:
    return [
        f"- **Item {flag.item}**: {flag.message}\n  *Source: {flag.source}*"
        for flag in sorted(flags, key=lambda f: f.item)
    ]


def render_summary(review: CaseReview) -> str:
    lines = [
        f"# Case review: Form {review.form}, edition {review.edition}",
        "",
        f"Case `{review.case_id}`, status: {review.status}.",
        f"Audit log intact: {'yes' if review.audit_verified else 'NO: records were altered'}.",
        "",
        f"*{DISCLAIMER}*",
        "",
    ]

    lines += ["## Open points for the attorney", ""]
    points = []
    if review.attorney_decision is None:
        points.append(
            "- **Interpreter / preparer question (Part 3 Items 1-2, Parts 4-5): no decision "
            "recorded.** These sections are left blank until an attorney decides."
        )
    else:
        decision = review.attorney_decision
        points.append(
            f"- Interpreter / preparer question: decision **{decision.decision}** recorded "
            f"{decision.occurred_at:%Y-%m-%d %H:%M} UTC. Note: {decision.note or '(none)'}"
        )
    if review.awaiting_translation:
        points.append(
            "- Answers awaiting the applicant's English confirmation (the form cannot be built): "
            + ", ".join(f"`{p}`" for p in review.awaiting_translation)
        )
    if review.unanswered_items:
        points.append(
            f"- Interview not finished: {len(review.unanswered_items)} question(s) unanswered "
            f"(next: item {review.unanswered_items[0]}). The form cannot be built yet."
        )
    elif review.missing:
        points.append(
            "- Information still missing (the form cannot be built yet): "
            + ", ".join(f"`{p}`" for p in review.missing)
        )
    if review.machine_translated:
        points.append(
            "- English text produced by the AI model and confirmed by the applicant (please "
            "verify against the original): "
            + ", ".join(f"`{p}`" for p in review.machine_translated)
        )
    if review.declined_requests:
        points.append(
            f"- The applicant asked {len(review.declined_requests)} time(s) for legal advice; the "
            "service declined (see below)."
        )
    lines += points or ["- None."]
    lines.append("")

    grouped: dict[Severity, list[Flag]] = defaultdict(list)
    for flag in review.flags:
        grouped[flag.severity].append(flag)
    if not review.application_built:
        lines += ["## Flags", "", "Flags are produced once the form can be built (see above).", ""]
    for severity in (Severity.ATTORNEY, Severity.BLOCKING, Severity.CHECK, Severity.INFO):
        if grouped[severity]:
            lines += [f"## {TITLES[severity]}", "", *_flag_lines(grouped[severity]), ""]

    if review.declined_requests:
        lines += ["## Requests for legal advice that were declined", ""]
        for request in review.declined_requests:
            lines.append(
                f"- {request.occurred_at:%Y-%m-%d %H:%M} UTC, item {request.item}, "
                f'language {request.language}: "{_cell(request.text)}"'
            )
        lines.append("")

    lines += [
        "## Answers",
        "",
        "| Item | Question | Applicant's original | Lang | English (on the form) | Method | By |",
        "|---|---|---|---|---|---|---|",
    ]
    for answer in review.answers:
        lines.append(
            f"| {_cell(answer.item)} | {_cell(answer.question)} | {_cell(answer.original)} | "
            f"{_cell(answer.original_language)} | {_cell(answer.english)} | "
            f"{_cell(answer.method)} | {_cell(answer.entered_by)} |"
        )
    lines += [
        "",
        "Method: `same` = no translation needed; `user` = typed by a person in English; "
        "`machine` = proposed by the AI model and confirmed by the applicant; `pending` / "
        "`proposed` = not yet usable.",
        "",
    ]
    return "\n".join(lines)


def render_audit_log(review: CaseReview) -> str:
    lines = [
        f"# Audit log, case `{review.case_id}`",
        "",
        f"Intact: {'yes' if review.audit_verified else 'NO: records were altered'}.",
        "",
        "| # | UTC time | Role | Event | Item / path | Details |",
        "|---|---|---|---|---|---|",
    ]
    for entry in review.audit_log:
        details = ""
        if entry.details:
            details = "; ".join(f"{k}: {_cell(v)}" for k, v in entry.details.items())
        lines.append(
            f"| {entry.seq} | {entry.occurred_at:%Y-%m-%d %H:%M:%S} | {entry.actor_role.value} | "
            f"{entry.event_type.value} | {_cell(entry.path)} | {details} |"
        )
    return "\n".join(lines) + "\n"
