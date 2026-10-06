import { hierarchy, treemap, treemapSquarify } from 'd3-hierarchy';

export const states = [
  { id: 'uncertain', label: 'Unknown', description: 'Reconnect the extension to check this file.' },
  { id: 'no_evidence', label: 'Never seen', description: 'No lines on screen.' },
  { id: 'brief', label: 'Glimpsed', description: 'On screen for less than a second.' },
  { id: 'partial', label: 'Partly seen', description: 'Some lines have been on screen.' },
  { id: 'reported', label: 'Seen', description: 'Every line has been on screen.' },
];
export const label = id => states.find(s => s.id === id)?.label || 'Sample passed';
export const number = n => new Intl.NumberFormat('en-US').format(n);
export const percent = (n, d) => d ? Math.round(100 * n / d) : null;
export const directory = path => path.includes('/') ? path.slice(0, path.lastIndexOf('/') + 1) : './';
export const filename = path => path.split('/').at(-1);
export const inRanges = (n, ranges) => ranges.some(([a, b]) => a <= n && n <= b);

export function coverageRatio(seen, total, uncertain = false) {
  if (uncertain || !Number.isFinite(seen) || !Number.isFinite(total) || total <= 0) return null;
  return Math.max(0, Math.min(1, seen / total));
}

export function coverageStyle(seen, total, uncertain = false) {
  const ratio = coverageRatio(seen, total, uncertain);
  return {
    '--fill': ratio === null ? 'var(--state-uncertain)' : ratio === 1 ? 'var(--coverage-blue)' : `color-mix(in srgb, var(--coverage-red) ${100 * (1 - ratio)}%, var(--coverage-yellow) ${100 * ratio}%)`,
    '--on': ratio === null ? 'var(--on-uncertain)' : 'var(--coverage-ink)',
  };
}

// Canvas uses the same endpoints and interpolation as CSS color-mix.
export function coverageColor(seen, total, palette, uncertain = false) {
  const ratio = coverageRatio(seen, total, uncertain);
  if (ratio === null) return palette.unknown;
  if (ratio === 1) return palette.blue;
  const channels = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  const red = channels(palette.red), yellow = channels(palette.yellow);
  return `rgb(${red.map((value, i) => Math.round(value + (yellow[i] - value) * ratio)).join(', ')})`;
}

export function missingLines(file) {
  if (file.current_uncertain) return null;
  if (Number.isFinite(file.unknown_lines)) return file.unknown_lines;
  if (Number.isFinite(file.line_count) && Number.isFinite(file.reported_lines)) return Math.max(0, file.line_count - file.reported_lines);
  return null;
}

export function gapSummary(data) {
  const files = data.files.filter(f => missingLines(f) !== null);
  const known = data.has_observations && files.length > 0;
  const gap = files.reduce((sum, f) => sum + missingLines(f), 0);
  const affected = files.filter(f => missingLines(f) > 0).length;
  const { reported_lines: seen, line_count: lines } = data.totals;
  return {
    known, gap, affected,
    headline: !known ? 'Start recording' : `${gap && lines ? new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(Math.max(0.1, gap / lines * 100)) : 0}%`,
    detail: !known ? 'Open Blindspot in VS Code to begin.' : gap ? `${number(gap)} lines never on screen, across ${number(affected)} ${affected === 1 ? 'file' : 'files'}` : 'No gaps recorded.',
    context: known ? `${number(seen)} of ${number(lines)} lines seen · ${number(data.files.length)} files tracked` : '',
    percentage: known && lines ? `${percent(seen, lines)}% seen` : '',
  };
}

export function calendarAxis(weeks, ticks) {
  const weekMs = 7 * 86400000;
  const monday = value => { const d = new Date(value); d.setUTCHours(0, 0, 0, 0); d.setUTCDate(d.getUTCDate() - (d.getUTCDay() + 6) % 7); return +d; };
  const starts = [...weeks.map(w => monday(`${w.week}T00:00:00Z`)), ...ticks.map(t => monday(t.at))];
  if (!starts.length) return null;
  const end = Math.max(...starts) + weekMs;
  const start = Math.max(Math.min(...starts), end - 26 * weekMs);
  const byWeek = new Map(weeks.map(w => [w.week, w]));
  const columns = [];
  for (let t = start; t < end; t += weekMs) {
    const week = new Date(t).toISOString().slice(0, 10);
    columns.push(byWeek.get(week) || { week, files_touched: 0, event_count: 0 });
  }
  return { start, end, columns };
}

