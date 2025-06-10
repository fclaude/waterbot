import time
from threading import Timer, Lock
import logging
from ..config import IS_EMULATION, DEVICE_TO_PIN

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("gpio_handler")

# Dictionary to store device status and timer objects
device_status = {}
device_timers = {}
gpio_lock = Lock()

# Initialize GPIO or emulation
if not IS_EMULATION:
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        # Set up all pins as output
        for device, pin in DEVICE_TO_PIN.items():
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
            device_status[device] = False
        logger.info("GPIO initialized in hardware mode")
    except (ImportError, RuntimeError):
        logger.error("Failed to initialize GPIO in hardware mode")
        raise
else:
    # Emulation mode
    for device in DEVICE_TO_PIN.keys():
        device_status[device] = False
    logger.info("GPIO initialized in emulation mode")

def turn_on(device, timeout=None):
    """
    Turn on a device, optionally with a timeout
    
    Args:
        device (str): Device name
        timeout (int, optional): Timeout in seconds
    
    Returns:
        bool: Success status
    """
    if device not in DEVICE_TO_PIN:
        logger.warning(f"Unknown device: {device}")
        return False
    
    with gpio_lock:
        # Cancel any existing timer
        if device in device_timers and device_timers[device]:
            device_timers[device].cancel()
            device_timers[device] = None
        
        # Turn on the device
        if not IS_EMULATION:
            GPIO.output(DEVICE_TO_PIN[device], GPIO.HIGH)
        else:
            logger.info(f"EMULATION: Turning ON device '{device}' on pin {DEVICE_TO_PIN[device]}")
        
        device_status[device] = True
        
        # Set a timer if timeout is specified
        if timeout:
            device_timers[device] = Timer(timeout, lambda: turn_off(device))
            device_timers[device].daemon = True
            device_timers[device].start()
            logger.info(f"Device '{device}' will turn off after {timeout} seconds")
    
    return True

def turn_off(device, timeout=None):
    """
    Turn off a device, optionally with a timeout
    
    Args:
        device (str): Device name
        timeout (int, optional): Timeout in seconds
    
    Returns:
        bool: Success status
    """
    if device not in DEVICE_TO_PIN:
        logger.warning(f"Unknown device: {device}")
        return False
    
    with gpio_lock:
        # Cancel any existing timer
        if device in device_timers and device_timers[device]:
            device_timers[device].cancel()
            device_timers[device] = None
        
        # Turn off the device
        if not IS_EMULATION:
            GPIO.output(DEVICE_TO_PIN[device], GPIO.LOW)
        else:
            logger.info(f"EMULATION: Turning OFF device '{device}' on pin {DEVICE_TO_PIN[device]}")
        
        device_status[device] = False
        
        # Set a timer if timeout is specified
        if timeout:
            device_timers[device] = Timer(timeout, lambda: turn_on(device))
            device_timers[device].daemon = True
            device_timers[device].start()
            logger.info(f"Device '{device}' will turn on after {timeout} seconds")
    
    return True

def get_status():
    """Get status of all devices
    
    Returns:
        dict: Device status dictionary
    """
    return device_status.copy()

def turn_all_on(timeout=None):
    """Turn on all devices
    
    Args:
        timeout (int, optional): Timeout in seconds
    
    Returns:
        bool: Success status
    """
    success = True
    for device in DEVICE_TO_PIN.keys():
        if not turn_on(device, timeout):
            success = False
    return success

def turn_all_off(timeout=None):
    """Turn off all devices
    
    Args:
        timeout (int, optional): Timeout in seconds
    
    Returns:
        bool: Success status
    """
    success = True
    for device in DEVICE_TO_PIN.keys():
        if not turn_off(device, timeout):
            success = False
    return success

def cleanup():
    """Clean up GPIO resources"""
    for device in device_timers:
        if device_timers[device]:
            device_timers[device].cancel()
    
    if not IS_EMULATION:
        try:
            # Turn off all pins before cleanup
            for device, pin in DEVICE_TO_PIN.items():
                GPIO.output(pin, GPIO.LOW)
            GPIO.cleanup()
            logger.info("GPIO resources cleaned up")
        except:
            logger.error("Error during GPIO cleanup")
    else:
        logger.info("EMULATION: GPIO cleanup called") 