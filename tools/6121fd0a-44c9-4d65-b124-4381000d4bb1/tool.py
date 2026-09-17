from datetime import datetime, timedelta, timezone
from typing import Any

import requests

__all__ = ["will_it_rain_nyc_10065"]


_POINT_URL = "https://api.weather.gov/points/40.7650,-73.9630"
_HEADERS = {
    "Accept": "application/geo+json",
    "User-Agent": "ToolForge rain forecast for NYC 10065",
}
_RAIN_TERMS = ("rain", "drizzle", "thunderstorm")


def _get_json(url: str) -> dict[str, Any]:
    response = requests.get(url, headers=_HEADERS, timeout=15)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Weather service returned an unexpected response.")
    return data


def will_it_rain_nyc_10065(hours_ahead: int = 24) -> dict[str, Any]:
    """Check whether rain is forecast near New York City ZIP code 10065 within the next 1 to 72 hours.

    Args:
        hours_ahead: Number of hours to check, from 1 through 72. Defaults to 24.

    Returns:
        A concise rain verdict plus timing, probability, and source details from the
        U.S. National Weather Service hourly forecast.
    """
    if isinstance(hours_ahead, bool) or not isinstance(hours_ahead, int):
        raise ValueError("hours_ahead must be an integer from 1 through 72.")
    if not 1 <= hours_ahead <= 72:
        raise ValueError("hours_ahead must be from 1 through 72.")

    try:
        point_data = _get_json(_POINT_URL)
        hourly_url = point_data.get("properties", {}).get("forecastHourly")
        if not hourly_url:
            raise ValueError("The weather service did not provide an hourly forecast URL.")

        forecast_data = _get_json(hourly_url)
        periods = forecast_data.get("properties", {}).get("periods", [])
        if not isinstance(periods, list) or not periods:
            raise ValueError("The weather service did not provide hourly forecast periods.")

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours_ahead)
        checked: list[dict[str, Any]] = []
        rainy: list[dict[str, Any]] = []

        for period in periods:
            start_text = period.get("startTime")
            if not start_text:
                continue
            start = datetime.fromisoformat(start_text.replace("Z", "+00:00"))
            if start > cutoff:
                break

            end_text = period.get("endTime")
            end = (
                datetime.fromisoformat(end_text.replace("Z", "+00:00"))
                if end_text
                else start + timedelta(hours=1)
            )
            if end <= now:
                continue

            forecast = str(period.get("shortForecast", ""))
            probability = period.get("probabilityOfPrecipitation", {}).get("value")
            probability = probability if isinstance(probability, (int, float)) else None
            item = {
                "start_time": start_text,
                "forecast": forecast,
                "rain_probability_percent": probability,
                "temperature": period.get("temperature"),
                "temperature_unit": period.get("temperatureUnit"),
            }
            checked.append(item)
            if any(term in forecast.lower() for term in _RAIN_TERMS):
                rainy.append(item)

        if not checked:
            raise ValueError("No forecast hours overlapped the requested time window.")

        probabilities = [
            item["rain_probability_percent"]
            for item in rainy
            if item["rain_probability_percent"] is not None
        ]
        max_probability = max(probabilities, default=0)

        if rainy and max_probability >= 50:
            verdict = "yes"
            summary = f"Rain is likely within the next {hours_ahead} hours."
        elif rainy:
            verdict = "possible"
            summary = f"Rain is possible within the next {hours_ahead} hours."
        else:
            verdict = "no"
            summary = f"No rain is currently forecast within the next {hours_ahead} hours."

        return {
            "will_it_rain": verdict,
            "summary": summary,
            "location": "New York, NY 10065",
            "hours_ahead": hours_ahead,
            "maximum_rain_probability_percent": max_probability,
            "rainy_hours": rainy,
            "forecast_generated_at": forecast_data.get("properties", {}).get("generatedAt"),
            "source": "U.S. National Weather Service (api.weather.gov)",
        }
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not retrieve the National Weather Service forecast: {exc}") from exc
