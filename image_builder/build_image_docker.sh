#!/bin/bash

set -e

# Configuration
RASPBERRY_PI_OS_URL="https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz"
IMAGE_NAME="waterbot.img"
MOUNT_POINT="/tmp/waterbot_mount"
CONFIG_NAME="${1:-default}"  # Use default config if none specified

# WiFi configuration (can be passed as environment variables)
WIFI_SSID="${WIFI_SSID:-}"
WIFI_PASSWORD="${WIFI_PASSWORD:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status messages
print_status() {
    echo -e "${GREEN}[+] $1${NC}"
}

# Function to print warning messages
print_warning() {
    echo -e "${YELLOW}[!] $1${NC}"
}

# Function to print error messages
print_error() {
    echo -e "${RED}[!] $1${NC}"
}

# Function to cleanup
cleanup() {
    print_status "Cleaning up..."
    if mountpoint -q "${MOUNT_POINT}" 2>/dev/null; then
        umount "${MOUNT_POINT}" || true
    fi
    if mountpoint -q "${MOUNT_POINT}/boot" 2>/dev/null; then
        umount "${MOUNT_POINT}/boot" || true
    fi
    rm -rf "${MOUNT_POINT}"
}

# Set up trap to ensure cleanup happens on script exit
trap cleanup EXIT

# Check if config exists
if [ ! -f "/waterbot/image_builder/configs/${CONFIG_NAME}.env" ]; then
    print_error "Configuration ${CONFIG_NAME} not found in configs directory"
    print_error "Looking for: /waterbot/image_builder/configs/${CONFIG_NAME}.env"
    print_error "Available configs:"
    ls -la /waterbot/image_builder/configs/ 2>/dev/null || echo "Configs directory not found!"
    exit 1
fi

# Check if waterbot source exists
if [ ! -d "/waterbot" ]; then
    print_error "WaterBot source code not found at /waterbot"
    print_error "Make sure to mount the waterbot directory when running the container"
    exit 1
fi

# Create mount point
mkdir -p "${MOUNT_POINT}"

# Set up image cache directory (persistent across builds)
CACHE_DIR="/builder/cache"
mkdir -p "${CACHE_DIR}"

# Get the base filename from URL for caching
BASE_IMAGE_NAME=$(basename "${RASPBERRY_PI_OS_URL}")
CACHED_IMAGE="${CACHE_DIR}/${BASE_IMAGE_NAME}"

# Download Raspberry Pi OS to cache if not exists
if [ ! -f "${CACHED_IMAGE}" ]; then
    print_status "Downloading Raspberry Pi OS to cache..."
    if ! wget "${RASPBERRY_PI_OS_URL}" -O "${CACHED_IMAGE}"; then
        print_warning "Certificate verification failed, retrying with --no-check-certificate..."
        wget --no-check-certificate "${RASPBERRY_PI_OS_URL}" -O "${CACHED_IMAGE}"
    fi
    print_status "Image cached at: ${CACHED_IMAGE}"
else
    print_status "Using cached Raspberry Pi OS image"
fi

# Copy cached image to working directory if needed
if [ ! -f "${IMAGE_NAME}.xz" ]; then
    print_status "Copying cached image to working directory..."
    cp "${CACHED_IMAGE}" "${IMAGE_NAME}.xz"
fi

# Extract image if not already extracted
if [ ! -f "${IMAGE_NAME}" ]; then
    print_status "Extracting image..."
    xz -d "${IMAGE_NAME}.xz"
fi

# Get partition information
print_status "Analyzing image partitions..."
PARTITION_INFO=$(fdisk -l "${IMAGE_NAME}")
BOOT_PARTITION_START=$(echo "$PARTITION_INFO" | grep "img1" | awk '{print $2}')
ROOT_PARTITION_START=$(echo "$PARTITION_INFO" | grep "img2" | awk '{print $2}')

# Mount the boot partition first (for WiFi config)
print_status "Mounting boot partition..."
mkdir -p "${MOUNT_POINT}/boot"
mount -o loop,offset=$((BOOT_PARTITION_START * 512)) "${IMAGE_NAME}" "${MOUNT_POINT}/boot"

# Configure default user (bypass initial setup)
print_status "Configuring default user account..."
# Create default user 'pi' with password 'raspberry' (generate hash dynamically)
PASSWORD_HASH=$(echo 'raspberry' | openssl passwd -6 -stdin)
echo "pi:${PASSWORD_HASH}" > "${MOUNT_POINT}/boot/userconf.txt"
print_status "Default user 'pi' configured with password 'raspberry'"

# Enable SSH
touch "${MOUNT_POINT}/boot/ssh"

# Configure WiFi if credentials provided
if [ -n "$WIFI_SSID" ] && [ -n "$WIFI_PASSWORD" ]; then
    print_status "Configuring WiFi network: $WIFI_SSID"

    # Create wpa_supplicant.conf
    cat > "${MOUNT_POINT}/boot/wpa_supplicant.conf" << EOF
country=US
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="$WIFI_SSID"
    psk="$WIFI_PASSWORD"
    key_mgmt=WPA-PSK
}
EOF

    print_status "WiFi configuration added for network: $WIFI_SSID"
else
    print_warning "No WiFi credentials provided. Set WIFI_SSID and WIFI_PASSWORD environment variables to configure WiFi."
    print_warning "The Pi will need manual WiFi configuration or ethernet connection."
fi

# Unmount boot partition
umount "${MOUNT_POINT}/boot"

# Mount the root partition
print_status "Mounting root partition..."
mount -o loop,offset=$((ROOT_PARTITION_START * 512)) "${IMAGE_NAME}" "${MOUNT_POINT}"

