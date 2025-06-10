# WaterBot - Signal GPIO Controller for Raspberry Pi

A Python bot that uses Signal messenger to control GPIO pins on a Raspberry Pi Zero W. The bot only responds to messages from a specific Signal group.

## Features

- Control GPIO pins remotely via Signal messenger
- Secure: only responds to messages from a specified Signal group
- Command-based interface to control devices
- Timed operations (e.g., turn on a device for 1 hour)
- Emulation mode for testing on non-RPi devices
- Configurable device-to-pin mapping via .env file

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

- `status` - Show the status of all devices
- `on <device>` - Turn on a specific device
- `off <device>` - Turn off a specific device
- `on <device> <seconds>` - Turn on a device for a specified time
- `off <device> <seconds>` - Turn off a device for a specified time
- `on all` - Turn on all devices
- `off all` - Turn off all devices

### Examples

```
status
on light
off pump
on fan 3600
off heater 1800
on all
off all
```

## Development and Testing

For development and testing on non-RPi devices, set `OPERATION_MODE=emulation` in your `.env` file. In this mode, GPIO operations will be simulated and printed to the console.

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
