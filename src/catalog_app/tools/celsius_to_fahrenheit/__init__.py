"""A stateless Celsius-to-Fahrenheit converter with an interactive MCP App."""

from __future__ import annotations

from decimal import Decimal, localcontext
from functools import lru_cache
import math
from pathlib import Path
from typing import Annotated, TypedDict

from pydantic import Field

RESOURCE_URI = "ui://celsius-to-fahrenheit/app.html"
ASSETS = Path(__file__).resolve().parent
Celsius = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False, description="Celsius temperature; a finite number, including negatives and decimals."),
]


class Conversion(TypedDict):
    celsius: float
    fahrenheit: float
    formula: str
    result: str


def _number(value: float) -> str:
    text = str(value)
    return text[:-2] if text.endswith(".0") else text


def _convert(celsius: float) -> Conversion:
    # Decimal arithmetic avoids distracting results such as 98.60000000000001
    # for common decimal inputs. The MCP number contract is still float64.
    with localcontext() as context:
        context.prec = 32
        fahrenheit = float(Decimal(str(celsius)) * Decimal("1.8") + Decimal("32"))
    if not math.isfinite(fahrenheit):
        raise ValueError("The Fahrenheit result is outside the supported numeric range. Try a smaller magnitude.")
    celsius = 0.0 if celsius == 0 else celsius
    fahrenheit = 0.0 if fahrenheit == 0 else fahrenheit
    return {
        "celsius": celsius,
        "fahrenheit": fahrenheit,
        "formula": "°F = °C × 9/5 + 32",
        "result": f"{_number(celsius)} °C = {_number(fahrenheit)} °F",
    }


@lru_cache(maxsize=1)
def _app_html() -> str:
    html = (ASSETS / "app.html").read_text(encoding="utf-8")
    script = (ASSETS / "app.js").read_text(encoding="utf-8")
    if html.count("<!-- app.js -->") != 1:
        raise ValueError("Converter HTML must have exactly one script insertion marker.")
    return html.replace("<!-- app.js -->", f'<script type="module">\n{script}\n</script>')


def celsius_to_fahrenheit(celsius: Celsius = 0.0) -> Conversion:
    """Convert Celsius to Fahrenheit and open an interactive temperature converter.

    celsius is a finite number, defaulting to 0. Negative and decimal values
    are supported. Returns celsius, fahrenheit, the formula, and a readable
    result for clients without App rendering. Uses °F = °C × 9/5 + 32;
    rejects nonnumeric/nonfinite inputs and results outside float64 range.
    This is a mathematical conversion, with no absolute-zero restriction.
    No state, files, or external services are read or written by conversion.
    """
    return _convert(celsius)


def celsius_to_fahrenheit_app() -> str:
    """Serve the converter with the pinned official MCP Apps browser SDK."""
    return _app_html()
