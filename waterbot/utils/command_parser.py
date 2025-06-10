import re
import logging
from ..config import DEFAULT_TIMEOUT, DEVICE_TO_PIN

logger = logging.getLogger("command_parser")

def parse_command(text):
    """
    Parse a command string into an action and parameters
    
    Args:
        text (str): Command text from user
        
    Returns:
        tuple: (command_type, params) or (None, None) if invalid
    """
    text = text.strip().lower()
    
    # Status command
    if text == "status":
        return "status", {}
    
    # All devices commands
    if text == "on all":
        return "all_on", {}
    
    if text == "off all":
        return "all_off", {}
    
    # Device-specific commands
    on_match = re.match(r'on\s+(\w+)(?:\s+(\d+))?', text)
    if on_match:
        device, time_str = on_match.groups()
        if device not in DEVICE_TO_PIN:
            logger.warning(f"Unknown device: {device}")
            return "error", {"message": f"Unknown device: {device}"}
        
        timeout = int(time_str) if time_str else None
        return "device_on", {"device": device, "timeout": timeout}
    
    off_match = re.match(r'off\s+(\w+)(?:\s+(\d+))?', text)
    if off_match:
        device, time_str = off_match.groups()
        if device not in DEVICE_TO_PIN:
            logger.warning(f"Unknown device: {device}")
            return "error", {"message": f"Unknown device: {device}"}
        
        timeout = int(time_str) if time_str else None
        return "device_off", {"device": device, "timeout": timeout}
    
    # Unknown command
    return "help", {} 