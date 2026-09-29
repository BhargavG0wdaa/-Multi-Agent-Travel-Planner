"""
weather.py — real daily forecasts from Open-Meteo (free, no key).

Open-Meteo forecasts at most 16 days ahead; dates past that are simply left
out of the result, and the caller decides what "no forecast" means.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta

from travel_planner.services.http import get_json

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_HORIZON_DAYS = 16

# A day's weather code is its WORST hour, so a short shower would flag the whole
# day. Only call it rain if the chance of rain is also at least this high.
RAIN_CHANCE_THRESHOLD = 50


@dataclass(frozen=True)
class DailyWeather:
    condition: str              # sunny | cloudy | rain | storm | snow | unknown
    high_c: int | None
    rain_chance: int | None     # max % chance of precipitation that day


def condition_from_wmo(code: int | None, rain_chance: int | None) -> str:
    """Map a WMO weather code (the standard Open-Meteo uses) to our conditions."""
    if code is None:
        return "unknown"
    if code >= 95:
        return "storm"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "rain" if (rain_chance or 0) >= RAIN_CHANCE_THRESHOLD else "cloudy"
    if code in (0, 1):
        return "sunny"
    if code in (2, 3, 45, 48):
        return "cloudy"
    return "unknown"


def daily_forecast(lat: float, lon: float, start: date, end: date) -> dict[date, DailyWeather]:
    """Forecast for each date in [start, end] that is within the forecast horizon."""
    last = min(end, date.today() + timedelta(days=FORECAST_HORIZON_DAYS - 1))
    if start > last:
        return {}
    data = get_json(FORECAST_URL, {
        "latitude": lat,
        "longitude": lon,
        "daily": "weather_code,temperature_2m_max,precipitation_probability_max",
        "timezone": "auto",                 # dates in the destination's local time
        "start_date": start.isoformat(),
        "end_date": last.isoformat(),
    })
    d = data["daily"]
    out = {}
    for day, code, high, chance in zip(d["time"], d["weather_code"],
                                       d["temperature_2m_max"], d["precipitation_probability_max"]):
        out[date.fromisoformat(day)] = DailyWeather(
            condition=condition_from_wmo(code, chance),
            high_c=round(high) if high is not None else None,
            rain_chance=chance,
        )
    return out
