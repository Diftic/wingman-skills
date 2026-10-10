/* SC NavPoint HUD — Frontend Logic */

const API = '';
let state = {
  navpoints: [],
  servers: [],
  activeTarget: null,
  currentPos: null,
  lastToken: -1,
  serverFilter: '',
};

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  refreshWaypoints();
  pollNavState();
  setInterval(pollNavState, 2000);
});

// ── Data fetching ─────────────────────────────────────────────────────────────

async function refreshWaypoints() {
  const url = state.serverFilter
    ? `/api/navpoints?server_id=${encodeURIComponent(state.serverFilter)}`
    : '/api/navpoints';
  try {
    const data = await fetchJSON(url);
    state.navpoints = data.navpoints || [];
    state.servers   = data.servers   || [];
    renderServerFilter();
    renderWaypointList();
  } catch (e) {
    setStatus('Error loading waypoints');
  }
}

async function pollNavState() {
  try {
    const data = await fetchJSON('/api/nav/state');
    if (data.update_token !== state.lastToken) {
      state.lastToken     = data.update_token;
      state.activeTarget  = data.active_target;
      state.currentPos    = data.current_position;
      await refreshWaypoints();
      renderNavPanel();
    }
  } catch (_) { /* server may not be ready yet */ }
}

async function fetchJSON(url) {
  const r = await fetch(API + url);
  if (!r.ok) throw new Error(r.statusText);
  return r.json();
}

// ── Render: Server filter ─────────────────────────────────────────────────────

function renderServerFilter() {
  const sel = document.getElementById('server-filter');
  const current = sel.value;
  sel.innerHTML = '<option value="">All Servers</option>';
  state.servers.forEach(srv => {
    const opt = document.createElement('option');
    opt.value = srv;
    opt.textContent = srv;
    if (srv === current) opt.selected = true;
    sel.appendChild(opt);
  });
  sel.onchange = () => { state.serverFilter = sel.value; refreshWaypoints(); };
}

// ── Render: Waypoint list ─────────────────────────────────────────────────────

function renderWaypointList() {
  const list = document.getElementById('waypoint-list');
  if (!state.navpoints.length) {
    list.innerHTML = '<div class="empty-state">No waypoints saved yet.<br>Say "mark location" in game to save one.</div>';
    return;
  }

  list.innerHTML = '';
  state.navpoints.forEach(wp => {
    const isActive = state.activeTarget && state.activeTarget.id === wp.id;
    const card = document.createElement('div');
    card.className = 'waypoint-card' + (isActive ? ' active' : '');
    card.dataset.id = wp.id;

    const location = [wp.zone, wp.moon, wp.planet].filter(Boolean).find(x => x) || wp.system || 'Unknown';
    const ts = wp.timestamp ? new Date(wp.timestamp).toLocaleDateString() : '';

    card.innerHTML = `
      <div class="wp-header">
        <span class="wp-name" id="wp-name-${wp.id}">${escHtml(wp.name)}</span>
        <input class="wp-name-edit" id="wp-edit-${wp.id}" type="text"
               value="${escHtml(wp.name)}"
               onblur="saveRename(${wp.id})"
               onkeydown="if(event.key==='Enter')this.blur();if(event.key==='Escape')cancelRename(${wp.id})">
        <div class="wp-actions">
          <button class="wp-btn nav-btn" onclick="setTarget(${wp.id})" title="Navigate here">▶</button>
          <button class="wp-btn edit-btn" onclick="startRename(${wp.id})" title="Rename">✏</button>
          <button class="wp-btn del-btn" onclick="deleteWaypoint(${wp.id})" title="Delete">✕</button>
        </div>
      </div>
      <div class="wp-meta">
        <span class="wp-tag">${escHtml(location)}</span>
        ${wp.system ? `<span class="wp-tag">${escHtml(wp.system)}</span>` : ''}
        ${ts ? `<span>${ts}</span>` : ''}
      </div>
      <div class="wp-coords">X ${fmt(wp.x)} · Y ${fmt(wp.y)} · Z ${fmt(wp.z)}</div>
      ${wp.server_id ? `<div class="wp-server">Server: ${escHtml(wp.server_id)}</div>` : ''}
    `;

    list.appendChild(card);
  });
}

