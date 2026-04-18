/* ═══════════════════════════════════════════════════════════════
   RewindDB — Application Logic v3.1 — Interactive Edition
   Serveo · Event-sourced · FastAPI backend
   NEW: Command Palette · Keyboard Shortcuts · Expandable Cards
        Filter Pills · Copy Clipboard · SVG Chart · Page Transitions
        Account Search · G-key chord navigation
   ═══════════════════════════════════════════════════════════════ */

/* ── CONFIG ───────────────────────────────────────────────── */
const DEFAULT_API = 'https://39236c827d224b01-115-244-141-202.serveousercontent.com';
let API = DEFAULT_API;
localStorage.removeItem('rewinddb_api_url');

function getApi() { return API; }
function setApi(url) {
  API = url.trim().replace(/\/$/, '');
  localStorage.setItem('rewinddb_api_url', API);
  document.getElementById('api-url-display').textContent = API.replace(/^https?:\/\//, '');
}
setApi(API);

/* ── API ──────────────────────────────────────────────────── */
async function apiCall(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body != null) opts.body = JSON.stringify(body);
  const r = await fetch(getApi() + path, opts);
  if (!r.ok) {
    let msg;
    try { const j = await r.json(); msg = j.detail || j.message || r.statusText; } catch { msg = r.statusText; }
    throw new Error(`${r.status}: ${msg}`);
  }
  return r.json();
}

