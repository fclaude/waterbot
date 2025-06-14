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

# Update system
print_status "Updating system..."
apt-get update
apt-get upgrade -y

# Install required packages
print_status "Installing required packages..."
apt-get install -y \
    python3-pip \
    python3-venv \
    signal-cli \
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
print_status "Installing Python dependencies..."
pip install -r requirements.txt

# Copy configuration
print_status "Setting up configuration..."
mv /root/waterbot.env /opt/waterbot/.env
chown waterbot-service:waterbot-service /opt/waterbot/.env
chmod 600 /opt/waterbot/.env

# Setup Signal CLI
print_status "Setting up Signal CLI..."
# Note: You'll need to manually register the phone number and verify it
# This is a security measure to prevent automated registration

# Create systemd service
print_status "Creating systemd service..."
cat > /etc/systemd/system/waterbot.service << 'EOF'
[Unit]
Description=WaterBot Signal GPIO Controller
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=waterbot-service
Group=waterbot-service
WorkingDirectory=/opt/waterbot
Environment=PATH=/opt/waterbot/venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/opt/waterbot/venv/bin/python -m waterbot.bot

Restart=always
RestartSec=10
StartLimitInterval=60
StartLimitBurst=3

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/waterbot

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

print_status "Setup complete! Please follow these steps:"
echo "1. Register your Signal phone number:"
echo "   signal-cli -u YOUR_PHONE_NUMBER register"
echo "2. Verify your phone number:"
echo "   signal-cli -u YOUR_PHONE_NUMBER verify CODE"
echo "3. Check service status:"
echo "   systemctl status waterbot.service"
echo "4. View logs:"
echo "   journalctl -u waterbot.service -f"
