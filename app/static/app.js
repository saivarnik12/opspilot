(() => {
'use strict';
const app = document.getElementById('app');
const TOKEN_KEY = 'opspilot_token';
const THEME_KEY = 'opspilot_theme';
const state = { email: null, hours: 24, logs: { q: '', level: '', source: '', page: 0 }, incStatus: '' };
const PAGE_SIZE = 25;

/* ---------- DOM helpers: nodes are built from text only, so untrusted log content can never become markup ---------- */
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'value') el.value = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const SVG_NS = 'http://www.w3.org/2000/svg';
function svg(tag, attrs, ...kids) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const ICONS = {
  dashboard: 'M3 3h8v8H3z M13 3h8v5h-8z M13 10h8v11h-8z M3 13h8v8H3z',
  logs: 'M4 6h16 M4 12h16 M4 18h10',
  incidents: 'M12 3l10 18H2z M12 10v5 M12 18v.01',
  keys: 'M8 11a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M10.8 12.2L20 3 M16 7l3 3 M14 9l2 2',
  sun: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M12 2v2 M12 20v2 M4.9 4.9l1.4 1.4 M17.7 17.7l1.4 1.4 M2 12h2 M20 12h2 M4.9 19.1l1.4-1.4 M17.7 6.3l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z',
};
function icon(name) {
  return svg('svg', { class: 'icon', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2,
    'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' }, svg('path', { d: ICONS[name] }));
}
function logo() {
  return svg('svg', { class: 'logo', viewBox: '0 0 32 32', 'aria-hidden': 'true' },
    svg('rect', { width: 32, height: 32, rx: 8, fill: '#4c8dff' }),
    svg('path', { d: 'M6 19h5l3-9 4 14 3-9h5', fill: 'none', stroke: '#fff', 'stroke-width': 2.4, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
}

/* ---------- helpers ---------- */
const getToken = () => localStorage.getItem(TOKEN_KEY);
function fmtTime(iso) {
  if (!iso) return '';
  if (!/(Z|[+-]\d\d:?\d\d)$/i.test(iso)) iso += 'Z'; // SQLite returns naive UTC timestamps
  const d = new Date(iso);
  return isNaN(d) ? String(iso) : d.toLocaleString();
}
function fmtTick(iso, hours) {
  if (!/(Z|[+-]\d\d:?\d\d)$/i.test(iso)) iso += 'Z';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  return hours > 48
    ? d.toLocaleDateString([], { month: 'short', day: 'numeric' })
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
const num = (n) => Number(n).toLocaleString();
const badge = (text, cls) => h('span', { class: 'badge ' + (cls || text) }, text);
const errorBox = (msg) => h('div', { class: 'error', role: 'alert' }, msg);
const empty = (msg) => h('div', { class: 'empty' }, msg);
function errMsg(d) {
  if (!d) return null;
  if (typeof d.detail === 'string') return d.detail;
  if (Array.isArray(d.detail)) return d.detail.map(e => (e.loc || []).slice(1).join('.') + ': ' + e.msg).join('; ');
  return null;
}
async function api(path, { method = 'GET', body, form, auth = true } = {}) {
  const headers = {};
  if (auth && getToken()) headers.Authorization = 'Bearer ' + getToken();
  let payload;
  if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded';
    payload = new URLSearchParams(form).toString();
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  const res = await fetch(path, { method, headers, body: payload });
  if (res.status === 401 && auth) { logout(); throw new Error('Session expired. Please sign in again.'); }
  if (res.status === 204) return { data: null, res };
  let data = null;
  try { data = await res.json(); } catch (_) { /* no body */ }
  if (!res.ok) throw new Error(errMsg(data) || 'Request failed (' + res.status + ')');
  return { data, res };
}

/* ---------- theme ---------- */
const currentTheme = () => (document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark');
function toggleTheme() {
  const next = currentTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem(THEME_KEY, next); } catch (_) { /* storage blocked */ }
  document.querySelectorAll('#theme-toggle').forEach(b => b.replaceChildren(icon(next === 'dark' ? 'sun' : 'moon')));
  document.querySelectorAll('#theme-toggle').forEach(b => b.setAttribute('aria-label', next === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'));
}
function themeButton() {
  const dark = currentTheme() === 'dark';
  return h('button', { class: 'secondary icon-btn', id: 'theme-toggle', type: 'button', title: 'Toggle theme',
    'aria-label': dark ? 'Switch to light theme' : 'Switch to dark theme', onclick: toggleTheme }, icon(dark ? 'sun' : 'moon'));
}

/* ---------- auth ---------- */
function logout() {
  localStorage.removeItem(TOKEN_KEY);
  state.email = null;
  location.hash = '#/login';
  route();
}
function renderAuth() {
  let mode = 'login';
  const msg = h('div');
  const email = h('input', { type: 'email', id: 'email', autocomplete: 'username', required: true, placeholder: 'you@company.com' });
  const password = h('input', { type: 'password', id: 'password', autocomplete: 'current-password', required: true, minlength: 8 });
  const submit = h('button', { type: 'submit', id: 'auth-submit' }, 'Sign in');
  const tabLogin = h('button', { type: 'button', id: 'tab-login', onclick: () => setMode('login') }, 'Sign in');
  const tabReg = h('button', { type: 'button', class: 'secondary', id: 'tab-register', onclick: () => setMode('register') }, 'Create account');
  function setMode(m) {
    mode = m;
    tabLogin.className = m === 'login' ? '' : 'secondary';
    tabReg.className = m === 'register' ? '' : 'secondary';
    submit.textContent = m === 'login' ? 'Sign in' : 'Create account';
    password.autocomplete = m === 'login' ? 'current-password' : 'new-password';
    msg.replaceChildren();
  }
  const form = h('form', {
    onsubmit: async (e) => {
      e.preventDefault();
      msg.replaceChildren();
      submit.disabled = true;
      try {
        if (mode === 'register') {
          await api('/api/v1/auth/register', { method: 'POST', auth: false, body: { email: email.value.trim(), password: password.value } });
        }
        const { data } = await api('/api/v1/auth/login', { method: 'POST', auth: false, form: { username: email.value.trim(), password: password.value } });
        localStorage.setItem(TOKEN_KEY, data.access_token);
        state.email = null;
        location.hash = '#/dashboard';
        route();
      } catch (err) {
        msg.replaceChildren(errorBox(err.message));
      } finally {
        submit.disabled = false;
      }
    },
  },
    h('label', {}, 'Email', email),
    h('label', {}, 'Password (min 8 characters)', password),
    submit, msg);
  app.replaceChildren(h('div', { class: 'auth-wrap' },
    h('div', { class: 'corner' }, themeButton()),
    h('div', { class: 'auth card' },
      h('div', { class: 'brand' }, logo(), 'OpsPilot'),
      h('p', { class: 'muted' }, 'Find the cause faster. Log monitoring with AI incident analysis.'),
      h('div', { class: 'tabs' }, tabLogin, tabReg),
      form)));
}

/* ---------- shell ---------- */
const NAV = [['#/dashboard', 'Dashboard', 'dashboard'], ['#/logs', 'Logs', 'logs'], ['#/incidents', 'Incidents', 'incidents'], ['#/keys', 'API keys', 'keys']];
function renderShell(path) {
  const who = h('div', { class: 'who', id: 'who' }, state.email || '');
  const healthDot = h('span', { class: 'pulse', id: 'health-dot' });
  const healthText = h('span', { id: 'health-text' }, 'Checking…');
  const links = NAV.map(([href, label, ic]) =>
    h('a', { href, class: path.startsWith(href.slice(1)) ? 'active' : '' }, icon(ic), h('span', {}, label)));
  const main = h('main', { id: 'main' });
  app.replaceChildren(h('div', { class: 'layout' },
    h('aside', { class: 'side' },
      h('a', { class: 'brand', href: '#/dashboard' }, logo(), 'OpsPilot'),
      h('nav', { class: 'side-nav', 'aria-label': 'Main' }, links),
      h('div', { class: 'side-foot' },
        h('div', { class: 'status' }, healthDot, healthText),
        who,
        h('div', { class: 'foot-actions' }, themeButton(), h('button', { class: 'secondary grow', id: 'logout', onclick: logout }, 'Log out')))),
    main));
  fetch('/health').then(r => { if (!r.ok) throw new Error(); healthDot.className = 'pulse up'; healthText.textContent = 'API online'; })
    .catch(() => { healthDot.className = 'pulse down'; healthText.textContent = 'API unreachable'; });
  if (!state.email) {
    api('/api/v1/auth/me').then(({ data }) => { state.email = data.email; who.textContent = data.email; }).catch(() => {});
  }
  return main;
}
const pageHead = (title, subtitle, ...controls) =>
  h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, title), subtitle && h('p', { class: 'muted' }, subtitle)), h('span', { class: 'spacer' }), controls);

/* ---------- dashboard ---------- */
function barChart(points, hours, width) {
  const W = Math.max(300, Math.min(1000, Math.round(width || 760)));
  const H = W < 500 ? 210 : 250, L = 40, B = 26, T = 10, R = 8;
  const max = Math.max(1, ...points.map(p => p.total));
  const bw = (W - L - R) / points.length;
  const y = v => T + (H - T - B) * (1 - v / max);
  const root = svg('svg', { class: 'chart', viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Log volume and errors over time' });
  const ticks = [0, 1, 2, 3, 4].map(i => Math.round(max * i / 4));
  for (const v of [...new Set(ticks)]) {
    root.append(svg('line', { class: 'gridline', x1: L, x2: W - R, y1: y(v), y2: y(v) }));
    root.append(svg('text', { x: L - 8, y: y(v) + 4, 'text-anchor': 'end' }, num(v)));
  }
  points.forEach((p, i) => {
    const x = L + i * bw + 1.5, w = Math.max(1.5, bw - 3);
    const other = p.total - p.errors;
    const g = svg('g', { class: 'col' }, svg('title', {}, `${fmtTime(p.start)}: ${p.total} logs, ${p.errors} errors`));
    if (other > 0) g.append(svg('rect', { class: 'bar-ok', x, y: y(other), width: w, height: y(0) - y(other), rx: 2 }));
    if (p.errors > 0) g.append(svg('rect', { class: 'bar-err', x, y: y(p.total), width: w, height: y(other) - y(p.total), rx: 2 }));
    root.append(g);
  });
  const fracs = W < 500 ? [0, 0.5, 1] : [0, 0.25, 0.5, 0.75, 1];
  fracs.forEach((f, k) => {
    const idx = Math.min(points.length - 1, Math.round(f * (points.length - 1)));
    root.append(svg('text', { x: L + idx * bw + bw / 2, y: H - 7, 'text-anchor': k === 0 ? 'start' : k === fracs.length - 1 ? 'end' : 'middle' }, fmtTick(points[idx].start, hours)));
  });
  return root;
}
function statCard(label, value, accent, hot, sub) {
  return h('div', { class: `card stat accent-${accent}${hot ? ' hot' : ''}` },
    h('div', { class: 'label' }, label), h('div', { class: 'value' }, value), sub && h('div', { class: 'sub' }, sub));
}
function barList(items, total, fillClass) {
  if (items.length === 0) return empty('No data yet.');
  return h('div', { class: 'barlist' }, items.map(([label, count, cls]) => {
    const pct = total ? Math.max(1.5, (count / total) * 100) : 0;
    return h('div', { class: 'barrow' },
      h('div', { class: 'barhead' }, h('span', {}, label), h('span', { class: 'muted' }, num(count))),
      svg('svg', { class: 'bar-svg', width: '100%', height: 8, role: 'presentation' },
        svg('rect', { class: 'bar-track', width: '100%', height: 8, rx: 4 }),
        svg('rect', { class: cls || fillClass, width: pct + '%', height: 8, rx: 4 })));
  }));
}
const LEVELS = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'];
async function viewDashboard(main) {
  main.replaceChildren(pageHead('Dashboard', 'Loading…'));
  const [stats, ts, open, recent] = await Promise.all([
    api('/api/v1/logs/stats'),
    api('/api/v1/logs/timeseries?hours=' + state.hours),
    api('/api/v1/incidents?status=open&limit=200'),
    api('/api/v1/logs?level=ERROR&limit=5'),
  ]);
  const by = stats.data.by_level, total = stats.data.total;
  const errors = (by.ERROR || 0) + (by.CRITICAL || 0);
  const windowErrors = ts.data.points.reduce((a, p) => a + p.errors, 0);
  const windowTotal = ts.data.points.reduce((a, p) => a + p.total, 0);
  const rate = total ? ((errors / total) * 100).toFixed(1) : '0.0';
  const hoursSel = h('select', { id: 'hours', 'aria-label': 'Time range', onchange: (e) => { state.hours = +e.target.value; route(); } },
    [[1, 'Last hour'], [6, 'Last 6 hours'], [24, 'Last 24 hours'], [72, 'Last 3 days'], [168, 'Last 7 days']]
      .map(([v, l]) => h('option', { value: v, selected: v === state.hours }, l)));
  const chartBox = h('div', { id: 'chart-box' }, windowTotal === 0 ? empty('No logs in this time range yet. Send some with an API key.') : null);
  const topSources = Object.entries(stats.data.by_source).sort((a, b) => b[1] - a[1]).slice(0, 5);
  main.replaceChildren(
    pageHead('Dashboard', 'Live overview of your logs and incidents', hoursSel),
    h('div', { class: 'grid kpis', id: 'stats' },
      statCard('Total logs', num(total), 'blue'),
      statCard('Errors (all time)', num(errors), 'red', errors > 0, `${rate}% of all logs`),
      statCard('Critical', num(by.CRITICAL || 0), 'pink', (by.CRITICAL || 0) > 0),
      statCard('Open incidents', num(open.data.length), 'amber', open.data.length > 0)),
    h('div', { class: 'card mt-lg' },
      h('h2', {}, 'Logs and errors over time'),
      chartBox,
      h('div', { class: 'legend' },
        h('span', {}, h('span', { class: 'dot ok' }), 'Other logs'),
        h('span', {}, h('span', { class: 'dot err' }), 'Errors'),
        h('span', { class: 'spacer' }),
        h('span', {}, `${num(windowTotal)} logs, ${num(windowErrors)} errors in range`))),
    h('div', { class: 'grid two mt-lg' },
      h('div', { class: 'card' }, h('h2', {}, 'Logs by level'),
        barList(LEVELS.filter(l => by[l]).map(l => [l, by[l], 'lvl-' + l]), total)),
      h('div', { class: 'card' }, h('h2', {}, 'Top sources'),
        barList(topSources.map(([s, c]) => [s, c]), total, 'bar-fill'))),
    h('div', { class: 'card mt-lg' }, h('h2', {}, 'Latest errors'),
      recent.data.length === 0 ? empty('No errors. All quiet.') : logTable(recent.data)));
  // measure after layout so the chart is drawn 1:1 (labels stay readable on phones)
  if (windowTotal > 0) chartBox.replaceChildren(barChart(ts.data.points, state.hours, chartBox.clientWidth || 760));
}

/* ---------- logs ---------- */
function logTable(rows) {
  return h('div', { class: 'table-wrap' }, h('table', { class: 'stack' },
    h('thead', {}, h('tr', {}, ['Time', 'Level', 'Source', 'Message'].map(t => h('th', {}, t)))),
    h('tbody', {}, rows.map(r => h('tr', {},
      h('td', { class: 'nowrap' }, fmtTime(r.timestamp)),
      h('td', {}, badge(r.level)),
      h('td', {}, r.source),
      h('td', { class: 'msg' }, r.message))))));
}
async function viewLogs(main) {
  const f = state.logs;
  const q = h('input', { type: 'search', id: 'q', placeholder: 'Search messages…', value: f.q, 'aria-label': 'Search messages' });
  const level = h('select', { id: 'level', 'aria-label': 'Level' },
    [['', 'All levels'], ['DEBUG', 'DEBUG'], ['INFO', 'INFO'], ['WARNING', 'WARNING'], ['ERROR', 'ERROR'], ['CRITICAL', 'CRITICAL']]
      .map(([v, l]) => h('option', { value: v, selected: v === f.level }, l)));
  const source = h('input', { type: 'text', id: 'source', placeholder: 'Source (exact)', value: f.source, 'aria-label': 'Source' });
  const result = h('div', { id: 'log-results', class: 'mt' });
  const apply = (e) => { e.preventDefault(); f.q = q.value.trim(); f.level = level.value; f.source = source.value.trim(); f.page = 0; load(); };
  main.replaceChildren(pageHead('Log explorer', 'Search and filter everything your servers send'),
    h('form', { class: 'toolbar', id: 'log-filter', onsubmit: apply }, q, level, source, h('button', { type: 'submit' }, 'Search')),
    result);
  async function load() {
    result.replaceChildren(h('p', { class: 'muted' }, 'Loading…'));
    const p = new URLSearchParams({ limit: PAGE_SIZE, offset: f.page * PAGE_SIZE });
    if (f.q) p.set('q', f.q);
    if (f.level) p.set('level', f.level);
    if (f.source) p.set('source', f.source);
    try {
      const { data, res } = await api('/api/v1/logs?' + p);
      const total = +res.headers.get('X-Total-Count') || 0;
      const from = total === 0 ? 0 : f.page * PAGE_SIZE + 1, to = f.page * PAGE_SIZE + data.length;
      result.replaceChildren(
        h('div', { class: 'card' }, data.length ? logTable(data) : empty('No logs match your filters.')),
        h('div', { class: 'pager' },
          h('button', { class: 'secondary', id: 'prev', disabled: f.page === 0, onclick: () => { f.page--; load(); } }, '← Previous'),
          h('button', { class: 'secondary', id: 'next', disabled: to >= total, onclick: () => { f.page++; load(); } }, 'Next →'),
          h('span', { class: 'muted', id: 'range' }, `Showing ${from}–${to} of ${total}`)));
    } catch (e) { result.replaceChildren(errorBox(e.message)); }
  }
  await load();
}

/* ---------- incidents ---------- */
async function viewIncidents(main) {
  const [patterns, incidents] = await Promise.all([
    api('/api/v1/incidents/patterns?hours=24&limit=20'),
    api('/api/v1/incidents?limit=100' + (state.incStatus ? '&status=' + state.incStatus : '')),
  ]);
  const msg = h('div');
  const analyze = async (btn, fp) => {
    btn.disabled = true; msg.replaceChildren();
    try {
      const { data } = await api('/api/v1/incidents/analyze', { method: 'POST', body: { fingerprint: fp, hours: 24 } });
      location.hash = '#/incidents/' + data.id;
    } catch (e) { msg.replaceChildren(errorBox(e.message)); btn.disabled = false; }
  };
  const statusSel = h('select', { id: 'inc-status', 'aria-label': 'Status filter', onchange: (e) => { state.incStatus = e.target.value; route(); } },
    [['', 'All statuses'], ['open', 'Open'], ['resolved', 'Resolved']].map(([v, l]) => h('option', { value: v, selected: v === state.incStatus }, l)));
  main.replaceChildren(
    pageHead('Incidents', 'Recurring errors, grouped and analyzed'),
    msg,
    h('div', { class: 'card' },
      h('h2', {}, 'Detected error patterns (last 24h)'),
      patterns.data.length === 0
        ? empty('No recurring errors detected.')
        : h('div', { class: 'table-wrap' }, h('table', { id: 'patterns' },
          h('thead', {}, h('tr', {}, ['Pattern', 'Count', 'Sources', 'Last seen', ''].map(t => h('th', {}, t)))),
          h('tbody', {}, patterns.data.map(p => {
            const btn = h('button', { onclick: () => analyze(btn, p.fingerprint) }, 'Analyze');
            return h('tr', {},
              h('td', { class: 'msg' }, h('span', { class: 'code' }, p.template)),
              h('td', {}, p.count),
              h('td', {}, p.sources.slice(0, 3).join(', ') + (p.sources.length > 3 ? ' +' + (p.sources.length - 3) : '')),
              h('td', { class: 'nowrap' }, fmtTime(p.last_seen)),
              h('td', {}, btn));
          }))))),
    h('div', { class: 'card mt-lg' },
      h('div', { class: 'row' }, h('h2', {}, 'Incident history'), h('span', { class: 'spacer' }), statusSel),
      incidents.data.length === 0
        ? empty('No incidents yet. Analyze a pattern above to create one.')
        : h('div', { class: 'table-wrap' }, h('table', { id: 'incident-list' },
          h('thead', {}, h('tr', {}, ['Incident', 'Severity', 'Status', 'Events', 'Last seen'].map(t => h('th', {}, t)))),
          h('tbody', {}, incidents.data.map(i => h('tr', {},
            h('td', { class: 'msg' }, h('a', { href: '#/incidents/' + i.id }, i.title)),
            h('td', {}, badge(i.severity)),
            h('td', {}, badge(i.status)),
            h('td', {}, i.log_count),
            h('td', { class: 'nowrap' }, fmtTime(i.last_seen)))))))));
}
async function viewIncident(main, id) {
  const { data: i } = await api('/api/v1/incidents/' + id);
  const msg = h('div');
  const setStatus = async (status) => {
    try { await api('/api/v1/incidents/' + id, { method: 'PATCH', body: { status } }); route(); }
    catch (e) { msg.replaceChildren(errorBox(e.message)); }
  };
  const reanalyze = async (btn) => {
    btn.disabled = true; msg.replaceChildren();
    try { await api('/api/v1/incidents/analyze', { method: 'POST', body: { fingerprint: i.fingerprint, hours: 24 } }); route(); }
    catch (e) { msg.replaceChildren(errorBox(e.message)); btn.disabled = false; }
  };
  const reBtn = h('button', { class: 'secondary', onclick: () => reanalyze(reBtn) }, 'Re-run analysis');
  main.replaceChildren(
    h('p', {}, h('a', { href: '#/incidents' }, '← All incidents')),
    h('div', { class: 'page-head' },
      h('div', {}, h('h1', { id: 'inc-title' }, i.title),
        h('p', { class: 'muted' }, `${num(i.log_count)} events · ${fmtTime(i.first_seen)} → ${fmtTime(i.last_seen)} · ${i.affected_sources.join(', ')}`)),
      h('span', { class: 'spacer' }), badge(i.severity), badge(i.status)),
    msg,
    h('div', { class: 'card detail-grid' },
      h('div', {}, h('h2', {}, 'Summary'), h('p', {}, i.summary)),
      h('div', {}, h('h2', {}, 'Likely root cause'), h('div', { class: 'callout', id: 'root-cause' }, i.root_cause)),
      h('div', {}, h('h2', {}, 'Recommended fixes'), h('ol', { class: 'fixes', id: 'fixes' }, i.recommended_fixes.map(f => h('li', {}, f)))),
      h('p', { class: 'muted' },
        i.analysis_source === 'claude' ? `Analysis by Claude (${i.analysis_model})` : 'Analysis by built-in rule engine',
        ` · analyzed ${fmtTime(i.analyzed_at)}`)),
    h('div', { class: 'row mt' },
      i.status === 'open'
        ? [h('button', { id: 'resolve', onclick: () => setStatus('resolved') }, 'Mark resolved'), reBtn]
        : h('button', { class: 'secondary', id: 'reopen', onclick: () => setStatus('open') }, 'Reopen')));
}

/* ---------- API keys ---------- */
async function viewKeys(main) {
  const { data: keys } = await api('/api/v1/api-keys');
  const msg = h('div');
  const name = h('input', { type: 'text', id: 'key-name', placeholder: 'Key name, e.g. prod-server-1', maxlength: 100, required: true, 'aria-label': 'Key name' });
  const create = async (e) => {
    e.preventDefault(); msg.replaceChildren();
    try {
      const { data } = await api('/api/v1/api-keys', { method: 'POST', body: { name: name.value.trim() } });
      const copy = h('button', { class: 'secondary', onclick: async () => {
        try { await navigator.clipboard.writeText(data.key); copy.textContent = 'Copied'; } catch (_) { copy.textContent = 'Copy failed'; }
      } }, 'Copy');
      await viewKeys(main);
      main.querySelector('#key-msg').replaceChildren(h('div', { class: 'notice', id: 'new-key' },
        h('strong', {}, 'Copy your key now. It will not be shown again.'),
        h('p', {}, h('span', { class: 'code', id: 'new-key-value' }, data.key)), copy,
        h('p', { class: 'muted' }, 'Send logs with the header ', h('code', {}, 'X-API-Key: <key>'), '.')));
    } catch (err) { msg.replaceChildren(errorBox(err.message)); }
  };
  const revoke = async (k) => {
    if (!confirm(`Revoke key "${k.name}"? Agents using it will stop working.`)) return;
    try { await api('/api/v1/api-keys/' + k.id, { method: 'DELETE' }); route(); }
    catch (err) { msg.replaceChildren(errorBox(err.message)); }
  };
  main.replaceChildren(
    pageHead('API keys', 'Keys let servers and agents send logs without a password'),
    h('form', { class: 'toolbar', onsubmit: create }, name, h('button', { type: 'submit' }, 'Create key')),
    h('div', { id: 'key-msg' }), msg,
    h('div', { class: 'card mt' }, keys.length === 0
      ? empty('No API keys yet. Create one to start sending logs.')
      : h('div', { class: 'table-wrap' }, h('table', { id: 'key-list' },
        h('thead', {}, h('tr', {}, ['Name', 'Key prefix', 'Created', 'Status', ''].map(t => h('th', {}, t)))),
        h('tbody', {}, keys.map(k => h('tr', {},
          h('td', {}, k.name), h('td', {}, h('span', { class: 'code' }, k.prefix + '…')),
          h('td', { class: 'nowrap' }, fmtTime(k.created_at)),
          h('td', {}, k.revoked ? badge('revoked') : badge('active')),
          h('td', {}, k.revoked ? '' : h('button', { class: 'danger', onclick: () => revoke(k) }, 'Revoke')))))))));
}

/* ---------- router ---------- */
const routes = [
  [/^\/dashboard$/, viewDashboard], [/^\/logs$/, viewLogs], [/^\/incidents$/, viewIncidents],
  [/^\/incidents\/(\d+)$/, viewIncident], [/^\/keys$/, viewKeys],
];
async function route() {
  const path = (location.hash || '#/dashboard').slice(1);
  if (!getToken()) { renderAuth(); return; }
  for (const [rx, fn] of routes) {
    const m = path.match(rx);
    if (m) {
      const main = renderShell(path);
      try { await fn(main, ...m.slice(1)); } catch (e) { main.replaceChildren(errorBox(e.message)); }
      return;
    }
  }
  location.hash = '#/dashboard';
}
window.addEventListener('hashchange', route);
let lastWidth = window.innerWidth, resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (Math.abs(window.innerWidth - lastWidth) > 120 && (location.hash || '#/dashboard').startsWith('#/dashboard') && getToken()) route();
    lastWidth = window.innerWidth;
  }, 250);
});
route();
})();
