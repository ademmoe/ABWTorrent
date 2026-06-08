#!/usr/bin/env python3
"""ABWTorrent Watchdog — monitors an ISO directory and auto-seeds via Transmission."""

import argparse
import logging
import logging.handlers
import os
import signal
import subprocess
import sys
import time
import threading
from pathlib import Path

from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

# Allow running from the project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.config import Config
from lib.torrent_gen import TorrentGenerator
from lib.transmission_api import TransmissionClient

logger = logging.getLogger("abwtorrent")


# ── Mount verification ───────────────────────────────────

def is_mount_point(path: str) -> bool:
    """
    Check if a path is an actual mount point by reading /proc/mounts.
    More reliable than Path.is_mount() for NAS mounts.
    """
    path_str = str(Path(path).resolve())
    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mount_point = parts[1]
                    if mount_point == path_str:
                        return True
    except (OSError, IOError):
        pass
    return False


def wait_for_mount(mountpoint: str, max_wait: int = 300, check_interval: int = 5) -> bool:
    """
    Wait for the NAS to be mounted at the specified mountpoint.
    
    If the mount doesn't exist after initial check, attempt to mount it via systemctl.
    Returns True if mount is successful, False if timeout.
    """
    mountpoint = str(Path(mountpoint).resolve())
    logger.info("Waiting for mount at %s (timeout: %ds)…", mountpoint, max_wait)
    
    elapsed = 0
    first_check = True
    
    while elapsed < max_wait:
        # Check if already mounted
        if is_mount_point(mountpoint):
            logger.info("✓ Mount point %s is ready", mountpoint)
            return True
        
        # On first iteration, try to mount via systemctl if not already mounted
        if first_check:
            first_check = False
            mount_unit = _path_to_mount_unit(mountpoint)
            if mount_unit:
                logger.info("Attempting to mount via systemctl start %s", mount_unit)
                try:
                    result = subprocess.run(
                        ["systemctl", "start", mount_unit],
                        capture_output=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        logger.info("Systemctl mount command succeeded")
                        time.sleep(2)  # Give mount time to settle
                        if is_mount_point(mountpoint):
                            logger.info("✓ Mount point %s is ready", mountpoint)
                            return True
                    else:
                        stderr = result.stderr.decode(errors="ignore").strip()
                        logger.warning("Systemctl mount failed: %s", stderr if stderr else "(no error output)")
                except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                    logger.warning("Could not invoke systemctl: %s", exc)
        
        # Wait and retry
        logger.debug("Mount check failed, retrying in %ds… (elapsed: %ds/%ds)",
                    check_interval, elapsed, max_wait)
        time.sleep(check_interval)
        elapsed += check_interval
    
    logger.error("✗ Mount point %s did not become available within %ds", mountpoint, max_wait)
    return False


def _path_to_mount_unit(path: str) -> str:
    """Convert a filesystem path to a systemd mount unit name."""
    # e.g., /media/nas → media-nas.mount
    path = str(path).strip("/")
    if not path:
        return None
    unit = path.replace("/", "-")
    return f"{unit}.mount"


def extract_nas_mount(watch_dir: str) -> str:
    """
    Find the actual mount point containing watch_dir by walking up the directory tree.
    
    Starts at watch_dir and walks up until finding a mount point.
    Works with any directory structure.
    
    Examples:
    - /media/nas/iso/... → walks up and finds /media/nas (if mounted)
    - /mnt/storage/data/iso/... → walks up and finds /mnt/storage (if mounted)
    """
    watch_path = Path(watch_dir).resolve()
    
    # Walk UP from watch_dir until we find a mount point (but skip root)
    current = watch_path
    while str(current) != "/" and current.parent != current:
        if is_mount_point(str(current)):
            logger.info("Detected NAS mount: %s", current)
            return str(current)
        current = current.parent
    
    # Fallback (shouldn't reach here in normal operation)
    logger.warning("Could not detect NAS mount, assuming /media/nas")
    return "/media/nas"


# ── Event handler ────────────────────────────────────────

class ISOHandler(FileSystemEventHandler):
    def __init__(self, config: Config, gen: TorrentGenerator, tc: TransmissionClient):
        super().__init__()
        self.config = config
        self.gen = gen
        self.tc = tc
        self._lock = threading.Lock()
        self._fingerprints: dict[str, str] = {}

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".iso"):
            self._process(event.src_path, "created")

    def on_modified(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".iso"):
            self._process(event.src_path, "modified")

    def _process(self, path: str, reason: str):
        with self._lock:
            if not Path(path).exists():
                return
            logger.info("ISO %s: %s", reason, Path(path).name)

            # Wait for copy to finish
            if not self.gen.wait_for_stability(path):
                return

            # Skip if file hasn't actually changed
            fp = TorrentGenerator.file_fingerprint(path)
            if self._fingerprints.get(path) == fp:
                logger.info("Fingerprint unchanged — skipping %s", Path(path).name)
                return
            self._fingerprints[path] = fp

            # Generate .torrent
            out_dir = self.config.get("torrent_output_dir")
            torrent_path = self.gen.generate_torrent(path, out_dir)
            if not torrent_path:
                return

            # Inject into Transmission (data_dir = parent of the ISO)
            data_dir = str(Path(path).parent)
            self.tc.inject_torrent(torrent_path, data_dir)


