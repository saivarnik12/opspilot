const { JSDOM } = require('jsdom');
const B = process.env.BASE_URL || 'http://127.0.0.1:8000';
const RUN = Date.now();
const EMAIL = `ui-${RUN}@example.com`;
const EMAIL2 = `new-${RUN}@example.com`;
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok, extra='') => { console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '  ' + extra)); if (!ok) failures++; };

async function seed() {
  const j = (p, o={}) => fetch(B + p, o).then(async r => ({ s: r.status, b: await r.json().catch(()=>null) }));
  await j('/api/v1/auth/register', { method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({email: EMAIL, password:'a-long-password'}) });
  const t = (await j('/api/v1/auth/login', { method:'POST', headers:{'content-type':'application/x-www-form-urlencoded'}, body:`username=${EMAIL}&password=a-long-password` })).b.access_token;
  const logs = [];
  for (let i = 0; i < 30; i++) logs.push({ source: 'api-1', level: 'INFO', message: `request ok ${i}` });
  for (let i = 0; i < 4; i++) logs.push({ source: 'api-2', level: 'ERROR', message: `upstream timed out after ${i + 20}s (req ${i})` });
  logs.push({ source: 'web', level: 'CRITICAL', message: '<img src=x onerror="window.__xss=1"> <script>window.__xss=2</script>' });
  const r = await j('/api/v1/logs/batch', { method:'POST', headers:{'content-type':'application/json', Authorization:'Bearer '+t}, body: JSON.stringify({ logs }) });
  check('seed 35 logs', r.s === 201);
}

async function waitFor(win, fn, label, ms = 4000) {
  const end = Date.now() + ms;
  while (Date.now() < end) { try { const v = fn(); if (v) return v; } catch (_) {} await sleep(40); }
  throw new Error('timeout waiting for: ' + label);
}
const $ = (win, sel) => win.document.querySelector(sel);
const text = (win, sel) => ($(win, sel) || {}).textContent || '';
function setVal(win, sel, v) { const el = $(win, sel); el.value = v; }
function click(win, el) { el.dispatchEvent(new win.MouseEvent('click', { bubbles: true, cancelable: true })); }
function submit(win, form) { form.dispatchEvent(new win.Event('submit', { bubbles: true, cancelable: true })); }

