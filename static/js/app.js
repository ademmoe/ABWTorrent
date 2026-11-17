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
    return;
  }

  let currentTorrents = [];
  const selectedIds = new Set();
  let pendingRemoveIds = [];

  const selectAllCheckbox = document.getElementById('select-all-checkbox');
  const btnSelectAll = document.getElementById('btn-select-all');
  const bulkActions = document.getElementById('bulk-actions');
  const selectedCountLabel = document.getElementById('selected-count-label');
  const removeModalEl = document.getElementById('remove-modal');
  const removeModal = removeModalEl ? M.Modal.init(removeModalEl) : null;

  function syncSelectionUI() {
    const validIds = new Set(currentTorrents.map(t => t.id));
    for (const id of Array.from(selectedIds)) {
      if (!validIds.has(id)) selectedIds.delete(id);
    }

    const total = currentTorrents.length;
    const count = selectedIds.size;
    const allSelected = total > 0 && count === total;

    if (selectAllCheckbox) {
      selectAllCheckbox.checked = allSelected;
      selectAllCheckbox.indeterminate = count > 0 && count < total;
    }

    if (btnSelectAll) {
      const label = btnSelectAll.querySelector('span');
      if (label) label.textContent = allSelected ? 'Deselect All' : 'Select All';
      btnSelectAll.disabled = total === 0;
    }

    if (bulkActions) {
      bulkActions.style.display = count > 0 ? 'flex' : 'none';
    }
    if (selectedCountLabel) {
      selectedCountLabel.textContent = `${count} selected`;
    }
  }

  function toggleSelectAll(forceState) {
    const selectAll = typeof forceState === 'boolean'
      ? forceState
      : !(currentTorrents.length > 0 && selectedIds.size === currentTorrents.length);

    selectedIds.clear();
    if (selectAll) {
      currentTorrents.forEach(t => selectedIds.add(t.id));
    }
    tbody.querySelectorAll('.torrent-checkbox').forEach(cb => {
      cb.checked = selectedIds.has(Number(cb.dataset.id));
    });
    syncSelectionUI();
  }

  if (selectAllCheckbox) {
    selectAllCheckbox.addEventListener('change', (e) => toggleSelectAll(e.target.checked));
  }
  if (btnSelectAll) {
    btnSelectAll.addEventListener('click', () => toggleSelectAll());
  }

  async function refresh() {
    try {
      const tRes = await fetch('/api/torrents');
      const tData = await tRes.json();

      currentTorrents = tData.torrents || [];
      updateStats(tData.stats || {}, currentTorrents);
      updateTable(currentTorrents);
      syncSelectionUI();
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
      tbody.innerHTML = '<tr><td colspan="10" class="center-align grey-text" style="padding: 3rem;">No torrents loaded yet. Add ISOs to the watch directory.</td></tr>';
      return;
    }

    tbody.innerHTML = torrents.map(t => {
      const sc = statusClass(t.status);
      const checked = selectedIds.has(t.id) ? 'checked' : '';
      let badgeColor = 'grey';
      if (sc === 'seeding') badgeColor = 'green';
      if (sc === 'downloading') badgeColor = 'blue';
      if (sc === 'checking') badgeColor = 'orange';

      return `<tr>
        <td>
          <label>
            <input type="checkbox" class="filled-in torrent-checkbox" data-id="${t.id}" ${checked} />
            <span></span>
          </label>
        </td>
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

  tbody.addEventListener('change', (e) => {
    if (!e.target.classList.contains('torrent-checkbox')) return;
    const id = Number(e.target.dataset.id);
    if (e.target.checked) {
      selectedIds.add(id);
    } else {
      selectedIds.delete(id);
    }
    syncSelectionUI();
  });

  // ── Torrent actions ───────────────────────────

  function openRemoveModal(ids) {
    pendingRemoveIds = ids;
    const titleEl = document.getElementById('remove-modal-title');
    const descEl = document.getElementById('remove-modal-desc');

    if (ids.length === 1) {
      const t = currentTorrents.find(x => x.id === ids[0]);
      const name = t ? t.name : `#${ids[0]}`;
      if (titleEl) titleEl.textContent = 'Remove Torrent';
      if (descEl) descEl.innerHTML = `How would you like to remove <strong>${name}</strong>?`;
    } else {
      if (titleEl) titleEl.textContent = `Remove ${ids.length} Torrents`;
      if (descEl) descEl.innerHTML = `How would you like to remove the <strong>${ids.length}</strong> selected torrents?`;
    }

    if (removeModal) {
      removeModal.open();
    }
  }

  async function executeRemove(deleteData) {
    const ids = pendingRemoveIds.slice();
    if (!ids.length) return;
    if (removeModal) removeModal.close();

    try {
      let res;
      if (ids.length === 1) {
        res = await fetch(`/api/torrent/${ids[0]}/remove`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ delete_data: deleteData }),
        });
      } else {
        res = await fetch('/api/torrents/bulk', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids, action: 'remove', delete_data: deleteData }),
        });
      }
      const j = await res.json();
      if (j.ok) {
        ids.forEach(id => selectedIds.delete(id));
        showToast(deleteData ? 'Removed torrent(s) and .iso file(s).' : 'Removed .torrent(s) only.');
        refresh();
      } else {
        showToast(j.message || 'Remove failed.', 'error');
      }
    } catch (e) {
      showToast('Remove failed: ' + e.message, 'error');
    }
  }

  const btnRemoveTorrentOnly = document.getElementById('modal-remove-torrent-only');
  const btnRemoveWithIso = document.getElementById('modal-remove-with-iso');
  if (btnRemoveTorrentOnly) btnRemoveTorrentOnly.addEventListener('click', () => executeRemove(false));
  if (btnRemoveWithIso) btnRemoveWithIso.addEventListener('click', () => executeRemove(true));

  async function bulkAction(action) {
    const ids = Array.from(selectedIds);
    if (!ids.length) return;
    if (action === 'remove') {
      openRemoveModal(ids);
      return;
    }
    try {
      const res = await fetch('/api/torrents/bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids, action }),
      });
      const j = await res.json();
      if (j.ok) {
        showToast(`${ids.length} torrent(s) ${action}d successfully.`);
        refresh();
      } else {
        showToast(j.message || 'Bulk action failed.', 'error');
      }
    } catch (e) {
      showToast('Bulk action failed: ' + e.message, 'error');
    }
  }

  const btnBulkResume = document.getElementById('btn-bulk-resume');
  const btnBulkPause = document.getElementById('btn-bulk-pause');
  const btnBulkRemove = document.getElementById('btn-bulk-remove');
  if (btnBulkResume) btnBulkResume.addEventListener('click', () => bulkAction('resume'));
  if (btnBulkPause) btnBulkPause.addEventListener('click', () => bulkAction('pause'));
  if (btnBulkRemove) btnBulkRemove.addEventListener('click', () => bulkAction('remove'));

  window.torrentAction = async function (id, action) {
    if (action === 'remove') {
      openRemoveModal([id]);
      return;
    }
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
