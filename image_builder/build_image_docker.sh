#!/bin/bash

set -e

# Configuration
RASPBERRY_PI_OS_URL="https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2023-05-03/2023-05-03-raspios-bullseye-arm64-lite.img.xz"
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
if [ ! -f "configs/${CONFIG_NAME}.env" ]; then
    print_error "Configuration ${CONFIG_NAME} not found in configs directory"
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

# Download Raspberry Pi OS if not exists
if [ ! -f "${IMAGE_NAME}.xz" ]; then
    print_status "Downloading Raspberry Pi OS..."
    if ! wget "${RASPBERRY_PI_OS_URL}" -O "${IMAGE_NAME}.xz"; then
        print_warning "Certificate verification failed, retrying with --no-check-certificate..."
        wget --no-check-certificate "${RASPBERRY_PI_OS_URL}" -O "${IMAGE_NAME}.xz"
    fi
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
cp "configs/${CONFIG_NAME}.env" "${MOUNT_POINT}/root/waterbot.env"

# Create enhanced firstboot script with network resilience and filesystem expansion
cat > "${MOUNT_POINT}/root/firstboot.sh" << 'EOF'
#!/bin/bash
cd /root

echo "WaterBot First Boot Setup"
echo "========================="

# Expand filesystem to use full SD card
echo "Expanding filesystem to use full SD card..."
/usr/bin/raspi-config --expand-rootfs

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

echo "First boot setup complete. Rebooting to apply filesystem expansion..."
rm firstboot.sh
reboot
EOF

chmod +x "${MOUNT_POINT}/root/firstboot.sh"

# Add firstboot to rc.local
sed -i '/exit 0/i /root/firstboot.sh &' "${MOUNT_POINT}/etc/rc.local"

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
