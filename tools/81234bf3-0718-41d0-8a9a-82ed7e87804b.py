from typing import Any

import requests

__all__ = ["get_nyc_weather"]


_WEATHER_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def get_nyc_weather() -> dict[str, Any]:
    """Fetch the current weather and today's forecast for New York City."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "precipitation,weather_code,cloud_cover,wind_speed_10m,"
            "wind_direction_10m"
        ),
        "daily": (
            "temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max,sunrise,sunset"
        ),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "America/New_York",
        "forecast_days": 1,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError("Unable to fetch NYC weather right now.") from exc

    current = data.get("current", {})
    current_units = data.get("current_units", {})
    daily = data.get("daily", {})
    daily_units = data.get("daily_units", {})
    weather_code = current.get("weather_code")

    def first(values: Any) -> Any:
        return values[0] if isinstance(values, list) and values else None

    return {
        "location": "New York City, NY",
        "coordinates": {
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
        },
        "timezone": data.get("timezone", "America/New_York"),
        "observed_at": current.get("time"),
        "current": {
            "conditions": _WEATHER_DESCRIPTIONS.get(
                weather_code, f"Weather code {weather_code}"
            ),
            "temperature": current.get("temperature_2m"),
            "temperature_unit": current_units.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "relative_humidity": current.get("relative_humidity_2m"),
            "humidity_unit": current_units.get("relative_humidity_2m"),
            "precipitation": current.get("precipitation"),
            "precipitation_unit": current_units.get("precipitation"),
            "cloud_cover": current.get("cloud_cover"),
            "cloud_cover_unit": current_units.get("cloud_cover"),
            "wind_speed": current.get("wind_speed_10m"),
            "wind_speed_unit": current_units.get("wind_speed_10m"),
            "wind_direction": current.get("wind_direction_10m"),
            "wind_direction_unit": current_units.get("wind_direction_10m"),
        },
        "today": {
            "date": first(daily.get("time")),
            "high_temperature": first(daily.get("temperature_2m_max")),
            "low_temperature": first(daily.get("temperature_2m_min")),
            "temperature_unit": daily_units.get("temperature_2m_max"),
            "max_precipitation_probability": first(
                daily.get("precipitation_probability_max")
            ),
            "precipitation_probability_unit": daily_units.get(
                "precipitation_probability_max"
            ),
            "sunrise": first(daily.get("sunrise")),
            "sunset": first(daily.get("sunset")),
        },
        "source": "Open-Meteo",
    }
