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
    headline: !known ? 'Start recording' : gap ? `${number(gap)} lines` : 'No gaps recorded',
    detail: !known ? 'Open Blindspot in VS Code to begin.' : gap ? `never on screen, across ${number(affected)} ${affected === 1 ? 'file' : 'files'}` : 'Every tracked line has been on screen.',
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
