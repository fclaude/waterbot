#!/bin/bash

set -e

# Configuration
RASPBERRY_PI_OS_URL="https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2023-05-03/2023-05-03-raspios-bullseye-arm64-lite.img.xz"
IMAGE_NAME="waterbot.img"
MOUNT_POINT="/tmp/waterbot_mount"
CONFIG_NAME="${1:-default}"  # Use default config if none specified

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Function to print status messages
print_status() {
    echo -e "${GREEN}[+] $1${NC}"
}

# Function to print error messages
print_error() {
    echo -e "${RED}[!] $1${NC}"
}

# Function to cleanup
cleanup() {
    print_status "Cleaning up..."
    if mountpoint -q "${MOUNT_POINT}"; then
        umount "${MOUNT_POINT}"
    fi
    rm -rf "${MOUNT_POINT}"
}

# Set up trap to ensure cleanup happens on script exit
trap cleanup EXIT

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root"
    exit 1
fi

# Check if config exists
if [ ! -f "configs/${CONFIG_NAME}.env" ]; then
    print_error "Configuration ${CONFIG_NAME} not found in configs directory"
    exit 1
fi

# Create mount point
mkdir -p "${MOUNT_POINT}"

# Download Raspberry Pi OS if not exists
if [ ! -f "${IMAGE_NAME}.xz" ]; then
    print_status "Downloading Raspberry Pi OS..."
    wget "${RASPBERRY_PI_OS_URL}" -O "${IMAGE_NAME}.xz"
fi

# Extract image if not already extracted
if [ ! -f "${IMAGE_NAME}" ]; then
    print_status "Extracting image..."
    xz -d "${IMAGE_NAME}.xz"
fi

# Find the start of the second partition
PARTITION_START=$(fdisk -l "${IMAGE_NAME}" | grep "img2" | awk '{print $2}')

# Mount the image
print_status "Mounting image..."
mount -o loop,offset=$((PARTITION_START * 512)) "${IMAGE_NAME}" "${MOUNT_POINT}"

# Copy setup scripts
print_status "Copying setup scripts..."
cp scripts/* "${MOUNT_POINT}/root/"

# Copy local WaterBot files
print_status "Copying WaterBot files..."
mkdir -p "${MOUNT_POINT}/root/waterbot"
cp -r ../waterbot/* "${MOUNT_POINT}/root/waterbot/"

# Copy selected configuration
print_status "Copying configuration..."
cp "configs/${CONFIG_NAME}.env" "${MOUNT_POINT}/root/waterbot.env"

# Create firstboot script
cat > "${MOUNT_POINT}/root/firstboot.sh" << 'EOF'
#!/bin/bash
cd /root
chmod +x setup.sh
./setup.sh
rm firstboot.sh
reboot
EOF

chmod +x "${MOUNT_POINT}/root/firstboot.sh"

# Add firstboot to rc.local
sed -i '/exit 0/i /root/firstboot.sh &' "${MOUNT_POINT}/etc/rc.local"

# Unmount the image
print_status "Unmounting image..."
umount "${MOUNT_POINT}"

print_status "Image creation complete! You can now write ${IMAGE_NAME} to your SD card using:"
echo "sudo dd if=${IMAGE_NAME} of=/dev/sdX bs=4M status=progress"
echo "Replace /dev/sdX with your SD card device"
