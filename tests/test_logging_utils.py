import logging

import pytest

from uscis_assistant.logging_utils import REDACTED, RedactingFormatter, redact

# All values below are fictitious test data.


@pytest.mark.parametrize(
    "sensitive",
    [
        "A123456789",
        "A-123-456-789",
        "a12345678",
        "123-45-6789",
        "IOE0912345678",
        "FX1234567",
        "+380 67 123 4567",
        "(555) 123-4567",
        "12345678901",
        "jane.doe@example.com",
    ],
)
def test_redacts_identifiers(sensitive):
    out = redact(f"value={sensitive} end")
    assert sensitive not in out
    assert REDACTED in out


@pytest.mark.parametrize(
    "safe",
    [
        "2026-10-17 18:07:20,123 INFO app: case created",
        "Form I-765 edition 09/15/26",
        "HTTP 200 in 35 ms",
    ],
)
def test_keeps_ordinary_log_text(safe):
    assert redact(safe) == safe


def _format(record: logging.LogRecord) -> str:
    return RedactingFormatter("%(asctime)s %(message)s").format(record)


def test_formatter_redacts_interpolated_args():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "lookup %s", ("A123456789",), None)
    out = _format(record)
    assert "A123456789" not in out
    assert "lookup" in out


def test_formatter_redacts_tracebacks():
    try:
        raise ValueError("bad A-number A987654321")
    except ValueError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())
    out = _format(record)
    assert "A987654321" not in out
    assert "ValueError" in out
