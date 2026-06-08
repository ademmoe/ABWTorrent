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
    M.toast({
      html: message,
      classes: type === 'error' ? 'red lighten-1' : 'green lighten-1'
    });
  };

  // ── Dashboard refresh ─────────────────────────

  const tbody = document.getElementById('torrents-tbody');
  if (!tbody) {
    // Not on dashboard page, but initialize sidebar toggle
    initSidebarToggle();
    return;
  }

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
      tbody.innerHTML = '<tr><td colspan="9" class="center-align grey-text" style="padding: 3rem;">No torrents loaded yet. Add ISOs to the watch directory.</td></tr>';
      return;
    }

    tbody.innerHTML = torrents.map(t => {
      const sc = statusClass(t.status);
      let badgeColor = 'grey';
      if (sc === 'seeding') badgeColor = 'green';
      if (sc === 'downloading') badgeColor = 'blue';
      if (sc === 'checking') badgeColor = 'orange';

      return `<tr>
        <td title="${t.name}" style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${t.name}</td>
        <td><span class="new badge ${badgeColor}" data-badge-caption="">${statusLabel(t.status)}</span></td>
        <td style="width: 150px;">
          <div class="progress" style="margin: 0; background-color: #e0e0e0;">
              <div class="determinate indigo" style="width: ${t.progress}%"></div>
          </div>
          <small>${t.progress}%</small>
        </td>
        <td>${fmtBytes(t.size)}</td>
        <td>${fmtBytes(t.uploaded)}</td>
        <td>${t.ratio}</td>
        <td>${fmtSpeed(t.upload_speed)}</td>
        <td>${t.peers}</td>
        <td>
          ${sc === 'seeding' || sc === 'downloading'
            ? `<a href="#!" class="indigo-text" title="Pause" onclick="torrentAction(${t.id},'pause')"><i class="material-icons">pause</i></a>`
            : `<a href="#!" class="indigo-text" title="Resume" onclick="torrentAction(${t.id},'resume')"><i class="material-icons">play_arrow</i></a>`
          }
          <a href="#!" class="red-text" style="margin-left:8px;" title="Remove" onclick="torrentAction(${t.id},'remove')"><i class="material-icons">close</i></a>
        </td>
      </tr>`;
    }).join('');
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

  // ── Sidebar Toggle Initialization ─────────────
  
  function initSidebarToggle() {
    document.addEventListener('DOMContentLoaded', function() {
      var elems = document.querySelectorAll('.sidenav');
      M.Sidenav.init(elems);
      
      // Add sidebar-open class by default on desktop (width > 992px)
      if (window.innerWidth > 992) {
        document.body.classList.add('sidebar-open');
      }
      
      var toggleBtn = document.getElementById('sidebar-toggle');
      
      if (toggleBtn) {
        toggleBtn.addEventListener('click', function(e) {
          e.preventDefault();
          if (window.innerWidth > 992) {
            // Toggle the sidebar-open class on body to adjust content padding
            document.body.classList.toggle('sidebar-open');
          }
        });
      }
    });
  }

  // ── Start polling ─────────────────────────────

  refresh();
  setInterval(refresh, REFRESH_INTERVAL);
  initSidebarToggle();

})();