(async () => {
  await seed();
  const html = await (await fetch(B + '/app/')).text();
  const dom = new JSDOM(html, {
    url: B + '/app/', runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true,
    beforeParse(win) {
      win.fetch = (u, o) => fetch(new URL(u, win.location.href), o);
      win.confirm = () => true;
      win.scrollTo = () => {};
    },
  });
  const win = dom.window;
  const errors = [];
  win.addEventListener('error', e => errors.push(e.message));

  try {
    await waitFor(win, () => $(win, '#auth-submit'), 'login screen');
    check('shows login screen when signed out', true);

    // wrong password shows an error
    setVal(win, '#email', EMAIL); setVal(win, '#password', 'wrong-password-1');
    submit(win, $(win, '.auth form'));
    await waitFor(win, () => $(win, '[role=alert]'), 'login error');
    check('bad login shows error', /incorrect/i.test(text(win, '[role=alert]')));

    // correct login -> dashboard
    setVal(win, '#password', 'a-long-password');
    submit(win, $(win, '.auth form'));
    await waitFor(win, () => $(win, '#stats'), 'dashboard stats');
    const stats = text(win, '#stats');
    check('dashboard: total logs = 35', /Total logs35/.test(stats), stats);
    check('dashboard: errors = 5 (4 ERROR + 1 CRITICAL)', /Errors \(all time\)5/.test(stats), stats);
    check('dashboard: critical = 1', /Critical1/.test(stats), stats);
    check('dashboard: chart rendered with bars', win.document.querySelectorAll('svg.chart rect').length >= 2);
    await waitFor(win, () => text(win, '#who') === EMAIL, 'user email in header');
    check('header shows signed-in email', true);

    // redesign: layout, theme, health, new panels
    check('sidebar has 4 nav links', win.document.querySelectorAll('.side-nav a').length === 4);
    check('dashboard nav link is active', text(win, '.side-nav a.active').trim() === 'Dashboard');
    await waitFor(win, () => text(win, '#health-text') === 'API online', 'health indicator');
    check('health indicator shows API online', $(win, '#health-dot').classList.contains('up'));
    const mainText = text(win, 'main');
    check('dashboard: logs-by-level panel lists INFO, ERROR, CRITICAL', ['INFO', 'ERROR', 'CRITICAL'].every(l => mainText.includes(l)));
    check('dashboard: top sources panel lists api-1', mainText.includes('Top sources') && mainText.includes('api-1'));
    check('dashboard: error rate shown (5 of 35 = 14.3%)', /14\.3% of all logs/.test(text(win, '#stats')), text(win, '#stats'));
    const root = win.document.documentElement;
    check('theme: dark by default', root.getAttribute('data-theme') === 'dark');
    click(win, $(win, '#theme-toggle'));
    check('theme: toggle -> light', root.getAttribute('data-theme') === 'light' && win.localStorage.getItem('opspilot_theme') === 'light');
    check('theme: chart still rendered after toggle', win.document.querySelectorAll('svg.chart rect').length >= 2);
    click(win, $(win, '#theme-toggle'));
    check('theme: toggle -> dark again', root.getAttribute('data-theme') === 'dark' && win.localStorage.getItem('opspilot_theme') === 'dark');
    check('no inline style attributes anywhere in the live DOM', win.document.querySelectorAll('[style]').length === 0);

    // XSS safety on dashboard "latest errors" and in logs explorer
    win.location.hash = '#/logs';
    await waitFor(win, () => $(win, '#log-results table'), 'log table');
    check('logs: pagination shows 1–25 of 35', /Showing 1–25 of 35/.test(text(win, '#range')), text(win, '#range'));
    click(win, $(win, '#next'));
    await waitFor(win, () => /Showing 26–35 of 35/.test(text(win, '#range')), 'page 2');
    check('logs: next page works', true);
    check('logs: next disabled on last page', $(win, '#next').disabled);

    setVal(win, '#q', 'img src=x'); submit(win, $(win, '#log-filter'));
    await waitFor(win, () => /of 1$/.test(text(win, '#range')), 'search result');
    check('logs: search finds the hostile message', /1–1 of 1/.test(text(win, '#range')));
    check('XSS: payload shown as literal text', text(win, '#log-results td.msg').includes('<img src=x onerror='));
    check('XSS: no <img> element created', win.document.querySelectorAll('#log-results img').length === 0);
    check('XSS: no <script> injected, nothing executed', win.__xss === undefined && win.document.querySelectorAll('#log-results script').length === 0);

    setVal(win, '#q', ''); setVal(win, '#level', 'ERROR'); submit(win, $(win, '#log-filter'));
    await waitFor(win, () => /of 4$/.test(text(win, '#range')), 'level filter');
    check('logs: level filter ERROR -> 4', true);

    // incidents
    win.location.hash = '#/incidents';
    await waitFor(win, () => $(win, '#patterns'), 'patterns table');
    const firstRow = $(win, '#patterns tbody tr');
    check('incidents: timeout pattern grouped (count 4)', /timed out/.test(firstRow.children[0].textContent) && firstRow.children[1].textContent === '4', firstRow.textContent);
    check('incidents: 2 patterns (timeouts + hostile critical)', win.document.querySelectorAll('#patterns tbody tr').length === 2);
    const analyze = [...win.document.querySelectorAll('#patterns button')].find(b => /Analyze/.test(b.textContent));
    click(win, analyze);
    await waitFor(win, () => $(win, '#root-cause'), 'incident detail');
    check('incident detail: title', /Timeouts/i.test(text(win, '#inc-title')), text(win, '#inc-title'));
    check('incident detail: root cause shown', text(win, '#root-cause').length > 10);
    check('incident detail: >=2 recommended fixes', win.document.querySelectorAll('#fixes li').length >= 2);
    check('incident detail: shows analysis source', /rule engine/i.test(win.document.body.textContent));
    click(win, $(win, '#resolve'));
    await waitFor(win, () => $(win, '#reopen'), 'resolved state');
    check('incident: can be resolved (Reopen appears)', true);

    // api keys
    win.location.hash = '#/keys';
    await waitFor(win, () => $(win, '#key-name'), 'keys page');
    setVal(win, '#key-name', 'prod-server-1');
    submit(win, $(win, '#key-name').closest('form'));
    await waitFor(win, () => $(win, '#new-key-value'), 'new key banner');
    const key = text(win, '#new-key-value');
    check('api keys: raw key shown once (op_…)', /^op_/.test(key));
    const ing = await fetch(B + '/api/v1/logs', { method:'POST', headers:{'content-type':'application/json','X-API-Key':key}, body: JSON.stringify({source:'agent',level:'INFO',message:'hello'}) });
    check('api keys: created key actually works for ingestion', ing.status === 201);
    await waitFor(win, () => $(win, '#key-list'), 'key list');
    const revoke = [...win.document.querySelectorAll('#key-list button')].find(b => /Revoke/.test(b.textContent));
    click(win, revoke);
    await waitFor(win, () => /revoked/.test(text(win, '#key-list')), 'revoked badge');
    const after = await fetch(B + '/api/v1/logs', { method:'POST', headers:{'content-type':'application/json','X-API-Key':key}, body: JSON.stringify({source:'agent',level:'INFO',message:'again'}) });
    check('api keys: revoked key is rejected (401)', after.status === 401);

    // logout
    click(win, $(win, '#logout'));
    await waitFor(win, () => $(win, '#auth-submit'), 'back to login');
    check('logout returns to login and clears token', win.localStorage.getItem('opspilot_token') === null);

    // register a brand-new account through the UI
    click(win, $(win, '#tab-register'));
    setVal(win, '#email', EMAIL2); setVal(win, '#password', 'another-long-pass');
    submit(win, $(win, '.auth form'));
    await waitFor(win, () => $(win, '#stats'), 'dashboard after register');
    check('register -> auto login -> empty dashboard (0 logs)', /Total logs0/.test(text(win, '#stats')), text(win, '#stats'));
    check('data isolation: new user sees no chart data', /No logs in this time range/.test(text(win, 'main')));
  } catch (e) {
    console.log('FAIL (exception) ' + e.message); failures++;
    console.log('--- body ---\n' + win.document.body.textContent.slice(0, 600));
  }
  // saved light theme is applied on load (no flash): theme.js runs before first paint
  try {
    const dom2 = new JSDOM(html, { url: B + '/app/', runScripts: 'dangerously', resources: 'usable',
      beforeParse(w) { w.localStorage.setItem('opspilot_theme', 'light'); w.fetch = (u, o) => fetch(new URL(u, w.location.href), o); } });
    await waitFor(dom2.window, () => dom2.window.document.querySelector('#auth-submit'), 'second window login');
    check('theme: saved light preference applied on load', dom2.window.document.documentElement.getAttribute('data-theme') === 'light');
    dom2.window.close();
  } catch (e) { console.log('FAIL (exception) ' + e.message); failures++; }
  check('no uncaught JS errors in page', errors.length === 0, errors.join('|'));
  console.log(failures === 0 ? '\nALL UI CHECKS PASSED' : `\n${failures} UI CHECK(S) FAILED`);
  process.exit(failures ? 1 : 0);
})();