# Copy setup scripts
print_status "Copying setup scripts..."
cp scripts/* "${MOUNT_POINT}/root/"

# Copy local WaterBot files
print_status "Copying WaterBot files..."
mkdir -p "${MOUNT_POINT}/root/waterbot"
# Copy files while excluding img files and output directory
rsync -av --exclude='*.img' --exclude='output/' /waterbot/ "${MOUNT_POINT}/root/waterbot/"

# Copy selected configuration
print_status "Copying configuration..."
print_status "Source config: /waterbot/image_builder/configs/${CONFIG_NAME}.env"
print_status "Destination: ${MOUNT_POINT}/root/waterbot.env"

if [ -f "/waterbot/image_builder/configs/${CONFIG_NAME}.env" ]; then
    print_status "Source config file exists, copying..."
    cp "/waterbot/image_builder/configs/${CONFIG_NAME}.env" "${MOUNT_POINT}/root/waterbot.env"

    # Verify the copy worked
    if [ -f "${MOUNT_POINT}/root/waterbot.env" ]; then
        print_status "Configuration file copied successfully"
        print_status "File size: $(wc -c < "${MOUNT_POINT}/root/waterbot.env") bytes"
        print_status "First few lines of config:"
        head -3 "${MOUNT_POINT}/root/waterbot.env" || true
    else
        print_error "Configuration file copy failed!"
        exit 1
    fi
else
    print_error "Source configuration file not found!"
    exit 1
fi

# Copy schedules.json if it exists
print_status "Copying schedules configuration..."
if [ -f "/waterbot/image_builder/configs/schedules.json" ]; then
    print_status "Copying schedules.json to image..."
    cp "/waterbot/image_builder/configs/schedules.json" "${MOUNT_POINT}/root/schedules.json"
    print_status "Schedules file copied successfully"
else
    print_status "No schedules.json found, will start with empty schedules"
fi

# Create two-phase firstboot script
cat > "${MOUNT_POINT}/root/firstboot.sh" << 'EOF'
#!/bin/bash
cd /root

# Check if we've already completed everything
if [ -f /root/.setup_complete ]; then
    exit 0
fi

echo "WaterBot Boot Setup"
echo "=================="

# Phase 1: Filesystem expansion (first boot)
if [ ! -f /root/.filesystem_expanded ]; then
    echo "Phase 1: Expanding filesystem to use full SD card..."
    /usr/bin/raspi-config --expand-rootfs

    # Mark filesystem expansion as done
    touch /root/.filesystem_expanded

    echo "Filesystem expansion complete. Rebooting..."
    reboot
    exit 0
fi

# Phase 2: Software installation and configuration (second boot)
echo "Phase 2: Installing and configuring WaterBot..."

chmod +x setup.sh

# Wait for network (with timeout)
echo "Waiting for network connection..."
for i in {1..30}; do
    if ping -c 1 8.8.8.8 &> /dev/null; then
        echo "Network connection established"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "Warning: No network connection detected. Proceeding with offline setup..."
        export OFFLINE_MODE=true
    fi
    sleep 2
done

./setup.sh

# Mark setup as complete
touch /root/.setup_complete
echo "WaterBot setup complete!"

# Remove firstboot from rc.local
sed -i '/firstboot.sh/d' /etc/rc.local

# Remove the firstboot script and markers
rm -f /root/firstboot.sh
rm -f /root/.filesystem_expanded

echo "System ready. WaterBot service will start on next boot."
EOF

chmod +x "${MOUNT_POINT}/root/firstboot.sh"

# Add firstboot to rc.local with file locking to prevent concurrent execution
sed -i '/exit 0/i [ -f /root/firstboot.sh ] && flock -n /var/lock/firstboot.lock /root/firstboot.sh' "${MOUNT_POINT}/etc/rc.local"

# Final verification before unmounting
print_status "Final verification - files in /root before unmounting:"
ls -la "${MOUNT_POINT}/root/"
if [ -f "${MOUNT_POINT}/root/waterbot.env" ]; then
    print_status "✓ waterbot.env present in final image"
    print_status "File size: $(wc -c < "${MOUNT_POINT}/root/waterbot.env") bytes"
else
    print_error "✗ waterbot.env missing from final image!"
    print_error "This will cause the service to fail on boot"
fi

# Unmount the image
print_status "Unmounting image..."
umount "${MOUNT_POINT}"

# Copy image to output directory if it exists
if [ -d "/builder/output" ]; then
    print_status "Copying image to output directory..."
    cp "${IMAGE_NAME}" "/builder/output/"
fi

print_status "Image creation complete!"
print_status "Output: ${IMAGE_NAME}"
print_status ""
print_status "You can now write this image to your SD card using:"
echo "  sudo dd if=${IMAGE_NAME} of=/dev/sdX bs=4M status=progress"
echo "  Replace /dev/sdX with your SD card device"
print_status "Login credentials:"
echo "  Username: pi"
echo "  Password: raspberry"
echo "  SSH is enabled by default"
print_status ""
if [ -n "$WIFI_SSID" ]; then
    print_status "WiFi is pre-configured for network: $WIFI_SSID"
    print_status "The Pi will connect automatically on first boot"
else
    print_warning "No WiFi configured. You'll need to:"
    echo "  1. Connect via Ethernet, or"
    echo "  2. Manually configure WiFi after booting"
fi

print_status "After first boot, the WaterBot service will start automatically."
echo "You can check service status with: systemctl status waterbot.service"
print_warning "IMPORTANT: Change the default password after first login for security!"
