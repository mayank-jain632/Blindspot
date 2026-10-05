import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { calendarAxis, gapSummary, guideItems, guideMarkdown, layout, lineSpan, missingLines, percent, inRanges, rangeText } from '../src/data.js';

test('squarified layout includes every file once and preserves line area', () => {
  const files = [{ path: 'src/nested/one.py', line_count: 90 }, { path: 'src/nested/two.py', line_count: 10 }, { path: 'readme.md', line_count: 20 }];
  const tree = layout(files, 900, 600);
  assert.equal(tree.value, 120);
  assert.deepEqual(tree.leaves().map(n => n.data.file.path).sort(), files.map(f => f.path).sort());
  for (const n of tree.leaves()) assert.ok(n.x0 >= 0 && n.x1 <= 900 && n.y0 >= 0 && n.y1 <= 600);
  const nested = tree.leaves().filter(n => n.parent.data.name === 'nested');
  const area = n => (n.x1 - n.x0) * (n.y1 - n.y0);
  assert.ok(area(nested[0]) / area(nested[1]) > 8);
});

test('zero denominator is unavailable; inclusive ranges preserve boundary lines', () => {
  assert.equal(percent(0, 0), null);
  assert.equal(percent(3, 4), 75);
  assert.ok(inRanges(10, [[1, 10]]));
  assert.ok(!inRanges(11, [[1, 10]]));
});

test('timeline uses real calendar spacing and includes review-only weeks', () => {
  const axis = calendarAxis([{ week: '2026-09-07', files_touched: 2 }, { week: '2026-09-21', files_touched: 1 }], [{ at: '2026-09-30T12:00:00Z' }]);
  assert.equal(axis.columns.length, 4);
  assert.equal(axis.columns[1].week, '2026-09-14');
  assert.equal(axis.columns[1].files_touched, 0);
  assert.equal(axis.columns.at(-1).week, '2026-09-28');
  assert.equal(calendarAxis([], []), null);
});

test('gap headline leads with missing lines and handles zero and unavailable data', () => {
  const file = { line_count: 446, reported_lines: 436, unknown_lines: 10 };
  const data = { has_observations: true, files: [file], totals: { line_count: 446, reported_lines: 436 } };
  assert.equal(gapSummary(data).headline, '10 lines');
  assert.equal(gapSummary(data).percentage, '98% seen');
  assert.equal(gapSummary({ ...data, files: [{ ...file, unknown_lines: 0 }] }).headline, 'No gaps recorded');
  assert.equal(gapSummary({ ...data, has_observations: false }).headline, 'Start recording');
  assert.equal(missingLines({ line_count: 446, reported_lines: 436 }), 10);
  assert.equal(missingLines({ ...file, current_uncertain: true }), null);
});

test('small uppercase label token meets WCAG AA against panel', () => {
  const css = readFileSync(new URL('../src/style.css', import.meta.url), 'utf8');
  const token = name => css.match(new RegExp(`--${name}: (#[0-9A-F]{6})`))[1];
  const luminance = hex => {
    const rgb = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4);
    return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
  };
  assert.ok((luminance(token('text-label')) + .05) / (luminance(token('panel')) + .05) >= 4.5);
  const outsideRoot = css.slice(css.indexOf('\n*'));
  assert.ok(!/#[0-9a-f]{3,8}\b/i.test(outsideRoot));
  for (const name of ['main.jsx', 'charts.jsx', 'data.js']) {
    const source = readFileSync(new URL(`../src/${name}`, import.meta.url), 'utf8');
    assert.ok(!/#[0-9a-f]{6}\b/i.test(source));
    assert.ok(!/<x-dc|<helmet|<sc-for|<sc-if|DCLogic|renderVals|\{\{hole\}\}/.test(source));
  }
});

test('study guide orders unseen units by size and keeps file order for the whole file', () => {
  const unit = (name, start, unseen) => ({ name, start, end: start + 4, lines: 5, unseen, unseen_ranges: unseen ? [[start, start + unseen - 1]] : [], changes: [], calls: [], raises: [], signature: '', doc: '' });
  const guide = { path: 'a.py', unseen_lines: 6, items: [unit('seen', 1, 0), unit('small', 6, 1), unit('big', 11, 5)] };
  assert.deepEqual(guideItems(guide, 'unseen').map(i => i.name), ['big', 'small']);
  assert.deepEqual(guideItems(guide, 'whole').map(i => i.name), ['seen', 'small', 'big']);
  assert.equal(lineSpan({ start: 3, end: 3 }), 'Line 3');
  assert.equal(rangeText([[4, 4], [7, 9]]), '4, 7–9');
  const text = guideMarkdown(guide, 'unseen');
  assert.match(text, /## big \(lines 11–15\)/);
  assert.doesNotMatch(text, /## seen/);
});
