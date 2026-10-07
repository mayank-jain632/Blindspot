import { chromium, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { mkdirSync, readdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
const { sidebarHtml } = createRequire(import.meta.url)('../../extension/sidebar.js');
const root = resolve(import.meta.dirname, '../..');
const fixture = spawn(resolve(root, '.venv/bin/python'), ['-B', '-m', 'scripts.release_demo_fixture'], { cwd: root, stdio: ['ignore', 'pipe', 'inherit'] });
let browser;
try {
  const { url } = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Screenshot fixture timeout')), 15000);
    createInterface({ input: fixture.stdout }).once('line', line => { clearTimeout(timer); resolve(JSON.parse(line)); });
    fixture.once('exit', code => { clearTimeout(timer); reject(new Error(`Fixture exited ${code}`)); });
  });
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  mkdirSync(resolve(root, 'docs/screenshots'), { recursive: true });
  for (const [name, hash, selector] of [['map', '#map', '.map-cell'], ['risk', '#risk', '.risk-table'], ['learning', '#learn', '.learning-file'], ['guide', '#guide?path=fines.py', '.guide-item'], ['insights', '#insights', '.calibration']]) {
    await page.goto(url + '/' + hash);
    await expect(page.locator(selector).first()).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: resolve(root, `docs/screenshots/${name}.png`), fullPage: true });
  }
  await page.goto(url + '/#share');
  await expect(page.getByRole('button', { name: 'Download PNG' })).toBeEnabled();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download PNG' }).click();
  await (await download).saveAs(resolve(root, 'docs/screenshots/share.png'));
  const data = await (await page.request.get(url + '/api/dashboard')).json();
  const assets = { cspSource: url };
  const files = readdirSync(resolve(root, 'blindspot/observer/dashboard_dist/assets'));
  for (const [id, family] of [['mono','ibm-plex-mono'],['body','eb-garamond'],['display','cormorant-garamond']]) assets[id] = url + '/assets/' + files.find(n => n.startsWith(family + '-latin-400-normal') && n.endsWith('.woff2'));
  const sidebar = await browser.newPage({ viewport: { width: 360, height: 1100 } });
  await sidebar.addInitScript(() => { window.acquireVsCodeApi = () => ({ postMessage() {} }); });
  await sidebar.route(url + '/sidebar-preview', route => route.fulfill({ contentType: 'text/html', body: sidebarHtml(data, null, 'screenshot', assets) }));
  await sidebar.goto(url + '/sidebar-preview');
  await sidebar.evaluate(() => document.fonts.ready);
  await sidebar.screenshot({ path: resolve(root, 'docs/screenshots/sidebar.png'), fullPage: true });
  console.log('Release screenshots captured from disposable Shelfmark demo. Sidebar is a webview preview.');
} finally {
  await browser?.close(); fixture.kill('SIGTERM');
}
