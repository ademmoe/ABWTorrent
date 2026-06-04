"""ABWTorrent — Torrent File Generator using torf."""

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

from torf import Torrent

logger = logging.getLogger("abwtorrent.generator")


class TorrentGenerator:
    """Create .torrent files from ISO images on the NAS."""

    def __init__(self, config):
        self.config = config

    # ── File stability ───────────────────────────────────

    def wait_for_stability(self, filepath: str) -> bool:
        """Poll file size/mtime until it stops changing (large-copy safety)."""
        path = Path(filepath)
        interval = self.config.get("file_stability.check_interval", 2)
        required = self.config.get("file_stability.stable_count", 3)

        logger.info("Waiting for file stability: %s", path.name)
        prev_size, prev_mtime, stable = -1, -1.0, 0
        max_wait, elapsed = 3600, 0

        while stable < required and elapsed < max_wait:
            try:
                st = path.stat()
                if st.st_size == prev_size and st.st_mtime == prev_mtime:
                    stable += 1
                    logger.debug("  Stable %d/%d  (%s, %d bytes)", stable, required, path.name, st.st_size)
                else:
                    stable = 0
                    prev_size, prev_mtime = st.st_size, st.st_mtime
                time.sleep(interval)
                elapsed += interval
            except FileNotFoundError:
                logger.warning("File disappeared during stability check: %s", filepath)
                return False
            except OSError as exc:
                logger.error("OS error during stability check: %s", exc)
                return False

        if elapsed >= max_wait:
            logger.error("Timed out waiting for stability: %s", filepath)
            return False

        logger.info("File stable: %s (%d bytes)", path.name, prev_size)
        return True

    # ── Torrent creation ─────────────────────────────────

    def generate_torrent(self, iso_path: str, output_dir: str) -> Optional[str]:
        """Generate a .torrent file.  Returns the output path or None on error."""
        iso = Path(iso_path)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        torrent_path = out / (iso.stem + ".torrent")
        piece_size = self.config.get("torrent.piece_size", 4194304)

        logger.info("Generating torrent for %s (piece size %d KiB)", iso.name, piece_size // 1024)

        try:
            t = Torrent(
                path=str(iso),
                trackers=None,
                comment=self.config.get("torrent.comment", "ABWTorrent"),
                created_by=self.config.get("torrent.created_by", "ABWTorrent"),
                private=False,       # MUST stay False — private flag disables LPD!
                piece_size=piece_size,
            )
            t.generate()
            t.write(str(torrent_path), overwrite=True)
            logger.info("Torrent saved: %s", torrent_path)
            return str(torrent_path)
        except Exception as exc:
            logger.error("Torrent generation failed for %s: %s", iso.name, exc)
            return None

    # ── Fingerprinting ───────────────────────────────────

    @staticmethod
    def file_fingerprint(filepath: str) -> str:
        """Quick fingerprint from size + mtime (no full hash of multi-GB files)."""
        st = Path(filepath).stat()
        return hashlib.sha256(f"{st.st_size}:{st.st_mtime}".encode()).hexdigest()[:16]
