"""Tests for weather context providers."""

from waterbot.weather import WeatherContextProvider


def test_parse_open_meteo_payload():
    """Test converting Open-Meteo payloads to policy context metrics."""
    provider = WeatherContextProvider()
    payload = {
        "current": {"temperature_2m": 91.5, "precipitation": 0.01},
        "hourly": {
            "time": ["2099-01-01T00:00", "2099-01-01T01:00"],
            "precipitation": [0.1, 0.2],
            "precipitation_probability": [20, 70],
        },
    }

    context = provider._parse_open_meteo_payload(payload)

    assert context["temperature_f"] == 91.5
    assert context["current_rain_inches"] == 0.01
    assert "rain_last_24h_inches" in context
    assert "forecast_rain_next_12h_inches" in context
    assert "rain_probability_next_12h" in context
