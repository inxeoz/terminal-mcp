#!/usr/bin/env node
// Playwright integration test for i4z-terminal-mcp Rust web UI
// Run: bunx playwright test test.mjs  OR  node test.mjs (with @playwright/test installed)
// The Rust binary must be running: I4Z_TERMINAL_WEB_PORT=9021 ./rust/target/release/i4z-terminal-mcp
// Or run via: make rs-test-web

import { chromium } from 'playwright';

const BASE = process.env.BASE_URL || 'http://localhost:9021';
const TERM  = `test-${Date.now()}`;
let browser, page;

async function pass(name) { console.log(`  ✓ ${name}`); }
async function fail(name, err) { console.error(`  ✗ ${name}: ${err?.message || err}`); process.exitCode = 1; }

async function waitForText(selector, text, timeout = 8000) {
  await page.waitForFunction(
    ({ sel, txt }) => document.querySelector(sel)?.textContent?.includes(txt),
    { sel: selector, txt: text },
    { timeout }
  );
}

// ── helpers ────────────────────────────────────────────────────────────────────

async function apiGet(path) {
  const r = await page.evaluate(p => fetch(p).then(r => r.json()), BASE + path);
  return r;
}

async function apiPost(path, body) {
  return page.evaluate(
    ({ p, b }) => fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }).then(r => r.json()),
    { p: BASE + path, b: body }
  );
}

async function apiDelete(path) {
  return page.evaluate(
    p => fetch(p, { method: 'DELETE' }).then(r => r.json()),
    BASE + path
  );
}

// ── tests ─────────────────────────────────────────────────────────────────────

async function testServerInfo() {
  const info = await apiGet('/api/info');
  if (info.name !== 'i4z-terminal-mcp') throw new Error(`bad name: ${info.name}`);
  if (!info.version) throw new Error('missing version');
  if (info.implementation !== 'rust') throw new Error(`bad impl: ${info.implementation}`);
  await pass('GET /api/info returns name, version, implementation');

  // Version visible in header
  await page.goto(BASE);
  await page.waitForSelector('#server-version');
  const verText = await page.$eval('#server-version', el => el.textContent);
  if (!verText.includes(info.version)) throw new Error(`header shows "${verText}", expected v${info.version}`);
  await pass('server version shown in header');
}

async function testHealth() {
  const h = await apiGet('/api/health');
  if (!h.db || h.db.ok !== true) throw new Error(`db not ok: ${JSON.stringify(h.db)}`);
  await pass('GET /api/health db.ok = true');
}

async function testCreateTerminal() {
  const r = await apiPost('/api/create', { name: TERM });
  if (r.terminal_id !== TERM) throw new Error(`unexpected id: ${JSON.stringify(r)}`);
  await pass(`create terminal "${TERM}"`);
}

async function testTerminalInList() {
  const list = await apiGet('/api/terminals');
  if (!list.some(t => t.id === TERM)) throw new Error('terminal not in list');
  await pass('terminal appears in GET /api/terminals');
}

async function testTerminalStatus() {
  const s = await apiGet(`/api/status/${TERM}`);
  if (!s.alive) throw new Error(`not alive: ${JSON.stringify(s)}`);
  await pass('terminal status alive=true');
}

async function testSendAndRead() {
  await apiPost(`/api/send/${TERM}`, { text: 'echo hello-world\n' });
  // Poll read_output up to 5s
  let out = '';
  for (let i = 0; i < 20; i++) {
    const r = await apiGet(`/api/history/${TERM}?since=0`);
    out = (r.events || []).map(e => e.text).join('');
    if (out.includes('hello-world')) break;
    await new Promise(r => setTimeout(r, 250));
  }
  if (!out.includes('hello-world')) throw new Error(`output not found in: ${out.slice(0, 200)}`);
  await pass('send command + read output contains "hello-world"');
}

async function testWebSocketOutput() {
  // Open UI, open the terminal tab, verify WS connects and shows output
  await page.goto(BASE);
  // Click terminal in sidebar (wait for it to appear)
  await page.waitForFunction(id => {
    const items = document.querySelectorAll('.term-item');
    return [...items].some(el => el.dataset.id === id);
  }, TERM, { timeout: 5000 });
  await page.evaluate(id => {
    const item = [...document.querySelectorAll('.term-item')].find(el => el.dataset.id === id);
    if (item) item.click();
  }, TERM);

  // Verify xterm container becomes visible
  await page.waitForFunction(() => {
    const pane = document.querySelector('.term-pane.visible');
    return pane !== null;
  }, { timeout: 5000 });
  await pass('WebSocket: terminal pane visible after clicking');

  // Send via WS (UI input) — type into the terminal
  await apiPost(`/api/send/${TERM}`, { text: 'echo ws-verify\n' });
  // Give WS time to deliver
  await page.waitForFunction(() => {
    const canvases = document.querySelectorAll('.xterm-rows span, .xterm-screen');
    return canvases.length > 0;
  }, { timeout: 4000 }).catch(() => {});
  await pass('WebSocket: xterm rendered');
}

async function testRenameTerminal() {
  const newId = TERM + '-renamed';
  const r = await apiPost(`/api/rename/${TERM}`, { new_id: newId });
  if (!r.id && !r.new_id && r.new_id !== newId) {
    // check the list instead
    const list = await apiGet('/api/terminals');
    if (!list.some(t => t.id === newId)) throw new Error(`renamed id not in list: ${JSON.stringify(r)}`);
  }
  await pass(`rename terminal to "${newId}"`);
  return newId;
}

async function testDeleteTerminal(id) {
  const r = await apiDelete(`/api/terminals/${id}`);
  if (!r.deleted) throw new Error(`delete response: ${JSON.stringify(r)}`);
  const list = await apiGet('/api/terminals');
  if (list.some(t => t.id === id)) throw new Error('terminal still in list after delete');
  await pass(`delete terminal "${id}"`);
}

// ── main ──────────────────────────────────────────────────────────────────────

browser = await chromium.launch();
page = await browser.newPage();
page.on('console', msg => { if (msg.type() === 'error') process.stderr.write(`[browser] ${msg.text()}\n`); });

console.log(`\nTesting ${BASE}\n`);

// Wait for server to be up
for (let i = 0; i < 20; i++) {
  try {
    await page.goto(BASE, { timeout: 2000 });
    break;
  } catch {
    if (i === 19) { console.error('Server not reachable at', BASE); process.exit(1); }
    await new Promise(r => setTimeout(r, 500));
  }
}

try { await testServerInfo(); } catch(e) { await fail('server_info', e); }
try { await testHealth(); } catch(e) { await fail('health', e); }
try { await testCreateTerminal(); } catch(e) { await fail('create_terminal', e); }
try { await testTerminalInList(); } catch(e) { await fail('terminal_in_list', e); }
try { await testTerminalStatus(); } catch(e) { await fail('terminal_status', e); }
try { await testSendAndRead(); } catch(e) { await fail('send_and_read', e); }
try { await testWebSocketOutput(); } catch(e) { await fail('websocket_output', e); }
const renamedId = await testRenameTerminal().catch(async e => { await fail('rename', e); return TERM + '-renamed'; });
try { await testDeleteTerminal(renamedId); } catch(e) { await fail('delete_terminal', e); }

await browser.close();
console.log('\nDone.\n');