# ── Initial scan ─────────────────────────────────────────

def initial_scan(config: Config, gen: TorrentGenerator, tc: TransmissionClient):
    """Process every existing ISO on startup."""
    watch_dir = config.get("watch_dir")
    logger.info("Initial scan of %s", watch_dir)
    for iso in sorted(Path(watch_dir).rglob("*.iso")):
        fp = TorrentGenerator.file_fingerprint(str(iso))
        out_dir = config.get("torrent_output_dir")
        torrent_file = Path(out_dir) / (iso.stem + ".torrent")

        if torrent_file.exists():
            logger.info("  Torrent exists for %s — ensuring seeded", iso.name)
        else:
            logger.info("  New ISO found: %s", iso.name)

        torrent_path = gen.generate_torrent(str(iso), out_dir)
        if torrent_path:
            tc.inject_torrent(torrent_path, str(iso.parent))


# ── Logging setup ────────────────────────────────────────

def setup_logging(config: Config):
    level = getattr(logging, config.get("log.level", "INFO").upper(), logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)-8s %(name)s — %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    logger.setLevel(level)

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File (if writable)
    log_file = config.get("log.file")
    if log_file:
        try:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=5)
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except OSError as exc:
            logger.warning("Cannot write to log file %s: %s", log_file, exc)


# ── Main ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ABWTorrent ISO Watchdog")
    parser.add_argument("--config", "-c", default="/etc/abwtorrent/abwtorrent.conf",
                        help="Path to config file")
    args = parser.parse_args()

    config = Config(args.config)
    setup_logging(config)

    logger.info("╔══════════════════════════════════════╗")
    logger.info("║       ABWTorrent Watchdog v1.0       ║")
    logger.info("╚══════════════════════════════════════╝")
    logger.info("Watch dir : %s", config.get("watch_dir"))
    logger.info("Output dir: %s", config.get("torrent_output_dir"))

    gen = TorrentGenerator(config)
    tc  = TransmissionClient(config)

    # Wait for NAS mount (read timeout from config)
    watch_dir = config.get("watch_dir")
    nas_mount = extract_nas_mount(watch_dir)
    max_wait = config.get("mount.max_wait_seconds", 300)
    check_interval = config.get("mount.check_interval_seconds", 5)
    
    if not wait_for_mount(nas_mount, max_wait=max_wait, check_interval=check_interval):
        logger.error("NAS mount point %s is unavailable. Giving up.", nas_mount)
        sys.exit(1)

    # Make sure watch directory exists
    if not Path(watch_dir).is_dir():
        logger.error("Watch directory does not exist: %s", watch_dir)
        sys.exit(1)

    # Run initial scan
    initial_scan(config, gen, tc)

    # Start filesystem observer (PollingObserver for NAS/NFS/CIFS reliability)
    handler = ISOHandler(config, gen, tc)
    observer = PollingObserver(timeout=10)
    observer.schedule(handler, watch_dir, recursive=True)
    observer.start()
    logger.info("Watching for ISO changes…")

    # Graceful shutdown
    stop = threading.Event()

    def _shutdown(signum, _frame):
        logger.info("Received signal %d — shutting down", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    try:
        while not stop.is_set():
            stop.wait(1)
    finally:
        observer.stop()
        observer.join()
        logger.info("Watchdog stopped.")


if __name__ == "__main__":
    main()
