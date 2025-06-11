"""Tests for GPIO handler functionality."""

from unittest.mock import Mock, patch

from waterbot.gpio.handler import DeviceController
from waterbot.gpio.interface import MockGPIO


class TestDeviceController:
    """Test cases for DeviceController."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_gpio = MockGPIO()

        # Mock DEVICE_TO_PIN configuration
        self.device_config = {"pump": 17, "light": 18, "fan": 27}

        # Patch DEVICE_TO_PIN before creating controller
        self.patcher = patch("waterbot.gpio.handler.DEVICE_TO_PIN", self.device_config)
        self.patcher.start()

        self.controller = DeviceController(self.mock_gpio)

    def teardown_method(self):
        """Clean up patches."""
        self.patcher.stop()

    def test_device_setup(self):
        """Test that devices are properly set up during initialization."""
        # Check that all devices were setup
        assert len(self.mock_gpio.setup_calls) == 3
        expected_calls = [(17, "OUT"), (18, "OUT"), (27, "OUT")]
        for call in expected_calls:
            assert call in self.mock_gpio.setup_calls

        # Check that all devices are initially off
        for device in self.device_config:
            assert self.controller.device_status[device] is False

    def test_turn_on_device(self):
        """Test turning on a device."""
        success = self.controller.turn_on("pump")

        assert success is True
        assert self.controller.device_status["pump"] is True
        assert (17, True) in self.mock_gpio.output_calls

    def test_turn_off_device(self):
        """Test turning off a device."""
        # First turn on
        self.controller.turn_on("pump")

        # Then turn off
        success = self.controller.turn_off("pump")

        assert success is True
        assert self.controller.device_status["pump"] is False
        assert (17, False) in self.mock_gpio.output_calls

    def test_turn_on_unknown_device(self):
        """Test turning on unknown device returns False."""
        success = self.controller.turn_on("unknown")

        assert success is False
        # Check no GPIO calls were made
        initial_calls = len(self.mock_gpio.output_calls)
        assert len(self.mock_gpio.output_calls) == initial_calls

    def test_get_status(self):
        """Test getting device status."""
        self.controller.turn_on("pump")
        self.controller.turn_on("light")

        status = self.controller.get_status()

        assert status["pump"] is True
        assert status["light"] is True
        assert status["fan"] is False

    def test_turn_all_on(self):
        """Test turning on all devices."""
        success = self.controller.turn_all_on()

        assert success is True
        for device in self.device_config:
            assert self.controller.device_status[device] is True

    def test_turn_all_off(self):
        """Test turning off all devices."""
        # First turn all on
        self.controller.turn_all_on()

        # Then turn all off
        success = self.controller.turn_all_off()

        assert success is True
        for device in self.device_config:
            assert self.controller.device_status[device] is False

    def test_turn_on_with_timeout(self):
        """Test turning on device with timeout."""
        with patch("waterbot.gpio.handler.Timer") as mock_timer:
            mock_timer_instance = Mock()
            mock_timer.return_value = mock_timer_instance

            success = self.controller.turn_on("pump", timeout=5)

            assert success is True
            assert self.controller.device_status["pump"] is True
            mock_timer.assert_called_once()
            mock_timer_instance.start.assert_called_once()

    def test_cleanup(self):
        """Test cleanup functionality."""
        # Set up some active timers
        with patch("waterbot.gpio.handler.Timer") as mock_timer:
            mock_timer_instance = Mock()
            mock_timer.return_value = mock_timer_instance

            self.controller.turn_on("pump", timeout=5)
            self.controller.cleanup()

            # Check that timer was cancelled
            mock_timer_instance.cancel.assert_called_once()

            # Check that GPIO cleanup was called
            assert self.mock_gpio.cleanup_called is True


class TestDeviceControllerModuleFunctions:
    """Test module-level functions."""

    def setup_method(self):
        """Reset global controller for each test."""
        import waterbot.gpio.handler as handler

        handler._controller = None

    @patch("waterbot.gpio.handler.DEVICE_TO_PIN", {"pump": 17})
    @patch("waterbot.gpio.handler.IS_EMULATION", True)
    def test_module_turn_on(self):
        """Test module-level turn_on function."""
        from waterbot.gpio.handler import set_controller, turn_on
        from waterbot.gpio.interface import MockGPIO

        # Set up mock controller
        mock_gpio = MockGPIO()
        controller = DeviceController(mock_gpio)
        set_controller(controller)

        success = turn_on("pump")
        assert success is True
        assert (17, True) in mock_gpio.output_calls

    @patch("waterbot.gpio.handler.DEVICE_TO_PIN", {"pump": 17})
    @patch("waterbot.gpio.handler.IS_EMULATION", True)
    def test_module_get_status(self):
        """Test module-level get_status function."""
        from waterbot.gpio.handler import get_status, set_controller, turn_on
        from waterbot.gpio.interface import MockGPIO

        # Set up mock controller
        mock_gpio = MockGPIO()
        controller = DeviceController(mock_gpio)
        set_controller(controller)

        turn_on("pump")
        status = get_status()

        assert status["pump"] is True
