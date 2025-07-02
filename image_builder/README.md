# WaterBot Image Builder

This tool helps you create pre-configured Raspberry Pi OS images for WaterBot.
It automates the installation and configuration process, allowing you to
quickly deploy WaterBot to multiple Raspberry Pi devices.

## Cross-Platform Support

The image builder uses Docker and works on **any platform**:

### ✅ Supported Platforms

- **macOS** (Intel and Apple Silicon)
- **Linux** (all distributions with Docker support)
- **Windows** (with Docker Desktop or WSL2)

### 🚀 Key Benefits

- **No sudo/admin privileges required** - just Docker
- **Unified experience** across all platforms
- **Automatic WiFi configuration** support
- **Network resilience** built-in
- **Easy to use** script interface

## Prerequisites

1. **Install Docker:**
   - **macOS:** [Docker Desktop for macOS](
     https://www.docker.com/products/docker-desktop)
   - **Linux:** [Docker Engine](https://docs.docker.com/engine/install/) or
     [Docker Desktop](https://docs.docker.com/desktop/install/linux-install/)
   - **Windows:** [Docker Desktop for Windows](
     https://docs.docker.com/desktop/install/windows-install/)

2. **Ensure Docker is running**

## Directory Structure

```text
waterbot/
├── waterbot/          # Your WaterBot source code
└── image_builder/
    ├── configs/       # Different .env configurations
    │   └── default.env # Default configuration
    ├── scripts/       # Setup scripts
    │   └── setup.sh   # Main setup script
    ├── output/        # Generated images appear here
    └── build.sh       # Unified build script for all platforms
```

## Usage

### 1. Create your configuration

- Copy `configs/default.env` to a new file (e.g., `configs/home.env`)
- Modify the Discord bot token, channel ID, and device mappings

### 2. Build the image with WiFi configuration

```bash
# Basic usage (no WiFi configured)
./build.sh

# With specific config
./build.sh home

# With WiFi configuration
./build.sh home "MyWiFiNetwork" "MyWiFiPassword"

# WiFi with spaces in name/password (use quotes)
./build.sh home "My Home WiFi" "My Complex Password 123"

# Show help and available configurations
./build.sh --help
```

### 3. Write to SD card

The script will provide platform-specific instructions:

#### macOS

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

#### Linux

```bash
# Find your SD card
lsblk

# Unmount the SD card (replace sdX with your device)
sudo umount /dev/sdX*

# Write the image
sudo dd if=output/waterbot.img of=/dev/sdX bs=4M status=progress

# Safely remove
sync && sudo eject /dev/sdX
```

#### Windows

Use a tool like [Balena Etcher](https://www.balena.io/etcher/) or
[Raspberry Pi Imager](https://www.raspberrypi.com/software/) to write the
image to your SD card.

### 4. First Boot

The first boot process automatically handles several setup tasks:

1. **Filesystem expansion:** Automatically expands to use the full SD card
   capacity
2. **WiFi connection:** If configured, connects to the specified network
3. **WaterBot installation:** Installs and configures the service
4. **Automatic reboot:** Reboots to complete the filesystem expansion

**Timeline:**

- First boot: ~2-5 minutes (depends on SD card speed and internet connection)
- Automatic reboot after setup completion
- Second boot: Service starts and WaterBot becomes operational

**Check service status:**

```bash
systemctl status waterbot.service
journalctl -u waterbot.service -f
df -h  # Check available disk space
```

## Configuration Files

Configuration files are stored in the `configs/` directory. Each file
should be named `[name].env`
and contain the following settings:

- `DISCORD_BOT_TOKEN`: Your bot's Discord token
- `DISCORD_CHANNEL_ID`: The Discord channel ID where the bot will operate
- `OPERATION_MODE`: Either `rpi` or `emulation`
- Device to GPIO pin mappings (e.g., `DEVICE_BED1=17`)
- Scheduling configuration (e.g., `SCHEDULE_BED1_ON=05:00,21:00`)
- Other WaterBot settings

## Network Resilience Features

The image builder creates a robust system that handles network issues
gracefully:

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

### Docker Issues

1. **Docker not installed:**
   - Follow platform-specific installation instructions above
   - Restart your terminal after installation

2. **Docker not running:**
   - **macOS/Windows:** Start Docker Desktop
   - **Linux:** `sudo systemctl start docker`

3. **Permission denied:**
   - **Linux:** Add your user to docker group: `sudo usermod -aG docker $USER`
   - **macOS/Windows:** Usually handled by Docker Desktop

### Build Issues

1. **Configuration not found:**
   - Check available configs with `./build.sh --help`
   - Ensure the `.env` file exists in `configs/` directory

2. **Image build fails:**
   - Check Docker logs for errors
   - Ensure sufficient disk space
   - Verify internet connection for downloading base image

3. **WiFi not working:**
   - Check WiFi credentials are correct
   - Ensure network supports WPA-PSK authentication
   - Try connecting via Ethernet first

### Pi Boot Issues

1. **Service won't start:**
   - Check logs: `journalctl -u waterbot.service -f`
   - Verify configuration: `cat /opt/waterbot/.env`
   - Test manually: `cd /opt/waterbot && python -m waterbot.bot`

2. **Discord bot offline:**
   - Check internet connection
   - Verify Discord token is valid
   - Ensure bot has channel permissions

3. **GPIO not working:**
   - Verify `OPERATION_MODE=rpi` in configuration
   - Check device pin mappings
   - Ensure user is in `gpio` group

## Advanced Usage

### Custom Base Images

You can modify the Dockerfile to use different base images or add
additional packages:

```dockerfile
# Example: Add custom packages
RUN apt-get update && apt-get install -y \
    your-custom-package \
    && rm -rf /var/lib/apt/lists/*
```

### Multiple Configurations

Create different configuration files for different deployments:

```bash
# Production configuration
./build.sh production "HomeWiFi" "password123"

# Development configuration
./build.sh dev "TestWiFi" "devpass"

# Greenhouse configuration
./build.sh greenhouse "GreenHouseWiFi" "plantpass"
```

### Batch Building

Build multiple images with different configurations:

```bash
#!/bin/bash
for config in home greenhouse lab; do
    ./build.sh "$config" "CommonWiFi" "SharedPassword"
    mv output/waterbot.img "output/waterbot-${config}.img"
done
```

## Security Notes

- The image includes SSH enabled for initial setup - disable if not needed
- WiFi passwords are stored in plain text during build - use secure build
  environment
- Default configurations should be modified for production use
- Consider using environment-specific Discord tokens and channels
- The service runs with limited privileges for security
