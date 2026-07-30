"""Weather context providers for schedule policies."""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from .config import (
    WEATHER_CONTEXT_FILE,
    WEATHER_LATITUDE,
    WEATHER_LONGITUDE,
    WEATHER_PROVIDER,
    WEATHER_REQUEST_TIMEOUT,
)

logger = logging.getLogger("waterbot.weather")


class WeatherContextProvider:
    """Provide weather metrics used by flexible schedule policies."""

    def __init__(self, cache_seconds: int = 600) -> None:
        """Initialize the provider."""
        self.cache_seconds = cache_seconds
        self._cached_context: Dict[str, float] = {}
        self._cached_at: Optional[datetime] = None

    def get_context(self) -> Dict[str, float]:
        """Return current weather context metrics."""
        now = datetime.now()
        if self._cached_at and now - self._cached_at < timedelta(seconds=self.cache_seconds):
            return dict(self._cached_context)

        context: Dict[str, float] = {}
        context.update(self._load_static_context())

        if WEATHER_PROVIDER == "open_meteo":
            context.update(self._load_open_meteo_context())
        elif WEATHER_PROVIDER not in {"none", ""}:
            logger.warning("Unknown WEATHER_PROVIDER '%s'", WEATHER_PROVIDER)

        self._cached_context = context
        self._cached_at = now
        return dict(context)

    def _load_static_context(self) -> Dict[str, float]:
        """Load manually supplied weather context from env/file."""
        context: Dict[str, float] = {}

        raw_json = os.getenv("WEATHER_CONTEXT_JSON")
        if raw_json:
            try:
                context.update(_numeric_values(json.loads(raw_json)))
            except json.JSONDecodeError as exc:
                logger.warning("Invalid WEATHER_CONTEXT_JSON: %s", exc)

        if WEATHER_CONTEXT_FILE and os.path.exists(WEATHER_CONTEXT_FILE):
            try:
                with open(WEATHER_CONTEXT_FILE, "r") as file_handle:
                    context.update(_numeric_values(json.load(file_handle)))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Could not load WEATHER_CONTEXT_FILE '%s': %s", WEATHER_CONTEXT_FILE, exc)

        return context

    def _load_open_meteo_context(self) -> Dict[str, float]:
        """Load weather metrics from Open-Meteo."""
        if not WEATHER_LATITUDE or not WEATHER_LONGITUDE:
            logger.warning("WEATHER_LATITUDE and WEATHER_LONGITUDE are required for open_meteo")
            return {}

        params: Dict[str, str] = {
            "latitude": WEATHER_LATITUDE,
            "longitude": WEATHER_LONGITUDE,
            "current": "temperature_2m,precipitation",
            "hourly": "temperature_2m,precipitation,precipitation_probability",
            "temperature_unit": "fahrenheit",
            "precipitation_unit": "inch",
            "timezone": "auto",
            "past_days": "1",
            "forecast_days": "2",
        }

        try:
            import requests

            response = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params=params,
                timeout=WEATHER_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except ImportError:
            logger.warning("requests is required for WEATHER_PROVIDER=open_meteo")
            return {}
        except Exception as exc:
            logger.warning("Open-Meteo request failed: %s", exc)
            return {}

        return self._parse_open_meteo_payload(payload)

    def _parse_open_meteo_payload(self, payload: Dict[str, Any]) -> Dict[str, float]:
        """Convert Open-Meteo payload into WaterBot policy metrics."""
        context: Dict[str, float] = {}

        current = payload.get("current") or {}
        if "temperature_2m" in current:
            context["temperature_f"] = float(current["temperature_2m"])
        if "precipitation" in current:
            context["current_rain_inches"] = float(current["precipitation"])

        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        precipitation = hourly.get("precipitation") or []
        probabilities = hourly.get("precipitation_probability") or []

        if times and precipitation:
            now = datetime.now()
            rain_last_24h = 0.0
            rain_next_12h = 0.0
            probability_next_12h = 0.0

            for index, time_value in enumerate(times):
                try:
                    hour = datetime.fromisoformat(time_value)
                except ValueError:
                    continue

                if index < len(precipitation):
                    rain = float(precipitation[index] or 0)
                else:
                    rain = 0.0

                if now - timedelta(hours=24) <= hour <= now:
                    rain_last_24h += rain
                if now <= hour <= now + timedelta(hours=12):
                    rain_next_12h += rain
                    if index < len(probabilities) and probabilities[index] is not None:
                        probability_next_12h = max(probability_next_12h, float(probabilities[index]))

            context["rain_last_24h_inches"] = rain_last_24h
            context["forecast_rain_next_12h_inches"] = rain_next_12h
            context["rain_probability_next_12h"] = probability_next_12h

        return context


def _numeric_values(data: Any) -> Dict[str, float]:
    """Return numeric key/value pairs from an arbitrary mapping."""
    if not isinstance(data, dict):
        return {}

    values: Dict[str, float] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, (int, float)):
            values[key] = float(value)
    return values