// ── Render: Navigation panel ──────────────────────────────────────────────────

function renderNavPanel() {
  const target = state.activeTarget;
  const pos    = state.currentPos;

  const targetCard = document.getElementById('target-card');
  const noTargetMsg = document.getElementById('no-target-msg');
  const clearBtn = document.getElementById('clear-target-btn');

  if (!target) {
    targetCard.classList.add('hidden');
    noTargetMsg.style.display = '';
    clearBtn.style.display = 'none';
    drawCompass(null);
    setNavRow('nav-distance', '—');
    setNavRow('nav-turn', '—');
    setNavRow('nav-elev', '—');
    setNavRow('nav-bearing', '—');
    renderGuidance([]);
    renderPosition(pos);
    return;
  }

  noTargetMsg.style.display = 'none';
  targetCard.classList.remove('hidden');
  clearBtn.style.display = '';

  const location = [target.zone, target.moon, target.planet].filter(Boolean).find(x => x) || '';
  document.getElementById('target-name').textContent = target.name;
  document.getElementById('target-meta').textContent =
    [location, target.system].filter(Boolean).join(' · ');

  // Bearing if we have both positions
  if (pos && hasCoords(pos) && hasCoords(target)) {
    const b = calcBearing(pos, target);
    drawCompass(b.horizontalOffset);
    setNavRow('nav-distance', formatDist(b.distanceKm));
    setNavRow('nav-turn',     b.turnInstruction);
    setNavRow('nav-elev',     b.elevInstruction);
    setNavRow('nav-bearing',  b.bearing.toFixed(1) + '°  ' + b.dirLabel);
    renderGuidance(buildSteps(target, b));
  } else {
    drawCompass(null);
    setNavRow('nav-distance', '—');
    setNavRow('nav-turn',     '—');
    setNavRow('nav-elev',     '—');
    setNavRow('nav-bearing',  '—');
    renderGuidance(buildApproachSteps(target));
  }

  renderPosition(pos);
}

// ── Navigation math ───────────────────────────────────────────────────────────

function hasCoords(obj) {
  return obj && obj.x != null && obj.y != null && obj.z != null;
}

function calcBearing(from, to) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const dz = to.z - from.z;

  const distM  = Math.sqrt(dx*dx + dy*dy + dz*dz);
  const distKm = distM / 1000;

  // Horizontal bearing using X/Z axes
  let bearing = (Math.atan2(dx, dz) * 180 / Math.PI + 360) % 360;
  const currentHeading = from.heading || 0;

  // Offset from player's heading
  let offset = ((bearing - currentHeading + 180) % 360) - 180;

  // Elevation angle
  const horizDist = Math.sqrt(dx*dx + dz*dz);
  const elev = horizDist > 0 ? Math.atan2(dy, horizDist) * 180 / Math.PI : (dy > 0 ? 90 : -90);

  const dirLabels = ['N','NE','E','SE','S','SW','W','NW'];
  const dirLabel  = dirLabels[Math.round(bearing / 45) % 8];

  return {
    distanceKm: distKm,
    bearing,
    horizontalOffset: offset,
    elevation: elev,
    dirLabel,
    turnInstruction: turnInstruction(offset),
    elevInstruction: elevInstruction(elev),
  };
}

function turnInstruction(offset) {
  const a = Math.abs(offset);
  if (a <= 5)   return 'Ahead';
  if (a > 150)  return 'Turn around';
  const side = offset > 0 ? 'right' : 'left';
  if (a > 90)   return `Hard ${side}`;
  if (a > 45)   return `Turn ${side}`;
  return `Bear ${side} ${a.toFixed(0)}°`;
}

function elevInstruction(angle) {
  if (Math.abs(angle) <= 5) return 'Level';
  const dir = angle > 0 ? 'up' : 'down';
  return `Pitch ${dir} ${Math.abs(angle).toFixed(0)}°`;
}

function formatDist(km) {
  if (km >= 1e6) return (km/1e6).toFixed(2) + ' Gm';
  if (km >= 1e3) return (km/1e3).toFixed(1) + ' Mm';
  if (km >= 1)   return km.toFixed(1) + ' km';
  return (km*1000).toFixed(0) + ' m';
}

// ── Compass rose canvas ───────────────────────────────────────────────────────

