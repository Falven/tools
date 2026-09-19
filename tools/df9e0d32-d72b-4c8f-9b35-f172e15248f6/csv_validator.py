"""CSV validation logic implemented with Python's standard library."""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from typing import Any


def validate_csv_text(
    csv_text: str,
    required_columns: Sequence[str],
) -> dict[str, Any]:
    """Validate header-based CSV text and return a JSON-serializable report."""
    required = list(dict.fromkeys(required_columns))
    rows: list[list[str]] = []
    parse_errors: list[dict[str, Any]] = []

    reader = csv.reader(io.StringIO(csv_text, newline=""), strict=True)
    try:
        rows = list(reader)
    except csv.Error as exc:
        parse_errors.append(
            {
                "line": reader.line_num,
                "message": str(exc),
            }
        )

    header = rows[0] if rows else []
    data_rows = rows[1:] if rows else []
    expected_width = len(header)
    missing_columns = [name for name in required if name not in header]

    empty_values: list[dict[str, Any]] = []
    inconsistent_widths: list[dict[str, int]] = []
    duplicate_rows: list[dict[str, Any]] = []
    first_seen: dict[tuple[str, ...], int] = {}

    for row_number, row in enumerate(data_rows, start=2):
        if len(row) != expected_width:
            inconsistent_widths.append(
                {
                    "row": row_number,
                    "expected_width": expected_width,
                    "actual_width": len(row),
                }
            )

        for column_index, value in enumerate(row, start=1):
            if value.strip() == "":
                empty_values.append(
                    {
                        "row": row_number,
                        "column_index": column_index,
                        "column": (
                            header[column_index - 1]
                            if column_index <= expected_width
                            else None
                        ),
                    }
                )

        row_key = tuple(row)
        if row_key in first_seen:
            duplicate_rows.append(
                {
                    "row": row_number,
                    "duplicate_of": first_seen[row_key],
                    "values": row,
                }
            )
        else:
            first_seen[row_key] = row_number

    duplicate_groups = len({item["duplicate_of"] for item in duplicate_rows})
    summary = {
        "total_records": len(rows),
        "data_rows": len(data_rows),
        "column_count": expected_width,
        "required_column_count": len(required),
        "missing_column_count": len(missing_columns),
        "empty_value_count": len(empty_values),
        "duplicate_row_count": len(duplicate_rows),
        "duplicate_group_count": duplicate_groups,
        "inconsistent_row_count": len(inconsistent_widths),
        "parse_error_count": len(parse_errors),
    }

    return {
        "valid": not any(
            (
                missing_columns,
                empty_values,
                duplicate_rows,
                inconsistent_widths,
                parse_errors,
            )
        ),
        "header": header,
        "missing_columns": missing_columns,
        "empty_values": empty_values,
        "duplicate_rows": duplicate_rows,
        "inconsistent_row_widths": inconsistent_widths,
        "parse_errors": parse_errors,
        "summary": summary,
    }
