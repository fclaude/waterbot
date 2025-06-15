"""GPIO device control and management for WaterBot."""

import logging
from threading import Lock, Timer
from typing import Dict, Optional

from ..config import DEVICE_TO_PIN, IS_EMULATION
from .interface import EmulationGPIO, GPIOInterface, HardwareGPIO  # noqa: I100

logger = logging.getLogger("gpio_handler")


class DeviceController:
    """Controls GPIO devices with proper abstraction for testing."""

    def __init__(self, gpio_interface: Optional[GPIOInterface] = None):
        """Initialize the device controller."""
        self.gpio = gpio_interface
        self.device_status: Dict[str, bool] = {}
        self.device_timers: Dict[str, Optional[Timer]] = {}
        self.gpio_lock = Lock()

        # Initialize GPIO if not provided
        if self.gpio is None:
            self._initialize_gpio()

        # Setup devices
        self._setup_devices()

    def _initialize_gpio(self) -> None:
        """Initialize GPIO interface based on operation mode."""
        if not IS_EMULATION:
            try:
                self.gpio = HardwareGPIO()
                # Clean up any previous GPIO state
                self.gpio.cleanup()
                logger.info(
                    "GPIO initialized in hardware mode (previous state cleaned)"
                )
            except (ImportError, RuntimeError) as e:
                logger.error(f"Failed to initialize GPIO in hardware mode: {e}")
                raise
        else:
            self.gpio = EmulationGPIO()
            logger.info("GPIO initialized in emulation mode")

    def _setup_devices(self) -> None:
        """Set up all configured devices."""
        for device, pin in DEVICE_TO_PIN.items():
            if self.gpio is not None:
                self.gpio.setup(pin, "OUT")
                self.gpio.output(pin, False)
            self.device_status[device] = False
            self.device_timers[device] = None

        logger.info(f"Setup {len(DEVICE_TO_PIN)} devices")

    def turn_on(self, device: str, timeout: Optional[int] = None) -> bool:
        """Turn on a device by setting GPIO pin HIGH (for low-activated relays).

        Args:
            device: Name of the device to turn on
            timeout: Optional timeout in seconds to automatically turn off

        Returns:
            bool: True if successful, False if device not found
        """
        if device not in DEVICE_TO_PIN:
            logger.warning(f"Unknown device: {device}")
            return False

        with self.gpio_lock:
            # Cancel any existing timer
            timer = self.device_timers[device]
            if timer is not None:
                timer.cancel()
                self.device_timers[device] = None

            # Turn on the device (set pin HIGH for low-activated relays)
            pin = DEVICE_TO_PIN[device]
            if self.gpio is not None:
                self.gpio.output(pin, True)  # HIGH = ON
            self.device_status[device] = True

            if IS_EMULATION:
                logger.info(f"EMULATION: Turning ON device '{device}' on pin {pin}")

            # Set a timer if timeout is specified
            if timeout:
                self.device_timers[device] = Timer(
                    timeout, lambda: self.turn_off(device)
                )
                timer = self.device_timers[device]
                if timer is not None:
                    timer.daemon = True
                    timer.start()
                logger.info(
                    f"Device '{device}' will turn off after {timeout // 60} minutes"
                )

        return True

    def turn_off(self, device: str, timeout: Optional[int] = None) -> bool:
        """Turn off a device by setting GPIO pin LOW (for low-activated relays).

        Args:
            device: Name of the device to turn off
            timeout: Optional timeout in seconds to automatically turn on

        Returns:
            bool: True if successful, False if device not found
        """
        if device not in DEVICE_TO_PIN:
            logger.warning(f"Unknown device: {device}")
            return False

        with self.gpio_lock:
            # Cancel any existing timer
            timer = self.device_timers[device]
            if timer is not None:
                timer.cancel()
                self.device_timers[device] = None

            # Turn off the device (set pin LOW for low-activated relays)
            pin = DEVICE_TO_PIN[device]
            if self.gpio is not None:
                self.gpio.output(pin, False)  # LOW = OFF
            self.device_status[device] = False

            if IS_EMULATION:
                logger.info(f"EMULATION: Turning OFF device '{device}' on pin {pin}")

            # Set a timer if timeout is specified
            if timeout:
                self.device_timers[device] = Timer(
                    timeout, lambda: self.turn_on(device)
                )
                timer = self.device_timers[device]
                if timer is not None:
                    timer.daemon = True
                    timer.start()
                logger.info(
                    f"Device '{device}' will turn on after {timeout // 60} minutes"
                )
            else:
                logger.info(f"Device '{device}' turned off permanently")

        return True

    def get_status(self) -> Dict[str, bool]:
        """Get status of all devices."""
        return self.device_status.copy()

    def turn_all_on(self, timeout: Optional[int] = None) -> bool:
        """Turn on all devices."""
        success = True
        for device in DEVICE_TO_PIN.keys():
            if not self.turn_on(device, timeout):
                success = False
        return success

    def turn_all_off(self, timeout: Optional[int] = None) -> bool:
        """Turn off all devices."""
        success = True
        for device in DEVICE_TO_PIN.keys():
            if not self.turn_off(device, timeout):
                success = False
        return success

    def cleanup(self) -> None:
        """Clean up GPIO resources."""
        # Cancel all timers
        for device in self.device_timers:
            timer = self.device_timers[device]
            if timer is not None:
                timer.cancel()

        # Turn off all devices before cleanup
        for device in DEVICE_TO_PIN.keys():
            self.device_status[device] = False

        # Cleanup GPIO
        if self.gpio:
            self.gpio.cleanup()

        logger.info("GPIO resources cleaned up")


# Global device controller instance
_controller: Optional[DeviceController] = None


def _get_controller() -> DeviceController:
    """Get the global device controller instance."""
    global _controller
    if _controller is None:
        _controller = DeviceController()
    return _controller


def set_controller(controller: DeviceController) -> None:
    """Set a custom controller (for testing)."""
    global _controller
    _controller = controller


# Backward compatibility functions
def turn_on(device: str, timeout: Optional[int] = None) -> bool:
    """Turn on a device, optionally with a timeout."""
    return _get_controller().turn_on(device, timeout)


def turn_off(device: str, timeout: Optional[int] = None) -> bool:
    """Turn off a device, optionally with a timeout."""
    return _get_controller().turn_off(device, timeout)


def get_status() -> Dict[str, bool]:
    """Get status of all devices."""
    return _get_controller().get_status()


def turn_all_on(timeout: Optional[int] = None) -> bool:
    """Turn on all devices."""
    return _get_controller().turn_all_on(timeout)


def turn_all_off(timeout: Optional[int] = None) -> bool:
    """Turn off all devices."""
    return _get_controller().turn_all_off(timeout)


def cleanup() -> None:
    """Clean up GPIO resources."""
    controller = _get_controller()
    controller.cleanup()
