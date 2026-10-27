#!/bin/bash
# =============================================================
# scripts/install_service.sh
# Purpose: Installs Digital Spotter as a systemd service
#          so it autostarts on every boot.
# Usage:   bash scripts/install_service.sh
# Author:  bimalawijekoon
# =============================================================

set -e

SERVICE_NAME="digitalspotter"
SERVICE_FILE="$(dirname "$0")/digital-spotter.service"
SYSTEMD_DIR="/etc/systemd/system"

echo "======================================"
echo " Digital Spotter — Service Installer"
echo "======================================"

# Check we are running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo "[!] Please run with sudo:"
    echo "    sudo bash scripts/install_service.sh"
    exit 1
fi

# Copy service file to systemd directory
echo "[1/4] Installing service file to $SYSTEMD_DIR..."
cp "$SERVICE_FILE" "$SYSTEMD_DIR/$SERVICE_NAME.service"
chmod 644 "$SYSTEMD_DIR/$SERVICE_NAME.service"

# Reload systemd daemon to recognise new service
echo "[2/4] Reloading systemd daemon..."
systemctl daemon-reload

# Enable service to start on boot
echo "[3/4] Enabling $SERVICE_NAME to start on boot..."
systemctl enable "$SERVICE_NAME"

# Start the service right now
echo "[4/4] Starting $SERVICE_NAME now..."
systemctl start "$SERVICE_NAME"

echo ""
echo "======================================"
echo " ✓ Done! Digital Spotter is running."
echo "======================================"
echo ""
DEVICE_ADDRESS="${DS_DEVICE_ADDRESS:-}"
if [ -z "$DEVICE_ADDRESS" ] && command -v tailscale >/dev/null 2>&1; then
    DEVICE_ADDRESS="$(tailscale ip -4 2>/dev/null | head -n 1)"
fi
if [ -z "$DEVICE_ADDRESS" ]; then
    DEVICE_ADDRESS="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
DEVICE_ADDRESS="${DEVICE_ADDRESS:-<pi-address>}"
echo " Dashboard : http://$DEVICE_ADDRESS:8000/"
echo " Health    : http://$DEVICE_ADDRESS:8000/health"
echo ""
echo " Useful commands:"
echo "   Check status  : sudo systemctl status $SERVICE_NAME"
echo "   View logs     : journalctl -u $SERVICE_NAME -f"
echo "   Stop service  : sudo systemctl stop $SERVICE_NAME"
echo "   Restart       : sudo systemctl restart $SERVICE_NAME"
echo "   Disable boot  : sudo systemctl disable $SERVICE_NAME"
echo "======================================"
