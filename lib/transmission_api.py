"""ABWTorrent — Transmission RPC Client Wrapper."""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import transmission_rpc

logger = logging.getLogger("abwtorrent.transmission")


class TransmissionClient:
    """High-level wrapper around transmission-rpc."""

    def __init__(self, config):
        self.config = config
        self._client: Optional[transmission_rpc.Client] = None

    # ── Connection ───────────────────────────────────────

    def _connect(self) -> transmission_rpc.Client:
        host = self.config.get("transmission.host", "127.0.0.1")
        port = self.config.get("transmission.port", 9091)
        user = self.config.get("transmission.username", "abwtorrent")
        pw   = self.config.get("transmission.password", "changeme")
        self._client = transmission_rpc.Client(host=host, port=port, username=user, password=pw, timeout=30)
        logger.debug("Connected to Transmission at %s:%s", host, port)
        return self._client

    @property
    def client(self) -> transmission_rpc.Client:
        if self._client is None:
            return self._connect()
        return self._client

    def _call(self, fn):
        """Execute a Transmission RPC call, reconnecting once if the session expired."""
        try:
            return fn(self.client)
        except Exception:
            return fn(self._connect())

    # ── Torrent injection ────────────────────────────────

    def inject_torrent(self, torrent_path: str, data_dir: str) -> Optional[int]:
        """Add torrent pointing at existing data.  Returns torrent ID or None."""
        name = Path(torrent_path).stem
        logger.info("Injecting torrent: %s → %s", name, data_dir)

        try:
            # Remove duplicate if present
            existing = self._find_by_name(name)
            if existing:
                logger.info("  Removing previous copy (ID %d)", existing.id)
                self.client.remove_torrent(existing.id, delete_data=False)
                time.sleep(1)

            torrent = self.client.add_torrent(torrent_path, download_dir=data_dir, paused=True)
            logger.info("  Added ID %d — verifying data…", torrent.id)

            self.client.verify_torrent(torrent.id)
            time.sleep(0.5)

            # Wait for hash-check to finish (up to 10 min)
            deadline = time.time() + 600
            while time.time() < deadline:
                t = self.client.get_torrent(torrent.id, arguments=["id", "status", "percentDone"])
                status = str(t.status).lower()
                if "check" not in status:
                    break
                logger.debug("  Verify %.1f%%", t.percent_done * 100)
                time.sleep(1)

            self.client.start_torrent(torrent.id)
            logger.info("  Seeding started: %s (ID %d)", name, torrent.id)
            return torrent.id
        except Exception as exc:
            logger.error("Injection failed for %s: %s", name, exc)
            return None

    def _find_by_name(self, name: str) -> Optional[Any]:
        try:
            for t in self.client.get_torrents():
                if t.name == name:
                    return t
        except Exception:
            pass
        return None

    # ── Dashboard queries ────────────────────────────────

    _TORRENT_FIELDS = [
        "id", "name", "status", "percentDone", "totalSize",
        "uploadedEver", "uploadRatio", "rateUpload", "rateDownload",
        "peersConnected", "addedDate", "downloadDir",
    ]

    def get_all_torrents(self) -> List[Dict[str, Any]]:
        try:
            torrents = self._call(lambda c: c.get_torrents(arguments=self._TORRENT_FIELDS))
            return [
                {
                    "id": t.id,
                    "name": t.name,
                    "status": getattr(t.status, 'value', str(t.status)),
                    "progress": round(getattr(t, 'percent_done', getattr(t, 'percentDone', 0)) * 100, 1),
                    "size": getattr(t, 'total_size', getattr(t, 'totalSize', 0)),
                    "uploaded": getattr(t, 'uploaded_ever', getattr(t, 'uploadedEver', 0)),
                    "ratio": round(getattr(t, 'ratio', 0), 2),
                    "upload_speed": getattr(t, 'rate_upload', getattr(t, 'rateUpload', 0)),
                    "download_speed": getattr(t, 'rate_download', getattr(t, 'rateDownload', 0)),
                    "peers": getattr(t, 'peers_connected', getattr(t, 'peersConnected', 0)),
                    "added": str(getattr(t, 'date_added', getattr(t, 'addedDate', ''))),
                    "download_dir": getattr(t, 'download_dir', getattr(t, 'downloadDir', '')),
                }
                for t in torrents
            ]
        except Exception as exc:
            logger.error("get_all_torrents: %s", exc)
            return []

    def get_torrents_info(self, tids: List[int]) -> List[Dict[str, Any]]:
        """Fetch minimal name/download_dir metadata for specific torrent IDs."""
        if not tids:
            return []
        try:
            torrents = self._call(lambda c: c.get_torrents(ids=tids, arguments=["id", "name", "downloadDir"]))
            return [
                {
                    "id": t.id,
                    "name": t.name,
                    "download_dir": getattr(t, 'download_dir', getattr(t, 'downloadDir', '')),
                }
                for t in torrents
            ]
        except Exception as exc:
            logger.error("get_torrents_info: %s", exc)
            return []

    def get_session_stats(self) -> Dict[str, Any]:
        try:
            s = self._call(lambda c: c.session_stats())
            return {
                "active": getattr(s, 'active_torrent_count', getattr(s, 'activeTorrentCount', 0)),
                "paused": getattr(s, 'paused_torrent_count', getattr(s, 'pausedTorrentCount', 0)),
                "total": getattr(s, 'torrent_count', getattr(s, 'torrentCount', 0)),
                "upload_speed": getattr(s, 'upload_speed', getattr(s, 'uploadSpeed', 0)),
                "download_speed": getattr(s, 'download_speed', getattr(s, 'downloadSpeed', 0)),
            }
        except Exception as exc:
            logger.error("get_session_stats: %s", exc)
            return {}

    # ── Torrent actions ──────────────────────────────────

    def remove_torrent(self, tid: int, delete_data: bool = False):
        self._call(lambda c: c.remove_torrent(tid, delete_data=delete_data))

    def remove_torrents(self, tids: List[int], delete_data: bool = False):
        if tids:
            self._call(lambda c: c.remove_torrent(tids, delete_data=delete_data))

    def pause_torrent(self, tid: int):
        self._call(lambda c: c.stop_torrent(tid))

    def pause_torrents(self, tids: List[int]):
        if tids:
            self._call(lambda c: c.stop_torrent(tids))

    def resume_torrent(self, tid: int):
        self._call(lambda c: c.start_torrent(tid))

    def resume_torrents(self, tids: List[int]):
        if tids:
            self._call(lambda c: c.start_torrent(tids))
