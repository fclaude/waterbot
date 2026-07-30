"""Tests for weather context providers."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from waterbot.weather import WeatherContextProvider, _numeric_values


class TestWeatherContextProvider:
    def test_numeric_values_filters_non_numeric(self):
        assert _numeric_values({"a": 1, "b": "x", 3: 4}) == {"a": 1.0}
        assert _numeric_values(["not", "a", "dict"]) == {}

    def test_static_json_context(self, monkeypatch):
        monkeypatch.setenv("WEATHER_CONTEXT_JSON", '{"temperature_f": 90, "rain_last_24h_inches": 0.2}')
        with patch("waterbot.weather.WEATHER_PROVIDER", "none"):
            provider = WeatherContextProvider(cache_seconds=0)
            context = provider.get_context()
        assert context["temperature_f"] == 90.0
        assert context["rain_last_24h_inches"] == 0.2

    def test_static_file_context(self, tmp_path, monkeypatch):
        weather_file = tmp_path / "weather.json"
        weather_file.write_text(json.dumps({"temperature_f": 80}), encoding="utf-8")
        monkeypatch.delenv("WEATHER_CONTEXT_JSON", raising=False)
        with (
            patch("waterbot.weather.WEATHER_PROVIDER", "none"),
            patch("waterbot.weather.WEATHER_CONTEXT_FILE", str(weather_file)),
        ):
            provider = WeatherContextProvider(cache_seconds=0)
            assert provider.get_context()["temperature_f"] == 80.0

    def test_invalid_static_json_is_ignored(self, monkeypatch):
        monkeypatch.setenv("WEATHER_CONTEXT_JSON", "{not-json")
        with patch("waterbot.weather.WEATHER_PROVIDER", "none"):
            provider = WeatherContextProvider(cache_seconds=0)
            assert provider.get_context() == {}

    def test_cache_reuses_previous_context(self, monkeypatch):
        monkeypatch.setenv("WEATHER_CONTEXT_JSON", '{"temperature_f": 70}')
        with patch("waterbot.weather.WEATHER_PROVIDER", "none"):
            provider = WeatherContextProvider(cache_seconds=600)
            first = provider.get_context()
            monkeypatch.setenv("WEATHER_CONTEXT_JSON", '{"temperature_f": 99}')
            second = provider.get_context()
        assert first == second == {"temperature_f": 70.0}

    def test_unknown_provider_logs_and_returns_static(self, monkeypatch):
        monkeypatch.setenv("WEATHER_CONTEXT_JSON", '{"temperature_f": 71}')
        with patch("waterbot.weather.WEATHER_PROVIDER", "mystery"):
            provider = WeatherContextProvider(cache_seconds=0)
            assert provider.get_context()["temperature_f"] == 71.0

    def test_open_meteo_requires_coordinates(self):
        with (
            patch("waterbot.weather.WEATHER_PROVIDER", "open_meteo"),
            patch("waterbot.weather.WEATHER_LATITUDE", None),
            patch("waterbot.weather.WEATHER_LONGITUDE", None),
        ):
            provider = WeatherContextProvider(cache_seconds=0)
            assert provider.get_context() == {}

    def test_open_meteo_success(self):
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        times = [
            (now - timedelta(hours=1)).isoformat(timespec="minutes"),
            now.isoformat(timespec="minutes"),
            (now + timedelta(hours=1)).isoformat(timespec="minutes"),
        ]
        payload = {
            "current": {"temperature_2m": 88.5, "precipitation": 0.1},
            "hourly": {
                "time": times,
                "precipitation": [0.2, 0.0, 0.3],
                "precipitation_probability": [10, 20, 40],
            },
        }
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = payload

        with (
            patch("waterbot.weather.WEATHER_PROVIDER", "open_meteo"),
            patch("waterbot.weather.WEATHER_LATITUDE", "37.7"),
            patch("waterbot.weather.WEATHER_LONGITUDE", "-122.4"),
            patch("requests.get", return_value=mock_response) as mock_get,
        ):
            provider = WeatherContextProvider(cache_seconds=0)
            context = provider.get_context()

        mock_get.assert_called_once()
        assert context["temperature_f"] == 88.5
        assert context["current_rain_inches"] == 0.1
        assert context["rain_last_24h_inches"] >= 0.2
        assert context["forecast_rain_next_12h_inches"] >= 0.3
        assert context["rain_probability_next_12h"] == 40.0

    def test_open_meteo_request_failure(self):
        with (
            patch("waterbot.weather.WEATHER_PROVIDER", "open_meteo"),
            patch("waterbot.weather.WEATHER_LATITUDE", "37.7"),
            patch("waterbot.weather.WEATHER_LONGITUDE", "-122.4"),
            patch("requests.get", side_effect=RuntimeError("network")),
        ):
            provider = WeatherContextProvider(cache_seconds=0)
            assert provider.get_context() == {}

    def test_parse_open_meteo_skips_bad_timestamps(self):
        provider = WeatherContextProvider(cache_seconds=0)
        context = provider._parse_open_meteo_payload(
            {
                "hourly": {
                    "time": ["not-a-time"],
                    "precipitation": [1.0],
                    "precipitation_probability": [50],
                }
            }
        )
        assert context == {
            "rain_last_24h_inches": 0.0,
            "forecast_rain_next_12h_inches": 0.0,
            "rain_probability_next_12h": 0.0,
        }
