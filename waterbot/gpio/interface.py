"""GPIO interface abstractions for WaterBot."""
from abc import ABC, abstractmethod
from typing import Dict


class GPIOInterface(ABC):
    """Abstract interface for GPIO operations."""

    @abstractmethod
    def setup(self, pin: int, mode: str) -> None:
        """Set up a GPIO pin."""
        pass

    @abstractmethod
    def output(self, pin: int, value: bool) -> None:
        """Set GPIO pin output value."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Cleanup GPIO resources."""
        pass


class HardwareGPIO(GPIOInterface):
    """Hardware GPIO implementation using RPi.GPIO."""

    def __init__(self):
        """Initialize hardware GPIO interface."""
        try:
            import RPi.GPIO as GPIO

            self.GPIO = GPIO
            self.GPIO.setmode(GPIO.BCM)
            self.GPIO.setwarnings(False)
        except ImportError:
            raise RuntimeError("RPi.GPIO not available")

    def setup(self, pin: int, mode: str) -> None:
        """Set up a GPIO pin."""
        gpio_mode = self.GPIO.OUT if mode == "OUT" else self.GPIO.IN
        self.GPIO.setup(pin, gpio_mode)

    def output(self, pin: int, value: bool) -> None:
        """Set GPIO pin output value."""
        gpio_value = self.GPIO.HIGH if value else self.GPIO.LOW
        self.GPIO.output(pin, gpio_value)

    def cleanup(self) -> None:
        """Cleanup GPIO resources."""
        self.GPIO.cleanup()


class EmulationGPIO(GPIOInterface):
    """Emulation GPIO implementation for testing."""

    def __init__(self):
        """Initialize emulation GPIO interface."""
        self.pin_states: Dict[int, bool] = {}
        self.setup_pins: Dict[int, str] = {}

    def setup(self, pin: int, mode: str) -> None:
        """Set up a GPIO pin."""
        self.setup_pins[pin] = mode
        self.pin_states[pin] = False

    def output(self, pin: int, value: bool) -> None:
        """Set GPIO pin output value."""
        if pin not in self.setup_pins:
            raise RuntimeError(f"Pin {pin} not setup")
        self.pin_states[pin] = value

    def get_pin_state(self, pin: int) -> bool:
        """Get current pin state (for testing)."""
        return self.pin_states.get(pin, False)

    def get_setup_pins(self) -> Dict[int, str]:
        """Get setup pins (for testing)."""
        return self.setup_pins.copy()

    def cleanup(self) -> None:
        """Cleanup GPIO resources."""
        self.pin_states.clear()
        self.setup_pins.clear()


class MockGPIO(GPIOInterface):
    """Mock GPIO implementation for unit testing."""

    def __init__(self):
        """Initialize mock GPIO interface."""
        self.setup_calls = []
        self.output_calls = []
        self.cleanup_called = False
        self.pin_states: Dict[int, bool] = {}

    def setup(self, pin: int, mode: str) -> None:
        """Set up a GPIO pin."""
        self.setup_calls.append((pin, mode))
        self.pin_states[pin] = False

    def output(self, pin: int, value: bool) -> None:
        """Set GPIO pin output value."""
        self.output_calls.append((pin, value))
        self.pin_states[pin] = value

    def get_pin_state(self, pin: int) -> bool:
        """Get current pin state (for testing)."""
        return self.pin_states.get(pin, False)

    def cleanup(self) -> None:
        """Cleanup GPIO resources."""
        self.cleanup_called = True
        self.pin_states.clear()
