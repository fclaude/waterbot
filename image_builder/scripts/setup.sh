#!/bin/bash

set -e

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

# Check if we're in offline mode
if [ "${OFFLINE_MODE:-}" = "true" ]; then
    print_warning "Running in offline mode - skipping system updates and package installation"
    print_warning "Make sure all required packages are pre-installed in the base image"
else
    # Update system
    print_status "Updating system..."
    if ! apt-get update; then
        print_warning "System update failed - continuing in offline mode"
        OFFLINE_MODE=true
    else
        apt-get upgrade -y

        # Install required packages
        print_status "Installing required packages..."
        apt-get install -y \
            python3-pip \
            python3-venv \
            git \
            libasound2-dev \
            libdbus-1-dev \
            libglib2.0-dev \
            libpulse-dev \
            libssl-dev \
            libsystemd-dev \
            libunwind-dev \
            libzstd-dev \
            pkg-config \
            build-essential
    fi
fi

# Create waterbot user
print_status "Creating waterbot user..."
useradd -r -s /bin/false -d /opt/waterbot waterbot-service
usermod -a -G gpio waterbot-service

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
python3 -m venv venv
chown -R waterbot-service:waterbot-service venv
# shellcheck disable=SC1091
. venv/bin/activate

# Install dependencies
if [ "${OFFLINE_MODE:-}" = "true" ]; then
    print_warning "Offline mode: Skipping pip install. Dependencies must be pre-installed."
else
    print_status "Installing Python dependencies..."
    if ! pip install -r requirements.txt; then
        print_warning "Failed to install Python dependencies - service may not work properly"
    fi
fi

# Copy configuration
print_status "Setting up configuration..."
mv /root/waterbot.env /opt/waterbot/.env
chown waterbot-service:waterbot-service /opt/waterbot/.env
chmod 600 /opt/waterbot/.env

# Setup Signal CLI
print_status "Setting up Signal CLI..."
# Note: You'll need to manually register the phone number and verify it
# This is a security measure to prevent automated registration

# Create systemd service with network resilience
print_status "Creating systemd service..."
cat > /etc/systemd/system/waterbot.service << 'EOF'
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
ExecStart=/opt/waterbot/venv/bin/python -m waterbot.bot

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

# Enable and start service
print_status "Enabling and starting service..."
systemctl daemon-reload
systemctl enable waterbot.service
systemctl start waterbot.service

print_status "Setup complete!"
echo ""
print_status "WaterBot has been installed and configured as a system service."
echo "The service will start automatically and restart if it fails."
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
echo ""
if [ "${OFFLINE_MODE:-}" = "true" ]; then
    print_warning "Setup completed in offline mode. Some features may not work until network is available."
fi
