/* ─────────────────────────────────────────────
   ABWTorrent — Dashboard JavaScript
   ───────────────────────────────────────────── */

(function () {
  'use strict';

  const REFRESH_INTERVAL = 3000; // ms

  // ── Helpers ───────────────────────────────────

  function fmtBytes(n) {
    if (n == null || n === 0) return '0 B';
    const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
    let i = 0;
    while (Math.abs(n) >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return n.toFixed(1) + ' ' + units[i];
  }

  function fmtSpeed(n) {
    return fmtBytes(n) + '/s';
  }

  function statusClass(status) {
    const s = (status || '').toLowerCase();
    if (s.includes('seed'))  return 'seeding';
    if (s.includes('stop'))  return 'stopped';
    if (s.includes('check')) return 'checking';
    if (s.includes('down'))  return 'downloading';
    return 'stopped';
  }

  function statusLabel(status) {
    const s = (status || '').toLowerCase();
    if (s.includes('seed'))  return 'Seeding';
    if (s.includes('stop'))  return 'Stopped';
    if (s.includes('check')) return 'Checking';
    if (s.includes('down'))  return 'Downloading';
    return status || 'Unknown';
  }

  // ── Toast system ──────────────────────────────

  window.showToast = function (message, type = 'success') {
    let container = document.querySelector('.toast-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    const el = document.createElement('div');
    el.className = 'toast toast-' + type;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 3200);
  };

  // ── Dashboard refresh ─────────────────────────

  const tbody = document.getElementById('torrents-tbody');
  if (!tbody) return; // Not on dashboard page

  async function refresh() {
    try {
      const [tRes, fRes] = await Promise.all([
        fetch('/api/torrents'),
        fetch('/api/torrent-files'),
      ]);
      const tData = await tRes.json();
      const fData = await fRes.json();

      updateStats(tData.stats, tData.torrents);
      updateTable(tData.torrents);
      updateFiles(fData.files);
    } catch (e) {
      console.warn('Refresh failed:', e);
    }
  }

  function updateStats(stats, torrents) {
    const el = (id) => document.getElementById(id);
    const totalPeers = torrents.reduce((s, t) => s + (t.peers || 0), 0);

    el('stat-active').textContent  = stats.active  ?? '—';
    el('stat-upload').textContent  = fmtSpeed(stats.upload_speed ?? 0);
    el('stat-peers').textContent   = totalPeers;
    el('stat-total').textContent   = stats.total ?? '—';

    const badge = document.getElementById('torrent-count-badge');
    if (badge) badge.textContent = torrents.length;
  }

  function updateTable(torrents) {
    if (!torrents.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty-state">No torrents loaded yet. Add ISOs to the watch directory.</td></tr>';
      return;
    }

    tbody.innerHTML = torrents.map(t => {
      const sc = statusClass(t.status);
      return `<tr>
        <td title="${t.name}" style="max-width:220px;overflow:hidden;text-overflow:ellipsis">${t.name}</td>
        <td><span class="status status--${sc}">${statusLabel(t.status)}</span></td>
        <td>
          <span class="progress-bar"><span class="progress-bar__fill" style="width:${t.progress}%"></span></span>
          ${t.progress}%
        </td>
        <td>${fmtBytes(t.size)}</td>
        <td>${fmtBytes(t.uploaded)}</td>
        <td>${t.ratio}</td>
        <td>${fmtSpeed(t.upload_speed)}</td>
        <td>${t.peers}</td>
        <td>
          ${sc === 'seeding' || sc === 'downloading'
            ? `<button class="btn-icon" title="Pause" onclick="torrentAction(${t.id},'pause')">⏸</button>`
            : `<button class="btn-icon" title="Resume" onclick="torrentAction(${t.id},'resume')">▶</button>`
          }
          <button class="btn-icon" title="Remove" onclick="torrentAction(${t.id},'remove')">✕</button>
        </td>
      </tr>`;
    }).join('');
  }

  function updateFiles(files) {
    const grid = document.getElementById('torrent-files-grid');
    if (!grid) return;

    if (!files.length) {
      grid.innerHTML = '<p class="empty-state">No .torrent files generated yet.</p>';
      return;
    }

    grid.innerHTML = files.map(f => `
      <div class="file-item">
        <div class="file-icon">
          <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        </div>
        <div class="file-info">
          <span class="file-name" title="${f.name}">${f.name}</span>
          <span class="file-size">${fmtBytes(f.size)}</span>
        </div>
        <a href="/download/${encodeURIComponent(f.name)}" class="file-download">Download</a>
      </div>
    `).join('');
  }

  // ── Torrent actions ───────────────────────────

  window.torrentAction = async function (id, action) {
    if (action === 'remove' && !confirm('Remove this torrent? (Data on NAS is NOT deleted)')) return;
    try {
      const res = await fetch(`/api/torrent/${id}/${action}`, { method: 'POST' });
      const j = await res.json();
      if (j.ok) {
        showToast(`Torrent ${action}d successfully.`);
        refresh();
      }
    } catch (e) {
      showToast('Action failed: ' + e.message, 'error');
    }
  };

  // ── Start polling ─────────────────────────────

  refresh();
  setInterval(refresh, REFRESH_INTERVAL);
})();
