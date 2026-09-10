from datetime import datetime, timezone
from typing import Any, Literal

import requests

__all__ = ["compare_new_york_miami_weather"]


def compare_new_york_miami_weather(
    units: Literal["imperial", "metric"] = "imperial",
) -> dict[str, Any]:
    """Compare current weather and today's forecast for New York City and Miami.

    Returns temperatures, feels-like temperatures, conditions, humidity, wind,
    today's highs/lows and maximum precipitation probabilities, and differences
    between the cities. Imperial uses Fahrenheit and mph; metric uses Celsius
    and km/h. Times are local to each city, with a UTC retrieval timestamp.
    Uses Open-Meteo model-based current estimates and forecasts, not direct
    station observations. No API key is needed for its non-commercial endpoint.
    """
    if units not in ("imperial", "metric"):
        return {
            "status": "error",
            "error": "units must be 'imperial' or 'metric'.",
        }

    source = {
        "name": "Open-Meteo",
        "url": "https://open-meteo.com/",
        "data_type": "Model-based current estimates and forecasts",
        "license": "CC BY 4.0",
        "usage_note": "The public API is for non-commercial use.",
    }
    params = {
        "latitude": "40.7128,25.7617",
        "longitude": "-74.0060,-80.1918",
        "current": (
            "temperature_2m,apparent_temperature,relative_humidity_2m,"
            "weather_code,wind_speed_10m"
        ),
        "daily": (
            "temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max"
        ),
        "temperature_unit": "fahrenheit" if units == "imperial" else "celsius",
        "wind_speed_unit": "mph" if units == "imperial" else "kmh",
        "timezone": "America/New_York",
        "forecast_days": "1",
    }
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
            timeout=(5, 20),
        )
        response.raise_for_status()
    except requests.Timeout:
        return {
            "status": "error",
            "error": "The weather provider timed out. Please try again.",
            "source": source,
        }
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        return {
            "status": "error",
            "error": "The weather provider returned an HTTP error.",
            "http_status": status,
            "source": source,
        }
    except requests.RequestException:
        return {
            "status": "error",
            "error": "Unable to connect to the weather provider. Please try again.",
            "source": source,
        }

    conditions = {
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
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
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
    locations = [
        ("New York City", 40.7128, -74.0060),
        ("Miami", 25.7617, -80.1918),
    ]
    cities: list[dict[str, Any]] = []
    try:
        payload = response.json()
        if not isinstance(payload, list) or len(payload) != len(locations):
            raise ValueError("Expected weather for both cities.")
        for (name, latitude, longitude), data in zip(locations, payload):
            current = data["current"]
            daily = data["daily"]
            current_units = data["current_units"]
            daily_units = data["daily_units"]
            code = current["weather_code"]
            cities.append(
                {
                    "city": name,
                    "requested_coordinates": {
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                    "timezone": data["timezone"],
                    "utc_offset_seconds": data["utc_offset_seconds"],
                    "current": {
                        "time_local": current["time"],
                        "temperature": current["temperature_2m"],
                        "feels_like": current["apparent_temperature"],
                        "temperature_unit": current_units["temperature_2m"],
                        "humidity_percent": current["relative_humidity_2m"],
                        "wind_speed": current["wind_speed_10m"],
                        "wind_speed_unit": current_units["wind_speed_10m"],
                        "weather_code": code,
                        "conditions": conditions.get(code, "Unknown"),
                    },
                    "today": {
                        "date_local": daily["time"][0],
                        "high": daily["temperature_2m_max"][0],
                        "low": daily["temperature_2m_min"][0],
                        "temperature_unit": daily_units["temperature_2m_max"],
                        "max_precipitation_probability_percent": (
                            daily["precipitation_probability_max"][0]
                        ),
                    },
                }
            )
    except (ValueError, KeyError, TypeError, IndexError):
        return {
            "status": "error",
            "error": "The weather provider returned invalid or incomplete data.",
            "source": source,
        }

    new_york, miami = cities

    def difference(section: str, field: str) -> float | None:
        ny_value = new_york[section][field]
        miami_value = miami[section][field]
        if (
            isinstance(ny_value, (int, float))
            and not isinstance(ny_value, bool)
            and isinstance(miami_value, (int, float))
            and not isinstance(miami_value, bool)
        ):
            return round(miami_value - ny_value, 2)
        return None

    temperature_difference = difference("current", "temperature")
    warmer_city = None
    if temperature_difference is not None:
        warmer_city = (
            "Miami" if temperature_difference > 0 else
            "New York City" if temperature_difference < 0 else
            "Neither; temperatures are equal"
        )

    return {
        "status": "ok",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "units": units,
        "source": source,
        "cities": cities,
        "comparison": {
            "difference_convention": "Miami minus New York City",
            "temperature_unit": miami["current"]["temperature_unit"],
            "wind_speed_unit": miami["current"]["wind_speed_unit"],
            "warmer_city": warmer_city,
            "current_temperature_difference": temperature_difference,
            "feels_like_difference": difference("current", "feels_like"),
            "humidity_difference_percentage_points": difference(
                "current", "humidity_percent"
            ),
            "wind_speed_difference": difference("current", "wind_speed"),
            "today_high_difference": difference("today", "high"),
            "today_low_difference": difference("today", "low"),
            "today_max_precipitation_probability_difference_percentage_points": (
                difference("today", "max_precipitation_probability_percent")
            ),
            "current_times_match": (
                new_york["current"]["time_local"] == miami["current"]["time_local"]
            ),
        },
    }
