"""Logging that keeps personal data out of log output.

The primary rule is that code never logs answers, documents, prompts, or model output.
Redaction here is a safety net for identifiers that slip into messages or exception
text by mistake. It cannot detect names or free-text stories, which is why the
primary rule exists.
"""

import logging
import re

REDACTED = "[REDACTED]"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Email addresses.
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    # USCIS receipt numbers, e.g. IOE0912345678.
    re.compile(r"\b[A-Z]{3}\d{10}\b"),
    # A-Numbers: "A" followed by 7-9 digits, optionally grouped (A-123-456-789).
    re.compile(r"\bA[- ]?\d{3}[- ]?\d{3}[- ]?\d{1,3}\b", re.IGNORECASE),
    # SSNs.
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    # Passport-style document numbers: 1-3 letters followed by 6-10 digits.
    re.compile(r"\b[A-Z]{1,3}\d{6,10}\b"),
    # Phone numbers: international (+380 67 123 4567) and US (555) 123-4567 formats.
    # Kept narrow so that timestamps and dates in log lines are not redacted.
    re.compile(r"\+\d[\d\s-]{7,}\d"),
    re.compile(r"\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"),
    # Any remaining run of 6+ digits (I-94 numbers, USCIS online account numbers, ...).
    re.compile(r"\d{6,}"),
)


def redact(text: str) -> str:
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


class RedactingFormatter(logging.Formatter):
    """Formats the record normally, then redacts the full output, tracebacks included."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
