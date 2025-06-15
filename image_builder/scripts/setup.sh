#!/bin/bash

set -e

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

# Check if we're in offline mode
if [ "${OFFLINE_MODE:-}" = "true" ]; then
    print_warning "Running in offline mode - skipping system updates and package installation"
    print_warning "Make sure all required packages are pre-installed in the base image"
else
    # Update system with retries
    print_status "Updating system..."
    UPDATE_SUCCESS=false
    for i in {1..3}; do
        if apt-get update; then
            UPDATE_SUCCESS=true
            break
        else
            print_warning "System update attempt $i failed, retrying..."
            sleep 5
        fi
    done

    if [ "$UPDATE_SUCCESS" = "false" ]; then
        print_warning "All system update attempts failed - continuing in offline mode"
        OFFLINE_MODE=true
    else
        # Upgrade system packages
        print_status "Upgrading system packages..."
        apt-get upgrade -y || print_warning "System upgrade had some issues, continuing..."

        # Install required packages with error handling
        print_status "Installing required packages..."
        PACKAGES=(
            "python3-pip"
            "python3-venv"
            "git"
            "libasound2-dev"
            "libdbus-1-dev"
            "libglib2.0-dev"
            "libpulse-dev"
            "libssl-dev"
            "libsystemd-dev"
            "libunwind-dev"
            "libzstd-dev"
            "pkg-config"
            "build-essential"
        )

        FAILED_PACKAGES=()
        for package in "${PACKAGES[@]}"; do
            if ! apt-get install -y "$package"; then
                print_warning "Failed to install $package"
                FAILED_PACKAGES+=("$package")
            fi
        done

        if [ ${#FAILED_PACKAGES[@]} -gt 0 ]; then
            print_warning "Some packages failed to install: ${FAILED_PACKAGES[*]}"
            print_warning "Service may not work properly"
        fi
    fi
fi

# Create waterbot user
print_status "Creating waterbot user..."
if ! id "waterbot-service" &>/dev/null; then
    useradd -r -s /bin/false -d /opt/waterbot waterbot-service
fi
usermod -a -G gpio,dialout waterbot-service

# Create application directory
print_status "Setting up application directory..."
mkdir -p /opt/waterbot
chown waterbot-service:waterbot-service /opt/waterbot

# Copy local files
print_status "Copying WaterBot files..."
cp -r /root/waterbot/* /opt/waterbot/
chown -R waterbot-service:waterbot-service /opt/waterbot

# Create and activate virtual environment
print_status "Setting up Python virtual environment..."
cd /opt/waterbot

# Check if python3-venv is available
if ! python3 -m venv --help >/dev/null 2>&1; then
    print_warning "python3-venv not available, trying alternative installation..."

    # Try to install python3-venv specifically - but don't fail if offline
    if apt-get update && apt-get install -y python3-venv; then
        print_status "python3-venv installed successfully"
    else
        print_warning "Cannot install python3-venv (possibly offline). Virtual environment creation may fail."
        print_warning "WaterBot may not work properly without a virtual environment."
        OFFLINE_MODE=true
    fi
fi

# Create virtual environment with error handling
if python3 -m venv venv; then
    print_status "Virtual environment created successfully"
    chown -R waterbot-service:waterbot-service venv
    # shellcheck disable=SC1091
    . venv/bin/activate
else
    print_warning "Failed to create virtual environment"
    print_warning "Continuing without virtual environment (dependencies may conflict)"
    OFFLINE_MODE=true
fi

# Install system dependencies for GPIO
print_status "Installing system dependencies for GPIO..."
if [ "${OFFLINE_MODE:-}" != "true" ]; then
    if apt-get update && apt-get install -y pigpio python3-pigpio; then
        print_status "GPIO dependencies installed successfully"
    else
        print_warning "Failed to install GPIO dependencies - GPIO may not work properly"
    fi
else
    print_warning "Offline mode: Skipping GPIO dependency installation"
fi

# Install dependencies
if [ "${OFFLINE_MODE:-}" = "true" ]; then
    print_warning "Offline mode: Skipping pip install. Dependencies must be pre-installed."
else
    print_status "Installing Python dependencies..."
    if ! pip install -r /opt/waterbot/requirements.txt; then
        print_warning "Failed to install Python dependencies - service may not work properly"
    fi
fi

# Copy configuration
print_status "Setting up configuration..."
print_status "DEBUG: Contents of /root directory:"
ls -la /root/

print_status "DEBUG: Looking for waterbot.env..."
if [ -f /root/waterbot.env ]; then
    print_status "Found waterbot.env, size: $(wc -c < /root/waterbot.env) bytes"
    print_status "First few lines:"
    head -3 /root/waterbot.env || true

    mv /root/waterbot.env /opt/waterbot/.env
    chown waterbot-service:waterbot-service /opt/waterbot/.env
    chmod 600 /opt/waterbot/.env
    print_status "Configuration file copied successfully"
else
    print_error "Configuration file /root/waterbot.env not found!"
    print_error "Available .env and .txt files in /root:"
    find /root -maxdepth 1 \( -name "*.env" -o -name "*.txt" \) -exec ls -la {} \; 2>/dev/null || echo "No .env or .txt files found"
    print_error "All files in /root:"
    find /root -maxdepth 1 -type f -exec ls -la {} \;
    exit 1
fi

# Setup Signal CLI
print_status "Setting up Signal CLI..."
# Note: You'll need to manually register the phone number and verify it
# This is a security measure to prevent automated registration

# Create systemd service with network resilience
print_status "Creating systemd service..."

# Determine Python executable and path
if [ -d "/opt/waterbot/venv" ]; then
    PYTHON_EXEC="/opt/waterbot/venv/bin/python"
    PYTHON_PATH="/opt/waterbot/venv/bin:/usr/local/bin:/usr/bin:/bin"
else
    PYTHON_EXEC="/usr/bin/python3"
    PYTHON_PATH="/usr/local/bin:/usr/bin:/bin"
    print_warning "Using system Python (no virtual environment available)"
fi

cat > /etc/systemd/system/waterbot.service << EOF
[Unit]
Description=WaterBot Discord GPIO Controller
After=network.target
Wants=network-online.target pigpiod.service

[Service]
Type=simple
User=waterbot-service
Group=waterbot-service
WorkingDirectory=/opt/waterbot
Environment=PATH=${PYTHON_PATH}
ExecStart=${PYTHON_EXEC} -m waterbot.bot

# Restart configuration for network resilience
Restart=always
RestartSec=30
StartLimitInterval=300
StartLimitBurst=5

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
EOF

# Enable and configure pigpiod service
print_status "Configuring pigpiod service..."
if systemctl enable pigpiod; then
    print_status "pigpiod service enabled successfully"
else
    print_warning "Failed to enable pigpiod service - may need manual configuration"
fi

# Create IP display script
print_status "Creating IP display script..."
cat > /usr/local/bin/show-ip.sh << 'EOF'
#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}      WaterBot IP Information${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Display IP addresses
found_ip=false
for iface in /sys/class/net/*; do
    iface=$(basename "$iface")
    [ "$iface" = "lo" ] && continue
    ip_addr=$(ip addr show "$iface" 2>/dev/null | grep -o 'inet [0-9.]*' | head -1 | cut -d' ' -f2)
    if [ -n "$ip_addr" ] && [ "$ip_addr" != "127.0.0.1" ]; then
        echo -e "${BLUE}SSH to this device:${NC}"
        echo -e "  ssh pi@${ip_addr}"
        echo -e "${BLUE}Interface:${NC} $iface"
        echo ""
        found_ip=true
    fi
done

if [ "$found_ip" = false ]; then
    echo "No network interfaces found with IP addresses."
    echo "Please check your network connection."
    echo ""
fi

echo -e "${GREEN}Default credentials:${NC}"
echo "  Username: pi"
echo "  Password: raspberry"
echo ""
echo -e "${GREEN}Service status:${NC}"
systemctl is-active --quiet waterbot.service && echo "  WaterBot service: Running" || echo "  WaterBot service: Not running"
echo ""
echo -e "${GREEN}================================${NC}"
echo ""
EOF

chmod +x /usr/local/bin/show-ip.sh

# Create systemd service for IP display
cat > /etc/systemd/system/show-ip.service << 'EOF'
[Unit]
Description=Display IP Address Information
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'sleep 10 && /usr/local/bin/show-ip.sh'
StandardOutput=journal+console

[Install]
WantedBy=multi-user.target
EOF

# Enable IP display service
systemctl daemon-reload
systemctl enable show-ip.service

# Enable service (but don't start it during setup)
print_status "Enabling service..."
systemctl enable waterbot.service

print_status "Setup complete!"
echo ""
print_status "WaterBot has been installed and configured as a system service."
echo "The service will start automatically and restart if it fails."
echo ""
print_status "System information:"
echo "- Filesystem expanded to use full SD card capacity"
echo "- SSH enabled for remote access"
echo "- Service will start after reboot"
echo ""

# Display IP addresses
print_status "Network information:"
for iface in /sys/class/net/*; do
    iface=$(basename "$iface")
    [ "$iface" = "lo" ] && continue
    ip_addr=$(ip addr show "$iface" 2>/dev/null | grep -o 'inet [0-9.]*' | head -1 | cut -d' ' -f2)
    if [ -n "$ip_addr" ] && [ "$ip_addr" != "127.0.0.1" ]; then
        echo "- $iface: $ip_addr"
    fi
done

echo ""
print_status "Network resilience features:"
echo "- Service continues running even without internet connection"
echo "- Scheduled tasks work offline"
echo "- Discord bot reconnects automatically when network returns"
echo ""
print_status "Useful commands:"
echo "- Check service status: systemctl status waterbot.service"
echo "- View logs: journalctl -u waterbot.service -f"
echo "- Restart service: systemctl restart waterbot.service"
echo "- Check disk usage: df -h"
echo ""
if [ "${OFFLINE_MODE:-}" = "true" ]; then
    print_warning "Setup completed in offline mode. Some features may not work until network is available."
fi