export async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    // Technical backend diagnostics stay out of the interface.
    throw new Error(response.status === 409 ? 'This file or quiz changed. Refresh and try again.' : 'Cannot connect. Start the local server and refresh.');
  }
  return data;
}

// Local-model calls surface the server's message (for example "Ollama is not running").
export async function explainApi(path, body) {
  let response;
  try { response = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); }
  catch { throw new Error('Cannot connect. Start the local server and refresh.'); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : 'Cannot connect. Start the local server and refresh.');
  return data;
}

export function layout(files, width, height) {
  const tree = { name: '', children: [] };
  for (const file of files) {
    let node = tree;
    const parts = file.path.split('/');
    for (const part of parts.slice(0, -1)) {
      let child = node.children.find(c => c.name === part && c.children);
      if (!child) { child = { name: part, children: [] }; node.children.push(child); }
      node = child;
    }
    node.children.push({ name: parts.at(-1), file, size: file.line_count });
  }
  const root = hierarchy(tree).sum(d => d.size || 0).sort((a, b) => b.value - a.value || a.data.name.localeCompare(b.data.name));
  treemap().tile(treemapSquarify).size([width, height]).paddingOuter(2).paddingInner(3)
    .paddingTop(node => node.depth > 0 && node.children ? 22 : 2).round(true)(root);
  return root;
}

export function directories(files) {
  const grouped = new Map();
  for (const file of files) {
    const name = directory(file.path);
    const row = grouped.get(name) || { name, files: 0, lines: 0, reported: 0, uncertain: 0 };
    row.files++;
    if (!file.current_uncertain) { row.lines += file.line_count; row.reported += file.reported_lines; }
    else row.uncertain++;
    grouped.set(name, row);
  }
  return [...grouped.values()].sort((a, b) => b.uncertain - a.uncertain || (percent(a.reported, a.lines) ?? -1) - (percent(b.reported, b.lines) ?? -1) || a.name.localeCompare(b.name));
}

// Study guide: the server returns every code unit; the toggle only filters and orders.
export const GUIDE_STATES = { unseen: 'no_evidence', partial: 'partial', seen: 'reported' };
export const lineSpan = i => i.start === i.end ? `Line ${i.start}` : `Lines ${i.start}–${i.end}`;
export function guideItems(guide, scope) {
  if (scope === 'whole') return guide.items;
  return guide.items.filter(i => i.unseen > 0).sort((a, b) => b.unseen - a.unseen || a.start - b.start);
}
export const rangeText = ranges => ranges.map(([a, b]) => a === b ? `${a}` : `${a}–${b}`).join(', ');
export function guideMarkdown(guide, scope, explanations = {}) {
  const items = guideItems(guide, scope);
  const out = [`# Study guide: ${guide.path}`, '',
    scope === 'whole' ? 'Every code unit, in file order.' : `${guide.unseen_lines} lines were never on screen. Read these first.`, ''];
  if (explanations.file) out.push(`> Generated by ${explanations.file.model} on this machine, unverified:`, ...explanations.file.text.split('\n').map(l => `> ${l}`), '');
  for (const i of items) {
    out.push(`## ${i.name} (${lineSpan(i).toLowerCase()})`, `- ${i.unseen} of ${i.lines} lines never on screen`);
    if (i.signature) out.push(`- \`${i.signature}\``);
    if (i.doc) out.push(`- ${i.doc}`);
    if (i.calls?.length) out.push(`- Calls: ${i.calls.join(', ')}`);
    if (i.raises?.length) out.push(`- Raises: ${i.raises.join(', ')}`);
    for (const c of i.changes.slice(0, 2)) out.push(`- Last changed ${c.date || 'now'}: ${c.summary}`);
    const note = explanations[`${i.start}-${i.end}`];
    if (note) out.push('', `> Generated by ${note.model} on this machine, unverified:`, ...note.text.split('\n').map(l => `> ${l}`));
    out.push('');
  }
  if (!items.length) out.push('Nothing to list.');
  return out.join('\n');
}

// A stored quiz that covers (part of) a guide unit, if one is waiting to be taken.
export const quizForUnit = (file, unit) => file.review.available.find(q => q.start_line <= unit.end && unit.start <= q.end_line);
