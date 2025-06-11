from unittest.mock import MagicMock, patch

import pytest

from waterbot.gpio.interface import EmulationGPIO, HardwareGPIO, MockGPIO


class TestEmulationGPIO:
    """Test cases for EmulationGPIO"""

    def test_setup_pin(self):
        gpio = EmulationGPIO()
        gpio.setup(17, "OUT")

        assert 17 in gpio.setup_pins
        assert gpio.setup_pins[17] == "OUT"
        assert gpio.pin_states[17] is False

    def test_output_pin_value(self):
        gpio = EmulationGPIO()
        gpio.setup(17, "OUT")

        gpio.output(17, True)
        assert gpio.get_pin_state(17) is True

        gpio.output(17, False)
        assert gpio.get_pin_state(17) is False

    def test_output_without_setup_raises_error(self):
        gpio = EmulationGPIO()

        with pytest.raises(RuntimeError, match="Pin 17 not setup"):
            gpio.output(17, True)

    def test_cleanup(self):
        gpio = EmulationGPIO()
        gpio.setup(17, "OUT")
        gpio.output(17, True)

        gpio.cleanup()

        assert len(gpio.pin_states) == 0
        assert len(gpio.setup_pins) == 0


class TestMockGPIO:
    """Test cases for MockGPIO"""

    def test_setup_tracking(self):
        gpio = MockGPIO()
        gpio.setup(17, "OUT")
        gpio.setup(18, "IN")

        assert len(gpio.setup_calls) == 2
        assert (17, "OUT") in gpio.setup_calls
        assert (18, "IN") in gpio.setup_calls

    def test_output_tracking(self):
        gpio = MockGPIO()
        gpio.setup(17, "OUT")
        gpio.output(17, True)
        gpio.output(17, False)

        assert len(gpio.output_calls) == 2
        assert (17, True) in gpio.output_calls
        assert (17, False) in gpio.output_calls

    def test_pin_state_tracking(self):
        gpio = MockGPIO()
        gpio.setup(17, "OUT")

        gpio.output(17, True)
        assert gpio.get_pin_state(17) is True

        gpio.output(17, False)
        assert gpio.get_pin_state(17) is False

    def test_cleanup_tracking(self):
        gpio = MockGPIO()
        gpio.setup(17, "OUT")
        gpio.output(17, True)

        gpio.cleanup()

        assert gpio.cleanup_called is True
        assert len(gpio.pin_states) == 0


class TestHardwareGPIO:
    """Test cases for HardwareGPIO"""

    def test_hardware_gpio_initialization(self):
        mock_gpio = MagicMock()

        # Mock the entire RPi module and make sure RPi.GPIO returns our mock
        mock_rpi = MagicMock()
        mock_rpi.GPIO = mock_gpio

        with patch.dict("sys.modules", {"RPi": mock_rpi, "RPi.GPIO": mock_gpio}):
            gpio = HardwareGPIO()

            # The actual GPIO object stored should be our mock
            assert gpio.GPIO == mock_gpio
            mock_gpio.setmode.assert_called_once_with(mock_gpio.BCM)
            mock_gpio.setwarnings.assert_called_once_with(False)

    def test_setup_pin(self):
        mock_gpio = MagicMock()
        mock_rpi = MagicMock()
        mock_rpi.GPIO = mock_gpio

        with patch.dict("sys.modules", {"RPi": mock_rpi, "RPi.GPIO": mock_gpio}):
            gpio = HardwareGPIO()
            gpio.setup(17, "OUT")

            mock_gpio.setup.assert_called_once_with(17, mock_gpio.OUT)

    def test_output_pin_value(self):
        mock_gpio = MagicMock()
        mock_rpi = MagicMock()
        mock_rpi.GPIO = mock_gpio

        with patch.dict("sys.modules", {"RPi": mock_rpi, "RPi.GPIO": mock_gpio}):
            gpio = HardwareGPIO()

            gpio.output(17, True)
            mock_gpio.output.assert_called_with(17, mock_gpio.HIGH)

            gpio.output(17, False)
            mock_gpio.output.assert_called_with(17, mock_gpio.LOW)

    def test_cleanup(self):
        mock_gpio = MagicMock()
        mock_rpi = MagicMock()
        mock_rpi.GPIO = mock_gpio

        with patch.dict("sys.modules", {"RPi": mock_rpi, "RPi.GPIO": mock_gpio}):
            gpio = HardwareGPIO()
            gpio.cleanup()

            mock_gpio.cleanup.assert_called_once()

    def test_hardware_gpio_import_error(self):
        # Simulate ImportError by removing RPi from sys.modules
        with patch.dict("sys.modules", {}, clear=True):
            with patch(
                "builtins.__import__", side_effect=ImportError("No module named 'RPi'")
            ):
                with pytest.raises(RuntimeError, match="RPi.GPIO not available"):
                    HardwareGPIO()
