# WaterBot - Discord GPIO Controller for Raspberry Pi

[![CI](https://github.com/fclaude/waterbot/workflows/CI/badge.svg)](https://github.com/fclaude/waterbot/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/fclaude/waterbot/graph/badge.svg?token=G2DI5V03O1)](https://codecov.io/gh/fclaude/waterbot)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

![WaterBot Logo](waterbot.png)

A Python bot that uses Discord to control GPIO pins on a Raspberry
Pi Zero W. The bot only responds to messages from a specific Discord channel.

## Features

- Control GPIO pins remotely via Discord
- Only responds to messages from a specified Discord channel
- Command-based interface to control devices
- Timed operations (e.g., turn on a device for 1 hour)
- **Automatic scheduling**: Set devices to turn on/off at specific times
- Flexible every-N-days and weather-aware watering policies
- SQLite-backed agent memory, action audit history, and confirmation tokens
- Optional web dashboard with public schedule views and authenticated chat
- Emulation mode for testing on non-RPi devices
- Configurable device-to-pin mapping via .env file
- Reasonable unit test coverage

## Requirements

- Python 3.11+
- Raspberry Pi Zero W (or any Raspberry Pi)
- Discord bot token
- Discord server with a channel for the bot

## Installation

1. Clone this repository:

```bash
git clone https://github.com/fclaude/waterbot.git
cd waterbot
```

1. Install the required packages:

```bash
# Runtime dependencies (works on laptops and CI without Raspberry Pi GPIO)
pip install -r requirements.txt

# Development / tests
pip install -r requirements-dev.txt

# On a Raspberry Pi, also install GPIO support
pip install -r requirements-rpi.txt
```

1. Create a `.env` file with your configuration:

```env
# Discord Configuration
DISCORD_BOT_TOKEN="your_discord_bot_token_here"
DISCORD_CHANNEL_ID="123456789012345678"

# OpenAI-compatible LLM (optional, enables natural-language control)
# Leave OPENAI_BASE_URL unset to use api.openai.com. Point it at any Chat
# Completions-compatible server (OpenRouter, vLLM, Ollama, LiteLLM, etc.).
OPENAI_API_KEY="your_openai_api_key_here"  # pragma: allowlist secret
OPENAI_MODEL="gpt-4o-mini"
# OPENAI_BASE_URL="http://127.0.0.1:11434/v1"

# Operation Mode (rpi or emulation)
OPERATION_MODE=rpi

# Device to GPIO Pin Mapping
# Format: DEVICE_NAME=GPIO_PIN_NUMBER
DEVICE_LIGHT=17
DEVICE_FAN=18
DEVICE_PUMP=27
DEVICE_HEATER=22

# Relay defaults
# Global startup/cleanup state: on or off
RELAY_DEFAULT_STATE=off
RELAY_CLEANUP_STATE=off
# Optional per-device startup override
# RELAY_DEFAULT_PUMP=on
# Relay polarity: high means GPIO HIGH turns the relay on; low means GPIO LOW turns it on
RELAY_ACTIVE_STATE=high
# Optional per-device polarity override
# RELAY_ACTIVE_PUMP=low

# Default timeout in minutes (optional, for timed operations)
DEFAULT_TIMEOUT=60

# Scheduling Configuration
# Enable automatic scheduling of devices
ENABLE_SCHEDULING=true
# JSON file to store schedule configuration (optional)
SCHEDULE_CONFIG_FILE=schedules.json
# JSON file to store flexible policy schedules
POLICY_SCHEDULE_CONFIG_FILE=schedule_policies.json

# Conversational agent memory and confirmations
AGENT_DB_FILE=waterbot_agent.db
AGENT_MEMORY_RETENTION_DAYS=30
AGENT_CONFIRMATION_TIMEOUT_MINUTES=10
AGENT_REQUIRE_CONFIRMATION=true

# Optional authenticated web interface
ENABLE_WEB_INTERFACE=false
WEB_HOST=127.0.0.1
WEB_PORT=8080
WEB_AUTH_USERNAME=admin
# WEB_AUTH_PASSWORD="change_me"  # pragma: allowlist secret
# WEB_AUTH_TOKEN="optional_api_token"  # pragma: allowlist secret
WEB_PUBLIC_SCHEDULES=false

# Schedule Configuration (alternative to JSON file)
# Format: SCHEDULE_<DEVICE>_<ACTION>=HH:MM[,HH:MM,...]
# Examples:
# SCHEDULE_PUMP_ON=08:00,20:00
# SCHEDULE_PUMP_OFF=12:00,23:00
# SCHEDULE_LIGHT_ON=06:30
# SCHEDULE_LIGHT_OFF=22:00

# Optional weather context for flexible policy schedules
# WEATHER_PROVIDER=none or open_meteo
WEATHER_PROVIDER=none
# WEATHER_LATITUDE=37.7749
# WEATHER_LONGITUDE=-122.4194
# WEATHER_CONTEXT_JSON={"temperature_f":90,"rain_last_24h_inches":0}
```

Use `data/schedules.json`, `data/schedule_policies.json`, and `data/waterbot_agent.db` by default
(see `env.sample`). Copy `env.sample` to `.env` for a full template.

### Discord Bot Setup

This bot uses Discord's bot API to communicate. Follow these steps to set up
your Discord bot:

1. Create a Discord Application at the
   [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a bot user in your application
3. Copy the bot token and add it to your `.env` file as `DISCORD_BOT_TOKEN`
4. Invite the bot to your Discord server with appropriate permissions:
   - Send Messages
   - Read Message History
   - Use Slash Commands
5. Get your Discord channel ID (enable Developer Mode in Discord,
   right-click channel, Copy ID)
6. Update your `.env` file with the channel ID

## Usage

### Starting the Bot

```bash
python -m waterbot.bot
```

### Available Commands

Send these commands from the Discord channel to control your devices:

#### Device Control

- `status` - Show the status of all devices
- `on <device>` - Turn on a specific device (permanent)
- `off <device>` - Turn off a specific device (permanent)
- `on <device> <minutes>` - Turn on a device for a specified time
- `off <device> <minutes>` - Turn off a device for a specified time
- `on all` - Turn on all devices
- `off all` - Turn off all devices
- `on all <minutes>` / `off all <minutes>` - Timed all-device operations

#### Scheduling Commands

- `schedules` - Show all configured schedules and next runs
- `schedule <device> <on|off> <HH:MM>` - Add a new schedule
- `unschedule <device> <on|off> <HH:MM>` - Remove a schedule
- `cycles` - Show flexible cycle schedules
- `cycle <device> every <N> days at <HH:MM> for <minutes> minutes` - Add an every-N-days cycle
- `uncycle <policy_id>` - Remove a flexible cycle
- `confirm <token>` - Execute a pending risky agent action
- `cancel <token>` - Cancel a pending risky agent action
- `why <device>` - Explain recent flexible schedule decisions
- `feedback <device> <note>` - Record observations such as too wet or too dry

#### Help

- Send any unrecognized command to get help

### Conversational Agent

When `OPENAI_API_KEY` or `OPENAI_BASE_URL` is configured, WaterBot keeps a conversational
agent memory in `AGENT_DB_FILE`. The client uses the official OpenAI SDK and speaks the
OpenAI Chat Completions + tools protocol, so you can leave `OPENAI_BASE_URL` unset for
OpenAI itself, or point it at any compatible server:

```env
OPENAI_API_KEY="your_openai_api_key_here"  # pragma: allowlist secret
OPENAI_MODEL="gpt-4o-mini"
# Optional: OpenAI-compatible endpoint (OpenRouter, vLLM, Ollama, LiteLLM, …)
# OPENAI_BASE_URL="https://openrouter.ai/api/v1"
```

For local servers that ignore auth, set `OPENAI_BASE_URL` and either a dummy
`OPENAI_API_KEY` or omit the key entirely.

- Recent turns are replayed to the model as real chat messages
- Older turns fold into a long-term channel summary
- Feedback, pending confirmation tokens, and recent audited actions stay available
  for follow-ups

Risky actions such as all-device changes, schedule replacement, clearing schedules,
or saving/removing flexible policies return a confirmation token first. Reply with
`confirm <token>` to execute or `cancel <token>` to discard.

The agent also records action events, flexible policy decisions, and user
feedback. Ask `why pump` to see recent automatic watering decisions for a device,
or send `feedback pump too dry after the last cycle` to add context for future
conversations.

### Web Interface

Set `ENABLE_WEB_INTERFACE=true` and configure `WEB_AUTH_PASSWORD` or
`WEB_AUTH_TOKEN` to start the local web server. By default the server binds to
`127.0.0.1` and schedules require authentication. Set `WEB_PUBLIC_SCHEDULES=true`
to expose the schedule dashboard without auth on a trusted network, and use a
reverse proxy with TLS if you bind to `0.0.0.0`.

Authenticated users can open `/chat` to ask the bot to change schedules, create
cycles, explain recent policy decisions, record feedback, and confirm risky
actions. The web chat uses the same action engine and confirmation flow as
Discord. Health probes can hit `/healthz`.

### Examples

#### Basic Device Control

```text
status
on light
off pump
on fan 60
off heater 30
on all
off all
```

#### Scheduling Examples

```text
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

#### Flexible Policy Schedule Example

Flexible policies are stored in `schedule_policies.json` and can express cycles,
duration bounds, seasonal windows, and weather-aware rules. The agent can create
these from natural language when `OPENAI_API_KEY` is configured, or you can edit
the JSON file directly.

```json
{
  "version": 1,
  "policies": [
    {
      "id": "pump-summer-cycle",
      "device": "pump",
      "enabled": true,
      "recurrence": {
        "type": "every_n_days",
        "every": 3,
        "at": "06:00",
        "anchor_date": "2026-07-01",
        "active_between": {"start": "04-01", "end": "10-31"}
      },
      "duration": {
        "base_minutes": 8,
        "min_minutes": 2,
        "max_minutes": 15
      },
      "rules": [
        {
          "name": "recent rain",
          "when": {"rain_last_24h_inches": {">=": 0.25}},
          "then": {"skip": true}
        },
        {
          "name": "forecast rain",
          "when": {"forecast_rain_next_12h_inches": {">=": 0.15}},
          "then": {"duration_multiplier": 0.5}
        },
        {
          "name": "hot day",
          "when": {"temperature_f": {">=": 90}},
          "then": {"duration_multiplier": 1.25}
        }
      ]
    }
  ]
}
```

## Development and Testing

For development and testing on non-RPi devices, set
`OPERATION_MODE=emulation` in your `.env` file. In this mode, GPIO
operations will be simulated and printed to the console.

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
- Discord bot message handling
- Command parsing and validation
- Error handling and edge cases

### Testing Configuration

Tests use mock objects and dependency injection to ensure they can run
without hardware dependencies or external services.

## CI/CD Integration

WaterBot includes comprehensive CI/CD pipelines for automated testing and deployment:

### GitLab CI/CD

- Automated testing on every commit and merge request
- Python 3.11 and 3.12 matrix testing
- Code quality checks (linting, formatting, type checking)
- Security scanning with Bandit and pip-audit
- Coverage gate at 85%

### GitHub Actions

- Same quality and test gates as GitLab
- Codecov integration for coverage reporting

See [CI-CD.md](CI-CD.md) for detailed pipeline documentation.
See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Running as a Service

A checked-in unit file lives at `deploy/waterbot.service`. On a Pi you can run:

```bash
sudo ./scripts/install-service.sh
sudo nano /opt/waterbot/.env
sudo systemctl start waterbot.service
```

For a manual install, follow these steps:

### Prerequisites

1. **Ensure you have a dedicated user for the service** (recommended for
   security):

```bash
# Create a dedicated user for the bot (optional but recommended)
sudo useradd -r -s /bin/false -d /opt/waterbot waterbot-service

# Or use the default 'pi' user if you prefer
```

1. **Add the service user to the gpio group** (for GPIO access):

```bash
# If using dedicated user:
sudo usermod -a -G gpio waterbot-service

# If using pi user:
sudo usermod -a -G gpio pi
```

### Installation for Service

1. **Install the bot in a system location** (recommended):

```bash
# Create application directory
sudo mkdir -p /opt/waterbot
sudo chown $USER:$USER /opt/waterbot

# Clone and setup the application
cd /opt/waterbot
git clone https://github.com/fclaude/waterbot.git .
```

1. **Install Python dependencies**:

```bash
# Install system-wide or in a virtual environment
sudo pip3 install -r requirements.txt

# Or create a virtual environment (recommended):
python3 -m venv /opt/waterbot/venv
sudo chown -R waterbot-service:waterbot-service /opt/waterbot
source /opt/waterbot/venv/bin/activate
pip install -r requirements.txt
```

1. **Setup configuration**:

```bash
# Create and configure the .env file
sudo cp env.sample .env
sudo nano /opt/waterbot/.env

# Ensure proper ownership
sudo chown waterbot-service:waterbot-service /opt/waterbot/.env
sudo chmod 600 /opt/waterbot/.env  # Secure the config file
```

1. **Configure Discord bot credentials for the service user**:

```bash
# Ensure the .env file contains proper Discord configuration
# DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID should be set
# The service user should have read access to this file
```

### Creating the Service

1. **Create the systemd service file**:

```bash
sudo nano /etc/systemd/system/waterbot.service
```

1. **Add the service configuration**:

```ini
[Unit]
Description=WaterBot Discord GPIO Controller
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=waterbot-service
Group=waterbot-service
WorkingDirectory=/opt/waterbot
Environment=PATH=/opt/waterbot/venv/bin:/usr/local/bin:/usr/bin:/bin

# Use virtual environment if created
ExecStart=/opt/waterbot/venv/bin/python -m waterbot.bot
# Or use system Python
# ExecStart=/usr/bin/python3 -m waterbot.bot

# Restart configuration
Restart=always
RestartSec=10
StartLimitInterval=60
StartLimitBurst=3

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/waterbot

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=waterbot

[Install]
WantedBy=multi-user.target
```

**Note**: If using the `pi` user instead of a dedicated user, change `User=pi`
and `Group=pi` in the service file, and adjust paths accordingly (e.g.,
`/home/pi/waterbot`).

### Managing the Service

1. **Reload systemd and enable the service**:

```bash
sudo systemctl daemon-reload
sudo systemctl enable waterbot.service
```

1. **Start the service**:

```bash
sudo systemctl start waterbot.service
```

1. **Check service status**:

```bash
sudo systemctl status waterbot.service
```

1. **View service logs**:

```bash
# View recent logs
sudo journalctl -u waterbot.service -f

# View logs from specific time
sudo journalctl -u waterbot.service --since "1 hour ago"

# View all logs for the service
sudo journalctl -u waterbot.service --no-pager
```

### Troubleshooting

**Common issues and solutions:**

1. **Permission denied errors**:
   - Ensure the service user is in the `gpio` group
   - Check file ownership and permissions for the bot directory
   - Verify the .env file is accessible to the service user

2. **Discord bot not working**:
   - Ensure the Discord bot token is valid and properly configured
   - Check that the bot has permissions in the Discord channel
   - Verify the Discord channel ID is correct

3. **Module import errors**:
   - Ensure all dependencies are installed in the correct Python environment
   - Check that the PYTHONPATH includes the waterbot directory
   - Verify the virtual environment path (if used) is correct

4. **Service won't start**:
   - Check the service logs: `sudo journalctl -u waterbot.service`
   - Verify all file paths in the service configuration
   - Test the bot manually first: `python3 -m waterbot.bot`

5. **GPIO access issues**:
   - Ensure the service user is in the `gpio` group:
     `groups waterbot-service`
   - Check that GPIO pins are not being used by other processes
   - Verify the device-to-pin mapping in your .env file

### Service Management Commands

```bash
# Start the service
sudo systemctl start waterbot.service

# Stop the service
sudo systemctl stop waterbot.service

# Restart the service
sudo systemctl restart waterbot.service

# Enable service to start on boot
sudo systemctl enable waterbot.service

# Disable service from starting on boot
sudo systemctl disable waterbot.service

# Check if service is running
sudo systemctl is-active waterbot.service

# View service configuration
sudo systemctl show waterbot.service
```
