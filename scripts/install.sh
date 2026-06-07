#!/usr/bin/env bash
# ─────────────────────────────────────────────────
# ABWTorrent — Automated Installation Script
# Run as root on the target Debian server.
# ─────────────────────────────────────────────────
set -euo pipefail

INSTALL_DIR="/opt/abwtorrent"
CONFIG_DIR="/etc/abwtorrent"
LOG_DIR="/var/log/abwtorrent"
LAN_SUBNET="172.16.0.0/16"

# Source directory (where this script lives)
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "╔══════════════════════════════════════╗"
echo "║    ABWTorrent Installer v1.0         ║"
echo "║                                      ║"
echo "║    Credits:                          ║"
echo "║    Adem Karagöz (Main Programmer)    ║"
echo "║    Dominic Naumann                   ║"
echo "║    Sönke Einnolf                     ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. System packages ──────────────────────────
echo "> Installing system packages..."
apt-get update -qq
apt-get install -y -qq transmission-daemon python3 python3-venv python3-pip ufw

# ── 2. Stop Transmission (so settings.json isn't overwritten) ──
echo "> Stopping transmission-daemon..."
systemctl stop transmission-daemon 2>/dev/null || true

# ── 3. Create directories ───────────────────────
echo "> Creating directories..."
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR"
chown debian-transmission:debian-transmission "$LOG_DIR"

# ── 4. Copy application files ───────────────────
echo "> Copying application files to $INSTALL_DIR..."
cp "$SRC_DIR/watchdog_service.py" "$INSTALL_DIR/"
cp "$SRC_DIR/web_ui.py"           "$INSTALL_DIR/"
cp "$SRC_DIR/requirements.txt"    "$INSTALL_DIR/"
cp -r "$SRC_DIR/lib"              "$INSTALL_DIR/"
cp -r "$SRC_DIR/templates"        "$INSTALL_DIR/"
cp -r "$SRC_DIR/static"           "$INSTALL_DIR/"

# ── 5. Install Python venv + deps ───────────────
echo "> Setting up Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# ── 6. Configuration ────────────────────────────
if [ ! -f "$CONFIG_DIR/abwtorrent.conf" ]; then
    echo "> Installing default configuration..."
    cp "$SRC_DIR/abwtorrent.conf" "$CONFIG_DIR/"
else
    echo "> Configuration already exists — skipping."
fi

# ── 7. Transmission configuration ───────────────
echo "> Installing Transmission settings..."
TRANS_CONFIG_DIR="/var/lib/transmission-daemon/info"
mkdir -p "$TRANS_CONFIG_DIR"
cp "$SRC_DIR/transmission/settings.json" "$TRANS_CONFIG_DIR/settings.json"
chown -R debian-transmission:debian-transmission "$TRANS_CONFIG_DIR"

# ── 8. Systemd services ─────────────────────────
echo "> Installing systemd services..."

# Transmission override
mkdir -p /etc/systemd/system/transmission-daemon.service.d/
cp "$SRC_DIR/systemd/transmission-daemon.service.d/override.conf" \
   /etc/systemd/system/transmission-daemon.service.d/override.conf

# ABWTorrent services
cp "$SRC_DIR/systemd/abwtorrent-watchdog.service" /etc/systemd/system/
cp "$SRC_DIR/systemd/abwtorrent-web.service"      /etc/systemd/system/

systemctl daemon-reload

# ── 9. Permissions ───────────────────────────────
echo "> Setting permissions..."
chown -R debian-transmission:debian-transmission "$INSTALL_DIR"
chown -R debian-transmission:debian-transmission "$CONFIG_DIR"

# ── 10. Firewall (UFW) ──────────────────────────
echo "> Configuring firewall rules..."

# Transmission peer port — LAN only
ufw allow from "$LAN_SUBNET" to any port 51413 proto tcp comment "ABWTorrent peer TCP"
ufw allow from "$LAN_SUBNET" to any port 51413 proto udp comment "ABWTorrent peer UDP"

# LPD multicast — LAN only
ufw allow from "$LAN_SUBNET" to 239.192.152.143 port 6771 proto udp comment "ABWTorrent LPD"

# Transmission Web UI — LAN only
ufw allow from "$LAN_SUBNET" to any port 9091 proto tcp comment "Transmission Web UI"

# ABWTorrent Web UI — LAN only
ufw allow from "$LAN_SUBNET" to any port 8080 proto tcp comment "ABWTorrent Web UI"

# Enable UFW if not already active
ufw --force enable 2>/dev/null || true

# ── 11. Enable & start services ─────────────────
echo "> Enabling and starting services..."
systemctl enable transmission-daemon
systemctl start  transmission-daemon

# Wait for Transmission to initialize
sleep 3

systemctl enable abwtorrent-watchdog
systemctl start  abwtorrent-watchdog

systemctl enable abwtorrent-web
systemctl start  abwtorrent-web

# ── Done ─────────────────────────────────────────
echo ""
echo "================================================="
echo "  ABWTorrent installed successfully!      "
echo "================================================="
echo "                                              "
echo "  Transmission Web UI:                        "
echo "    http://<server-ip>:9091/transmission/web/ "
echo "    User: abwtorrent / Pass: changeme         "
echo "                                              "
echo "  ABWTorrent Dashboard:                       "
echo "    http://<server-ip>:8080                   "
echo "    User: admin / Pass: changeme              "
echo "                                              "
echo "  WARNING: Change default passwords immediately!   "
echo "================================================="
