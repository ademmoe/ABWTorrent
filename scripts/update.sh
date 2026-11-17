#!/usr/bin/env bash
# ─────────────────────────────────────────────────
# ABWTorrent — Automated Self-Update Script
# Fetches the latest version directly from GitHub
# while preserving all configuration and data.
#
# Usage:
#   sudo bash /opt/abwtorrent/scripts/update.sh
#   OR:
#   curl -fsSL https://raw.githubusercontent.com/ademmoe/ABWTorrent/main/scripts/update.sh | sudo bash
# ─────────────────────────────────────────────────
set -euo pipefail

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    echo "ERROR: Please run as root (e.g. sudo bash update.sh)." >&2
    exit 1
fi

REPO_TARBALL_URL="${ABWTORRENT_TARBALL_URL:-https://github.com/ademmoe/ABWTorrent/archive/refs/heads/main.tar.gz}"
INSTALL_DIR="/opt/abwtorrent"
CONFIG_DIR="/etc/abwtorrent"
TRANS_CONFIG_DIR="/var/lib/transmission-daemon/info"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "╔══════════════════════════════════════╗"
echo "║      ABWTorrent Server Updater       ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Download latest release from GitHub ──────
echo "> Downloading latest ABWTorrent from GitHub..."
ARCHIVE="$TMP_DIR/abwtorrent.tar.gz"
if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$REPO_TARBALL_URL" -o "$ARCHIVE"
elif command -v wget >/dev/null 2>&1; then
    wget -qO "$ARCHIVE" "$REPO_TARBALL_URL"
else
    echo "ERROR: Neither curl nor wget is installed." >&2
    exit 1
fi

tar -xzf "$ARCHIVE" -C "$TMP_DIR"
SRC_DIR="$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [ -z "$SRC_DIR" ] || [ ! -f "$SRC_DIR/web_ui.py" ]; then
    echo "ERROR: Downloaded archive does not look like ABWTorrent." >&2
    exit 1
fi
echo "> Extracted to $SRC_DIR"

# ── 2. Stop services before updating ────────────
echo "> Stopping ABWTorrent and Transmission services..."
systemctl stop abwtorrent-watchdog 2>/dev/null || true
systemctl stop abwtorrent-web      2>/dev/null || true
systemctl stop transmission-daemon 2>/dev/null || true

# ── 3. Update application code (preserve data) ──
echo "> Updating application files in $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp "$SRC_DIR/watchdog_service.py" "$INSTALL_DIR/"
cp "$SRC_DIR/web_ui.py"           "$INSTALL_DIR/"
cp "$SRC_DIR/requirements.txt"    "$INSTALL_DIR/"

rm -rf "$INSTALL_DIR/lib" "$INSTALL_DIR/templates" "$INSTALL_DIR/static" "$INSTALL_DIR/scripts"
cp -r "$SRC_DIR/lib"       "$INSTALL_DIR/"
cp -r "$SRC_DIR/templates" "$INSTALL_DIR/"
cp -r "$SRC_DIR/static"    "$INSTALL_DIR/"
cp -r "$SRC_DIR/scripts"   "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/scripts/"*.sh

# ── 4. Update Python dependencies ───────────────
echo "> Updating Python virtual environment..."
if [ ! -d "$INSTALL_DIR/venv" ]; then
    python3 -m venv "$INSTALL_DIR/venv"
fi
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# ── 5. Preserve abwtorrent.conf ─────────────────
if [ ! -f "$CONFIG_DIR/abwtorrent.conf" ]; then
    echo "> No existing config found — installing default configuration..."
    mkdir -p "$CONFIG_DIR"
    cp "$SRC_DIR/abwtorrent.conf" "$CONFIG_DIR/"
else
    echo "> Preserving existing $CONFIG_DIR/abwtorrent.conf"
fi

# ── 6. Merge Transmission performance & privacy settings ──
if [ -f "$TRANS_CONFIG_DIR/settings.json" ]; then
    echo "> Merging performance & LAN-privacy settings into $TRANS_CONFIG_DIR/settings.json..."
    python3 - "$SRC_DIR/transmission/settings.json" "$TRANS_CONFIG_DIR/settings.json" <<'PYEOF'
import json
import sys

src_path, dst_path = sys.argv[1], sys.argv[2]
with open(src_path, "r") as f:
    src = json.load(f)
with open(dst_path, "r") as f:
    dst = json.load(f)

# Only update performance & LAN-privacy keys; preserve credentials, paths, whitelist, etc.
KEYS_TO_SYNC = [
    "cache-size-mb",
    "dht-enabled",
    "pex-enabled",
    "lpd-enabled",
    "utp-enabled",
    "prefetch-enabled",
    "peer-socket-tos",
    "upload-slots-per-torrent",
    "peer-limit-global",
    "peer-limit-per-torrent",
    "encryption",
]
for k in KEYS_TO_SYNC:
    if k in src:
        dst[k] = src[k]

with open(dst_path, "w") as f:
    json.dump(dst, f, indent=4, sort_keys=True)
    f.write("\n")
PYEOF
else
    echo "> Installing Transmission settings..."
    mkdir -p "$TRANS_CONFIG_DIR"
    cp "$SRC_DIR/transmission/settings.json" "$TRANS_CONFIG_DIR/settings.json"
fi
chown -R debian-transmission:debian-transmission "$TRANS_CONFIG_DIR"

# ── 7. Update systemd service files ─────────────
echo "> Updating systemd services..."
mkdir -p /etc/systemd/system/transmission-daemon.service.d/
cp "$SRC_DIR/systemd/transmission-daemon.service.d/override.conf" \
   /etc/systemd/system/transmission-daemon.service.d/override.conf
cp "$SRC_DIR/systemd/abwtorrent-watchdog.service" /etc/systemd/system/
cp "$SRC_DIR/systemd/abwtorrent-web.service"      /etc/systemd/system/
systemctl daemon-reload

# ── 8. Apply LAN TCP/network performance tuning ─
echo "> Applying LAN TCP/network sysctl tuning..."
modprobe tcp_bbr 2>/dev/null || true
cat > /etc/sysctl.d/99-abwtorrent.conf <<'SYSCTL'
# ABWTorrent — LAN high-throughput TCP tuning
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.core.netdev_max_backlog = 16384
net.ipv4.tcp_slow_start_after_idle = 0
SYSCTL
if sysctl -n net.ipv4.tcp_available_congestion_control 2>/dev/null | grep -qw bbr; then
    cat >> /etc/sysctl.d/99-abwtorrent.conf <<'SYSCTL_BBR'
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
SYSCTL_BBR
fi
sysctl --system >/dev/null 2>&1 || true

# ── 9. Fix permissions & restart services ───────
echo "> Setting permissions..."
chown -R debian-transmission:debian-transmission "$INSTALL_DIR"
chown -R debian-transmission:debian-transmission "$CONFIG_DIR"

echo "> Starting services..."
systemctl start transmission-daemon
sleep 2
systemctl start abwtorrent-watchdog
systemctl start abwtorrent-web

echo ""
echo "================================================="
echo "  ABWTorrent updated successfully!"
echo "  All config, users, logs, and ISOs preserved."
echo "================================================="
