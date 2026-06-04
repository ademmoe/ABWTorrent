# ABWTorrent

**Internal LAN-only automated ISO seeding via BitTorrent.**

ABWTorrent watches a NAS directory for Debian ISO files, automatically generates `.torrent` files, and injects them into Transmission for peer-to-peer distribution across your local network. No trackers, no internet exposure — peers discover each other via **Local Peer Discovery (LPD)** multicast.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  NAS (/media/nas)                                                │
│  ┌─────────────────────────────┐  ┌───────────────────────────┐  │
│  │ /iso/…/Debian/*.iso         │  │ /platz219/torrents/*.torrent│ │
│  │  (source ISOs)              │  │  (generated .torrent files)│  │
│  └──────────┬──────────────────┘  └───────────┬───────────────┘  │
│             │ inotify/poll                     │                  │
└─────────────┼──────────────────────────────────┼──────────────────┘
              ▼                                  ▲
    ┌─────────────────┐      generates     ┌─────┘
    │  Watchdog        │──────────────────→ │
    │  (Python)        │                    │
    │                  │──── injects via ──→ ┌──────────────────┐
    └─────────────────┘     RPC API         │  Transmission     │
                                            │  Daemon           │
              ┌──────────────────────────── │  :9091 Web UI     │
              │  LPD multicast              │  :51413 peers     │
              │  239.192.152.143:6771       └──────────────────┘
              ▼
    ┌─────────────────┐
    │  LAN Peers       │  (other Transmission/torrent clients)
    │  172.16.0.0/16   │
    └─────────────────┘

    ┌─────────────────┐
    │  ABWTorrent      │  Custom dashboard for monitoring
    │  Web UI :8080    │  + settings + user management
    └─────────────────┘
```

## How Peer Discovery Works

ABWTorrent uses **Local Peer Discovery (LPD)** — [BEP 14](https://www.bittorrent.org/beps/bep_0014.html):

- Transmission sends UDP multicast announcements to `239.192.152.143:6771`
- Only devices on the same LAN segment receive these announcements
- **No trackers** — no central server needed
- **No DHT** — no distributed hash table (internet peer discovery disabled)
- **No PEX** — no peer exchange protocol
- Torrent files are created **without the private flag** (private flag would disable LPD)
- LAN isolation is enforced at the **network layer** via UFW firewall rules

---

## Prerequisites

- **Debian 11+** (or Ubuntu 22.04+)
- **NAS mounted** at `/media/nas` (NFS, CIFS/SMB, etc.)
- **Root access** for installation
- **Network**: All machines on `172.16.0.0/16` subnet

## Quick Install

```bash
# 1. Clone/copy ABWTorrent to the server
scp -r ABWTorrent/ user@server:/tmp/

# 2. SSH into the server and run the installer
ssh user@server
sudo bash /tmp/ABWTorrent/scripts/install.sh
```

The installer will:
1. Install `transmission-daemon`, `python3-venv`, `ufw`
2. Create a Python venv at `/opt/abwtorrent/venv/`
3. Deploy config to `/etc/abwtorrent/abwtorrent.conf`
4. Configure Transmission for LAN-only operation
5. Set up UFW firewall rules (only `172.16.0.0/16` allowed)
6. Enable & start all systemd services

---

## Access Points

### ABWTorrent Dashboard (custom Web UI)

```
http://<server-ip>:8080
```

- **Default login**: `admin` / `changeme`
- Features:
  - Real-time torrent status, speeds, peer counts
  - Download `.torrent` files directly from the browser
  - Configure piece size, watch directories, log level
  - User management (add/remove users, change passwords)
  - Transmission connection settings

### Transmission Web UI (native)

```
http://<server-ip>:9091/transmission/web/
```

- **Default login**: `abwtorrent` / `changeme`
- Full torrent management (pause, resume, inspect, etc.)

---

## Configuration

Edit `/etc/abwtorrent/abwtorrent.conf` (YAML):

```yaml
watch_dir: /media/nas/iso/operating_systems/Linux/Debian
torrent_output_dir: /media/nas/platz219/torrents

transmission:
  host: 127.0.0.1
  port: 9091
  username: abwtorrent
  password: changeme

torrent:
  piece_size: 4194304        # 4 MiB (configurable in Web UI)
  comment: "ABWTorrent - Internal LAN ISO Distribution"

file_stability:
  check_interval: 2
  stable_count: 3
```

Most settings can also be changed via the Web UI **Settings** page.

---

## Client Setup (Downloading ISOs)

For other machines on the LAN to download ISOs via P2P:

### 1. Install Transmission (or any BitTorrent client)

```bash
sudo apt install transmission-gtk    # GUI
# OR
sudo apt install transmission-cli    # CLI
```

### 2. Configure for LAN-only

In the client's settings, enable **Local Peer Discovery (LPD)** and disable DHT/PEX:
- Settings → Network → ☑ Enable Local Peer Discovery
- Settings → Network → ☐ Enable DHT
- Settings → Network → ☐ Enable PEX

### 3. Get the .torrent file

- **Option A**: Download from ABWTorrent dashboard at `http://<server-ip>:8080`
- **Option B**: Copy from NAS: `/media/nas/platz219/torrents/`
- **Option C**: Access via Transmission Web UI at `http://<server-ip>:9091`

### 4. Open the .torrent in your client

The client will discover the seeding server via LPD multicast and begin downloading.

---

## Service Management

```bash
# Check status
sudo systemctl status transmission-daemon
sudo systemctl status abwtorrent-watchdog
sudo systemctl status abwtorrent-web

# View logs
sudo journalctl -u abwtorrent-watchdog -f
sudo journalctl -u abwtorrent-web -f

# Restart services
sudo systemctl restart abwtorrent-watchdog
sudo systemctl restart abwtorrent-web

# Restart Transmission (stop first, then start — protects settings.json)
sudo systemctl stop transmission-daemon
sudo systemctl start transmission-daemon
```

---

## Firewall Rules

The installer configures UFW with these rules:

| Port | Protocol | Source | Purpose |
|:-----|:---------|:-------|:--------|
| 51413 | TCP+UDP | `172.16.0.0/16` | Transmission peer connections |
| 6771 | UDP | `172.16.0.0/16` → `239.192.152.143` | LPD multicast |
| 9091 | TCP | `172.16.0.0/16` | Transmission Web UI |
| 8080 | TCP | `172.16.0.0/16` | ABWTorrent Dashboard |

All other inbound traffic is **denied** by default.

---

## Troubleshooting

### Torrents stuck at 0% / not seeding

1. Check that the ISO file exists at the expected path
2. Transmission needs the `download_dir` to match the ISO's parent directory
3. Force a re-verify: `transmission-remote -t <id> --verify`

### No peers discovered

1. Verify LPD is enabled: `grep lpd /var/lib/transmission-daemon/info/settings.json`
2. Check multicast traffic: `tcpdump -i any udp port 6771`
3. Ensure clients and server are on the **same L2 network segment** (multicast doesn't cross routers by default)

### Watchdog not detecting new files

1. The watchdog uses polling (10s interval) for NAS reliability — wait ~15 seconds
2. Check logs: `journalctl -u abwtorrent-watchdog -f`
3. Verify the watch directory is accessible: `ls /media/nas/iso/operating_systems/Linux/Debian/`

### Permission denied errors

```bash
# Ensure debian-transmission user can access the NAS
sudo -u debian-transmission ls /media/nas/iso/operating_systems/Linux/Debian/
# If denied, add to the appropriate group or adjust mount options
```

---

## File Structure

```
/opt/abwtorrent/                    # Application code
├── venv/                           # Python virtual environment
├── watchdog_service.py             # Watchdog daemon
├── web_ui.py                       # Flask web UI
├── lib/                            # Shared Python modules
├── templates/                      # Jinja2 HTML templates
├── static/                         # CSS + JS
└── requirements.txt

/etc/abwtorrent/
└── abwtorrent.conf                 # Configuration (YAML)

/var/log/abwtorrent/
└── watchdog.log                    # Watchdog log (rotated)

/var/lib/transmission-daemon/info/
└── settings.json                   # Transmission configuration
```

---

## Security Notes

- **No internet exposure**: All ports are firewalled to `172.16.0.0/16` only
- **No trackers/DHT/PEX**: Torrents have no announce URLs; DHT and PEX are globally disabled
- **LPD is L2-scoped**: Multicast doesn't cross routers without explicit configuration
- **Change default passwords** immediately after installation
- The Web UI uses session-based authentication with SHA-256 password hashing
