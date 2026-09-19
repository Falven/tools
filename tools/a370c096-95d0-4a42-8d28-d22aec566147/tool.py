from __future__ import annotations

from typing import Any

from csv_validator import validate_csv_text

__all__ = ["validate_csv"]


def validate_csv(
    csv_text: str,
    required_columns: list[str],
    delimiter: str = ",",
) -> dict[str, Any]:
    """Validate CSV text and return a JSON-compatible report.

    Pass the complete CSV content and the column names that must appear in its
    first row. ``delimiter`` defaults to a comma and must be one character.
    Values containing only whitespace count as empty. Data rows are compared
    exactly for duplicates, including their field order and whitespace.

    The result contains ``valid``, the parsed header, summary counts, missing
    required columns, empty cell locations, duplicate row groups, inconsistent
    row-width details, and a parse error when the CSV is malformed. Reported
    row numbers are one-based and include the header as row 1. The duplicate
    row count counts repeated occurrences after the first row in each group.
    This tool only analyzes the supplied text and has no external side effects.
    """
    return validate_csv_text(csv_text, required_columns, delimiter)
