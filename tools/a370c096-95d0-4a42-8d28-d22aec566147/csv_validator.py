"""CSV validation logic implemented with Python's standard library."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from typing import Any


def _empty_report(required_columns: list[str]) -> dict[str, Any]:
    """Create a report with a stable shape for empty or unparseable input."""
    return {
        "valid": False,
        "summary": {
            "data_row_count": 0,
            "header_column_count": 0,
            "required_column_count": len(required_columns),
            "missing_column_count": 0,
            "empty_value_count": 0,
            "rows_with_empty_values_count": 0,
            "duplicate_row_count": 0,
            "duplicate_group_count": 0,
            "inconsistent_row_width_count": 0,
        },
        "header": [],
        "missing_columns": [],
        "empty_values": [],
        "duplicate_rows": [],
        "inconsistent_row_widths": [],
        "parse_error": None,
    }


def validate_csv_text(
    csv_text: str,
    required_columns: list[str],
    delimiter: str = ",",
) -> dict[str, Any]:
    """Validate CSV text and return a JSON-serializable issue report."""
    if not isinstance(csv_text, str):
        raise TypeError("csv_text must be a string")
    if not isinstance(required_columns, list) or not all(
        isinstance(column, str) for column in required_columns
    ):
        raise TypeError("required_columns must be a list of strings")
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        raise ValueError("delimiter must be exactly one character")

    # Repeated required names do not represent additional requirements.
    unique_required_columns = list(dict.fromkeys(required_columns))
    report = _empty_report(unique_required_columns)

    try:
        reader = csv.reader(
            io.StringIO(csv_text, newline=""),
            delimiter=delimiter,
            strict=True,
        )
        rows = list(reader)
    except csv.Error as exc:
        report["missing_columns"] = unique_required_columns
        report["summary"]["missing_column_count"] = len(unique_required_columns)
        report["parse_error"] = {
            "message": str(exc),
            "line": getattr(reader, "line_num", None),
        }
        return report

    if not rows:
        report["missing_columns"] = unique_required_columns
        report["summary"]["missing_column_count"] = len(unique_required_columns)
        return report

    header = rows[0]
    data_rows = rows[1:]
    expected_width = len(header)
    header_names = set(header)
    missing_columns = [
        column for column in unique_required_columns if column not in header_names
    ]

    empty_values: list[dict[str, Any]] = []
    rows_with_empty_values: set[int] = set()
    inconsistent_widths: list[dict[str, int]] = []
    occurrences: dict[tuple[str, ...], list[int]] = defaultdict(list)

    for csv_row_number, row in enumerate(data_rows, start=2):
        if len(row) != expected_width:
            inconsistent_widths.append(
                {
                    "row": csv_row_number,
                    "expected_width": expected_width,
                    "actual_width": len(row),
                }
            )

        for column_index, value in enumerate(row, start=1):
            if value.strip() == "":
                rows_with_empty_values.add(csv_row_number)
                empty_values.append(
                    {
                        "row": csv_row_number,
                        "column_index": column_index,
                        "column_name": (
                            header[column_index - 1]
                            if column_index <= expected_width
                            else None
                        ),
                    }
                )

        occurrences[tuple(row)].append(csv_row_number)

    duplicate_groups = [
        {"rows": row_numbers, "values": list(values)}
        for values, row_numbers in occurrences.items()
        if len(row_numbers) > 1
    ]
    duplicate_row_count = sum(len(group["rows"]) - 1 for group in duplicate_groups)

    report.update(
        {
            "header": header,
            "missing_columns": missing_columns,
            "empty_values": empty_values,
            "duplicate_rows": duplicate_groups,
            "inconsistent_row_widths": inconsistent_widths,
        }
    )
    report["summary"].update(
        {
            "data_row_count": len(data_rows),
            "header_column_count": expected_width,
            "missing_column_count": len(missing_columns),
            "empty_value_count": len(empty_values),
            "rows_with_empty_values_count": len(rows_with_empty_values),
            "duplicate_row_count": duplicate_row_count,
            "duplicate_group_count": len(duplicate_groups),
            "inconsistent_row_width_count": len(inconsistent_widths),
        }
    )
    report["valid"] = not any(
        (
            missing_columns,
            empty_values,
            duplicate_groups,
            inconsistent_widths,
        )
    )
    return report
