import { chromium, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const project = resolve(import.meta.dirname, '../..');
const fixture = spawn(resolve(project, '.venv/bin/python'), ['-B', '-m', 'tests.dashboard_browser_fixture'], { cwd: project, stdio: ['ignore', 'pipe', 'inherit'] });
let browser;
try {
  const config = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Fixture startup timed out')), 15000);
    createInterface({ input: fixture.stdout }).once('line', line => { clearTimeout(timer); resolve(JSON.parse(line)); });
    fixture.once('exit', code => { clearTimeout(timer); reject(new Error(`Fixture exited: ${code}`)); });
  });
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.addInitScript(() => {
    window.canvasText = [];
    const original = CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillText = function(text, ...args) { window.canvasText.push({ text, font: this.font }); return original.call(this, text, ...args); };
  });
  const failures = [], external = [];
  page.on('pageerror', error => failures.push(error.message));
  page.on('request', request => { if (!request.url().startsWith(config.url) && !request.url().startsWith(config.empty_url) && !request.url().startsWith('blob:')) external.push(request.url()); });
  mkdirSync(resolve(project, 'reports/local/dashboard-checks'), { recursive: true });
  const screenshot = name => page.screenshot({ path: resolve(project, `reports/local/dashboard-checks/${name}.png`), fullPage: true });

  await page.goto(config.url);
  await expect(page.getByRole('heading', { name: 'Files with gaps' })).toBeVisible();
  await expect(page.locator('nav a[aria-current="page"]')).toHaveText('Risk');
  await expect(page.locator('.risk-table tbody tr')).toHaveCount(2);
  await expect(page.locator('.risk-table tbody tr').first()).toContainText('a.py');
  expect(await page.locator('.missing-lines').allTextContents()).toEqual(['18', '12']);
  expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe('rgb(0, 0, 0)');
  await screenshot('risk');
  await page.getByRole('button', { name: 'a.py ./', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('dialog').locator('.source-line')).toHaveCount(21);
  await expect(page.getByRole('dialog')).toContainText('3 of 21 lines seen.');
  await expect(page.getByRole('dialog').locator('.source-line.untested')).toHaveCount(21);
  await expect(page.getByRole('heading', { name: 'Study guide' })).toBeVisible();
  await expect(page.locator('.guide-item')).toHaveCount(1);
  await expect(page.locator('.guide-item').first()).toContainText('LIMIT = 10');
  await page.getByRole('button', { name: 'Whole file' }).click();
  await expect(page.locator('.guide-item')).toHaveCount(1);
  await page.getByRole('button', { name: 'Unseen code' }).click();
  await page.locator('.guide-name').first().click();
  await expect(page.getByRole('dialog').locator('.source-line.jump')).toHaveCount(1);
  await screenshot('file-detail');
  await page.getByRole('button', { name: 'Review this file', exact: true }).click();
  await expect(page.locator('.question-panel h1')).toHaveText('Question 0: first');
  await expect(page.locator('.state-chip, .app-header, .connection-strip, .headline, .risk-table')).toHaveCount(0);
  await expect(page.locator('[class*="state-"]')).toHaveCount(0);
  await expect(page.locator('.review-source .source-line')).toHaveCount(20);
  const answerRequests = [];
  page.on('request', request => { if (request.url().endsWith('/review/answer')) answerRequests.push(request.postDataJSON()); });
  await screenshot('review');
  for (let i = 0; i < 3; i++) {
    await page.locator('.options button').nth(i).click();
    await page.getByRole('button', { name: 'Solid', exact: true }).click();
    if (i < 2) await expect(page.locator('.question-panel h1')).toHaveText(`Question ${i+1}: first`);
  }
  await expect(page.getByRole('heading', { name: 'Quiz results' })).toBeVisible();
  expect(answerRequests).toHaveLength(3);
  for (const body of answerRequests) expect(Object.keys(body).sort()).toEqual(['attempt_id', 'chosen_index', 'confidence', 'question_id']);
  await page.getByRole('link', { name: 'Return to review queue' }).click();
  await expect(page.locator('.risk-table tbody tr').first()).toContainText('b.py');
  await expect(page.locator('.risk-table tbody tr').last()).toContainText('Sample passed');
  await expect(page.locator('.risk-table tbody tr').last().locator('.untested')).toHaveCount(0);
  await page.getByRole('link', { name: 'Map', exact: true }).click();
  await expect(page.locator('.map-cell')).toHaveCount(2);
  await expect(page.locator('.map-cell.untested')).toHaveCount(1);
  await expect(page.locator('.headline')).toHaveText('30 lines');
  await expect(page.getByText('never on screen, across 2 files')).toBeVisible();
  expect(await page.locator('.headline').evaluate(el => getComputedStyle(el).fontFamily)).toContain('Cormorant Garamond');
  await screenshot('map');
  await page.getByRole('link', { name: 'Timeline', exact: true }).click();
  await expect(page.locator('.weekly-chart')).toBeVisible();
  await expect(page.locator('.lane')).toHaveCount(1);
  expect(await page.locator('.weekly-bar').evaluate(el => el.getBoundingClientRect().width)).toBe(36);
  await expect(page.getByText('Busiest week: 1 file.')).toBeVisible();
  await screenshot('timeline');
  await page.getByRole('link', { name: 'Insights', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Confidently wrong' })).toBeVisible();
  await expect(page.locator('.calibration').last()).toContainText('3 / 3 answers correct');
  await screenshot('insights');
  await page.getByRole('link', { name: 'Share', exact: true }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download PNG' }).click();
  await (await download).saveAs(resolve(project, 'reports/local/dashboard-checks/share.png'));
  expect(await page.locator('canvas').evaluate(c => [c.width, c.height])).toEqual([1200, 630]);
  expect(await page.evaluate(() => window.canvasText.find(t => t.text === '30 lines')?.font)).toContain('EB Garamond');
  expect(await page.evaluate(() => window.canvasText.some(t => /reading|understanding|eligible|current source/i.test(t.text)))).toBe(false);
  await page.goto(config.empty_url);
  await expect(page.getByText('No recording yet.', { exact: true })).toBeVisible();
  await screenshot('empty');
  await page.getByRole('link', { name: 'Map', exact: true }).click();
  await expect(page.locator('.headline')).toHaveText('Start recording');
  await page.getByRole('link', { name: 'Insights', exact: true }).click();
  await expect(page.getByText('No quizzes taken yet.', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Review a file', exact: true })).toBeVisible();
  await expect(page.locator('.chart-panel, .big-stat')).toHaveCount(0);
  await page.getByRole('button', { name: 'How this is measured', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('does not establish that it was read or understood');
  await expect(page.getByText(/does not establish that it was read or understood/)).toHaveCount(1);
  await page.getByRole('button', { name: 'Close methodology' }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  for (const view of ['Risk', 'Map', 'Timeline', 'Insights', 'Share']) {
    await page.getByRole('link', { name: view, exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    expect(await page.locator('body').innerText()).not.toMatch(/eligible|current source|observer|binding|collector|stored|\brecord\b/i);
    await expect(page.getByRole('button', { name: 'How this is measured', exact: true })).toBeVisible();
  }
  // Exercise the empty-column and zero-gap branches with fixture responses.
  let scenario = 'unknown';
  await page.route('**/api/dashboard', async route => {
    const response = await route.fetch();
    const data = await response.json();
    if (scenario === 'unknown') {
      data.files = data.files.map(f => ({ ...f, current_uncertain: true, state: 'uncertain', commits_90d: null }));
    } else if (scenario === 'zero') {
      data.has_observations = true;
      data.files = data.files.map(f => ({ ...f, current_uncertain: false, unknown_lines: 0, reported_lines: f.line_count, state: 'reported' }));
      data.totals.reported_lines = data.totals.line_count;
    } else data.files = [];
    await route.fulfill({ response, json: data });
  });
  await page.goto(config.empty_url);
  await expect(page.locator('.risk-table tbody tr')).toHaveCount(2);
  await expect(page.getByRole('columnheader', { name: 'Missing lines', exact: true })).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'Commits', exact: true })).toHaveCount(0);
  scenario = 'zero';
  await page.goto(`${config.empty_url}/?scenario=zero#map`);
  await expect(page.locator('.headline')).toHaveText('No gaps recorded');
  scenario = 'empty';
  await page.goto(`${config.empty_url}/?scenario=empty#share`);
  await expect(page.getByText('No files to share.', { exact: true })).toBeVisible();
  await expect(page.locator('canvas')).toHaveCount(0);
  expect(external).toEqual([]);
  expect(failures).toEqual([]);
  console.log('Browser checks passed: Risk, evidence panel, source, server-graded review, lower rank, hatching, Map, Timeline, Insights, PNG, empty state, mobile, and local-only requests.');
} finally {
  if (browser) await browser.close();
  fixture.kill('SIGTERM');
}