/* ── TOAST ────────────────────────────────────────────────── */
const MAX_TOASTS = 4;
function toast(msg, type = '') {
  const c = document.getElementById('toast-container');
  while (c.children.length >= MAX_TOASTS) dismissToast(c.firstElementChild);
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span class="toast-msg">${esc(String(msg))}</span><button class="toast-x" aria-label="Dismiss"><span class="material-icons">close</span></button>`;
  c.appendChild(el);
  el.querySelector('.toast-x').addEventListener('click', () => dismissToast(el));
  setTimeout(() => dismissToast(el), type === 'error' ? 8000 : 4500);
}
function dismissToast(el) {
  if (!el?.parentNode) return;
  el.classList.add('toast-out');
  el.addEventListener('animationend', () => el.remove(), { once: true });
}

/* ── HELPERS ──────────────────────────────────────────────── */
const fmtMs  = v => v != null ? `${parseFloat(v).toFixed(2)}ms` : '—';
const fmtBal = v => v != null ? `$${parseFloat(v).toFixed(2)}` : '—';
const ago    = iso => iso ? new Date(iso).toLocaleTimeString() : '—';
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function syntaxHL(json) {
  if (typeof json !== 'string') json = JSON.stringify(json, null, 2);
  return json
    .replace(/(\"[\w _\-]+\")\s*:/g, '<span class="key">$1</span>:')
    .replace(/:\s*(\".*?\")/g,       ': <span class="str">$1</span>')
    .replace(/:\s*(-?\d+\.?\d*)/g,   ': <span class="value">$1</span>')
    .replace(/:\s*(true|false|null)/g,': <span class="value">$1</span>');
}

function dotCls(type) {
  if (!type) return 'tl-dot-default';
  const t = type.toLowerCase();
  if (t.includes('creat'))   return 'tl-dot-create';
  if (t.includes('deposit')) return 'tl-dot-deposit';
  if (t.includes('withdraw'))return 'tl-dot-withdraw';
  if (t.includes('transfer'))return 'tl-dot-transfer';
  if (t.includes('froz') || t.includes('freez')) return 'tl-dot-freeze';
  return 'tl-dot-default';
}

/* ── COPY TO CLIPBOARD ────────────────────────────────────── */
function copyText(text, el) {
  navigator.clipboard?.writeText(text).then(() => {
    if (!el) return;
    el.classList.add('just-copied');
    setTimeout(() => el.classList.remove('just-copied'), 1600);
  }).catch(() => {});
}

/* ── COUNT-UP ─────────────────────────────────────────────── */
function countUp(el, target, dur = 600, pre = '', suf = '') {
  if (typeof target !== 'number' || isNaN(target)) { el.textContent = pre + target + suf; return; }
  const start = performance.now();
  const from  = parseFloat(el.dataset.last) || 0;
  el.dataset.last = target;
  (function step(now) {
    const p    = Math.min((now - start) / dur, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    const v    = from + (target - from) * ease;
    el.textContent = pre + (Number.isInteger(target) ? Math.round(v) : v.toFixed(2)) + suf;
    if (p < 1) requestAnimationFrame(step);
  })(performance.now());
}

/* ── SIDEBAR ──────────────────────────────────────────────── */
const sidebar = document.getElementById('sidebar');
const main    = document.getElementById('main-content');
const overlay = document.getElementById('sidebar-overlay');

document.getElementById('sidebar-collapse-btn').addEventListener('click', () => {
  sidebar.classList.toggle('collapsed');
  main.classList.toggle('sidebar-collapsed');
});
document.getElementById('hamburger-btn').addEventListener('click', () => {
  sidebar.classList.add('mobile-open'); overlay.classList.add('show');
});
overlay.addEventListener('click', closeMobile);
function closeMobile() { sidebar.classList.remove('mobile-open'); overlay.classList.remove('show'); }

/* ── API MODAL ────────────────────────────────────────────── */
function openApiModal() {
  document.getElementById('api-url-input').value = API;
  document.getElementById('api-modal').classList.add('open');
}
document.getElementById('btn-config-api').addEventListener('click', openApiModal);
document.getElementById('modal-cancel').addEventListener('click', () => document.getElementById('api-modal').classList.remove('open'));
document.getElementById('api-modal').addEventListener('click', e => { if (e.target === e.currentTarget) e.currentTarget.classList.remove('open'); });
document.getElementById('modal-save').addEventListener('click', () => {
  const v = document.getElementById('api-url-input').value.trim();
  if (!v) return;
  setApi(v);
  document.getElementById('api-modal').classList.remove('open');
  toast('API updated — reconnecting…', 'info');
  checkHealth(); loadDashboard();
});

/* ── NAVIGATION WITH PAGE TRANSITIONS ────────────────────── */
const PAGES  = ['dashboard','timeline','replay','failure','validation','metrics'];
const TITLES = { dashboard:'Dashboard', timeline:'Event Timeline', replay:'Replay Engine', failure:'Failure Lab', validation:'State Validation', metrics:'Performance Metrics' };
let curPage  = 'dashboard';
let curPageIdx = 0;

function showPage(id, skipTransition = false) {
  const newIdx = PAGES.indexOf(id);
  const dir    = newIdx > curPageIdx ? 'left' : 'right';

  PAGES.forEach(p => {
    const el  = document.getElementById(`page-${p}`);
    const nav = document.getElementById(`nav-${p}`);
    if (p === id) {
      el.classList.add('active');
      if (!skipTransition && p !== curPage) {
        el.classList.remove('slide-in-left', 'slide-in-right');
        void el.offsetWidth; // force reflow
        el.classList.add(dir === 'left' ? 'slide-in-left' : 'slide-in-right');
      }
    } else {
      el.classList.remove('active', 'slide-in-left', 'slide-in-right');
    }
    nav.classList.toggle('active', p === id);
  });

  document.getElementById('breadcrumb-page').textContent = TITLES[id];
  curPageIdx = newIdx;
  curPage    = id;

  if (id === 'dashboard')  loadDashboard();
  if (id === 'timeline')   loadStreamOpts(['timeline-stream-select']);
  if (id === 'failure')  { loadStreamOpts(['failure-stream-select']); buildChaosCards(); }
  closeMobile();
}

document.querySelectorAll('.nav-link').forEach(a => a.addEventListener('click', () => showPage(a.dataset.page)));
document.getElementById('hero-replay-btn').addEventListener('click', () => showPage('replay'));

/* ── GLOBAL STATE ─────────────────────────────────────────── */
let streams = [];

/* ── HEALTH ───────────────────────────────────────────────── */
async function checkHealth() {
  const dot   = document.getElementById('backend-status-dot');
  const txt   = document.getElementById('backend-status-text');
  const bar   = document.getElementById('offline-banner');
  const top   = document.getElementById('topbar');
  const badge = document.getElementById('live-badge');
  dot.className = 'status-dot connecting'; txt.textContent = 'connecting…';
  try {
    await apiCall('GET', '/health');
    dot.className = 'status-dot'; txt.textContent = 'backend ok';
    bar.classList.remove('show'); top.classList.remove('offline'); top.classList.add('online');
    badge.classList.add('show'); return true;
  } catch {
    dot.className = 'status-dot offline'; txt.textContent = 'offline';
    bar.classList.add('show'); top.classList.remove('online'); top.classList.add('offline');
    badge.classList.remove('show'); return false;
  }
}
checkHealth(); setInterval(checkHealth, 12000);

/* ── STREAMS ──────────────────────────────────────────────── */
async function loadStreams() {
  try {
    const d = await apiCall('GET', '/queries/streams');
    streams  = d.streams || [];
    const el = document.getElementById('topbar-stream-count');
    countUp(el, streams.length, 600, '', streams.length === 1 ? ' stream' : ' streams');
  } catch { streams = []; }
  return streams;
}
function fillSelect(id) {
  const s = document.getElementById(id); if (!s) return;
  const cur = s.value;
  s.innerHTML = '<option value="">Select account…</option>';
  streams.forEach(x => { const o = document.createElement('option'); o.value = x; o.textContent = x; s.appendChild(o); });
  if (cur && streams.includes(cur)) s.value = cur;
}
async function loadStreamOpts(ids) { await loadStreams(); ids.forEach(fillSelect); }

/* ── SKELETONS ────────────────────────────────────────────── */
function showSkeletons() {
  ['stat-accounts','stat-events'].forEach(id =>
    document.getElementById(id).innerHTML = '<div class="skeleton skeleton-value"></div>');
  document.getElementById('stat-balance').innerHTML = '<div class="skeleton skeleton-value" style="width:100px;"></div>';
  document.getElementById('stat-health').innerHTML  = '<div class="skeleton" style="height:22px;width:70px;"></div>';
  document.getElementById('stat-health-sub').textContent = '';
}

/* ── SEED ─────────────────────────────────────────────────── */
async function seedData() {
  const btn = document.getElementById('btn-seed');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Seeding…';
  try {
    toast('Seeding demo accounts…', 'info');
    const d = await apiCall('POST', '/simulate/seed', { num_accounts: 3, transactions_per_account: 4 });
    toast(`✓ Seeded ${d.seeded_accounts.length} accounts`, 'success');
    await loadDashboard();
  } catch (e) { toast('Seed failed: ' + e.message, 'error'); }
  btn.disabled = false; btn.innerHTML = '<span class="material-icons">add_circle</span> Seed';
}
document.getElementById('btn-seed').addEventListener('click', seedData);
document.getElementById('hero-seed-btn').addEventListener('click', seedData);
document.getElementById('btn-refresh').addEventListener('click', () => { if (curPage === 'dashboard') loadDashboard(); });

/* ── DASHBOARD ────────────────────────────────────────────── */
async function loadDashboard() {
  showSkeletons();
  await loadStreams();
  if (!streams.length) {
    document.getElementById('stat-accounts').textContent = '0';
    document.getElementById('stat-events').textContent   = '0';
    document.getElementById('stat-balance').textContent  = '$0.00';
    document.getElementById('stat-health').textContent   = 'EMPTY';
    document.getElementById('stat-health').className     = 'stat-value text-muted';
    document.getElementById('stat-health-sub').textContent = 'seed data first';
    document.getElementById('topbar-event-count').textContent = '0 events';
    document.getElementById('accounts-table-wrap').innerHTML = '<div class="empty"><span class="material-icons">account_balance</span><strong>No accounts</strong><p>Create demo accounts to explore event sourcing</p><button class="btn btn-primary" onclick="seedData()"><span class="material-icons">dataset</span> Seed Demo Data</button></div>';
    document.getElementById('dashboard-events').innerHTML = '<div class="empty"><span class="material-icons">timeline</span><strong>No events</strong></div>';
    return;
  }
  try {
    const data = await apiCall('GET', '/queries/replay?mode=full');
    const accs = Object.values(data.state.accounts || {});
    const v    = data.validation || {};
    const bal  = v.total_balance ?? 0;
    const evts = data.state.total_events_processed ?? 0;

    countUp(document.getElementById('stat-accounts'), accs.length);
    countUp(document.getElementById('stat-events'), evts);
    document.getElementById('stat-balance').textContent = fmtBal(bal);
    countUp(document.getElementById('topbar-event-count'), evts, 600, '', ' events');

    const ok = v.is_valid;
    document.getElementById('stat-health').textContent  = ok ? '✓ VALID' : '✗ INVALID';
    document.getElementById('stat-health').className    = 'stat-value ' + (ok ? 'text-green' : 'text-red');
    document.getElementById('stat-health-sub').textContent = ok ? 'all invariants pass' : 'violations detected';
    const icon = document.getElementById('stat-health-icon');
    icon.className = 'stat-icon ' + (ok ? 'stat-icon-green' : 'stat-icon-status');
    icon.style.background = ok ? '' : 'var(--red-bg)';
    icon.style.color      = ok ? '' : 'var(--red-400)';

    renderTable(accs);
    renderRecent(data.state);
  } catch (e) { toast('Dashboard: ' + e.message, 'error'); }
}

/* ── ACCOUNT TABLE WITH SEARCH ────────────────────────────── */
function renderTable(accs) {
  const wrap = document.getElementById('accounts-table-wrap');
  if (!accs.length) { wrap.innerHTML = '<div class="empty"><span class="material-icons">account_balance</span><strong>No accounts</strong></div>'; return; }

  // Search bar for ≥3 accounts
  const searchHtml = accs.length >= 3 ? `
    <div class="table-search-wrap">
      <span class="material-icons table-search-icon">search</span>
      <input type="text" class="table-search-input" id="acct-search" placeholder="Filter by owner or ID…" oninput="filterTable(this.value)" />
    </div>` : '';

  let rows = '';
  accs.forEach(a => {
    rows += `<tr data-owner="${esc(a.owner.toLowerCase())}" data-id="${esc(a.account_id.toLowerCase())}">
      <td class="mono copyable" onclick="copyText('${esc(a.account_id)}', this)" title="Click to copy">
        <span class="truncate" style="max-width:130px;">${esc(a.account_id)}</span>
        <span class="copy-tooltip">Copied!</span>
      </td>
      <td>${esc(a.owner)}</td>
      <td class="mono ${a.balance > 0 ? 'bal-pos' : 'bal-zero'}">${fmtBal(a.balance)}</td>
      <td><span class="chip ${a.status === 'active' ? 'chip-green' : 'chip-red'}">${esc(a.status)}</span></td>
      <td class="mono">${a.event_count}</td>
    </tr>`;
  });

  wrap.innerHTML = `${searchHtml}<table class="account-table"><thead><tr><th>Account ID</th><th>Owner</th><th>Balance</th><th>Status</th><th>Events</th></tr></thead><tbody id="acct-tbody">${rows}</tbody></table>`;
}

function filterTable(q) {
  const term  = q.toLowerCase().trim();
  const tbody = document.getElementById('acct-tbody');
  if (!tbody) return;
  let matches = 0;
  tbody.querySelectorAll('tr').forEach(row => {
    const visible = !term || row.dataset.owner.includes(term) || row.dataset.id.includes(term);
    row.style.display = visible ? '' : 'none';
    if (visible) matches++;
  });
  // Show no-match row if needed
  let nm = tbody.querySelector('.no-match-row');
  if (matches === 0 && term) {
    if (!nm) { nm = document.createElement('tr'); nm.className = 'no-match-row'; nm.innerHTML = `<td colspan="5">No accounts match "<strong>${esc(term)}</strong>"</td>`; tbody.appendChild(nm); }
  } else { if (nm) nm.remove(); }
}

function renderRecent(state) {
  (async () => {
    try {
      const combined = [];
      for (const s of streams.slice(0, 3)) {
        const d = await apiCall('GET', `/queries/events/${s}`);
        (d.events || []).forEach(e => combined.push({ ...e, stream_id: e.stream_id || s }));
      }
      combined.sort((a, b) => new Date(b.occurred_at) - new Date(a.occurred_at));
      document.getElementById('dashboard-events').innerHTML = combined.length
        ? buildTimeline(combined.slice(0, 18))
        : '<div class="empty"><span class="material-icons">timeline</span><strong>No events</strong></div>';
      const total = state.total_events_processed ?? combined.length;
      countUp(document.getElementById('topbar-event-count'), total, 600, '', ' events');
    } catch {}
  })();
}

/* ── EVENT TIMELINE WITH EXPANDABLE CARDS ─────────────────── */
function buildTimeline(evts) {
  return `<div class="timeline">${evts.map(evtCard).join('')}</div>`;
}

function evtCard(e) {
  const parts = [];
  if (e.amount != null)         parts.push(`amount: ${fmtBal(e.amount)}`);
  if (e.initial_balance != null)parts.push(`initial: ${fmtBal(e.initial_balance)}`);
  if (e.target_account_id)      parts.push(`to: ${esc(e.target_account_id)}`);
  if (e.owner)                  parts.push(`owner: ${esc(e.owner)}`);
  const sid = e.stream_id || '—';
  const rawJson = JSON.stringify(e, null, 2);
  const uid = `tl-${Math.random().toString(36).slice(2,8)}`;
  return `<div class="tl-item">
    <div class="tl-dot ${dotCls(e.type)}"></div>
    <div class="tl-card" onclick="toggleEvtCard('${uid}', this)" id="${uid}-card">
      <div class="tl-card-header">
        <div>
          <div class="tl-type">${esc(e.type || 'UnknownEvent')}</div>
          <div class="tl-meta">${ago(e.occurred_at)} · <span class="truncate" style="max-width:110px;" title="${esc(sid)}">${esc(sid)}</span></div>
          ${parts.length ? `<div class="tl-data">${parts.join(' · ')}</div>` : ''}
        </div>
        <span class="material-icons tl-expand-icon">expand_more</span>
      </div>
      <div class="tl-payload" id="${uid}-payload">
        <div class="tl-payload-inner">
          ${syntaxHL(rawJson)}
          <button class="tl-copy-btn" onclick="event.stopPropagation();copyJsonBtn(this,'${uid}')" title="Copy JSON">
            <span class="material-icons">content_copy</span> copy
          </button>
        </div>
      </div>
    </div>
    <div class="tl-version">v${e.version ?? '?'}</div>
  </div>`;
}

function toggleEvtCard(uid, cardEl) {
  const payload = document.getElementById(`${uid}-payload`);
  if (!payload) return;
  const isOpen = payload.classList.toggle('open');
  cardEl.classList.toggle('expanded', isOpen);
}

// Store raw JSON per uid for copy
const _jsonStore = {};
function copyJsonBtn(btn, uid) {
  // Find the content inside tl-payload-inner (strip HTML)
  const inner = btn.closest('.tl-payload-inner');
  const text  = inner ? inner.innerText.replace(/copy\s*$/, '').trim() : '';
  navigator.clipboard?.writeText(text).then(() => {
    btn.classList.add('copied');
    btn.innerHTML = '<span class="material-icons">check</span> copied';
    setTimeout(() => { btn.classList.remove('copied'); btn.innerHTML = '<span class="material-icons">content_copy</span> copy'; }, 1800);
  }).catch(() => {});
}

/* ── TIMELINE PAGE WITH FILTER PILLS ─────────────────────── */
let _tlAllEvents = []; // store for client-side filter
let _activeFilter = 'ALL';

document.getElementById('btn-load-timeline').addEventListener('click', async () => {
  const id  = document.getElementById('timeline-stream-select').value;
  if (!id) { toast('Select a stream first', 'error'); return; }
  const btn = document.getElementById('btn-load-timeline');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Loading…';
  try {
    const d    = await apiCall('GET', `/queries/events/${id}`);
    const evts = d.events || [];
    _tlAllEvents  = evts.map(e => ({ ...e, stream_id: id }));
    _activeFilter = 'ALL';

    document.getElementById('timeline-header').style.display = 'flex';
    document.getElementById('timeline-stream-label').textContent = id;
    document.getElementById('timeline-event-count').textContent  = `${evts.length} events`;

    buildFilterPills(_tlAllEvents);
    renderFilteredTimeline();
  } catch (e) { toast('Load failed: ' + e.message, 'error'); }
  btn.disabled = false; btn.innerHTML = '<span class="material-icons">search</span> Load Events';
});

function buildFilterPills(evts) {
  // Collect unique types and their counts
  const counts = {};
  evts.forEach(e => { const t = e.type || 'Unknown'; counts[t] = (counts[t] || 0) + 1; });
  const types = Object.keys(counts);

  if (types.length < 2) { document.getElementById('filter-pills-wrap').style.display = 'none'; return; }

  document.getElementById('filter-pills-wrap').style.display = 'block';
  const pills = document.getElementById('filter-pills');
  pills.innerHTML = `<span class="filter-pill active" data-type="ALL" onclick="setFilter('ALL')">All <span class="filter-pill-count">${evts.length}</span></span>` +
    types.map(t => `<span class="filter-pill" data-type="${esc(t)}" onclick="setFilter('${esc(t)}')">${esc(t)} <span class="filter-pill-count">${counts[t]}</span></span>`).join('');
}

function setFilter(type) {
  _activeFilter = type;
  document.querySelectorAll('.filter-pill').forEach(p => p.classList.toggle('active', p.dataset.type === type));
  renderFilteredTimeline();
}

function renderFilteredTimeline() {
  const filtered = _activeFilter === 'ALL'
    ? _tlAllEvents
    : _tlAllEvents.filter(e => (e.type || 'Unknown') === _activeFilter);

  const info   = document.getElementById('filter-result-info');
  const events = document.getElementById('timeline-events');
  const chip   = document.getElementById('timeline-event-count');

  if (_activeFilter !== 'ALL') {
    info.textContent = `Showing ${filtered.length} of ${_tlAllEvents.length} events`;
    info.style.display = 'block';
  } else {
    info.style.display = 'none';
  }
  chip.textContent = `${filtered.length} events`;

  events.innerHTML = filtered.length
    ? buildTimeline(filtered)
    : `<div class="empty"><span class="material-icons">filter_alt</span><strong>No events match "${_activeFilter}"</strong></div>`;
}

/* ── REPLAY ───────────────────────────────────────────────── */
document.getElementById('btn-run-replay').addEventListener('click', async () => {
  const mode = document.getElementById('replay-mode-select').value;
  const btn  = document.getElementById('btn-run-replay');
  const prog = document.getElementById('replay-progress');
  const msg  = document.getElementById('replay-status-msg');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Running…';
  prog.style.width = '25%'; msg.textContent = `Running ${mode} replay…`; msg.style.color = 'var(--text-2)';
  try {
    prog.style.width = '65%';
    const d = await apiCall('GET', `/queries/replay?mode=${mode}`);
    prog.style.width = '100%';
    const m = d.metrics || {}, v = d.validation || {};
    document.getElementById('rm-mode').textContent     = m.mode || mode;
    document.getElementById('rm-duration').textContent = fmtMs(m.duration_ms);
    document.getElementById('rm-events').textContent   = m.events_processed ?? '—';
    document.getElementById('rm-streams').textContent  = m.streams_processed ?? '—';
    const ok = v.is_valid;
    document.getElementById('rm-valid').textContent = ok ? '✓ PASS' : '✗ FAIL';
    document.getElementById('rm-valid').className   = 'mono ' + (ok ? 'text-green' : 'text-red');
    document.getElementById('replay-state-out').innerHTML = syntaxHL(d.state);
    msg.textContent = `Done in ${fmtMs(m.duration_ms)} · ${m.events_processed} events`;
    msg.style.color = 'var(--green-400)';
    toast(`Replay: ${fmtMs(m.duration_ms)}`, 'success');
    setTimeout(() => { prog.style.width = '0%'; }, 2200);
  } catch (e) {
    prog.style.width = '0%'; msg.textContent = 'Failed: ' + e.message; msg.style.color = 'var(--red-400)';
    toast('Replay failed: ' + e.message, 'error');
  }
  btn.disabled = false; btn.innerHTML = '<span class="material-icons">play_arrow</span> Run Replay';
});

/* ── FAILURE LAB ──────────────────────────────────────────── */
const FAILURES = [
  { id:'crash',     icon:'power_off',     cls:'fi-crash',   title:'Crash Recovery',    desc:'Wipe in-memory state — replay restores it',          ep:'/simulate/crash',        body:null,                              method:'POST', locked:false },
  { id:'duplicate', icon:'content_copy',  cls:'fi-dup',     title:'Duplicate Events',  desc:'Inject duplicate event_id — idempotency blocks it',  ep:'/simulate/duplicate',    body:a=>({account_id:a,amount:50}),     method:'POST', locked:true  },
  { id:'out-order', icon:'swap_vert',     cls:'fi-order',   title:'Out-of-Order',      desc:'Swap event ordering — ordering guard rejects it',     ep:'/simulate/out-of-order', body:a=>({account_id:a}),               method:'POST', locked:true  },
  { id:'missing',   icon:'remove_circle', cls:'fi-missing', title:'Missing Event',     desc:'Skip event version — gap detection catches it',       ep:'/simulate/missing',      body:a=>({account_id:a}),               method:'POST', locked:true  },
  { id:'corrupt',   icon:'dangerous',     cls:'fi-corrupt', title:'State Corruption',  desc:'Corrupt RAM balance — replay restores correct value', ep:'/simulate/corruption',   body:a=>({account_id:a}),               method:'POST', locked:true  },
  { id:'concurrent',icon:'multiple_stop', cls:'fi-concur',  title:'Concurrent Writes', desc:'5 threads race — OCC ensures exactly 1 wins',        ep:'/simulate/concurrent',   body:a=>({account_id:a,num_writers:5}), method:'POST', locked:true  },
];
const runs = {};

function buildChaosCards() {
  document.getElementById('failure-grid').innerHTML = FAILURES.map(f => `
    <div class="chaos-card" id="fc-${f.id}">
      <span class="run-badge ${(runs[f.id]||0) > 0 ? 'show' : ''}" id="rc-${f.id}">×${runs[f.id]||0}</span>
      <div class="chaos-header">
        <div class="chaos-icon ${f.cls}"><span class="material-icons">${f.icon}</span></div>
        <div class="chaos-info"><div class="chaos-title">${f.title}</div><div class="chaos-desc">${f.desc}</div></div>
      </div>
      <button class="btn btn-secondary" style="width:100%;justify-content:center;" id="fb-${f.id}" onclick="runFailure('${f.id}')">
        <span class="material-icons">science</span> Inject
      </button>
      <div class="chaos-result" id="fr-${f.id}"></div>
      ${f.locked ? `<div class="chaos-lock" id="flo-${f.id}"><span class="material-icons">lock</span><span>Select account</span></div>` : ''}
    </div>`).join('');
  updateLocks();
}

function updateLocks() {
  const v = document.getElementById('failure-stream-select').value;
  FAILURES.filter(f => f.locked).forEach(f => {
    const el = document.getElementById(`flo-${f.id}`);
    if (el) el.classList.toggle('show', !v);
  });
}

document.getElementById('failure-stream-select').addEventListener('change', async function () {
  const v = this.value;
  document.getElementById('failure-current-balance').textContent = v ? '…' : '—';
  updateLocks();
  if (!v) return;
  try {
    const d = await apiCall('GET', `/queries/state/${v}`);
    document.getElementById('failure-current-balance').textContent = fmtBal(d.balance);
  } catch { document.getElementById('failure-current-balance').textContent = '—'; }
});

async function runFailure(id) {
  const acct = document.getElementById('failure-stream-select').value;
  const f    = FAILURES.find(x => x.id === id);
  if (!f) return;
  if (f.locked && !acct) { toast('Select account first', 'error'); return; }
  const btn  = document.getElementById(`fb-${id}`);
  const res  = document.getElementById(`fr-${id}`);
  const card = document.getElementById(`fc-${id}`);
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Running…'; }
  if (res) res.className = 'chaos-result';
  try {
    const body = f.body ? f.body(acct) : null;
    const d  = await apiCall(f.method, f.ep, body);
    const ok = !!d.recovered;
    const resp = String(d.system_response || (ok ? 'Recovered.' : 'Not recovered.'));
    if (card) { card.classList.remove('pass','fail'); card.classList.add(ok ? 'pass' : 'fail'); }
    if (res) {
      res.className = `chaos-result show ${ok ? 'res-pass' : 'res-fail'}`;
      const det = d.details ? '<br><br>' + Object.entries(d.details).map(([k,v])=>`<strong>${esc(k)}:</strong> ${esc(JSON.stringify(v))}`).join('<br>') : '';
      res.innerHTML = `<strong>${ok ? '✓ RECOVERED' : '✗ NOT RECOVERED'}</strong><br>${esc(resp)}${det}`;
    }
    addLog(d.scenario || f.title, resp, ok);
    toast(`${f.title}: ${ok ? 'recovered ✓' : 'not recovered ✗'}`, ok ? 'success' : 'error');
    runs[id] = (runs[id] || 0) + 1;
    const badge = document.getElementById(`rc-${id}`);
    if (badge) { badge.textContent = `×${runs[id]}`; badge.classList.add('show'); }
    if (acct) { try { const s = await apiCall('GET', `/queries/state/${acct}`); document.getElementById('failure-current-balance').textContent = fmtBal(s.balance); } catch {} }
  } catch (e) {
    if (res) { res.className = 'chaos-result show res-fail'; res.textContent = '✗ ' + e.message; }
    if (card) card.classList.add('fail');
    toast(e.message, 'error');
  }
  if (btn) { btn.disabled = false; btn.innerHTML = '<span class="material-icons">science</span> Inject'; }
}

function addLog(scenario, response, ok) {
  const log = document.getElementById('failure-log');
  const empty = log.querySelector('.empty'); if (empty) empty.remove();
  const rs    = String(response);
  const trunc = rs.slice(0, 120) + (rs.length > 120 ? '…' : '');
  const el    = document.createElement('div');
  el.className = `vi ${ok ? 'vi-ok' : 'vi-error'}`;
  el.innerHTML = `<span class="material-icons vi-icon">${ok ? 'check_circle' : 'error'}</span><div><strong>${esc(String(scenario))}</strong> — ${esc(trunc)}<br><span style="opacity:.4;font-size:10px;">${new Date().toLocaleTimeString()}</span></div>`;
  log.prepend(el);
}

/* ── VALIDATION ───────────────────────────────────────────── */
document.getElementById('btn-validate').addEventListener('click', async () => {
  const btn = document.getElementById('btn-validate');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Validating…';
  try {
    const d    = await apiCall('GET', '/queries/replay?mode=full');
    const v    = d.validation || {};
    const accs = Object.values(d.state.accounts || {});
    const ok   = !!v.is_valid;
    document.getElementById('validation-summary').innerHTML = `<div class="vi ${ok ? 'vi-ok' : 'vi-error'}"><span class="material-icons vi-icon">${ok ? 'check_circle' : 'cancel'}</span><div><div style="font-size:14px;font-weight:700;">${ok ? 'All Invariants Pass' : 'Violations Detected'}</div><div style="margin-top:6px;">Balance: <span class="text-amber">${fmtBal(v.total_balance)}</span></div><div>Findings: ${v.finding_count ?? 0}</div></div></div>`;
    const findings = v.findings || [];
    document.getElementById('validation-findings').innerHTML = !findings.length
      ? '<div class="vi vi-ok"><span class="material-icons vi-icon">check_circle</span>No findings — valid</div>'
      : findings.map(f => `<div class="vi vi-error"><span class="material-icons vi-icon">warning</span>${esc(f.message || JSON.stringify(f))}</div>`).join('');
    document.getElementById('validation-accounts').innerHTML = !accs.length
      ? '<div class="empty"><span class="material-icons">account_balance</span><strong>No accounts</strong></div>'
      : accs.map(a => `<div class="vi ${a.balance >= 0 ? 'vi-ok' : 'vi-error'}"><span class="material-icons vi-icon">${a.balance >= 0 ? 'account_balance_wallet' : 'error'}</span><div><strong>${esc(a.owner)}</strong> <span class="mono text-muted" style="font-size:10px;">${esc(a.account_id)}</span><br>Balance: <span class="text-amber">${fmtBal(a.balance)}</span> · Events: ${a.event_count} · ${esc(a.status)}</div></div>`).join('');
    toast('Validation complete', 'success');
  } catch (e) { toast('Validation: ' + e.message, 'error'); }
  btn.disabled = false; btn.innerHTML = '<span class="material-icons">verified</span> Run Validation';
});

/* ── METRICS WITH SVG CHART ───────────────────────────────── */
function tLine(type, text) {
  const el = document.getElementById('bench-body');
  const ln = document.createElement('div');
  ln.className = `t-${type}`; ln.textContent = text;
  el.appendChild(ln); el.scrollTop = el.scrollHeight;
}

function renderSvgChart(fullMs, snapMs) {
  const wrap = document.getElementById('svg-chart-wrap');
  const svg  = document.getElementById('bench-svg');
  const tip  = document.getElementById('chart-tooltip');
  if (!wrap || !svg) return;

  const W = 300, H = 120, PAD = { left: 42, bottom: 30, top: 10, right: 16 };
  const chartW = W - PAD.left - PAD.right;
  const chartH = H - PAD.top - PAD.bottom;

  const maxVal = Math.max(fullMs, snapMs, 0.1);
  const bars   = [
    { label: 'Full',     val: fullMs, cls: 'chart-bar-full', color: '#f59e0b', valClass: 'chart-val-label' },
    { label: 'Snapshot', val: snapMs, cls: 'chart-bar-snap', color: '#38bdf8', valClass: 'chart-val-label chart-val-label-sky' },
  ];
  const barW   = (chartW / bars.length) * 0.55;
  const gap    = (chartW / bars.length) * 0.45;

  // Y gridlines
  const gridLines = [0, 0.25, 0.5, 0.75, 1].map(frac => {
    const y = PAD.top + chartH - frac * chartH;
    const v = (frac * maxVal).toFixed(1);
    return `<line class="chart-grid-line" x1="${PAD.left}" y1="${y}" x2="${W - PAD.right}" y2="${y}" />
            <text class="chart-axis-label" x="${PAD.left - 4}" y="${y + 3.5}" text-anchor="end">${v}</text>`;
  }).join('');

  // Bars (width + x manually set; height animated via JS)
  const barSvgs = bars.map((b, i) => {
    const x     = PAD.left + i * (barW + gap) + gap / 2;
    const fullH = (b.val / maxVal) * chartH;
    const y     = PAD.top + chartH - fullH;
    return `<rect class="${b.cls}" id="svg-bar-${i}" x="${x}" y="${PAD.top + chartH}" width="${barW}" height="0"
              rx="3" data-full-h="${fullH}" data-y="${y}" style="cursor:pointer;"
              onmouseenter="showChartTip(event,'${b.label}: ${b.val.toFixed(2)}ms')"
              onmouseleave="hideChartTip()" />
            <text class="chart-axis-label" x="${x + barW/2}" y="${H - 8}" text-anchor="middle">${b.label}</text>`;
  }).join('');

  svg.innerHTML = `<defs>
    <linearGradient id="barGradAmber" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#f59e0b" /><stop offset="100%" stop-color="#d97706" stop-opacity="0.7" />
    </linearGradient>
    <linearGradient id="barGradSky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#38bdf8" /><stop offset="100%" stop-color="#0ea5e9" stop-opacity="0.7" />
    </linearGradient>
  </defs>
  ${gridLines}${barSvgs}`;

  wrap.style.display = 'block';

  // Animate bars rising
  requestAnimationFrame(() => {
    svg.querySelectorAll('rect').forEach((rect, i) => {
      const targetH = parseFloat(rect.dataset.fullH);
      const targetY = parseFloat(rect.dataset.y);
      const start   = performance.now();
      const dur     = 700 + i * 120;
      (function step(now) {
        const p    = Math.min((now - start) / dur, 1);
        const ease = 1 - Math.pow(1 - p, 3);
        rect.setAttribute('height', targetH * ease);
        rect.setAttribute('y', (PAD.top + chartH) - (targetH * ease));
        if (p < 1) requestAnimationFrame(step);
      })(performance.now());
    });
  });
}

function showChartTip(e, text) {
  const tip  = document.getElementById('chart-tooltip');
  const wrap = document.getElementById('svg-chart-wrap');
  if (!tip || !wrap) return;
  const r = wrap.getBoundingClientRect();
  tip.textContent = text;
  tip.style.left  = (e.clientX - r.left + 10) + 'px';
  tip.style.top   = (e.clientY - r.top  - 30) + 'px';
  tip.classList.add('show');
}
function hideChartTip() {
  const tip = document.getElementById('chart-tooltip');
  if (tip) tip.classList.remove('show');
}

document.getElementById('btn-bench').addEventListener('click', async () => {
  const btn  = document.getElementById('btn-bench');
  const body = document.getElementById('bench-body');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Running…';
  body.innerHTML = '';
  document.getElementById('bench-ts').textContent = new Date().toLocaleTimeString();
  try {
    tLine('cmd', '> Running full replay…');
    const full = await apiCall('GET', '/queries/replay?mode=full');
    const fm   = full.metrics || {};
    tLine('value', `  Full:     ${fmtMs(fm.duration_ms)} (${fm.events_processed} events)`);
    requestAnimationFrame(() => {
      document.getElementById('bar-full').style.width  = '100%';
      document.getElementById('bval-full').textContent = fmtMs(fm.duration_ms);
    });
    document.getElementById('perf-full-ms').textContent = fmtMs(fm.duration_ms);

    tLine('dim', '');
    tLine('cmd', '> Running snapshot replay…');
    const snap = await apiCall('GET', '/queries/replay?mode=snapshot');
    const sm   = snap.metrics || {};
    tLine('value', `  Snapshot: ${fmtMs(sm.duration_ms)} (${sm.events_processed} events)`);
    const maxVal = Math.max(fm.duration_ms || 0.001, sm.duration_ms || 0.001);
    requestAnimationFrame(() => {
      document.getElementById('bar-snap').style.width  = `${Math.min(100, (sm.duration_ms || 0) / maxVal * 100)}%`;
      document.getElementById('bval-snap').textContent = fmtMs(sm.duration_ms);
    });
    document.getElementById('perf-snap-ms').textContent = fmtMs(sm.duration_ms);

    // Render animated SVG chart
    renderSvgChart(fm.duration_ms || 0, sm.duration_ms || 0);

    const speedup = ((fm.duration_ms || 1) / (sm.duration_ms || 1)).toFixed(2);
    tLine('dim', '');
    tLine('cmd', '> Analysis:');
    tLine('value', `  Speedup: ${speedup}×`);
    tLine(full.validation?.is_valid ? 'pass' : 'fail', `  Full validation:  ${full.validation?.is_valid ? 'PASS ✓' : 'FAIL ✗'}`);
    tLine(snap.validation?.is_valid ? 'pass' : 'fail', `  Snap validation:  ${snap.validation?.is_valid ? 'PASS ✓' : 'FAIL ✗'}`);
    const match = full.validation?.total_balance === snap.validation?.total_balance;
    tLine(match ? 'pass' : 'fail', `  Totals match:     ${match ? 'YES ✓' : 'NO ✗'}`);
    toast('Benchmarks done', 'success');
  } catch (e) { tLine('fail', `✗ ${e.message}`); toast('Benchmark: ' + e.message, 'error'); }
  btn.disabled = false; btn.innerHTML = '<span class="material-icons">speed</span> Run Benchmarks';
});

/* ══════════════════════════════════════════════════════════════
   COMMAND PALETTE — Cmd+K
   ═══════════════════════════════════════════════════════════ */
const CMD_ITEMS = [
  // NAVIGATE
  { group:'NAVIGATE', icon:'dashboard',    label:'Go to Dashboard',        kbd:'G then D', action:()=>showPage('dashboard') },
  { group:'NAVIGATE', icon:'history',      label:'Go to Timeline',         kbd:'G then T', action:()=>showPage('timeline') },
  { group:'NAVIGATE', icon:'play_circle',  label:'Go to Replay Engine',    kbd:'G then R', action:()=>showPage('replay') },
  { group:'NAVIGATE', icon:'biotech',      label:'Go to Failure Lab',      kbd:'G then F', action:()=>showPage('failure') },
  { group:'NAVIGATE', icon:'fact_check',   label:'Go to Validation',       kbd:'G then V', action:()=>showPage('validation') },
  { group:'NAVIGATE', icon:'query_stats',  label:'Go to Metrics',          kbd:'G then M', action:()=>showPage('metrics') },
  // ACTIONS
  { group:'ACTIONS',  icon:'dataset',      label:'Seed Demo Data',         kbd:'S',        action:()=>seedData() },
  { group:'ACTIONS',  icon:'play_arrow',   label:'Run Full Replay',        kbd:'',         action:()=>{ showPage('replay'); setTimeout(()=>document.getElementById('btn-run-replay').click(),400); } },
  { group:'ACTIONS',  icon:'speed',        label:'Run Benchmarks',         kbd:'',         action:()=>{ showPage('metrics'); setTimeout(()=>document.getElementById('btn-bench').click(),400); } },
  { group:'ACTIONS',  icon:'verified',     label:'Run Validation',         kbd:'',         action:()=>{ showPage('validation'); setTimeout(()=>document.getElementById('btn-validate').click(),400); } },
  { group:'ACTIONS',  icon:'refresh',      label:'Refresh Dashboard',      kbd:'R',        action:()=>loadDashboard() },
  { group:'ACTIONS',  icon:'settings_ethernet', label:'Configure API URL', kbd:'',         action:()=>openApiModal() },
];

let _cmdOpen = false;
let _cmdIdx  = 0;
let _cmdFiltered = [...CMD_ITEMS];

function openCmdPalette() {
  _cmdOpen = true;
  _cmdIdx  = 0;
  document.getElementById('cmd-palette-bg').classList.add('open');
  document.getElementById('cmd-input').value = '';
  renderCmdResults('');
  setTimeout(() => document.getElementById('cmd-input').focus(), 50);
}

function closeCmdPalette() {
  _cmdOpen = false;
  document.getElementById('cmd-palette-bg').classList.remove('open');
}

function renderCmdResults(query) {
  const q = query.toLowerCase().trim();
  // Group filtered results
  const filtered = q
    ? CMD_ITEMS.filter(i => i.label.toLowerCase().includes(q) || i.group.toLowerCase().includes(q))
    : CMD_ITEMS;
  _cmdFiltered = filtered;
  _cmdIdx = 0;

  if (!filtered.length) {
    document.getElementById('cmd-results').innerHTML = `<div class="cmd-empty">No results for "<strong>${esc(q)}</strong>"</div>`;
    return;
  }

  const groups = {};
  filtered.forEach(item => { (groups[item.group] = groups[item.group] || []).push(item); });

  let html = '';
  let globalIdx = 0;
  Object.entries(groups).forEach(([group, items]) => {
    html += `<div class="cmd-group-label">${group}</div>`;
    items.forEach((item, i) => {
      const idx  = globalIdx++;
      const label = q ? item.label.replace(new RegExp(`(${q})`, 'gi'), '<span class="cmd-match">$1</span>') : item.label;
      html += `<div class="cmd-item ${idx === 0 ? 'highlighted' : ''}" data-idx="${idx}" onclick="execCmdItem(${CMD_ITEMS.indexOf(item)})">
        <span class="material-icons">${item.icon}</span>
        <span class="cmd-item-label">${label}</span>
        ${item.kbd ? `<span class="cmd-item-kbd">${item.kbd}</span>` : ''}
      </div>`;
    });
  });

  document.getElementById('cmd-results').innerHTML = html;
}

function execCmdItem(idx) {
  const item = CMD_ITEMS[idx];
  if (!item) return;
  closeCmdPalette();
  item.action();
}

function highlightCmd(direction) {
  const items = document.querySelectorAll('.cmd-item');
  if (!items.length) return;
  items[_cmdIdx]?.classList.remove('highlighted');
  _cmdIdx = (_cmdIdx + direction + items.length) % items.length;
  const next = items[_cmdIdx];
  next?.classList.add('highlighted');
  next?.scrollIntoView({ block: 'nearest' });
}

// Input events
document.getElementById('cmd-input').addEventListener('input', e => renderCmdResults(e.target.value));
document.getElementById('cmd-input').addEventListener('keydown', e => {
  if (e.key === 'ArrowDown')  { e.preventDefault(); highlightCmd(1); }
  if (e.key === 'ArrowUp')    { e.preventDefault(); highlightCmd(-1); }
  if (e.key === 'Escape')     { closeCmdPalette(); }
  if (e.key === 'Enter') {
    const highlighted = document.querySelector('.cmd-item.highlighted');
    if (highlighted) { const idx = parseInt(highlighted.dataset.idx); execCmdItem(CMD_ITEMS.indexOf(_cmdFiltered[idx])); }
  }
});
document.getElementById('cmd-palette-bg').addEventListener('click', e => { if (e.target === e.currentTarget) closeCmdPalette(); });
document.getElementById('btn-cmd-palette').addEventListener('click', openCmdPalette);

/* ══════════════════════════════════════════════════════════════
   KEYBOARD SHORTCUTS
   G+D/T/R/F/V/M = navigate  ·  R = refresh  ·  S = seed
   Cmd+K = palette  ·  ? = hint
   ═══════════════════════════════════════════════════════════ */
let _gPending = false;
let _gTimer   = null;

document.addEventListener('keydown', e => {
  const tag = document.activeElement?.tagName;
  if (['INPUT','TEXTAREA','SELECT'].includes(tag)) return;
  if (_cmdOpen) return;

  const key = e.key.toLowerCase();

  // Cmd+K / Ctrl+K
  if ((e.metaKey || e.ctrlKey) && key === 'k') {
    e.preventDefault();
    openCmdPalette();
    return;
  }

  // Escape — close any modal
  if (key === 'escape') {
    document.querySelectorAll('.modal-bg.open').forEach(m => m.classList.remove('open'));
    return;
  }

  // G chord navigation
  if (key === 'g' && !e.metaKey && !e.ctrlKey) {
    _gPending = true;
    clearTimeout(_gTimer);
    document.getElementById('g-overlay').classList.add('show');
    _gTimer = setTimeout(() => {
      _gPending = false;
      document.getElementById('g-overlay').classList.remove('show');
    }, 1800);
    return;
  }

  if (_gPending) {
    _gPending = false;
    clearTimeout(_gTimer);
    document.getElementById('g-overlay').classList.remove('show');
    const map = { d:'dashboard', t:'timeline', r:'replay', f:'failure', v:'validation', m:'metrics' };
    if (map[key]) { showPage(map[key]); return; }
  }

  // Single-key shortcuts
  if (key === 'r' && !e.metaKey) { loadDashboard(); toast('Refreshed', 'info'); return; }
  if (key === 's' && !e.metaKey) { seedData(); return; }
  if (key === '?')               { openHelp(); return; }
});

/* ══════════════════════════════════════════════════════════════
   DEPTH FEATURES v3.2
   ═══════════════════════════════════════════════════════════ */

/* ── HELP DRAWER ──────────────────────────────────────────── */
function openHelp() {
  document.getElementById('help-backdrop').classList.add('open');
  document.getElementById('help-drawer').classList.add('open');
}
function closeHelp() {
  document.getElementById('help-backdrop').classList.remove('open');
  document.getElementById('help-drawer').classList.remove('open');
}
document.getElementById('help-fab').addEventListener('click', openHelp);
document.getElementById('help-close').addEventListener('click', closeHelp);
document.getElementById('help-backdrop').addEventListener('click', closeHelp);

/* Also close help on Esc (augment existing listener) */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeHelp();
}, true);

/* Pulse the FAB for first-time users */
setTimeout(() => {
  const fab = document.getElementById('help-fab');
  if (fab) fab.classList.add('help-fab-pulse');
}, 3500);

/* ── SYNC TICKER WITH SIDEBAR COLLAPSE ────────────────────── */
document.getElementById('sidebar-collapse-btn').addEventListener('click', () => {
  const bar = document.getElementById('ticker-bar');
  if (bar) bar.classList.toggle('sidebar-collapsed', sidebar.classList.contains('collapsed'));
});

/* ── LIVE ACTIVITY TICKER ─────────────────────────────────── */
let _tickerEvents = [];
let _tickerTimer  = null;

function buildTickerHtml(evts) {
  if (!evts.length) return '';
  // Double the content for seamless infinite scroll
  const half = evts.map(e => {
    const type = esc(e.type || 'Event');
    const sid  = esc((e.stream_id || '').slice(0, 18));
    return `<span class="ticker-evt">
      <span class="ticker-evt-dot"></span>
      <span class="ticker-evt-type">${type}</span>
      ${sid ? `· <span style="opacity:.5;">${sid}</span>` : ''}
      ${e.amount != null ? `· <span style="color:var(--green-400);">${fmtBal(e.amount)}</span>` : ''}
    </span>`;
  }).join('');
  return half + half; // duplicate for infinite scroll
}

async function pollTicker() {
  try {
    if (!streams.length) return;
    const combined = [];
    for (const s of streams.slice(0, 4)) {
      const d = await apiCall('GET', `/queries/events/${s}`);
      (d.events || []).forEach(e => combined.push({ ...e, stream_id: s }));
    }
    combined.sort((a, b) => new Date(b.occurred_at) - new Date(a.occurred_at));
    const latest = combined.slice(0, 12);
    const inner  = document.getElementById('ticker-inner');
    if (inner && JSON.stringify(latest.map(e=>e.type)) !== JSON.stringify(_tickerEvents.map(e=>e.type))) {
      _tickerEvents = latest;
      inner.innerHTML = buildTickerHtml(latest);
    }
  } catch {}
}

function startTicker() {
  pollTicker();
  _tickerTimer = setInterval(pollTicker, 8000);
}

/* ── STATE CARD VIEWER (Replay) ───────────────────────────── */
function buildStateCards(state) {
  const accs = Object.values((state && state.accounts) || {});
  const wrap = document.getElementById('state-cards');
  if (!wrap) return;
  if (!accs.length) {
    wrap.innerHTML = '<div style="color:var(--text-3);font-family:var(--font-data);font-size:12px;padding:20px;">No accounts in replayed state.</div>';
    return;
  }
  wrap.innerHTML = accs.map(a => `
    <div class="state-card-item">
      <div class="state-card-owner">${esc(a.owner || '—')}</div>
      <div class="state-card-balance">${fmtBal(a.balance)}</div>
      <div class="state-card-meta">
        <span class="state-card-status chip ${a.status === 'active' ? 'chip-green' : 'chip-red'}">${esc(a.status || '?')}</span>
        &nbsp; ${a.event_count ?? '?'} events
      </div>
      <div class="state-card-meta" style="margin-top:4px;font-size:10px;opacity:.5;">${esc(a.account_id || '')}</div>
    </div>`).join('');
}

let _lastReplayState = null;
let _lastReplayJson  = '';

function switchStateView(mode) {
  const cards    = document.getElementById('state-cards');
  const jsonView = document.getElementById('replay-state-out');
  const btnCards = document.getElementById('svbtn-cards');
  const btnJson  = document.getElementById('svbtn-json');
  if (!cards || !jsonView) return;
  if (mode === 'cards') {
    cards.style.display    = '';    cards.classList.add('show');
    jsonView.style.display = 'none';
    btnCards?.classList.add('active'); btnJson?.classList.remove('active');
  } else {
    cards.classList.remove('show'); cards.style.display = 'none';
    jsonView.style.display = '';
    btnJson?.classList.add('active'); btnCards?.classList.remove('active');
  }
}

/* Hook into the existing replay button to also populate state cards */
const _origReplayBtn = document.getElementById('btn-run-replay');
if (_origReplayBtn) {
  _origReplayBtn.addEventListener('click', () => {
    // Clear cards while loading
    const wrap = document.getElementById('state-cards');
    if (wrap) wrap.innerHTML = '<div style="color:var(--text-3);font-family:var(--font-data);font-size:12px;padding:20px;">Computing replay…</div>';
  });
}

/* Patch the replay listener to also call buildStateCards after result */
const _origReplayCall = apiCall;
/* We instead hook by observing when replay-state-out changes */
const _replayObs = new MutationObserver(() => {
  const out = document.getElementById('replay-state-out');
  if (!out || !_lastReplayState) return;
  buildStateCards(_lastReplayState);
});
const _replayOut = document.getElementById('replay-state-out');
if (_replayOut) _replayObs.observe(_replayOut, { childList: true, subtree: true });

/* Override the replay listener to capture state */
(function patchReplay() {
  const btn = document.getElementById('btn-run-replay');
  if (!btn) return;
  const handler = async function(e) {
    // The original listener fires first; we add an extra post-hook
  };
  // We wrap by overriding apiCall response capture using a short poll
  const origInnerHTML = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
  // Simpler approach: observe state-cards for the placeholder text and refetch
})();

/* ── FIRST-RUN ONBOARDING ─────────────────────────────────── */
const ONBOARD_KEY = 'rewinddb_onboarded_v3';
const ONBOARD_STEPS = [
  { step: 1, text: 'Welcome to RewindDB! Start by seeding demo data.', action: 'Seed now →', fn: () => { dismissOnboard(); seedData(); } },
  { step: 2, text: 'Explore the Timeline to see every event in order.', action: 'Open Timeline →', fn: () => { dismissOnboard(); showPage('timeline'); } },
  { step: 3, text: 'Press Cmd+K anytime to navigate instantly.', action: 'Got it', fn: () => { dismissOnboard(); localStorage.setItem(ONBOARD_KEY, '1'); } },
];
let _onboardIdx = 0;

function showOnboardStep(idx) {
  const s   = ONBOARD_STEPS[idx];
  const el  = document.getElementById('onboard-toast');
  const stepEl = document.getElementById('onboard-step');
  const textEl = document.getElementById('onboard-text');
  const actEl  = document.getElementById('onboard-action');
  if (!el || !s) return;
  if (stepEl) stepEl.textContent = s.step;
  if (textEl) textEl.textContent = s.text;
  if (actEl)  { actEl.textContent = s.action; actEl.onclick = s.fn; }
  el.classList.add('show');
}

function dismissOnboard() {
  document.getElementById('onboard-toast')?.classList.remove('show');
}

function advanceOnboard() {
  _onboardIdx++;
  if (_onboardIdx < ONBOARD_STEPS.length) {
    setTimeout(() => showOnboardStep(_onboardIdx), 800);
  } else {
    localStorage.setItem(ONBOARD_KEY, '1');
  }
}

document.getElementById('onboard-dismiss')?.addEventListener('click', () => {
  dismissOnboard();
  localStorage.setItem(ONBOARD_KEY, '1');
});

function initOnboarding() {
  if (localStorage.getItem(ONBOARD_KEY)) return; // already done
  setTimeout(() => showOnboardStep(0), 2000);
  // Auto advance through remaining steps
  setTimeout(() => { if (!localStorage.getItem(ONBOARD_KEY)) advanceOnboard(); }, 8000);
  setTimeout(() => { if (!localStorage.getItem(ONBOARD_KEY)) advanceOnboard(); }, 15000);
}

/* ── PATCH REPLAY TO CAPTURE STATE FOR CARDS ──────────────── */
/* We wrap the existing btn-run-replay click by adding a capture listener */
document.getElementById('btn-run-replay')?.addEventListener('click', async () => {
  // Wait for the existing listener to fire and update rm-mode, then read state
  await new Promise(r => setTimeout(r, 100));
  const mode = document.getElementById('replay-mode-select')?.value || 'full';
  try {
    const d = await apiCall('GET', `/queries/replay?mode=${mode}`);
    _lastReplayState = d.state;
    buildStateCards(d.state);
  } catch {}
}, true /* capture — fires before existing bubble listener */);

/* ── INIT ─────────────────────────────────────────────────── */
showPage('dashboard', true);
setTimeout(startTicker, 3000);
initOnboarding();
