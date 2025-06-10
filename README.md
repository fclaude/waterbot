# WaterBot - Signal GPIO Controller for Raspberry Pi

A Python bot that uses Signal messenger to control GPIO pins on a Raspberry Pi Zero W. The bot only responds to messages from a specific Signal group.

## Features

- Control GPIO pins remotely via Signal messenger
- Secure: only responds to messages from a specified Signal group
- Command-based interface to control devices
- Timed operations (e.g., turn on a device for 1 hour)
- **Automatic scheduling**: Set devices to turn on/off at specific times
- Emulation mode for testing on non-RPi devices
- Configurable device-to-pin mapping via .env file
- Comprehensive unit test coverage

## Requirements

- Python 3.7+
- Raspberry Pi Zero W (or any Raspberry Pi)
- Signal account for the bot
- Signal CLI installed

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/waterbot.git
cd waterbot
```

2. Install the required packages:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your configuration:
```
# Signal Configuration
SIGNAL_PHONE_NUMBER="+1234567890"
SIGNAL_GROUP_ID="group.123456789"

# Operation Mode (rpi or emulation)
OPERATION_MODE=rpi

# Device to GPIO Pin Mapping
# Format: DEVICE_NAME=GPIO_PIN_NUMBER
DEVICE_LIGHT=17
DEVICE_FAN=18
DEVICE_PUMP=27
DEVICE_HEATER=22

# Default timeout in seconds (optional, for timed operations)
DEFAULT_TIMEOUT=3600

# Scheduling Configuration
# Enable automatic scheduling of devices
ENABLE_SCHEDULING=true
# JSON file to store schedule configuration (optional)
SCHEDULE_CONFIG_FILE=schedules.json

# Schedule Configuration (alternative to JSON file)
# Format: SCHEDULE_<DEVICE>_<ACTION>=HH:MM[,HH:MM,...]
# Examples:
# SCHEDULE_PUMP_ON=08:00,20:00
# SCHEDULE_PUMP_OFF=12:00,23:00
# SCHEDULE_LIGHT_ON=06:30
# SCHEDULE_LIGHT_OFF=22:00
```

### Signal CLI Setup

This bot uses Signal CLI to communicate with the Signal network. Follow these steps to set up Signal CLI:

1. Install Signal CLI according to [official instructions](https://github.com/AsamK/signal-cli)
2. Register a phone number for your bot:
```bash
signal-cli -u +1234567890 register
```
3. Verify with the code received:
```bash
signal-cli -u +1234567890 verify 123-456
```
4. Find your Signal group ID:
```bash
signal-cli -u +1234567890 listGroups
```
5. Update your `.env` file with the phone number and group ID

## Usage

### Starting the Bot

```bash
python -m waterbot.bot
```

### Available Commands

Send these commands from the Signal group to control your devices:

#### Device Control
- `status` - Show the status of all devices
- `on <device>` - Turn on a specific device
- `off <device>` - Turn off a specific device
- `on <device> <seconds>` - Turn on a device for a specified time
- `off <device> <seconds>` - Turn off a device for a specified time
- `on all` - Turn on all devices
- `off all` - Turn off all devices

#### Scheduling Commands
- `schedules` - Show all configured schedules and next runs
- `schedule <device> <on|off> <HH:MM>` - Add a new schedule
- `unschedule <device> <on|off> <HH:MM>` - Remove a schedule

#### Help
- Send any unrecognized command to get help

### Examples

#### Basic Device Control
```
status
on light
off pump
on fan 3600
off heater 1800
on all
off all
```

#### Scheduling Examples
```
# Show all schedules
schedules

# Turn on pump at 8:00 AM and 8:00 PM every day
schedule pump on 08:00
schedule pump on 20:00

# Turn off pump at 12:00 PM and 11:00 PM every day
schedule pump off 12:00
schedule pump off 23:00

# Turn on lights at 6:30 AM
schedule light on 06:30

# Turn off lights at 10:00 PM
schedule light off 22:00

# Remove a schedule
unschedule pump on 20:00
```

## Development and Testing

For development and testing on non-RPi devices, set `OPERATION_MODE=emulation` in your `.env` file. In this mode, GPIO operations will be simulated and printed to the console.

### Running Tests

The project includes comprehensive unit tests. To run the tests:

```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run tests with coverage report
pytest --cov=waterbot --cov-report=html

# Run specific test file
pytest tests/test_gpio_handler.py

# Run tests matching a pattern
pytest -k "test_device"
```

### Test Coverage

The test suite covers:
- GPIO interface and hardware abstraction
- Device control logic and timing
- Schedule configuration and management  
- Signal bot message handling
- Command parsing and validation
- Error handling and edge cases

### Testing Configuration

Tests use mock objects and dependency injection to ensure they can run without hardware dependencies or external services.

## CI/CD Integration

WaterBot includes comprehensive CI/CD pipelines for automated testing and deployment:

### GitLab CI/CD
- Automated testing on every commit and merge request
- Multi-Python version testing (3.8-3.11)
- Code quality checks (linting, formatting, type checking)
- Security vulnerability scanning
- Docker image building and testing

### GitHub Actions
- Similar comprehensive pipeline for GitHub repositories
- Automatic PyPI publishing on releases
- Codecov integration for coverage reporting

See [CI-CD.md](CI-CD.md) for detailed pipeline documentation.

## Running as a Service

To run the bot as a service on your Raspberry Pi:

1. Create a service file:
```bash
sudo nano /etc/systemd/system/waterbot.service
```

2. Add the following content (adjust paths as needed):
```
[Unit]
Description=WaterBot Signal GPIO Controller
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/waterbot
ExecStart=/usr/bin/python3 -m waterbot.bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. Enable and start the service:
```bash
sudo systemctl enable waterbot.service
sudo systemctl start waterbot.service
```

4. Check status:
```bash
sudo systemctl status waterbot.service
```

## License

MIT
