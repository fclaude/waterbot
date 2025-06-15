"""GPIO interface abstractions for WaterBot."""

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Any


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
    """Hardware GPIO implementation using gpiozero."""

    def __init__(self) -> None:
        """Initialize hardware GPIO interface."""
        try:
            from gpiozero import Device
            from gpiozero.pins.pigpio import PiGPIOFactory
            
            # Use pigpio for better performance
            Device.pin_factory = PiGPIOFactory()
            self._pins: Dict[int, Any] = {}
        except ImportError:
            raise RuntimeError("gpiozero not available")

    def setup(self, pin: int, mode: str) -> None:
        """Set up a GPIO pin."""
        if mode == "OUT":
            from gpiozero import OutputDevice
            self._pins[pin] = OutputDevice(pin, active_high=False)

    def output(self, pin: int, value: bool) -> None:
        """Set GPIO pin output value."""
        if pin in self._pins:
            if value:
                self._pins[pin].on()
            else:
                self._pins[pin].off()

    def cleanup(self) -> None:
        """Cleanup GPIO resources."""
        for pin_device in self._pins.values():
            pin_device.close()
        self._pins.clear()


class EmulationGPIO(GPIOInterface):
    """Emulation GPIO implementation for testing."""

    def __init__(self) -> None:
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

    def __init__(self) -> None:
        """Initialize mock GPIO interface."""
        self.setup_calls: List[Tuple[int, str]] = []
        self.output_calls: List[Tuple[int, bool]] = []
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
