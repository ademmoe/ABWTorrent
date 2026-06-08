#!/usr/bin/env python3
"""ABWTorrent Web UI — Flask dashboard for managing torrents and settings."""

import os
import sys
import json
import functools
import subprocess
from pathlib import Path

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, send_from_directory, abort)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.config import Config
from lib.transmission_api import TransmissionClient

# ── Globals ──────────────────────────────────────────────

CONFIG_PATH = os.environ.get("ABWTORRENT_CONFIG", "/etc/abwtorrent/abwtorrent.conf")
config = Config(CONFIG_PATH)
tc = TransmissionClient(config)

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)
app.secret_key = config.get("web.secret_key", os.urandom(24).hex())


# ── Auth decorator ───────────────────────────────────────

def login_required(f):
    @functools.wraps(f)
    def wrapper(*a, **kw):
        if not session.get("user"):
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper


# ── Helpers ──────────────────────────────────────────────

def _fmt_bytes(n):
    """Human-readable byte size."""
    if n is None:
        return "0 B"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PiB"


app.jinja_env.globals["fmt_bytes"] = _fmt_bytes


# ── Routes ───────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username", "").strip()
        pw   = request.form.get("password", "")
        if config.verify_password(user, pw):
            session["user"] = user
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/admin")
@login_required
def dashboard():
    return render_template("dashboard.html", user=session["user"])


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html", user=session["user"], config=config.data)


# ── API ──────────────────────────────────────────────────

@app.route("/api/torrents")
@login_required
def api_torrents():
    torrents = tc.get_all_torrents()
    stats = tc.get_session_stats()
    return jsonify({"torrents": torrents, "stats": stats})


@app.route("/api/torrent/<int:tid>/pause", methods=["POST"])
@login_required
def api_pause(tid):
    tc.pause_torrent(tid)
    return jsonify({"ok": True})


@app.route("/api/torrent/<int:tid>/resume", methods=["POST"])
@login_required
def api_resume(tid):
    tc.resume_torrent(tid)
    return jsonify({"ok": True})


@app.route("/api/torrent/<int:tid>/remove", methods=["POST"])
@login_required
def api_remove(tid):
    tc.remove_torrent(tid, delete_data=False)
    return jsonify({"ok": True})


@app.route("/api/settings", methods=["POST"])
@login_required
def api_save_settings():
    data = request.get_json(silent=True) or {}
    allowed = {
        "watch_dir", "torrent_output_dir",
        "torrent.piece_size", "torrent.comment", "torrent.created_by",
        "file_stability.check_interval", "file_stability.stable_count",
        "transmission.host", "transmission.port",
        "transmission.username", "transmission.password",
        "log.level",
    }
    needs_restart = False
    for key, val in data.items():
        if key in allowed:
            # Cast numeric values
            if key in ("torrent.piece_size", "file_stability.check_interval",
                       "file_stability.stable_count", "transmission.port"):
                val = int(val)

            # Check if watch_dir or torrent_output_dir has changed
            if key in ("watch_dir", "torrent_output_dir") and config.get(key) != val:
                needs_restart = True

            config.set(key, val)
    config.save()

    if needs_restart:
        try:
            subprocess.run(["sudo", "systemctl", "restart", "abwtorrent-watchdog"], capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to restart watchdog: {e}")

    # Reload the Transmission client with new credentials
    tc._client = None
    return jsonify({"ok": True, "message": "Settings saved."})


@app.route("/api/change-password", methods=["POST"])
@login_required
def api_change_password():
    data = request.get_json(silent=True) or {}
    current = data.get("current_password", "")
    new_pw  = data.get("new_password", "")
    user = session["user"]

    if not config.verify_password(user, current):
        return jsonify({"ok": False, "message": "Current password is incorrect."}), 400

    if len(new_pw) < 4:
        return jsonify({"ok": False, "message": "Password must be ≥ 4 characters."}), 400

    config.set(f"users.{user}.password_hash", Config.hash_password(new_pw))
    config.save()
    return jsonify({"ok": True, "message": "Password updated."})


@app.route("/api/add-user", methods=["POST"])
@login_required
def api_add_user():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role     = data.get("role", "viewer")

    if not username or not password:
        return jsonify({"ok": False, "message": "Username and password required."}), 400

    users = config._data.setdefault("users", {})
    if username in users:
        return jsonify({"ok": False, "message": "User already exists."}), 400

    users[username] = {
        "password_hash": Config.hash_password(password),
        "role": role,
    }
    config.save()
    return jsonify({"ok": True, "message": f"User '{username}' created."})


@app.route("/api/delete-user", methods=["POST"])
@login_required
def api_delete_user():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    if username == session["user"]:
        return jsonify({"ok": False, "message": "Cannot delete yourself."}), 400
    users = config._data.get("users", {})
    if username in users:
        del users[username]
        config.save()
        return jsonify({"ok": True, "message": f"User '{username}' deleted."})
    return jsonify({"ok": False, "message": "User not found."}), 404


@app.route("/api/users")
@login_required
def api_users():
    users = config._data.get("users", {})
    return jsonify({
        "users": [{"username": u, "role": d.get("role", "viewer")} for u, d in users.items()]
    })


@app.route("/download/<filename>")
def download_torrent(filename):
    torrent_dir = config.get("torrent_output_dir")
    if not filename.endswith(".torrent"):
        abort(400)
    return send_from_directory(torrent_dir, filename, as_attachment=True)


@app.route("/api/torrent-files")
def api_torrent_files():
    torrent_dir = config.get("torrent_output_dir")
    files = []
    try:
        for f in sorted(Path(torrent_dir).glob("*.torrent")):
            files.append({"name": f.name, "size": f.stat().st_size})
    except Exception:
        pass
    return jsonify({"files": files})


# ── Entry point ──────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ABWTorrent Web UI")
    parser.add_argument("--config", "-c", default=CONFIG_PATH)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    if args.config != CONFIG_PATH:
        config = Config(args.config)
        tc._client = None
        app.secret_key = config.get("web.secret_key", os.urandom(24).hex())

    host = args.host or config.get("web.host", "0.0.0.0")
    port = args.port or config.get("web.port", 8080)

    print(f"ABWTorrent Web UI → http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
