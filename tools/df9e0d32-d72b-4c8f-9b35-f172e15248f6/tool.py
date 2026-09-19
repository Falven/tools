from csv_validator import validate_csv_text

__all__ = ["validate_csv"]


def validate_csv(csv_text: str, required_columns: list[str]) -> dict:
    """Validate CSV text whose first record is a header.

    Pass the complete CSV document in ``csv_text`` and the exact header names
    that must exist in ``required_columns``. The returned JSON-compatible
    report lists missing columns, whitespace-only or empty data cells,
    duplicate data rows, inconsistent row widths, CSV parsing errors, and
    summary counts. Row and column indexes are one-based; duplicate comparison
    uses parsed cell values exactly, while empty checks ignore surrounding
    whitespace. This operation has no side effects.
    """
    if not isinstance(csv_text, str):
        raise TypeError("csv_text must be a string")
    if not isinstance(required_columns, list) or not all(
        isinstance(name, str) for name in required_columns
    ):
        raise TypeError("required_columns must be a list of strings")

    return validate_csv_text(csv_text, required_columns)