function drawCompass(offsetDeg) {
  const canvas = document.getElementById('compass');
  const ctx    = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const cx = W/2, cy = H/2;
  const r  = Math.min(cx, cy) - 8;

  ctx.clearRect(0, 0, W, H);

  // Background
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, 2*Math.PI);
  ctx.fillStyle = '#0b1626';
  ctx.fill();
  ctx.strokeStyle = '#1e3555';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // Tick marks and cardinal labels
  const cardinals = ['N','E','S','W'];
  for (let i = 0; i < 360; i += 15) {
    const rad = (i - 90) * Math.PI / 180;
    const outer = r - 2;
    const inner = i % 90 === 0 ? r - 14 : (i % 45 === 0 ? r - 10 : r - 6);
    ctx.beginPath();
    ctx.moveTo(cx + outer * Math.cos(rad), cy + outer * Math.sin(rad));
    ctx.lineTo(cx + inner * Math.cos(rad), cy + inner * Math.sin(rad));
    ctx.strokeStyle = i % 90 === 0 ? '#3a90d8' : '#1e3555';
    ctx.lineWidth = i % 90 === 0 ? 2 : 1;
    ctx.stroke();
  }

  cardinals.forEach((lbl, idx) => {
    const rad = (idx * 90 - 90) * Math.PI / 180;
    const lr  = r - 22;
    ctx.fillStyle = lbl === 'N' ? '#5db0ff' : '#6a8aaa';
    ctx.font = `bold ${lbl === 'N' ? 13 : 11}px 'Courier New', monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(lbl, cx + lr * Math.cos(rad), cy + lr * Math.sin(rad));
  });

  // Forward indicator (small triangle at top)
  ctx.beginPath();
  ctx.moveTo(cx, cy - r + 4);
  ctx.lineTo(cx - 5, cy - r + 13);
  ctx.lineTo(cx + 5, cy - r + 13);
  ctx.closePath();
  ctx.fillStyle = '#3a90d8';
  ctx.fill();

  if (offsetDeg == null) {
    // No target — grey question mark in centre
    ctx.fillStyle = '#6a8aaa';
    ctx.font = 'bold 28px monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('?', cx, cy);
    return;
  }

  // Arrow pointing toward target (relative to forward)
  const arrowAngle = (offsetDeg - 90) * Math.PI / 180;
  const arrowLen   = r * 0.58;
  const ax = cx + arrowLen * Math.cos(arrowAngle);
  const ay = cy + arrowLen * Math.sin(arrowAngle);

  // Glow
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(ax, ay);
  ctx.strokeStyle = 'rgba(0,232,144,0.2)';
  ctx.lineWidth = 8;
  ctx.stroke();

  // Arrow shaft
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(ax, ay);
  ctx.strokeStyle = '#00e890';
  ctx.lineWidth = 2.5;
  ctx.stroke();

  // Arrowhead
  const headSize = 11;
  const a1 = arrowAngle + Math.PI * 0.75;
  const a2 = arrowAngle - Math.PI * 0.75;
  ctx.beginPath();
  ctx.moveTo(ax, ay);
  ctx.lineTo(ax + headSize * Math.cos(a1), ay + headSize * Math.sin(a1));
  ctx.lineTo(ax + headSize * Math.cos(a2), ay + headSize * Math.sin(a2));
  ctx.closePath();
  ctx.fillStyle = '#00e890';
  ctx.fill();

  // Centre dot
  ctx.beginPath();
  ctx.arc(cx, cy, 4, 0, 2*Math.PI);
  ctx.fillStyle = '#00e890';
  ctx.fill();
}

// ── Guidance steps ────────────────────────────────────────────────────────────

function buildSteps(target, bearing) {
  const steps = [];
  if (bearing.distanceKm > 1e6) {
    if (target.system) steps.push(`Travel to ${target.system} system`);
  }
  if (target.planet) steps.push(`QT to ${target.planet}`);
  if (target.moon)   steps.push(`QT to ${target.moon}`);
  if (target.zone && target.zone !== target.planet && target.zone !== target.moon) {
    steps.push(`QT to ${target.zone}`);
  }
  steps.push(`${bearing.turnInstruction} · ${bearing.elevInstruction}`);
  steps.push(`${formatDist(bearing.distanceKm)} to destination`);
  return steps;
}

function buildApproachSteps(target) {
  const steps = [];
  if (target.system) steps.push(`Travel to ${target.system} system`);
  if (target.planet) steps.push(`QT to ${target.planet}`);
  if (target.moon)   steps.push(`QT to ${target.moon}`);
  if (target.zone && target.zone !== target.planet && target.zone !== target.moon) {
    steps.push(`Zone: ${target.zone}`);
  }
  steps.push(`Coords: ${fmt(target.x)}, ${fmt(target.y)}, ${fmt(target.z)}`);
  return steps;
}

function renderGuidance(steps) {
  const el = document.getElementById('guidance-steps');
  el.innerHTML = '';
  if (!steps.length) {
    el.innerHTML = '<li data-step="—" style="color:var(--text-dim)">No target set</li>';
    return;
  }
  steps.forEach((txt, i) => {
    const li = document.createElement('li');
    li.setAttribute('data-step', i + 1);
    li.textContent = txt;
    el.appendChild(li);
  });
}

// ── Position box ──────────────────────────────────────────────────────────────

function renderPosition(pos) {
  const el = document.getElementById('pos-grid');
  if (!pos) {
    el.textContent = '—';
    return;
  }
  const rows = [
    ['X', fmt(pos.x)],
    ['Y', fmt(pos.y)],
    ['Z', fmt(pos.z)],
  ];
  if (pos.heading != null) rows.push(['HDG', pos.heading.toFixed(1) + '°']);
  if (pos.zone)   rows.push(['Zone', pos.zone]);
  if (pos.planet) rows.push(['Planet', pos.planet]);

  el.innerHTML = rows.map(([k, v]) =>
    `<div class="pos-item"><span class="pos-key">${k}</span><span class="pos-val">${v}</span></div>`
  ).join('');
}

// ── Actions ───────────────────────────────────────────────────────────────────

async function setTarget(id) {
  try {
    await fetch(`/api/nav/target/${id}`, { method: 'POST' });
    setStatus('Navigation target set');
    await pollNavState();
  } catch (e) { setStatus('Error setting target'); }
}

async function clearTarget() {
  try {
    await fetch('/api/nav/target', { method: 'DELETE' });
    state.activeTarget = null;
    renderNavPanel();
    renderWaypointList();
    setStatus('Target cleared');
  } catch (e) { setStatus('Error clearing target'); }
}

async function deleteWaypoint(id) {
  const wp = state.navpoints.find(w => w.id === id);
  const name = wp ? wp.name : `#${id}`;
  if (!confirm(`Delete "${name}"?`)) return;
  try {
    await fetch(`/api/navpoints/${id}`, { method: 'DELETE' });
    setStatus(`Deleted: ${name}`);
    await refreshWaypoints();
  } catch (e) { setStatus('Error deleting waypoint'); }
}

function startRename(id) {
  const nameEl = document.getElementById(`wp-name-${id}`);
  const editEl = document.getElementById(`wp-edit-${id}`);
  if (!nameEl || !editEl) return;
  nameEl.style.display = 'none';
  editEl.style.display = 'block';
  editEl.focus();
  editEl.select();
}

async function saveRename(id) {
  const nameEl = document.getElementById(`wp-name-${id}`);
  const editEl = document.getElementById(`wp-edit-${id}`);
  if (!nameEl || !editEl) return;
  const newName = editEl.value.trim();
  if (newName) {
    try {
      await fetch(`/api/navpoints/${id}/name`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName }),
      });
      setStatus(`Renamed to: ${newName}`);
    } catch (e) { setStatus('Error renaming'); }
  }
  editEl.style.display = 'none';
  nameEl.style.display = '';
  await refreshWaypoints();
}

function cancelRename(id) {
  const nameEl = document.getElementById(`wp-name-${id}`);
  const editEl = document.getElementById(`wp-edit-${id}`);
  if (!nameEl || !editEl) return;
  editEl.style.display = 'none';
  nameEl.style.display = '';
}

// ── Utility ───────────────────────────────────────────────────────────────────

function setNavRow(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setStatus(msg) {
  const el = document.getElementById('status-bar');
  if (el) el.textContent = msg;
  setTimeout(() => { if (el) el.textContent = 'Ready'; }, 3000);
}

function fmt(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
