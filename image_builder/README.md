# WaterBot Image Builder

This tool helps you create pre-configured Raspberry Pi OS images for WaterBot. It automates the
installation and configuration process, allowing you to quickly deploy WaterBot to multiple
Raspberry Pi devices. The image is created using local files, so no internet connection is
required on the target Raspberry Pi.

## Prerequisites

- Linux system with root access
- `wget` for downloading the Raspberry Pi OS image
- `xz` for extracting the image
- `dd` for writing the image to SD card

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

1. Create your configuration:
   - Copy `configs/default.env` to a new file (e.g., `configs/my_config.env`)
   - Modify the settings as needed

2. Build the image:
   ```bash
   sudo ./build_image.sh [config_name]
   ```
   If no config name is provided, it will use `default.env`

3. Write the image to SD card:
   ```bash
   sudo dd if=waterbot.img of=/dev/sdX bs=4M status=progress
   ```
   Replace `/dev/sdX` with your SD card device (e.g., `/dev/sdb`)

4. Insert the SD card into your Raspberry Pi and boot it

5. After first boot, you'll need to:
   - Register your Signal phone number:
     ```bash
     signal-cli -u YOUR_PHONE_NUMBER register
     ```
   - Verify your phone number:
     ```bash
     signal-cli -u YOUR_PHONE_NUMBER verify CODE
     ```
   - Check the service status:
     ```bash
     systemctl status waterbot.service
     ```

## Configuration Files

Configuration files are stored in the `configs/` directory. Each file should be named `[name].env`
and contain the following settings:

- `SIGNAL_PHONE_NUMBER`: Your bot's Signal phone number
- `SIGNAL_GROUP_ID`: The Signal group ID where the bot will operate
- `OPERATION_MODE`: Either `rpi` or `emulation`
- Device to GPIO pin mappings
- Scheduling configuration
- Other WaterBot settings

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
