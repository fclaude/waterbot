#!/bin/bash

# Cross-platform image builder for WaterBot
# This script builds Raspberry Pi images using Docker (works on macOS, Linux, Windows)

set -e

# Configuration
CONFIG_NAME="${1:-default}"
WIFI_SSID="${2:-}"
WIFI_PASSWORD="${3:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print status messages
print_status() {
    echo -e "${GREEN}[+] $1${NC}"
}

# Function to print info messages
print_info() {
    echo -e "${BLUE}[i] $1${NC}"
}

# Function to print warning messages
print_warning() {
    echo -e "${YELLOW}[!] $1${NC}"
}

# Function to print error messages
print_error() {
    echo -e "${RED}[!] $1${NC}"
}

# Function to show usage
show_usage() {
    echo "WaterBot Cross-Platform Image Builder"
    echo "=====================================  "
    echo ""
    echo "Usage: $0 [config_name] [wifi_ssid] [wifi_password]"
    echo ""
    echo "This script uses Docker to build Raspberry Pi images on any platform."
    echo "No sudo privileges required - just Docker!"
    echo ""
    echo "Arguments:"
    echo "  config_name   - Configuration file to use (default: 'default')"
    echo "  wifi_ssid     - WiFi network name (optional)"
    echo "  wifi_password - WiFi network password (optional)"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Use default config, no WiFi"
    echo "  $0 home                              # Use home.env config, no WiFi"
    echo "  $0 default MyWiFi MyPassword         # Use default config with WiFi"
    echo "  $0 home \"My Network\" \"My Password\"   # Use home config with WiFi (spaces in quotes)"
    echo ""
    echo "Available configurations:"
    find configs/ -name "*.env" 2>/dev/null | sed 's|configs/||g' | sed 's|\.env||g' | sed 's/^/  - /' || echo "  No configurations found"
    echo ""
    echo "Supported platforms: macOS, Linux, Windows (with Docker)"
}

# Check if help requested
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    show_usage
    exit 0
fi

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed or not available in PATH"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        print_info "Please install Docker Desktop for macOS from: https://www.docker.com/products/docker-desktop"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        print_info "Please install Docker from: https://docs.docker.com/engine/install/"
    else
        print_info "Please install Docker from: https://docs.docker.com/get-docker/"
    fi
    exit 1
fi

# Check if Docker is running
if ! docker info &> /dev/null; then
    print_error "Docker is not running"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        print_info "Please start Docker Desktop and try again"
    else
        print_info "Please start the Docker service:"
        print_info "  sudo systemctl start docker"
        print_info "Or start Docker Desktop if using the desktop version"
    fi
    exit 1
fi

# Check if config exists
if [ ! -f "configs/${CONFIG_NAME}.env" ]; then
    print_error "Configuration '${CONFIG_NAME}' not found in configs directory"
    print_info "Available configurations:"
    find configs/ -name "*.env" 2>/dev/null | sed 's|configs/||g' | sed 's|\.env||g' | sed 's/^/  - /' || echo "  No configurations found"
    exit 1
fi

# Get absolute path to project root
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

print_status "WaterBot Raspberry Pi Image Builder (Docker)"
print_info "Configuration: ${CONFIG_NAME}"
if [ -n "$WIFI_SSID" ]; then
    print_info "WiFi Network: ${WIFI_SSID}"
    if [ -z "$WIFI_PASSWORD" ]; then
        print_warning "WiFi SSID provided but no password. WiFi will not be configured."
        WIFI_SSID=""
    fi
else
    print_info "WiFi: Not configured (manual setup required)"
fi

# Build Docker image
print_status "Building Docker image..."
docker build -t waterbot-image-builder .

# Create output directory
mkdir -p output

# Run the image builder in Docker
print_status "Running image builder in Docker container..."
docker run --rm --privileged \
    -v "${PROJECT_ROOT}:/waterbot:ro" \
    -v "$(pwd)/output:/builder/output" \
    -e WIFI_SSID="$WIFI_SSID" \
    -e WIFI_PASSWORD="$WIFI_PASSWORD" \
    waterbot-image-builder "$CONFIG_NAME"

# Move the generated image to output directory
if [ -f "output/waterbot.img" ]; then
    print_status "Image built successfully!"
    print_info "Output location: $(pwd)/output/waterbot.img"

    # Show image size
    IMAGE_SIZE=$(du -h "output/waterbot.img" | cut -f1)
    print_info "Image size: $IMAGE_SIZE"

    print_status "Next steps:"
    echo "1. Insert your SD card"

    # Platform-specific instructions
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "2. Find your SD card device:"
        echo "   diskutil list"
        echo "3. Unmount the SD card (replace diskX with your device):"
        echo "   diskutil unmountDisk /dev/diskX"
        echo "4. Write the image to SD card:"
        echo "   sudo dd if=output/waterbot.img of=/dev/rdiskX bs=1m"
        echo "   (Use 'rdiskX' instead of 'diskX' for faster writing on macOS)"
        echo "5. Eject the SD card:"
        echo "   diskutil eject /dev/diskX"
    else
        echo "2. Find your SD card device:"
        echo "   lsblk"
        echo "3. Unmount the SD card (replace sdX with your device):"
        echo "   sudo umount /dev/sdX*"
        echo "4. Write the image to SD card:"
        echo "   sudo dd if=output/waterbot.img of=/dev/sdX bs=4M status=progress"
        echo "5. Safely remove the SD card:"
        echo "   sync && sudo eject /dev/sdX"
    fi

    if [ -n "$WIFI_SSID" ]; then
        print_status "WiFi is pre-configured. The Pi will connect to '$WIFI_SSID' automatically."
    else
        print_warning "WiFi is not configured. You'll need to set up WiFi manually or use Ethernet."
    fi

    print_status "After first boot, the WaterBot service will start automatically."
    print_info "You can check service status with: systemctl status waterbot.service"

else
    print_error "Image generation failed. Check the output above for errors."
    exit 1
fi
