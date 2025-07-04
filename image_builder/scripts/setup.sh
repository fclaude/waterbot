#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[+] $1${NC}"
}

print_error() {
    echo -e "${RED}[!] $1${NC}"
}

# Sync system time before package operations
print_status "Syncing system time..."
# Set timezone to Pacific Time (common for SF/West Coast)
timedatectl set-timezone America/Los_Angeles
# Enable NTP and restart time sync service
timedatectl set-ntp true
systemctl restart systemd-timesyncd

# Wait for time sync with longer timeout and fallback
TIME_SYNCED=false
for ((i=1; i<=20; i++)); do
    if timedatectl status | grep -q "System clock synchronized: yes"; then
        print_status "System time synchronized successfully"
        TIME_SYNCED=true
        break
    fi
    sleep 3
done

# If NTP fails, try manual sync with common time servers
if [ "$TIME_SYNCED" = "false" ]; then
    print_status "NTP sync failed, trying manual time sync..."
    for server in "pool.ntp.org" "time.nist.gov" "0.pool.ntp.org"; do
        if ntpdate -s "$server" 2>/dev/null; then
            print_status "Time synchronized manually with $server"
            TIME_SYNCED=true
            break
        fi
    done
fi

if [ "$TIME_SYNCED" = "false" ]; then
    print_status "Warning: Time sync failed completely, packages may have certificate issues"
fi

# Update and install all packages
print_status "Updating system and installing packages..."
apt-get update
apt-get upgrade -y
apt-get install -y \
    python3-pip \
    python3-venv \
    git \
    python3-rpi.gpio \
    build-essential \
    ntpdate

# Create user
print_status "Creating waterbot user..."
useradd -r -s /bin/false -d /opt/waterbot waterbot-service || true
usermod -a -G gpio,dialout waterbot-service

# Create app directory and copy files
print_status "Setting up application..."
mkdir -p /opt/waterbot
cp -r /root/waterbot/* /opt/waterbot/
chown -R waterbot-service:waterbot-service /opt/waterbot

# Setup Python environment
print_status "Setting up Python environment..."
cd /opt/waterbot
python3 -m venv venv
chown -R waterbot-service:waterbot-service venv
./venv/bin/pip install -r requirements.txt

# Copy config
print_status "Setting up configuration..."
if [ -f /root/waterbot.env ]; then
    mv /root/waterbot.env /opt/waterbot/.env
    chown waterbot-service:waterbot-service /opt/waterbot/.env
    chmod 600 /opt/waterbot/.env
else
    print_error "Configuration file /root/waterbot.env not found!"
    exit 1
fi

# Copy schedules if available
print_status "Setting up schedules..."
if [ -f /root/schedules.json ]; then
    mv /root/schedules.json /opt/waterbot/schedules.json
    chown waterbot-service:waterbot-service /opt/waterbot/schedules.json
    chmod 644 /opt/waterbot/schedules.json
    print_status "Schedules file copied successfully"
else
    print_status "No schedules.json found, will start with empty schedules"
fi

# Create systemd service
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
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Enable services
print_status "Enabling services..."
systemctl daemon-reload
systemctl enable waterbot.service

print_status "Setup complete! Service will start on next boot."
