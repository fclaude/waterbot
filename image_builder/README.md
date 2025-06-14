# WaterBot Image Builder

This tool helps you create pre-configured Raspberry Pi OS images for WaterBot. It automates the
installation and configuration process, allowing you to quickly deploy WaterBot to multiple
Raspberry Pi devices.

## Cross-Platform Support

The image builder now supports both Linux and macOS:

### macOS (Recommended)

- Uses Docker to provide a Linux environment
- No special privileges required beyond Docker
- Automatic WiFi configuration support
- Easy to use script interface

### Linux (Traditional)

- Direct system access
- Requires root privileges
- Manual WiFi configuration

## Directory Structure

```text
waterbot/
├── waterbot/          # Your WaterBot source code
└── image_builder/
    ├── configs/       # Different .env configurations
    │   └── default.env # Default configuration
    ├── scripts/       # Setup scripts
    │   └── setup.sh   # Main setup script
    └── build_image.sh # Main script to build the image
```

## Usage

### macOS (Docker-based)

1. **Prerequisites:**
   - Install [Docker Desktop for macOS](https://www.docker.com/products/docker-desktop)
   - Ensure Docker is running

2. **Create your configuration:**
   - Copy `configs/default.env` to a new file (e.g., `configs/home.env`)
   - Modify the Discord bot token, channel ID, and device mappings

3. **Build the image with WiFi configuration:**

   ```bash
   # Basic usage (no WiFi configured)
   ./build_macos.sh

   # With specific config
   ./build_macos.sh home

   # With WiFi configuration
   ./build_macos.sh home "MyWiFiNetwork" "MyWiFiPassword"

   # WiFi with spaces in name/password (use quotes)
   ./build_macos.sh home "My Home WiFi" "My Complex Password 123"
   ```

4. **Write to SD card:**

   ```bash
   # Find your SD card
   diskutil list

   # Unmount the SD card (replace diskX with your device)
   diskutil unmountDisk /dev/diskX

   # Write the image (use rdiskX for faster writing)
   sudo dd if=output/waterbot.img of=/dev/rdiskX bs=1m

   # Eject the SD card
   diskutil eject /dev/diskX
   ```

### Linux (Traditional)

1. **Build the image:**

   ```bash
   sudo ./build_image.sh [config_name]
   ```

2. **Write to SD card:**

   ```bash
   sudo dd if=waterbot.img of=/dev/sdX bs=4M status=progress
   ```

### After Booting

1. **If WiFi was configured:** The Pi will connect automatically
2. **If no WiFi:** Connect via Ethernet or configure WiFi manually
3. **Check service status:**

   ```bash
   systemctl status waterbot.service
   journalctl -u waterbot.service -f
   ```

## Configuration Files

Configuration files are stored in the `configs/` directory. Each file should be named `[name].env`
and contain the following settings:

- `DISCORD_BOT_TOKEN`: Your bot's Discord token
- `DISCORD_CHANNEL_ID`: The Discord channel ID where the bot will operate
- `OPERATION_MODE`: Either `rpi` or `emulation`
- Device to GPIO pin mappings (e.g., `DEVICE_BED1=17`)
- Scheduling configuration (e.g., `SCHEDULE_BED1_ON=05:00,21:00`)
- Other WaterBot settings

## Network Resilience Features

The image builder creates a robust system that handles network issues gracefully:

### Offline Operation

- **Scheduled tasks continue working** even without internet
- **GPIO control remains functional** for local device management
- **Service automatically restarts** if crashes occur

### Network Recovery

- **Discord bot reconnects automatically** when internet returns
- **Exponential backoff** prevents rapid reconnection attempts
- **Systemd service** handles process management and restarts

### WiFi Configuration

- **Pre-configured WiFi** connects automatically on first boot
- **SSH enabled** for manual configuration if needed
- **No network dependency** for core functionality

## Troubleshooting

1. If the image build fails:
   - Check that you have all required tools installed
   - Ensure you have enough disk space
   - Verify that you're running as root
   - Make sure your WaterBot source code is in the correct location

2. If the Raspberry Pi doesn't boot:
   - Verify that the image was written correctly to the SD card
   - Check that the SD card is properly inserted
   - Try using a different SD card

3. If WaterBot doesn't start:
   - Check the service status: `systemctl status waterbot.service`
   - View the logs: `journalctl -u waterbot.service -f`
   - Verify Signal CLI setup: `signal-cli -u YOUR_PHONE_NUMBER listGroups`

## Security Notes

- The image includes a default configuration that should be modified for production use
- Signal CLI registration requires manual intervention for security reasons
- The service runs as a dedicated user with limited privileges
- Configuration files are protected with appropriate permissions
